"""Serve: the call orchestrator (session lifecycle + turn processing).

Owns the TTS/STT/LLM engines, the per-call session registry and the
turn-processing pipelines (batch /turn and streaming /turn_stream). All
behaviour is moved verbatim from the original call_agent.Serve — imports are
rewired to the new core/adapters layout.
"""

import base64
import json
import os
import re
import struct
import tempfile
import threading
import time
import uuid

from core.state import CallContext, CallBusyError, AdmissionError, \
    SESSION_TTL_SEC, DEFAULT_GREETING
from core.dialogue import Agent, _clean_llm, reply_looks_broken, \
    reply_looks_hallucinated
from core.stt_gates import gate_stt_transcript
from core.events import StreamingSTT, reply_segments
from adapters.audio import wav_to_pcm, pcm_to_wav, parse_multipart_wav
from adapters.moss_tts import TTSClient
from adapters.stt import STTEngine
from adapters.llm import LLMClient
from adapters.cloud import _maybe_cloud_stt, _maybe_cloud_llm, \
    _maybe_cloud_tts
from adapters.redis_store import _maybe_session_store
from adapters.postgres_results import Recorder
from adapters.pg_recorder import PgRecorder
from adapters.pg import maybe_pg_store, PgUnavailable
from adapters.s3_recordings import (save_wav, save_user_wav, minio_enabled,
                                     upload_local_file)
from core.migrate import apply_migrations, schema_missing
from core.persistence import PersistenceWorker
from core.provider_events import process_provider_event
from core.outbox_worker import OutboxWorker
from core.family import (FamilyAccessError, FamilyAuthError,
                         FamilyValidationError, hash_key, normalize_phone,
                         validate_question_text)


def env_bool(name, default=False):
    """Strict env-flag parser: only "1"/"true"/"yes" are true.

    FIX 2026-08-27: the old `if os.environ.get(...)` treated "0" as truthy
    (a leaky default), so MOSS_RETAIN_BLANK_AUDIO=0 still retained audio.
    """
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes")


class Serve:
    def __init__(self, args):
        self.tts = _maybe_cloud_tts(TTSClient(
            ref_paths=args.refs,
            port_file=args.tts_port_file,
            port=args.tts_port,
            inference_steps=args.inference_steps,
            style_enabled=not args.no_style,
            host=getattr(args, "tts_host", None),
        ))
        self.stt = _maybe_cloud_stt(STTEngine())
        self.outdir = args.outdir
        self.args = args
        self.outdir = getattr(args, "outdir", None) or (
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "calls"))
        self.tmpdir = getattr(args, "tmpdir", None) or "/tmp/mossvoice_turns"
        # Call audio/transcripts are sensitive PII. Shared spool directories
        # must never inherit the process umask as world-readable.
        for private_dir in (self.outdir, self.tmpdir):
            os.makedirs(private_dir, mode=0o700, exist_ok=True)
            os.chmod(private_dir, 0o700)
        self._greeting_cache = {}
        self._greeting_lock = threading.Lock()
        self.sessions = {}
        self._sess_lock = threading.Lock()
        self.llm = _maybe_cloud_llm(LLMClient.get())
        self.store = _maybe_session_store()
        # Data core (Phase 2): Postgres is the source of truth; Redis is a
        # cache (DEGRADED surfaced, never silent); MinIO holds recordings.
        self.pg = maybe_pg_store()
        self.pg_available = getattr(self.pg, "available", False)
        # PERSISTENCE WORKER (read.md rev-3 G1 + rev-4 gate B): PG / MinIO /
        # Redis network I/O is drained by background threads, never in the
        # voice hot path. Gate B makes the spool DURABLE (append-only JSONL
        # WAL + at-least-once replay + retry/backoff + dead-letter), so a slow
        # or down database can neither add latency nor silently drop a turn.
        # Handlers are registered by NAME and emit() takes JSON payloads only.
        self.persist = PersistenceWorker()
        self.persist.register("turn.pg", self._h_persist_turn_pg, "pg")
        self.persist.register(
            "turn.audio",
            lambda p: self._upload_turn_audio(p["audio_key"], p["audio_path"]),
            "s3")
        self.persist.register("session.redis", self._h_persist_session, "redis")
        self.persist.start()
        # SCHEMA OWNERSHIP (read.md rev-3): DDL is the migration JOB's job,
        # never a live call process's. The realtime process ONLY verifies the
        # schema it expects exists (read-only). MOSS_RUN_MIGRATIONS=1 keeps
        # single-box dev and the offline suite self-contained; production
        # compose runs a separate `migrate` service and sets it to 0 here.
        # read.md rev-4 gate D (product readiness): schema compatibility is an
        # explicit readiness capability. If the migration job hasn't produced
        # the expected schema, the process must NOT report /ready=true — it
        # would answer calls (STT/TTS fine) against a DB that's missing tables.
        # Default True: no PG (or pg not configured) is not a schema-mismatch;
        # a missing schema that we CAN see is.
        self.schema_compatible = True
        if self.pg_available:
            if os.environ.get("MOSS_RUN_MIGRATIONS", "1") == "1":
                try:
                    apply_migrations(self.pg.url)
                except Exception as e:  # noqa: BLE001
                    print(f"[call-agent] migrations failed: {e}", flush=True)
            else:
                try:
                    missing = schema_missing(self.pg.url)
                except Exception as e:  # noqa: BLE001
                    missing = [f"(check failed: {e})"]
                if missing:
                    self.schema_compatible = False
                    print(f"[call-agent] SCHEMA MISMATCH (run migration "
                          f"job first): missing={missing}", flush=True)
        # Outbox polling worker: delivers call.result etc. to downstream
        # (family notify). ARCHITECTURE (2026-08-21): in production the
        # standalone `workflow` deployment owns background business
        # processing (MOSS_OUTBOX_INPROCESS=0 in compose telephony) — an
        # outbox backlog must never steal CPU from live audio. Default "1"
        # keeps single-box dev and the test-suite self-contained.
        self.outbox = None
        if self.pg_available and os.environ.get(
                "MOSS_OUTBOX_INPROCESS", "1") == "1":
            from core.delivery import DeliveryRouter
            from core.incidents import IncidentEngine
            self.incidents = IncidentEngine(
                self.pg, DeliveryRouter())
            self.outbox = OutboxWorker(
                self.pg, self._dispatch_outbox, worker_id="telephony",
                tick=self.incidents.tick)
            self.outbox.start()
        else:
            self.incidents = None
        # Load the LLM FIRST, single-threaded, BEFORE any warmup threads.
        # mlx's module-import machinery deadlocks when a model import races
        # the greeting/STT warmup threads (observed: _ModuleLock deadlock →
        # the whole daemon hangs). Preference order: the separate llm-server
        # (remote_ready) → in-process load → scripted replies only.
        self.llm.ready()
        # Warmup loads real models (Whisper for STT) into THIS process. Tests
        # construct Serve with fake engines and must NOT pull the production
        # model into memory (it can double the container's RSS and OOM the
        # VM). The production daemon never sets MOSS_NO_WARMUP.
        if not os.environ.get("MOSS_NO_WARMUP"):
            self._warm_greeting()
            self._warm_acks()
            self._warm_stt()
        # LLM keep-alive: after ~1 min idle the first real turn costs 6-12 s
        # (prompt-cache + weights eviction). CRITICAL: the ping must use the
        # REAL system prompt — a tiny "ок" ping evicts the useful cache and
        # CAUSES the very cold start it was meant to prevent.
        if not os.environ.get("MOSS_NO_WARMUP"):
            def _llm_keepalive():
                import urllib.request
                from core.dialogue import VERA_SYSTEM_PROMPT, VERA_SCENARIOS
                sys_prompt = VERA_SYSTEM_PROMPT
                if VERA_SCENARIOS:
                    sys_prompt = f"{sys_prompt}\n\n{VERA_SCENARIOS}"
                while True:
                    try:
                        body = json.dumps({
                            "model": "local", "max_tokens": 1,
                            # EXACT same rendering as real turns (incl. the
                            # template kwarg): any difference risks splitting
                            # the KV-cache prefix the ping exists to keep.
                            "chat_template_kwargs": {"enable_thinking":
                                                     False},
                            "messages": [
                                {"role": "system", "content": sys_prompt},
                                {"role": "user", "content": "ок"},
                            ],
                        }).encode()
                        req = urllib.request.Request(
                            os.environ.get("MOSS_LLM_URL",
                                           "http://answers:9500").rstrip("/")
                            + "/v1/chat/completions",
                            data=body,
                            headers={"Content-Type": "application/json"})
                        urllib.request.urlopen(req, timeout=30).read()
                    except Exception:
                        pass
                    time.sleep(45)
            threading.Thread(target=_llm_keepalive, daemon=True).start()

    # ------------------------------------------------------------------ #
    # Session management (P0-SESSION-001)
    # ------------------------------------------------------------------ #
    # Data core (Phase 2): recorder selection + outbox dispatch
    # ------------------------------------------------------------------ #
    def _make_recorder(self):
        """Postgres-backed recorder when the data core is up, else the file
        recorder (offline/legacy mode)."""
        if self.pg_available:
            return PgRecorder(self.pg, self.outdir)
        return Recorder(self.outdir)

    def _persist_turn(self, ctx, role, text, source=None, confidence=None,
                      audio_path=None, audio_key=None):
        """Persist one dialogue turn, splitting LOCAL/MIRROR from NETWORK.

        read.md rev-3 G1. The in-memory ``rec.call["turns"]`` mirror and the
        local WAV are updated synchronously (cheap, still read by /calls and
        the live turn response). The Postgres INSERT and the MinIO object
        upload — the network-bound steps that used to run inside the per-call
        lock before Vera's first audio — are handed to the background
        ``self.persist`` worker, so a slow DB/object-store never raises voice
        latency. The legacy file Recorder has no network step and stays fully
        synchronous.
        """
        rec = ctx.recorder
        if rec.call is None:
            rec.new_call()
        cid = rec.call["id"]
        if isinstance(rec, PgRecorder):
            # mirror now (synchronous, in-memory only)
            rec.call["turns"].append({
                "role": role, "text": text, "audio": audio_path,
                "source": source or ("stt" if role == "user" else "agent"),
                "confidence": confidence, "audio_key": audio_key,
                "turn_id": None,
            })
            # PG INSERT + MinIO upload -> background worker (durable spool).
            # The minio_enabled() probe itself is network I/O (bucket_exists):
            # read.md rev-3 G1 — it must run in the WORKER thread, never in
            # the hot path inside the per-call lock. Gate B: emit() takes a
            # JSON payload and never blocks / never drops (WAL first).
            self.persist.emit("turn.pg", {
                "cid": cid, "role": role, "text": text,
                "source": source or ("stt" if role == "user" else "agent"),
                "confidence": confidence, "audio_key": audio_key,
            })
            if audio_key and audio_path:
                self.persist.emit("turn.audio", {
                    "audio_key": audio_key, "audio_path": audio_path,
                })
        else:
            # file/legacy recorder: no network, keep synchronous (same as ever)
            rec.add_turn(role, text, audio_path=audio_path,
                         source=source, confidence=confidence,
                         audio_key=audio_key)

    def _upload_turn_audio(self, audio_key, audio_path):
        """Worker-thread MinIO upload for a turn's audio.

        read.md rev-3 G1: runs inside the PersistenceWorker. The
        ``minio_enabled()`` probe (bucket_exists) is network I/O and therefore
        must not touch the hot path / per-call lock. Best-effort: a down or
        unconfigured object store simply skips the upload.
        """
        try:
            if minio_enabled():
                upload_local_file(audio_key, audio_path)
        except Exception as e:  # noqa: BLE001
            print(f"[persist] audio upload {audio_key} failed: {e}",
                  flush=True)

    def _dispatch_outbox(self, topic, payload, msg_id):
        """Route outbox messages to real consumers.

        ``call.result``   — RED verdict opens a durable incident (Phase 3).
        ``incident.notify`` — one delivery attempt for an incident action.
        Any other topic is acked (no-op) so the worker doesn't dead-letter it.
        """
        try:
            if topic == "call.result":
                if self.incidents is not None:
                    verdict = payload.get("verdict")
                    notes = payload.get("notes") or []
                    self.incidents.maybe_open(
                        payload.get("call_id"), verdict, notes=notes)
                return True
            if topic == "incident.notify" and self.incidents is not None:
                return bool(self.incidents.deliver(payload))
            print(f"[outbox] {msg_id} topic={topic} payload={payload}",
                  flush=True)
            return True
        except Exception as e:  # noqa: BLE001
            print(f"[outbox] dispatch error {msg_id}: {e}", flush=True)
            return False

    def handle_provider_event(self, event):
        """POST /webhook/provider entry point. Idempotent by construction
        (provider_events PK == provider event id)."""
        if not self.pg_available:
            raise PgUnavailable("Postgres not configured")
        return process_provider_event(self.pg, event)

    # ------------------------------------------------------------------ #
    # Phase 3: incident workflow (family ack / operator resolve).

    def list_incidents(self, active_only=True):
        if self.incidents is None:
            raise PgUnavailable("Postgres not configured")
        statuses = ("open", "ack", "checking") if active_only else None
        return self.incidents.pg.list_incidents(statuses=statuses)

    def incident_ack(self, incident_id, actor, action_id=None, note=None):
        if self.incidents is None:
            raise PgUnavailable("Postgres not configured")
        return self.incidents.ack(incident_id, actor, action_id, note)

    def incident_resolve(self, incident_id, actor, reason):
        if self.incidents is None:
            raise PgUnavailable("Postgres not configured")
        return self.incidents.resolve(incident_id, actor, reason)

    def incident_false_alarm(self, incident_id, actor, reason):
        if self.incidents is None:
            raise PgUnavailable("Postgres not configured")
        return self.incidents.false_alarm(incident_id, actor, reason)

    # ------------------------------------------------------------------ #
    # Family app API (iPhone client). Auth = X-Moss-Key (api key, sha256
    # stored); authorization = account_access grant for the elder's phone.
    # Raises FamilyAuthError / FamilyAccessError / FamilyValidationError.
    # ------------------------------------------------------------------ #
    def _family_auth(self, api_key, phone):
        """Resolve key -> account and phone -> elder; check the grant.
        Returns (account_row, elder_row) with the phone normalized."""
        if not api_key:
            raise FamilyAuthError("missing api key")
        acc = None
        if self.pg_available:
            try:
                acc = self.pg.family_account_by_key_hash(hash_key(api_key))
            except PgUnavailable:
                acc = None
        if acc is None:
            raise FamilyAuthError("invalid or revoked api key")
        digits = normalize_phone(phone)
        if not digits:
            raise FamilyValidationError("phone is required")
        if not self.pg_available:
            raise PgUnavailable("Postgres not configured")
        try:
            elder = self.pg.family_elder_by_phone(digits)
        except PgUnavailable:
            raise
        if elder is None:
            raise FamilyAccessError(f"unknown phone: …{digits[-4:]}")
        if not self.pg.family_has_access(acc["account_id"],
                                         elder["person_id"]):
            raise FamilyAccessError("phone is not granted to this account")
        return acc, elder

    def family_ask(self, api_key, phone, text, author=None):
        """POST /family/questions — store a question for the next call."""
        clean = validate_question_text(text)
        acc, elder = self._family_auth(api_key, phone)
        q_id = uuid.uuid4().hex[:12]
        self.pg.family_add_question(
            q_id, elder["person_id"], acc["account_id"],
            (author or "").strip()[:60] or None, clean)
        self.pg.audit("family.question.added", acc["account_id"],
                      "family_question", q_id,
                      {"phone_tail": normalize_phone(phone)[-4:]})
        return {"id": q_id, "status": "pending"}

    def family_list(self, api_key, phone):
        """GET /family/questions?phone=… — history incl. answers, for the
        app's polling screen."""
        _, elder = self._family_auth(api_key, phone)
        rows = self.pg.family_list(elder["phone"]) or []
        return [
            {"id": r["q_id"], "text": r["text"], "status": r["status"],
             "author": r.get("author_label"),
             "created_at": str(r["created_at"]),
             "asked_call_id": r.get("asked_call_id"),
             "answer": r.get("answer_text"),
             "answered_at": str(r["answered_at"]) if r.get("answered_at")
             else None}
            for r in rows
        ]

    # ------------------------------------------------------------------ #
    def new_call(self, caller_id=None, mode=None):
        """Create an isolated call context. Returns the call_id.

        ``mode`` optionally pins the agent's opening mode. When provided, the
        agent is set into that mode directly (e.g. ``"companion"`` so a direct
        phone call starts free, not forced through the check-in greeting).
        When ``mode`` is None the historical behaviour is kept ONLY for a
        call that knows its caller (family check-in flow); a caller-agnostic
        call starts in the default companion mode.

        ADMISSION CONTROL: MOSS_MAX_CONCURRENT_CALLS (0 = unlimited, dev
        default) caps live sessions. At capacity we REJECT with
        AdmissionError instead of degrading every active conversation —
        load shedding beats cascading failure (Google SRE)."""
        limit = int(os.environ.get("MOSS_MAX_CONCURRENT_CALLS", "0") or 0)
        if limit > 0:
            with self._sess_lock:
                active = len(self.sessions)
            if active >= limit:
                print(f"[call-agent] ADMISSION REJECT: {active}/{limit} "
                      "concurrent calls", flush=True)
                raise AdmissionError(active, limit)
        call_id = uuid.uuid4().hex[:12]
        ctx = CallContext(
            call_id=call_id,
            agent=Agent(llm=self.llm),
            recorder=self._make_recorder(),
            caller_id=caller_id,
        )
        ctx.recorder.new_call(call_id=call_id)
        # Resolve elder + consent gate (ROADMAP E3). Without active consent
        # the first call is a consent script — not a wellness check-in.
        need_consent = False
        if self.pg_available and caller_id:
            try:
                elder = self.pg.family_elder_by_phone(
                    normalize_phone(caller_id))
                if elder:
                    ctx.person_id = elder.get("person_id")
                    ctx.household_id = elder.get("household_id")
                    ctx.agent._pg = self.pg
                    ctx.agent._person_id = ctx.person_id
                    ctx.agent._household_id = ctx.household_id
                    from core.consent import has_active_consent
                    if not has_active_consent(self.pg, ctx.person_id):
                        need_consent = True
            except Exception as e:  # noqa: BLE001
                print(f"[call-agent] elder/consent resolve skipped: {e}",
                      flush=True)
        if need_consent:
            script = ctx.agent.start_consent_call()
            print(f"[call-agent] consent call for {ctx.person_id}",
                  flush=True)
            # Greeting override for Lua/runtime consumers via session emit.
            ctx.dialogue_state["consent_script"] = script
        # Serve-initiated family call: the agent opens in check_in mode (the
        # wellbeing-question state machine). Without this the agent sits in
        # companion mode and the whole check-in flow never activates.
        # An explicit ``mode`` (e.g. "companion" from the phone dialplan)
        # overrides it, so the phone starts free instead of a forced greeting.
        # FIX 2026-08-27: an arbitrary string from the API must NOT reach the
        # private _set_mode (it drove the state machine into an unknown mode);
        # only the declared Modes are accepted.
        elif mode is not None:
            _valid = getattr(Agent, "MODES", ())
            if mode not in _valid:
                raise ValueError(
                    f"unknown mode {mode!r}; expected one of {_valid}")
            if mode == "check_in":
                ctx.agent.start_check_in()
            # companion / clarify / safety_* / closing: stay in IDLE until
            # the FSM transitions on the first real turn.
        elif caller_id:
            ctx.agent.start_check_in()
        else:
            # Phone dialplan (Lua): plays MVERA_GREETING then expects the
            # wellness agenda. Without check_in, «хорошо/плохо» hit generic
            # acks and the call felt like «она не слышит».
            ctx.agent.start_check_in()
        # Family-app questions: ONE snapshot per call (deterministic turn).
        # Fail-open: a PG hiccup must never block a live call — questions
        # simply stay pending for the next one.
        if self.pg_available and caller_id and not need_consent:
            try:
                qs = self.pg.family_pending(normalize_phone(caller_id)) or []
                if qs:
                    ctx.agent.set_family_questions(qs)
                    print(f"[call-agent] agenda: +{len(qs)} family "
                          "question(s)", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"[call-agent] family questions skipped: {e}",
                      flush=True)
        if self.pg_available:
            self.pg.new_call(call_id, caller_id=caller_id)
        with self._sess_lock:
            self.sessions[call_id] = ctx
        self._emit_session(ctx)
        return call_id

    def handle_dtmf(self, call_id, digit):
        """Apply one DTMF digit to a live call (ROADMAP E2/E3)."""
        ctx = self.get_call(call_id)
        with ctx.lock:
            plan = ctx.agent.handle_dtmf(digit)
        return {
            "ok": True,
            "call_id": call_id,
            "digit": str(digit),
            "reply": (plan or {}).get("fallback") or "",
            "terminal": bool((plan or {}).get("terminal")),
            "done": bool(ctx.agent.done),
            "status": ctx.agent.status,
        }

    def _h_persist_turn_pg(self, payload):
        """PersistenceWorker 'turn.pg' handler (rev-4 gate B). Executes in the
        PG writer thread with a JSON payload {cid, role, text, source,
        confidence, audio_key}. Idempotent INSERT with a stable (call, turn)
        shape; a replayed duplicate simply overwrites the same row space."""
        self.pg.add_turn(
            payload["cid"], payload["role"], payload["text"],
            source=payload.get("source", "stt"),
            confidence=payload.get("confidence"),
            audio_key=payload.get("audio_key"))

    def _h_persist_session(self, payload):
        """PersistenceWorker 'session.redis' handler (rev-4 gate B). Mirrors
        the live context into the session store (Redis or memory) from a JSON
        payload so the record survives a restart. Never blocks the call path
        on failure (retry/backoff + dead-letter live in the worker)."""
        try:
            from moss_providers import session_doc
            doc = session_doc(
                payload["call_id"],
                dialogue_step=payload.get("dialogue_step"),
                summary=payload.get("summary", ""),
                last_intent=payload.get("last_intent", "") or "",
                worker_id="",
                customer_id=payload.get("customer_id", "") or "",
            )
            self.store.put(payload["call_id"], doc,
                           ttl_seconds=payload.get("ttl_seconds"))
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] session persist skipped: {e}", flush=True)

    def _emit_session(self, ctx, ttl_seconds=None):
        """Stage 6 (rev-4 gate B): mirror the live context into the session
        store (Redis or memory) via the durable persistence worker, so the
        Redis put never runs synchronously in the call hot path and never
        blocks VOICE on business infrastructure. Payload is JSON."""
        self.persist.emit("session.redis", {
            "call_id": ctx.call_id,
            "dialogue_step": ctx.agent.step,
            "summary": " ".join(ctx.agent.notes)[-500:],
            "last_intent": getattr(ctx.agent, "last_intent", "") or "",
            "customer_id": ctx.caller_id or "",
            "ttl_seconds": ttl_seconds,
        })

    def get_call(self, call_id):
        """Return the call context or raise KeyError.

        Legacy behaviour: callers that never create a session explicitly
        (e.g. the first Lua-script interop) still work — ``None`` now creates a
        fresh isolated call instead of matching the most recently created one.
        (SECURITY FIX: matching "the latest session" let any local client POST
        to `/turn` without a call_id and inject turns/transcripts into someone
        else's *live* phone call.)
        """
        if call_id:
            with self._sess_lock:
                ctx = self.sessions.get(call_id)
            if ctx is None:
                raise KeyError(call_id)
            ctx.last_seen = time.time()
            return ctx
        call_id = self.new_call()
        return self.get_call(call_id)

    def end_call(self, call_id):
        """Finalize a call: produce the verdict and drop the context."""
        ctx = self.get_call(call_id)
        ctx.outcome = ctx.agent.outcome
        ctx.finished = True
        # Data core: persist the verdict + enqueue the downstream notify.
        if self.pg_available and isinstance(ctx.recorder, PgRecorder):
            try:
                from core.call_status import family_fields_for_finalize
                notes = ctx.outcome.get("notes") or []
                tech_err = getattr(ctx.agent, "technical_error", None)
                declined = (
                    ctx.outcome.get("status") == "declined"
                    or getattr(ctx.agent, "_consent_declined", False))
                no_contact = ctx.outcome.get("status") in (
                    "no_contact", "no_speech")
                family = family_fields_for_finalize(
                    ctx.outcome.get("status", "unknown"),
                    notes=notes,
                    facts=getattr(ctx.agent, "facts", None) or [],
                    technical_error=tech_err,
                    no_contact=no_contact,
                    declined=declined,
                )
                # Enrich in-memory outcome for HTTP/UI consumers.
                ctx.outcome = {**ctx.outcome, **family}
                ctx.recorder.finalize(
                    ctx.outcome.get("status", "unknown"),
                    confidence=getattr(ctx.agent, "_last_confidence", None),
                    notes=notes,
                    family_status=family["family_status"],
                    reasons=family["reasons"],
                    summary_for_family=family["summary_for_family"],
                    scenario_version=family["scenario_version"],
                    safety_rules_version=family["safety_rules_version"],
                    technical_error=family["technical_error"])
                self.pg.enqueue(
                    "call.result",
                    {"call_id": call_id,
                     "verdict": ctx.outcome.get("status", "unknown"),
                     "notes": notes,
                     "family_status": family["family_status"],
                     "summary_for_family": family["summary_for_family"]},
                    dedup_key=f"call:{call_id}")
                # Family questions asked during THIS call: persist status +
                # answer snapshot (replay-safe: only 'pending' rows move).
                self.pg.family_sync_asked(call_id,
                                          ctx.agent.family_questions)
            except Exception as e:  # noqa: BLE001
                print(f"[call-agent] end_call persist failed: {e}",
                      flush=True)
        self._emit_session(ctx, ttl_seconds=60 * 60 * 24)
        with self._sess_lock:
            self.sessions.pop(call_id, None)
        return {
            "ok": True,
            "call_id": call_id,
            "finished": True,
            "outcome": ctx.outcome,
            "summary_path": ctx.recorder.summary_path(),
        }

    def list_calls(self):
        with self._sess_lock:
            return [
                {
                    "call_id": c.call_id,
                    "created_at": c.created_at,
                    "last_seen": c.last_seen,
                    "finished": c.finished,
                    "outcome": c.agent.outcome,
                    "caller_id": c.caller_id,
                }
                for c in self.sessions.values()
            ]

    def sweep_expired(self):
        now = time.time()
        with self._sess_lock:
            expired = [
                cid
                for cid, c in self.sessions.items()
                if now - c.last_seen > SESSION_TTL_SEC
            ]
            for cid in expired:
                self.sessions.pop(cid, None)
        if expired:
            print(f"[call-agent] swept {len(expired)} stale session(s)", flush=True)

    # ------------------------------------------------------------------ #
    def begin_turn(self, call_id):
        """Mark a call as turn-processing. Returns the ctx, or raises
        CallBusyError when a turn is already in flight for this call.

        AUDIT FIX: a second overlapping /turn or /turn_stream request used to
        interleave with the running one (double agent.reply, corrupted
        result.json). Now it is rejected fast.

        ``cancel_event`` is cleared HERE (atomically with the busy check) so a
        stray early /stream-cancel can no longer abort a reply that has not
        started yet (the old handler-level clear raced with delayed cancels).
        """
        ctx = self.get_call(call_id)
        with ctx.turn_lock:
            if ctx.turn_in_progress:
                raise CallBusyError(call_id)
            ctx.turn_in_progress = True
            ctx.cancel_event.clear()
            ctx.streaming = True
        # ARCHITECTURE 2026-08-27: each accepted turn starts a new dialogue
        # generation. turn_id/generation_id tag every downstream result so a
        # stale in-flight result can never be played over the new turn.
        ctx.new_turn()
        return ctx

    def end_turn(self, ctx):
        with ctx.turn_lock:
            ctx.turn_in_progress = False
            ctx.streaming = False

    def _warm_stt(self):
        def _warm():
            print("[call-agent] pre-warming STT...", flush=True)
            p = self._silence_wav()
            try:
                if p:
                    try:
                        self.stt.transcribe_clean(p)
                    except Exception as e:  # noqa: BLE001
                        print(f"[call-agent] STT warmup failed: {e}",
                              flush=True)
            finally:
                if p:
                    try:
                        os.remove(p)
                    except OSError:
                        pass
            # TRUTHFUL READINESS (2026-08-27): "STT ready" is only printed
            # when the engine ACTUALLY loaded. Before, a failed load (e.g.
            # missing tts_common) still printed ready, and /health claimed ok
            # while every phone turn degraded to "Повторите, пожалуйста".
            usable = bool(
                getattr(self.stt, "ready", lambda: False)())
            if usable:
                print("[call-agent] STT ready", flush=True)
            else:
                print("[call-agent] STT NOT ready — voice turns will degrade "
                      "to scripted replies until it is fixed", flush=True)
        threading.Thread(target=_warm, daemon=True).start()

    def _silence_wav(self):
        """Tiny silent clip used only to force Whisper into memory at startup."""
        pcm = struct.pack("<%dh" % 1600, *([0] * 1600))  # 0.1s @16k
        fd, p = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            import wave as _wave

            with _wave.open(p, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
                w.writeframes(pcm)
        except Exception:  # noqa: BLE001
            try:
                os.remove(p)
            except OSError:
                pass
            return None
        return p

    def _phone_wav(self, wav_bytes):
        """Resample a reply WAV to 16 kHz mono for FreeSWITCH playback.

        The TTS daemon renders 48 kHz, but FreeSWITCH channels negotiate
        G722 (16 kHz): a 48 kHz file stalls FS's resample path and the
        caller hears silence. 16 kHz matches the codec natively.
        """
        if not wav_bytes:
            return wav_bytes
        import io as _io
        import wave as _wave
        import numpy as _np
        try:
            with _wave.open(_io.BytesIO(wav_bytes)) as w:
                sr = w.getframerate()
                if sr == 16000 and w.getnchannels() == 1:
                    return wav_bytes
                data = w.readframes(w.getnframes())
            a = _np.frombuffer(data, dtype=_np.int16).astype(_np.float32)
            if a.ndim > 1:
                a = a.mean(axis=1)
            if sr > 16000:
                from scipy.signal import decimate
                a = decimate(a, max(1, int(round(sr / 16000.0))),
                             ftype="iir")
            elif sr < 16000:
                x = _np.arange(len(a), dtype=_np.float64)
                xi = _np.arange(0, len(a), sr / 16000.0)
                a = _np.interp(xi, x, a).astype(_np.float32)
            # a is still int16-scaled (±32768): rescale to ±1.0, then back.
            a = a / 32767.0
            out = _io.BytesIO()
            with _wave.open(out, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
                w.writeframes(
                    (_np.clip(a, -1.0, 1.0) * 32767).astype(_np.int16).tobytes())
            return out.getvalue()
        except Exception:  # noqa: BLE001
            return wav_bytes

    def _write_segment_file(self, segment_dir, seg_pcm):
        """Write one finished reply sentence as a 16 kHz wav (atomic rename).

        ``seg_pcm`` is a list of (pcm_bytes, sample_rate). Returns the final
        path or None. The .tmp -> rename dance lets the dialplan treat the
        final name as "ready to play"."""
        try:
            os.makedirs(segment_dir, exist_ok=True)
            raw = b"".join(p for p, _sr in seg_pcm)
            sr = seg_pcm[0][1] or 48000
            wav = self._phone_wav(pcm_to_wav(raw, sr))
            n = len([f for f in os.listdir(segment_dir)
                     if f.startswith("seg-") and f.endswith(".wav")]) + 1
            final = os.path.join(segment_dir, f"seg-{n:04d}.wav")
            tmp = final + ".tmp"
            with open(tmp, "wb") as f:
                f.write(wav)
            os.replace(tmp, final)
            return final
        except Exception:  # noqa: BLE001
            return None

    def _write_done_file(self, segment_dir, meta):
        """Atomic done.json: the dialplan polls for it to know the turn
        ended and to read the final reply/finished flags."""
        try:
            os.makedirs(segment_dir, exist_ok=True)
            tmp = os.path.join(segment_dir, "done.json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False)
            os.replace(tmp, os.path.join(segment_dir, "done.json"))
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _maybe_latency_trace(t_turn, t_stt, t_llm_first, t_first_audio,
                             transcript, reply, call_id, turn_id, gen_id):
        """Route step 6: print the end-to-end turn breakdown to the log.

        Absent timing (barge-in / aborted turn) is shown as '-' rather than
        NaN. One compact line per turn, always flushed so it appears in
        `make logs` without buffering lag.
        """
        try:
            def _ms(t_prev, t_cur):
                if t_prev is None or t_cur is None:
                    return "-"
                return f"{int((t_cur - t_prev) * 1000)}ms"

            stt_ms = _ms(t_turn, t_stt)
            # HONEST LABELS (2026-08-23): "llm" here is the deterministic
            # plan (state machine), NOT model generation — the LLM streams
            # DURING the next window, so "gen+tts" owns both. Old labels
            # ("llm=", "tts=") sent us chasing the wrong stage.
            llm_ms = _ms(t_stt, t_llm_first)
            tts_ms = _ms(t_llm_first, t_first_audio)
            total_ms = _ms(t_turn, t_first_audio)
            print(f"[call-agent] LATENCY {call_id}: turn={turn_id} gen={gen_id} "
                  f"stt={stt_ms} plan={llm_ms} gen+tts={tts_ms} "
                  f"first_audio={total_ms} "
                  # read.md rev-3 G8: NEVER log the raw conversation. The
                  # operational log carries call/turn/generation ids and
                  # latencies; content stays in the (separate, encrypted,
                  # ACL'd) dialogue store. Char counts give signal without PII.
                  f"in_chars={len(transcript or '')} "
                  f"out_chars={len(reply or '')}", flush=True)
        except Exception:  # noqa: BLE001
            pass  # tracing never breaks the turn

    def _warm_greeting(self):
        if os.environ.get("MOSS_NO_WARMUP"):
            return
        print("[call-agent] pre-warming greeting...", flush=True)
        try:
            self.greeting_wav(DEFAULT_GREETING)
            print("[call-agent] greeting ready", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] greeting warmup failed: {e}", flush=True)

    # Backchannel phrases ("ага, услышала вас"): pre-rendered at startup so
    # the dialplan can play one INSTANTLY while the LLM is still thinking —
    # natural conversational filler instead of silent dead air.
    ACK_PHRASES = (
        "Ага, услышала вас.",
        "Поняла вас.",
        "Да-да, я вас слушаю.",
        "Так, секунду.",
    )

    def _warm_acks(self):
        def _warm():
            try:
                ack_dir = os.path.join(self.outdir, "acks")
                os.makedirs(ack_dir, exist_ok=True)
                for i, phrase in enumerate(self.ACK_PHRASES):
                    path = os.path.join(ack_dir, f"ack-{i:02d}.wav")
                    if os.path.exists(path):
                        continue  # survive restarts without re-render
                    wav = self._phone_wav(self.tts.generate(phrase))
                    if wav:
                        with open(path, "wb") as f:
                            f.write(wav)
                print("[call-agent] ack phrases ready", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"[call-agent] ack warmup failed: {e}", flush=True)
        threading.Thread(target=_warm, daemon=True).start()

    def greeting_wav(self, text):
        text = (text or "").strip()
        if not text or not self.tts.ready():
            return None
        if text == DEFAULT_GREETING:
            # FIX: generate inside the lock so a concurrent warmup + first
            # request never double-generate the greeting.
            with self._greeting_lock:
                if not self._greeting_cache:
                    wav = self._phone_wav(self.tts.generate(text))
                    if wav:
                        self._greeting_cache = save_wav(self.outdir, wav)
                return self._greeting_cache or None
        wav = self._phone_wav(self.tts.generate(text))
        return save_wav(self.outdir, wav) if wav else None

    # directories whose WAV files may be referenced by {"audio": ...} JSON
    # bodies. Anything outside these prefixes is rejected — the old code
    # happily copied ~/.ssh/id_rsa into the call archive. Prefixes are
    # realpath-normalised at startup (macOS symlinks /var -> /private/var).
    # tempfile.gettempdir() is included so the whitelist follows whatever
    # TMPDIR the platform actually provides (isolated CI sandboxes ship
    # without /tmp — AUDIT fix), while staying restricted to temp space.
    UPLOAD_ALLOWED_DIRS = tuple(
        os.path.realpath(d) for d in
        ("/tmp", "/var/folders", "/private/tmp", "/private/var/folders",
         tempfile.gettempdir())
    )

    @staticmethod
    def _wav_diag(path):
        """Read the ACTUAL WAV header of a recorded chunk and return a compact
        diagnostic tuple (rate, channels, depth, frames, duration_sec, energy).

        ``_concat_chunks`` used to rely only on file SIZE, which cannot tell a
        real "caller not heard" bug apart from a format/codec problem. The
        genuine sample rate lives only in the fmt chunk: reading it here lets
        us catch chunk N differing in rate/channels from chunk 1 (which breaks
        the concat header + Lua's duration math) and 44-byte empty files.
        Best-effort: any stub/empty/invalid file yields None, never throws.
        """
        from adapters.stt import audio_energy
        import wave as _wave
        try:
            with _wave.open(path, "rb") as w:
                rate = w.getframerate()
                ch = w.getnchannels()
                depth = w.getsampwidth()
                nframes = w.getnframes()
            dur = nframes / float(rate) if rate else 0.0
            return (rate, ch, depth, nframes, round(dur, 3), os.path.getsize(path),
                    round(audio_energy(path), 4))
        except Exception:  # noqa: BLE001
            return None

    def _concat_chunks(self, paths):
        """Concatenate same-format mono WAV chunks (FS records) into one
        temp wav. PCM data is appended raw; the header comes from chunk 1."""
        import wave as _wave
        tmpdir = getattr(self, "tmpdir", None) or tempfile.gettempdir()
        fd, out = tempfile.mkstemp(suffix=".wav", dir=tmpdir)
        os.close(fd)
        real_paths = []
        for p in paths:
            if not p or not os.path.exists(p):
                continue
            real = os.path.realpath(p)
            allowed = any(
                real == d or real.startswith(d + os.sep)
                for d in self.UPLOAD_ALLOWED_DIRS
            )
            if allowed:
                real_paths.append(real)
        if not real_paths:
            raise ValueError("no valid chunks")
        # DIAG 2026-08-27: distinguish "RTP not arriving" (tiny/empty chunks)
        # from "silent RTP" (full-size all-zero chunks) AND catch a per-chunk
        # format/codec mismatch. Each chunk's ACTUAL header (rate, channels,
        # depth) is read directly — the "she can't hear me" incident lives on
        # this split. Concatenating a stereo chunk into a mono wire (or a 16k
        # chunk after an 8k header) yields recognised-then-garbled audio.
        _diags = [self._wav_diag(p) for p in real_paths]
        try:
            print(f"[turn-audio] {len(real_paths)} chunk(s): "
                  + "; ".join(
                      "-" if d is None else
                      f"{d[0]}Hz/{d[1]}ch/{d[2]*8}bit {d[3]}fr {d[4]}s "
                      f"{d[5]}B en={d[6]}"
                      for d in _diags), flush=True)
        except Exception:  # noqa: BLE001
            pass
        with _wave.open(real_paths[0], "rb") as w0:
            params = w0.getparams()
            first_data = w0.readframes(w0.getnframes())
        with _wave.open(out, "wb") as w:
            w.setnchannels(params.nchannels)
            w.setsampwidth(params.sampwidth)
            w.setframerate(params.framerate)
            w.writeframes(first_data)
            for p in real_paths[1:]:
                try:
                    with _wave.open(p, "rb") as wi:
                        w.writeframes(wi.readframes(wi.getnframes()))
                except Exception:  # noqa: BLE001
                    continue
        if params.nchannels == 2:
            # record_stereo chunks (FS): LEFT = CALLER, RIGHT = Vera's
            # playback. Keep LEFT only — otherwise whisper transcribes our
            # own voice as the user ("she hears herself" bug, live call
            # 2026-08-22).
            import numpy as _np
            with _wave.open(out, "rb") as r:
                sr2 = r.getframerate()
                frames2 = r.readframes(r.getnframes())
            left = _np.frombuffer(frames2, dtype=_np.int16).reshape(-1, 2)[:, 0]
            with _wave.open(out, "wb") as wr:
                wr.setnchannels(1)
                wr.setsampwidth(2)
                wr.setframerate(sr2)
                wr.writeframes(left.astype(_np.int16).tobytes())
        # DIAG 2026-08-27: log the FINAL file actually handed to STT (what the
        # transcribe hop sees), so a quiet/dead/mis-encoded wire is visible
        # BEFORE recognition scores it. Headers only — read-only, never throws.
        try:
            _fin = self._wav_diag(out)
            print(f"[turn-audio] merged -> "
                  f"{'-' if _fin is None else '%sHz/%sch/%sbit %sfr %.3fs %dB en=%.4f'
                        % (_fin[0], _fin[1], _fin[2]*8, _fin[3], _fin[4], _fin[5], _fin[6])}",
                  flush=True)
        except Exception:  # noqa: BLE001
            pass
        return out

    def save_upload(self, raw, ctype):
        """Return (path, is_temp). is_temp=True for files we created here
        (multipart body) so the handler only cleans up its own temp files —
        a JSON `{"audio": "/path"}` reference must never be deleted.

        SECURITY FIX: JSON audio paths are restricted to known temp dirs so a
        client cannot exfiltrate arbitrary files through the turn archive.
        """
        import shutil as _shutil

        if "multipart/form-data" in ctype:
            return parse_multipart_wav(raw, ctype), True
        # JSON body: {"audio": "/path/to.wav"} (shared filesystem) or
        # {"audio_b64": "<wav bytes base64>"} (Docker: no shared filesystem
        # between the gateway and the agent containers).
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001
            return None, False
        b64 = payload.get("audio_b64")
        if b64:
            try:
                data = base64.b64decode(b64)
            except Exception:  # noqa: BLE001
                return None, False
            if not data:
                return None, False
            tmpdir = getattr(self, "tmpdir", None) or tempfile.gettempdir()
            fd, staged = tempfile.mkstemp(suffix=".wav", dir=tmpdir)
            os.close(fd)
            with open(staged, "wb") as f:
                f.write(data)
            return staged, True
        # JSON: {"audio": "/path/to.wav"} or {"audio": [chunk1, chunk2, ...]}
        # (chunked recording: the dialplan records in short chunks when room
        # noise defeats the FS silence detector; the server concatenates).
        try:
            path = payload.get("audio")
            if isinstance(path, list):
                return self._concat_chunks(path), True
            if not path or not os.path.exists(path):
                return None, False
            real = os.path.realpath(path)
            allowed = any(
                real == d or real.startswith(d + os.sep)
                for d in self.UPLOAD_ALLOWED_DIRS
            )
            if not allowed:
                print(f"[call-agent] rejected audio outside allowed dirs: {real}",
                      flush=True)
                return None, False
            tmpdir = getattr(self, "tmpdir", None)
            if tmpdir:
                real_tmp = os.path.realpath(tmpdir)
                if not (real.startswith(real_tmp + os.sep) or real == real_tmp):
                    # move into our tmpdir so cleanup/tracking is local and the
                    # original is never modified.
                    fd, staged = tempfile.mkstemp(suffix=".wav", dir=tmpdir)
                    os.close(fd)
                    try:
                        _shutil.copyfile(real, staged)
                        return staged, True
                    except OSError:
                        try:
                            os.remove(staged)
                        except OSError:
                            pass
                        return None, False
            return path, False
        except Exception:
            pass
        return None, False

    def _audio_key(self, call_id, kind, turn_no):
        """Deterministic MinIO object key for a turn's audio (or None when
        object storage is not enabled).

        read.md rev-3 G1: this is called in the VOICE HOT PATH (inside the
        per-call lock), so it must NEVER probe the network. The key is purely
        deterministic; the worker decides whether MinIO is reachable when it
        actually uploads (_upload_turn_audio)."""
        if not (self.pg_available and turn_no):
            return None
        return f"calls/{call_id}/{kind}-{turn_no:04d}.wav"

    def process_turn(self, wav_path, call_id=None):
        ctx = self.get_call(call_id)
        self.sweep_expired()
        with ctx.lock:
            agent, rec = ctx.agent, ctx.recorder

            tci = getattr(self.stt, "transcribe_with_confidence", None)
            if tci is not None:
                res = tci(wav_path)
                transcript, _stt_reason = gate_stt_transcript(
                    res.text, res.confidence)
                confidence = res.confidence
            else:
                raw = self.stt.transcribe_clean(wav_path)
                transcript, _stt_reason = gate_stt_transcript(raw, None)
                confidence = None

            if not transcript:
                plan = agent.plan_reply("", reason=_stt_reason or None)
                reply = plan.get("fallback") or "Повторите, пожалуйста."
                agent.commit_reply(reply)
            elif self._looks_like_echo(transcript,
                                       getattr(agent, "_last_reply", None)):
                print("[call-agent] echo-guard: transcript matches "
                      "Vera's last reply -> repeat request", flush=True)
                plan = agent.plan_reply("", reason="echo")
                reply = plan.get("fallback") or "Повторите, пожалуйста."
                agent.commit_reply(reply)
                transcript = None
            elif _stt_reason == "stt_uncertain":
                plan = agent.plan_reply(transcript, reason="stt_uncertain")
                reply = plan.get("fallback") or "Повторите, пожалуйста."
                agent.commit_reply(reply)
            else:
                # U9: pass the STT confidence (0..1 | None) so low-confidence
                # transcripts cannot fabricate a GREEN or confirm a RED.
                agent.observe_confidence(confidence)
                reply = agent.reply(transcript)
            finished = agent.finished

            # AUDIT FIX: the reply audio used to be embedded as base64 in the
            # JSON response (~1 MB per turn). No consumer reads it — the Lua
            # script plays reply_wav_path. Keeping it only wasted bandwidth.
            reply_wav = self._phone_wav(self.tts.generate(reply))
            saved = None
            user_turn_no = len(rec.call["turns"]) + 1 if transcript else None
            if reply_wav:
                saved = save_wav(self.outdir, reply_wav, upload=False,
                                 call_id=ctx.call_id, turn_id=user_turn_no)

            if transcript:
                saved_user = save_user_wav(self.outdir, wav_path, upload=False,
                                           call_id=ctx.call_id,
                                           turn_id=user_turn_no)
                audio_key = self._audio_key(ctx.call_id, "user", user_turn_no)
                self._persist_turn(ctx, "user", transcript, source="stt",
                                   confidence=confidence,
                                   audio_path=saved_user, audio_key=audio_key)
            self._persist_turn(ctx, "assistant", reply, source="agent",
                               audio_path=saved, audio_key=self._audio_key(
                                   ctx.call_id, "reply", user_turn_no))
            summary = rec.summary_path()
            ctx.last_seen = time.time()

        return {
            "ok": True,
            "call_id": ctx.call_id,
            "turn_id": ctx.turn_id,
            "generation_id": ctx.generation_id,
            "transcript": transcript,
            "reply": reply,
            "finished": finished,
            "reply_wav_path": saved,
            "summary_path": summary,
            "outcome": agent.outcome,
        }

    def process_text_turn(self, text, call_id=None):
        """WebApp->Agent->LLM text channel: one turn with no audio.

        Reuses the same recorder API and turn flow as process_turn — only the
        user turn originates as typed text (source="text", confidence 1.0)
        instead of STT audio. The agent reply is generated through the normal
        dialogue engine and recorded as an assistant turn.

        FIX 2026-08-27: text turns now enter through begin_turn/end_turn like
        every other user turn (overlap -> CallBusyError, generation bumps,
        cancel_event safety). Previously text and voice used different paths,
        so a text turn could interleave with a running voice turn."""
        self.sweep_expired()
        ctx = self.begin_turn(call_id)
        try:
            with ctx.lock:
                agent, rec = ctx.agent, ctx.recorder
                reply = agent.reply(text)
                finished = agent.finished
                user_turn_no = len(rec.call["turns"]) + 1
                self._persist_turn(ctx, "user", text, source="text",
                                   confidence=1.0, audio_key=self._audio_key(
                                       ctx.call_id, "user", user_turn_no))
                self._persist_turn(ctx, "assistant", reply, source="agent",
                                   audio_key=self._audio_key(
                                       ctx.call_id, "reply", user_turn_no))
                summary = rec.summary_path()
                ctx.last_seen = time.time()

            return {
                "ok": True,
                "call_id": ctx.call_id,
                "turn_id": ctx.turn_id,
                "generation_id": ctx.generation_id,
                "transcript": text,
                "reply": reply,
                "finished": finished,
                "reply_wav_path": None,
                "summary_path": summary,
                "outcome": agent.outcome,
            }
        finally:
            self.end_turn(ctx)

    def _blank_turn_diag(self, wav_path, call_id, stream_confidence,
                         transcript):
        """Attribution for a "she can't hear me" turn on the PHONE path.

        A turn that produced no usable transcript always lands here. It is
        opaque WHY (client silent vs loud noise vs a dead/quiet RTP leg), so
        we log objective metrics from the VERY audio at that instant and, on
        request, retain a copy for offline VAD/whisper forensics.

        Three self-explanatory causes, decided from hard numbers:
          * SILENT  — Silero VAD found meaningfully no speech AND the energy
            of the whole turn is near the audio-energy silence gate.
          * MUTED   — speech energy is present but whisper could not map it
            to text above the confidence gate (background/quiet voice).
          * NOAUDIO — the chunks themselves carry no signal (RTP/device).
        Callers treat this as best-effort reporting; it never throws.
        """
        from adapters.stt import audio_energy
        try:
            energy = audio_energy(wav_path)
            # Silero VAD authoritative speech seconds (0 if floor kicks in).
            vad = None
            try:
                import tts_common
                vad = tts_common.vad_speech_seconds(wav_path)
            except Exception:  # noqa: BLE001
                vad = None
            no_speech = vad is not None and vad < 0.15
            if no_speech and energy < 0.004:
                cause = "SILENT"
            elif no_speech:
                cause = "MUTED"
            else:
                cause = "LOWCONF" if stream_confidence is not None \
                    and stream_confidence < 0.55 else "NOAUDIO"
            print(f"[call-agent] BLANK {call_id}: cause={cause} "
                  f"vad={'' if vad is None else f'{vad:.2f}s'} "
                  f"energy={energy:.4f} conf="
                  f"{'' if stream_confidence is None else f'{stream_confidence:.2f}'} "
                  # read.md rev-3 G8: no raw transcript in the log — the blank
                  # diagnosis is about WHY, not WHAT was (not) heard.
                  f"in_chars={len(transcript or '')}", flush=True)
            if env_bool("MOSS_RETAIN_BLANK_AUDIO") and wav_path \
                    and os.path.exists(wav_path):
                d = os.path.join(self.tmpdir, "blank_audio")
                os.makedirs(d, exist_ok=True)
                dst = os.path.join(d, f"{call_id}_{int(time.time())}.wav")
                import shutil as _sh
                _sh.copyfile(wav_path, dst)
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _looks_like_echo(transcript, last_reply):
        """True when the transcript is (mostly) Vera's own recent words.

        The phone recording mixes both directions (RECORD_STEREO is not
        honoured by this FS build — verified 2026-08-23), so whisper
        sometimes transcribes VERA'S PLAYBACK as user speech and she then
        "hears herself" (live calls 2026-08-22/23). Her actual reply text
        is known: a transcript that heavily overlaps it is echo, not the
        caller. Long overlap required so genuine short answers that reuse
        her question's words ("таблетка помогла") still pass."""
        if not transcript or not last_reply:
            return False
        # Canonical one-word wellness answers must never be dropped as echo
        # of the greeting («хорошо», «плохо») — live calls stalled here.
        from core.dialogue import short_real_answer
        if short_real_answer(transcript):
            return False

        def _tok(s):
            return [w for w in re.findall(r"[а-яёa-z0-9]+", s.lower())
                    if len(w) > 1]

        t, r = _tok(transcript), _tok(last_reply)
        if not t or len(t) < 3 or not r:
            return False
        rset = set(r)
        hit = sum(1 for w in t if w in rset)
        if hit / len(t) >= 0.6 and len(t) >= 4:
            return True
        # exact contiguous phrase from her reply repeated by "the caller"
        return hit >= 3 and " ".join(t) in " ".join(r)

    def process_turn_stream(self, wav_path, call_id=None, cancel_event=None,
                            segment_dir=None):
        """STT -> agent reply -> TTS, yielding each audio frame as it is made.

        Yields dicts: first frame carries metadata (transcript/reply/finished),
        each audio frame has wav_b64, and the last frame has done=True.
        ``cancel_event`` (threading.Event) lets a barge-in abort TTS generation
        mid-stream (no further frames are produced).

        PHONE PATH: when ``segment_dir`` is set, every finished reply sentence
        is ALSO written there as seg-NNNN.wav (16 kHz mono for FreeSWITCH,
        atomic rename) and announced with a {"seg_file": ...} frame, so the
        dialplan starts playing sentence 1 while the rest is still generating.
        done.json appears in segment_dir when the turn fully completes.

        STT is INCREMENTAL (P0-REALTIME-CORE step 11): the recorded turn is
        transcribed hop-by-hop and each confirmed hop is emitted as an
        ``{"type": "interim", "transcript": ...}`` frame BEFORE the reply
        begins, so a compliant client can show live transcription.
        """
        ctx = self.get_call(call_id)
        self.sweep_expired()

        # ARCHITECTURE 2026-08-27 (generation_id end-to-end): this stream was
        # started for ONE dialogue generation. Capture the generation/turn
        # NOW and attach it to every emitted frame so the receiver (WebApp,
        # host dialplan, future STT/TTS services) can discard anything that
        # arrives tagged with a superseded version after a barge-in.
        _turn_id = ctx.turn_id
        _gen_id = ctx.generation_id

        # LATENCY TRACE (architecture lesson): mark wall-clock at each stage
        # so a slow turn is attributable to STT / LLM / TTS, not guessed at.
        _t_turn = time.time()
        _t_stt = None
        _t_first_audio = None
        _t_llm_first = None

        _trace = self._maybe_latency_trace  # bound once (hot loop)

        # LATENCY FIX: the STT pass no longer runs under the per-call lock and
        # each confirmed hop is yielded THE MOMENT it is decoded — the client
        # sees live transcription while recognition is still running, instead
        # of getting every interim frame after STT+LLM finished. Decode is
        # pure (no ctx state touched); the overlapping-turn guard
        # (begin_turn/turn_in_progress) still makes this safe per call.
        transcript = None
        stream_confidence = None
        stt_reason = None
        pcm, sample_rate = None, None
        # PRECHECK: skip STT on truly silent audio to save ~5 s per
        # turn when the caller hasn't spoken at all (pure silence).
        # Threshold matches SILENCE_ENERGY in stt.py (0.002) so quiet
        # elderly speech is never skipped — it always reaches STT.
        _skip_stt = False
        try:
            from adapters.stt import audio_energy as _ae
            if _ae(wav_path) < 0.002:
                _skip_stt = True
                transcript = None
                stream_confidence = None
                stt_reason = None
                pcm, sample_rate = None, None
        except Exception:  # noqa: BLE001
            pass

        # PHONE PATH (segment_dir set) uses ONE-SHOT STT: the hop-by-hop
        # incremental decode exists for live captions and is ~3x slower
        # end-to-end; the caller only needs the final transcript fast.
        _stt_hard_fail = None
        if not _skip_stt:
            try:
                if segment_dir:
                    res = self.stt.transcribe_with_confidence(wav_path)
                    stream_confidence = res.confidence
                    transcript, stt_reason = gate_stt_transcript(
                        res.text, res.confidence)
                else:
                    with open(wav_path, "rb") as wf:
                        wav_bytes = wf.read()
                    pcm, sample_rate = wav_to_pcm(wav_bytes)
            except Exception as e:  # noqa: BLE001
                pcm, sample_rate = None, None
                _stt_hard_fail = f"stt:{type(e).__name__}"

        if segment_dir:
            _t_stt = time.time()

        if pcm and not segment_dir:
            samples = list(struct.unpack("<%dh" % (len(pcm) // 2), pcm))
            stream_stt = StreamingSTT(self.stt, sample_rate=sample_rate or 16000)
            for i in range(0, len(samples), 160):  # 10ms cadence
                if cancel_event is not None and cancel_event.is_set():
                    break
                hop_text, _interim = stream_stt.feed(samples[i:i + 160])
                if hop_text:
                    yield {"type": "interim", "transcript": hop_text,
                           "final": False, "i": i,
                           "turn_id": _turn_id, "generation_id": _gen_id}
            transcript = stream_stt.finish()
            # U9: the stream path exposes the fresh-decode confidence (None
            # when the turn came from hop concatenation only).
            stream_confidence = stream_stt.confidence
            transcript, stt_reason = gate_stt_transcript(
                transcript, stream_confidence)
        _t_stt = time.time()

        # Dialogue-state mutations run under the per-call lock. Only the
        # DETERMINISTIC plan (Stage 4 state machine) is computed here; the
        # model is NEVER run under the lock. The reply itself is produced by
        # TOKEN STREAMING below: the first finished sentence goes to TTS while
        # the LLM is still generating the rest (Stage 5).
        with ctx.lock:
            agent, rec = ctx.agent, ctx.recorder

            if _stt_hard_fail:
                # Hard STT failure ≠ silence: family status must be TECHNICAL.
                agent.mark_technical(_stt_hard_fail)

            if transcript is None:
                # STT failure and NO-SPEECH go through the dialogue engine
                # (empty-turn escalation: repeat request -> "Вам плохо?"),
                # never through a hardcoded phrase that bypasses it.
                # PHONE-PATH DIAGNOSTICS: attribute exactly WHY the turn is
                # blank (VAD-silence vs noise/quiet voice vs confidence gate)
                # so a live "он не слышит" becomes a number, not a guess.
                if segment_dir:
                    self._blank_turn_diag(wav_path, ctx.call_id,
                                          stream_confidence, transcript)
                plan = agent.plan_reply("")
                agent.last_intent = plan.get("intent") or ""
                canned_reply = None if plan.get("intent") \
                    else (plan.get("fallback") or "")
            elif self._looks_like_echo(transcript,
                                       getattr(agent, "_last_reply", None)):
                # ECHO GUARD: the transcript is Vera's own words coming
                # back from the mixed recording (_looks_like_echo) — do
                # not feed them to the dialogue engine and do not archive
                # the audio as "user"; run the empty-turn flow instead so
                # she asks the caller to repeat.
                print("[call-agent] echo-guard: transcript matches "
                      "Vera's last reply -> repeat request", flush=True)
                plan = agent.plan_reply("", reason="echo")
                agent.last_intent = plan.get("intent") or ""
                canned_reply = None if plan.get("intent") \
                    else (plan.get("fallback") or "")
                transcript = None
            else:
                agent.observe_confidence(stream_confidence)
                reason = stt_reason
                if not transcript and not reason:
                    reason = "low_conf"
                if segment_dir and not transcript:
                    self._blank_turn_diag(wav_path, ctx.call_id,
                                          stream_confidence, transcript)
                plan = agent.plan_reply(transcript or "", reason=reason)
                agent.last_intent = plan.get("intent") or ""
                canned_reply = None if plan.get("intent") \
                    else (plan.get("fallback") or "")

            finished = agent.finished

            # copy the caller's audio into the archive while the temp upload
            # still exists — LOCAL only (upload is handed to the worker below);
            # read.md rev-3 G1 removes MinIO/PG from before-first-audio.
            user_turn_no = len(rec.call["turns"]) + 1 if transcript else None
            saved_user = save_user_wav(self.outdir, wav_path, upload=False,
                                       call_id=ctx.call_id, turn_id=user_turn_no) \
                if transcript else None
            if transcript:
                self._persist_turn(
                    ctx, "user", transcript, source="stt",
                    confidence=stream_confidence, audio_path=saved_user,
                    audio_key=self._audio_key(ctx.call_id, "user",
                                              user_turn_no))

        # AUDIT FIX: register this reply's generation server-side so a
        # stream-cancel can abort the real model work (not just our read loop).
        sid = f"{ctx.call_id}-{uuid.uuid4().hex[:8]}"
        ctx.stream_id = sid

        meta_base = {"call_id": ctx.call_id, "turn_id": _turn_id,
                     "generation_id": _gen_id, "transcript": transcript,
                     "finished": finished, "outcome": agent.outcome}
        print(f"[call-agent] TURN {ctx.call_id} turn_id={_turn_id} "
              # read.md rev-3 G8: meta_base still carries the transcript for
              # downstream frames, but the OPERATIONAL log line must not dump
              # raw conversation content (separate encrypted store, ACL'd).
              f"generation_id={_gen_id} in_chars={len(transcript or '')}",
              flush=True)

        if canned_reply is not None:
            # No model involved (missing transcript / scripted step): keep the
            # simple single-shot flow.
            yield {"type": "interim", "transcript": transcript, "final": True,
                   "reply": canned_reply, "finished": finished,
                   "turn_id": _turn_id, "generation_id": _gen_id}
            segments = [canned_reply]
        else:
            # Live meta frame: the reply text is not final yet (it keeps
            # growing while tokens stream in); the done frame carries it.
            yield {"type": "interim", "transcript": transcript, "final": True,
                   "finished": finished,
                   "turn_id": _turn_id, "generation_id": _gen_id}
            segments = reply_segments(agent, plan, cancel_event)

        response_parts = []
        idx = 0
        got_audio = False
        pcm_parts = []
        sample_rate = None
        sent_done = False

        def meta_now():
            return {**meta_base, "reply": " ".join(response_parts),
                    "finished": agent.finished, "outcome": agent.outcome}

        seg_no = 0
        if _t_stt is not None:
            _t_llm_first = time.time()  # start of LLM + TTS pipeline (post-STT)
        try:
            for segment in segments:
                if cancel_event is not None and cancel_event.is_set():
                    self.tts.cancel_stream_by_id(ctx.stream_id)
                    break
                if not segment:
                    continue
                # HALLUCINATION + BROKEN-REPLY GUARDS: Qwen3 sometimes asserts
                # things the caller never said (appearance comments), parrots the
                # caller's words («Вы говорите о…») or code-switches to english.
                # Such a sentence is replaced with the scripted fallback BEFORE
                # it is spoken.
                if plan is not None and plan.get("intent") and (
                        reply_looks_hallucinated(segment, transcript or "")
                        or reply_looks_broken(segment)):
                    print(f"[call-agent] hallucination guard: {segment[:60]}",
                          flush=True)
                    segment = (plan.get("fallback") or segment)
                if plan is not None and plan.get("intent") and segment:
                    cleaned = _clean_llm(segment)
                    if cleaned:
                        segment = cleaned
                response_parts.append(segment)
                seg_sid = f"{sid}-{seg_no}"
                seg_no += 1
                ctx.stream_id = seg_sid
                seg_pcm = []
                seg_done = False
                for frame in self.tts.stream(segment, cancel_event=cancel_event,
                                             stream_id=seg_sid):
                    if cancel_event is not None and cancel_event.is_set():
                        # barge-in: emit a single done frame with the aborted state
                        # so the client knows the assistant stopped talking.
                        wire = {"done": True, "aborted": True}
                        wire.update(meta_now())
                        yield wire
                        sent_done = True
                        break
                    idx = frame.get("i", idx)
                    wire = {"i": idx, "turn_id": _turn_id,
                            "generation_id": _gen_id}
                    if frame.get("done"):
                        seg_done = True
                        break
                    audio = base64.b64decode(frame.get("wav_b64") or "")
                    if not audio:
                        continue
                    if _t_first_audio is None:
                        _t_first_audio = time.time()  # first audible frame
                    got_audio = True
                    pcm, sr = wav_to_pcm(audio)
                    if pcm:
                        sample_rate = sr or sample_rate
                        pcm_parts.append(pcm)
                        seg_pcm.append((pcm, sr or sample_rate or 48000))
                    wire["done"] = False
                    # LATENCY FIX: tell downstream (tg_server -> WebApp) the true
                    # sample rate of this frame so the client never resamples blindly.
                    if sr:
                        wire["sample_rate"] = sr
                    # metadata on the first audible frame so the client can show
                    # the transcript immediately while audio keeps streaming
                    if idx == 0:
                        wire.update(meta_now())
                    wire["wav_b64"] = frame["wav_b64"]
                    yield wire
                    idx += 1
                # PHONE PATH: this sentence is fully synthesized — drop a 16 kHz
                # wav into segment_dir so the dialplan can play it right away.
                if seg_done and segment_dir and seg_pcm:
                    seg_path = self._write_segment_file(segment_dir, seg_pcm)
                    if seg_path:
                        yield {"seg_file": seg_path, "i": idx,
                               "turn_id": _turn_id, "generation_id": _gen_id}
                if sent_done and cancel_event is not None and cancel_event.is_set():
                    break
        except Exception as e:  # noqa: BLE001
            agent.mark_technical(f"tts:{type(e).__name__}")
            if not response_parts and plan is not None:
                fb = plan.get("fallback") or (
                    "Сейчас помехи на линии. Повторите, пожалуйста.")
                response_parts.append(fb)

        reply = " ".join(response_parts).strip()
        if plan is not None and plan.get("intent") and reply:
            cleaned = _clean_llm(reply)
            if cleaned:
                reply = cleaned
        meta = meta_now()

        # The model produced nothing usable: speak the canned fallback so the
        # caller is never left without an answer (Stage 9 requirement).
        if not got_audio and not (cancel_event is not None and cancel_event.is_set()):
            fb = (plan or {}).get("fallback") if plan else None
            # FIX 2026-08-27: an EMPTY model reply (reply == "") used to make
            # this condition false, so the caller got silence exactly when the
            # model produced nothing usable. Only skip when we would recreate
            # the identical fallback already emitted through another path.
            if fb and reply != fb:
                reply = fb
                meta = {**meta_base, "reply": reply}
                fb_sid = f"{sid}-fallback"
                ctx.stream_id = fb_sid
                fb_pcm = []
                fb_idx0 = idx
                for frame in self.tts.stream(fb, cancel_event=cancel_event,
                                             stream_id=fb_sid):
                    if cancel_event is not None and cancel_event.is_set():
                        break
                    if frame.get("done"):
                        break
                    audio = base64.b64decode(frame.get("wav_b64") or "")
                    if not audio:
                        continue
                    got_audio = True
                    wire = {"i": idx, "turn_id": _turn_id,
                            "generation_id": _gen_id}
                    pcm, sr = wav_to_pcm(audio)
                    if pcm:
                        sample_rate = sr or sample_rate
                        pcm_parts.append(pcm)
                        fb_pcm.append((pcm, sr or sample_rate or 48000))
                        if sr:
                            wire["sample_rate"] = sr
                    wire["wav_b64"] = frame["wav_b64"]
                    yield wire
                    idx += 1
                # PHONE PATH: the fallback must actually reach the caller —
                # without a seg-file the dialplan plays silence exactly when
                # the caller is already getting nothing else.
                if fb_pcm and segment_dir:
                    seg_path = self._write_segment_file(segment_dir, fb_pcm)
                    if seg_path:
                        yield {"seg_file": seg_path, "i": fb_idx0,
                               "turn_id": _turn_id,
                               "generation_id": _gen_id}

        if not sent_done and not (cancel_event is not None and cancel_event.is_set()):
            yield {"done": True, **meta}

        ctx.stream_id = ""

        if cancel_event is not None and cancel_event.is_set():
            # CANCELLED (barge-in): nothing to persist, but the consumer
            # (VoiceRuntime/Lua) still needs the done.json marker — without
            # it the session would sit in streaming=True forever. Written
            # here, AFTER the done frame, so "done.json exists" still means
            # "this turn is fully over".
            if segment_dir:
                self._write_done_file(segment_dir, meta)
            return

        saved = None
        if pcm_parts:
            saved = save_wav(self.outdir,
                             pcm_to_wav(b"".join(pcm_parts), sample_rate or 24000),
                             upload=False,
                             call_id=ctx.call_id, turn_id=user_turn_no)
        with ctx.lock:
            # Canned and LLM replies must both land in llm_history / _last_reply
            # so echo-guard and the cloud LLM see what Vera actually said.
            if reply:
                agent.commit_reply(reply)
            # read.md rev-3 G1: assistant-turn PG INSERT + MinIO go through
            # the background persistence worker, never the hot path.
            self._persist_turn(
                ctx, "assistant", reply, source="agent", audio_path=saved,
                audio_key=self._audio_key(ctx.call_id, "reply", user_turn_no))
            ctx.last_seen = time.time()
        self._emit_session(ctx)
        _trace(_t_turn, _t_stt, _t_llm_first, _t_first_audio,
               transcript, reply, ctx.call_id, _turn_id, _gen_id)
        # DONE MARKER LAST (2026-08-29, FIXES_PLAN P2): written only after
        # persist/emit so the consumer never starts the next turn while the
        # current one is still finishing (it used to run before persist and
        # before the turn lock was released -> 429 busy on the next turn).
        if segment_dir:
            self._write_done_file(segment_dir, meta)