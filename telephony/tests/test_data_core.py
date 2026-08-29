"""Phase 2 data-core drills against a REAL Postgres.

Idempotency / durability invariants:
- webhook replayed 100x -> exactly 1 provider_events row, 1 side effect;
- late ``answered`` after ``completed`` is ignored (guarded transition);
- ``timeout`` cannot double-fire / create a second attempt;
- outbox accumulates when downstream is down and dispatches after recovery;
- unprocessed events are re-driven by reconciliation.

Skips itself when MOSS_PG_URL is unset (offline suite).
"""
import json
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

PG_URL = os.environ.get("MOSS_PG_URL", "")

from adapters.pg import PgStore, maybe_pg_store, _NoPg  # noqa: E402
from core.migrate import apply_migrations  # noqa: E402
from core.provider_events import (  # noqa: E402
    process_provider_event,
    reconcile_unprocessed,
)
from adapters.pg_recorder import PgRecorder  # noqa: E402
from core.outbox_worker import OutboxWorker  # noqa: E402
from adapters.stt import STTResult  # noqa: E402

_TABLES = [
    "dialogue_answers", "dialogue_turns", "call_results", "call_attempts",
    "call_sessions", "provider_events", "outbox_messages", "incidents",
    "incident_actions", "consents", "person_memory", "audit_log",
]


def _wav_bytes(n=1600):
    import io
    import struct
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(struct.pack("<%dh" % n, *([0] * n)))
    return buf.getvalue()


def _tmp_wav():
    import tempfile
    fd, p = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    with open(p, "wb") as f:
        f.write(_wav_bytes())
    return p


class _FakeSilentSTT:
    def transcribe_with_confidence(self, path):
        return STTResult("тишина", 0.1)


class _FakeTTS:
    def ready(self):
        return True

    def health(self):
        return True, None

    def generate(self, text):
        return _wav_bytes()


@unittest.skipUnless(PG_URL, "MOSS_PG_URL not set (offline suite)")
class DataCoreDrillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pg = PgStore(url=PG_URL)
        apply_migrations(PG_URL)
        cls._seq = 0

    def setUp(self):
        self._wipe(self.pg)

    @classmethod
    def tearDownClass(cls):
        cls._wipe(cls.pg)
        cls.pg.close()

    @staticmethod
    def _wipe(pg):
        with pg._pool.connection(timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute("SET session_replication_role = replica")
                for t in _TABLES:
                    cur.execute(f"TRUNCATE TABLE {t} RESTART IDENTITY CASCADE")
                cur.execute("SET session_replication_role = origin")
            conn.commit()

    def _event_id(self):
        self._seq += 1
        return f"ev-{self._seq}-{id(self)}"

    def _make_attempt(self, call_id="c1", attempt_id="a1"):
        self.pg.new_call(call_id)
        self.pg.create_attempt(attempt_id, call_id, callout_id="co-1")
        return attempt_id

    # ------------------------------------------------------------------ #
    def test_webhook_replay_100x_yields_one_processing(self):
        self._make_attempt("c-replay", "a-replay")
        first = None
        for _ in range(100):
            ev = process_provider_event(self.pg, {
                "event_id": "dup-event",
                "kind": "completed",
                "attempt_id": "a-replay",
                "payload": {"duration_seconds": 42},
            })
            first = first or ev
        self.assertTrue(first["processed"])
        self.assertEqual(first["new_status"], "completed")
        # 100 replays -> 1 row, attempt completed once, 1 outbox message.
        row = self.pg.event("dup-event")
        self.assertEqual(row["processed_at"] is not None, True)
        self.assertEqual(self.pg.get_attempt("a-replay")["status"], "completed")
        self.assertEqual(self.pg.get_attempt("a-replay")["duration_seconds"], 42)
        outbox = self.pg._exec(
            "SELECT count(*) AS n FROM outbox_messages "
            "WHERE dedup_key = 'provider:dup-event'", fetch="val")
        self.assertEqual(outbox, 1)
        self.assertEqual(self.pg._exec(
            "SELECT count(*) FROM provider_events", fetch="val"), 1)

    def test_late_answered_after_completed_is_ignored(self):
        self._make_attempt("c-late", "a-late")
        process_provider_event(self.pg, {
            "event_id": "e-completed", "kind": "completed",
            "attempt_id": "a-late", "payload": {}})
        late = process_provider_event(self.pg, {
            "event_id": "e-answered-late", "kind": "answered",
            "attempt_id": "a-late", "payload": {}})
        # The late event was processed (inboxed) but applied NO transition.
        self.assertTrue(late["processed"])
        self.assertFalse(late["transition_applied"])
        self.assertEqual(self.pg.get_attempt("a-late")["status"], "completed")

    def test_timeout_does_not_fire_twice_or_create_second_call(self):
        self._make_attempt("c-to", "a-to")
        t1 = process_provider_event(self.pg, {
            "event_id": "e-to-1", "kind": "timeout",
            "attempt_id": "a-to", "payload": {}})
        self.assertTrue(t1["transition_applied"])
        self.assertEqual(self.pg.get_attempt("a-to")["status"], "failed")
        self.assertEqual(self.pg.get_attempt("a-to")["hangup_cause"], "timeout")
        # A second timeout for the same attempt is a duplicate event id
        # (provider retries) and applies nothing new.
        t2 = process_provider_event(self.pg, {
            "event_id": "e-to-1", "kind": "timeout",
            "attempt_id": "a-to", "payload": {}})
        self.assertFalse(t2["processed"])
        # And a late answered after timeout stays ignored.
        late = process_provider_event(self.pg, {
            "event_id": "e-to-late", "kind": "answered",
            "attempt_id": "a-to", "payload": {}})
        self.assertFalse(late["transition_applied"])
        self.assertEqual(self.pg.get_attempt("a-to")["status"], "failed")
        # Webhook path never creates attempts: still exactly one.
        self.assertEqual(self.pg._exec(
            "SELECT count(*) FROM call_attempts WHERE call_id = 'c-to'",
            fetch="val"), 1)

    def test_full_ring_answer_complete_chain(self):
        self._make_attempt("c-chain", "a-chain")
        process_provider_event(self.pg, {
            "event_id": "e-ring", "kind": "call_started",
            "attempt_id": "a-chain", "payload": {}})
        self.assertEqual(self.pg.get_attempt("a-chain")["status"], "ringing")
        process_provider_event(self.pg, {
            "event_id": "e-ans", "kind": "answered",
            "attempt_id": "a-chain", "payload": {}})
        self.assertEqual(self.pg.get_attempt("a-chain")["status"], "answered")
        process_provider_event(self.pg, {
            "event_id": "e-done", "kind": "hangup",
            "attempt_id": "a-chain", "payload": {"duration_seconds": 60}})
        a = self.pg.get_attempt("a-chain")
        self.assertEqual(a["status"], "completed")
        self.assertEqual(a["duration_seconds"], 60)
        # session closed + downstream notify enqueued
        self.assertEqual(self.pg._exec(
            "SELECT status FROM call_sessions WHERE call_id = 'c-chain'",
            fetch="val"), "completed")
        self.assertEqual(self.pg._exec(
            "SELECT count(*) FROM outbox_messages WHERE topic = 'call.result' "
            "AND dedup_key = 'provider:e-done'", fetch="val"), 1)

    # ------------------------------------------------------------------ #
    def test_outbox_retry_then_dispatched(self):
        msg = self.pg.enqueue("test.topic", {"n": 1}, dedup_key="d1")
        self.assertIsNotNone(msg)
        # failing dispatcher -> retry scheduled
        pg = self.pg
        worker = OutboxWorker(pg, lambda *a: False, worker_id="w-test",
                              retry_delay_seconds=0)
        claimed, delivered = worker.run_once()
        self.assertEqual(claimed, 1)
        self.assertEqual(delivered, 0)
        row = pg._exec(
            "SELECT status, attempts FROM outbox_messages WHERE id = %s",
            (msg,), fetch="one")
        self.assertEqual(row["status"], "pending")  # retryable again
        self.assertEqual(row["attempts"], 1)
        # healthy downstream -> dispatch succeeds
        worker2 = OutboxWorker(pg, lambda *a: True, worker_id="w-test",
                               retry_delay_seconds=0)
        claimed, delivered = worker2.run_once()
        self.assertEqual(claimed, 1)
        self.assertEqual(delivered, 1)
        self.assertEqual(pg._exec(
            "SELECT status FROM outbox_messages WHERE id = %s",
            (msg,), fetch="val"), "dispatched")

    def test_outbox_dead_letter_after_max_attempts(self):
        pg = self.pg
        msg = pg.enqueue("test.topic", {"n": 2})
        worker = OutboxWorker(pg, lambda *a: False, worker_id="w-test",
                              retry_delay_seconds=0, max_attempts=2)
        for _ in range(2):
            worker.run_once()
        self.assertEqual(pg._exec(
            "SELECT status FROM outbox_messages WHERE id = %s",
            (msg,), fetch="val"), "dead")

    def test_outbox_dedup_key_is_unique(self):
        pg = self.pg
        m1 = pg.enqueue("test.topic", {"n": 3}, dedup_key="dup-x")
        m2 = pg.enqueue("test.topic", {"n": 4}, dedup_key="dup-x")
        self.assertIsNotNone(m1)
        self.assertIsNone(m2)
        self.assertEqual(pg._exec(
            "SELECT count(*) FROM outbox_messages WHERE dedup_key = 'dup-x'",
            fetch="val"), 1)

    # ------------------------------------------------------------------ #
    def test_reconcile_drives_crash_window_events(self):
        self._make_attempt("c-rec", "a-rec")
        # simulate: event ingested (committed) but never processed (crash)
        inserted = self.pg.ingest_provider_event(
            "e-orphan", "completed", {"duration_seconds": 9},
            call_id="c-rec", attempt_id="a-rec")
        self.assertTrue(inserted)
        self.assertIsNone(self.pg.get_attempt("a-rec")["provider_event_id"])
        n = reconcile_unprocessed(self.pg)
        self.assertGreaterEqual(n, 1)
        row = self.pg.event("e-orphan")
        self.assertIsNotNone(row["processed_at"])
        self.assertEqual(self.pg.get_attempt("a-rec")["provider_event_id"],
                         "e-orphan")

    def test_pg_recorder_roundtrip(self):
        rec = PgRecorder(self.pg)
        rec.new_call(call_id="c-recorder")
        rec.add_turn("user", "Мне плохо", source="stt", confidence=0.9,
                     audio_key="calls/c-recorder/user-0001.wav")
        rec.add_turn("assistant", "Перезвоним родным", source="agent")
        rec.finalize("alert", confidence=0.9, notes=["обнаружена опасность"])
        turns = self.pg.turns("c-recorder")
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0]["confidence"], 0.9)
        self.assertEqual(turns[0]["audio_key"],
                         "calls/c-recorder/user-0001.wav")
        result = self.pg._exec(
            "SELECT verdict, notes FROM call_results WHERE call_id = %s",
            ("c-recorder",), fetch="one")
        self.assertEqual(result["verdict"], "alert")
        self.assertIn("обнаружена опасность", result["notes"])
        self.assertEqual(self.pg._exec(
            "SELECT status FROM call_sessions WHERE call_id = 'c-recorder'",
            fetch="val"), "completed")

    def test_no_pg_configured_returns_loud_standin(self):
        store = maybe_pg_store(url="")
        self.assertIsInstance(store, _NoPg)
        self.assertFalse(store.available)
        with self.assertRaises(Exception):
            store.new_call("x")

    def test_webhook_route_100x_over_http_single_processing(self):
        """Drill at the HTTP boundary: POST /webhook/provider 100x with the
        same provider event id -> 1 provider_events row, attempt completed,
        1 outbox message."""
        from conftest_or_paths import SAMPLE_REF
        from core.orchestrator import Serve
        from legacy.call_agent_http import Handler, QuietHTTPServer

        class _Args:
            refs = [SAMPLE_REF]
            tts_port_file = None
            tts_port = None
            inference_steps = 6
            no_style = False
            outdir = os.path.join(_HERE, "_tmp_wh_calls")
            tts_host = None
            tmpdir = "/tmp/mossvoice_turns"

        serve = Serve(_Args())
        serve.stt = _FakeSilentSTT()
        serve.tts = _FakeTTS()
        try:
            self.assertTrue(serve.pg_available)
            serve.pg.new_call("c-http")
            serve.pg.create_attempt("a-http", "c-http", callout_id="co-http")
            srv = QuietHTTPServer(("127.0.0.1", 0), Handler)
            srv.serve = serve
            import threading
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            port = srv.server_address[1]
            import urllib.request

            body = json.dumps({
                "event_id": "wh-dup", "kind": "completed",
                "attempt_id": "a-http",
                "payload": {"duration_seconds": 15},
            }).encode()
            ok = 0
            for _ in range(100):
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/webhook/provider",
                    data=body,
                    headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    if resp.status == 200:
                        ok += 1
            self.assertEqual(ok, 100)  # 200 for every replay
            self.assertEqual(self.pg._exec(
                "SELECT count(*) FROM provider_events WHERE event_id='wh-dup'",
                fetch="val"), 1)
            self.assertEqual(self.pg.get_attempt("a-http")["status"],
                             "completed")
            self.assertEqual(self.pg._exec(
                "SELECT count(*) FROM outbox_messages "
                "WHERE dedup_key='provider:wh-dup'", fetch="val"), 1)
            srv.shutdown()
        finally:
            if serve.outbox is not None:
                serve.outbox.stop()
            serve.pg.close()

    def test_serve_with_pg_writes_data_core(self):
        """Full vertical slice: Serve + real PG + file-mode off.

        new_call/process_turn/end_call persist call_sessions,
        dialogue_turns (with STT confidence) and call_results, and enqueue a
        call.result outbox message for downstream notify.
        """
        os.environ["MOSS_NO_WARMUP"] = "1"
        from conftest_or_paths import SAMPLE_REF
        from adapters.stt import STTResult
        from core.orchestrator import Serve
        from core.state import CallContext

        class _Args:
            refs = [SAMPLE_REF]
            tts_port_file = None
            tts_port = None
            inference_steps = 6
            no_style = False
            outdir = os.path.join(_HERE, "_tmp_core_calls")
            tts_host = None
            tmpdir = "/tmp/mossvoice_turns"

        class _FakeSTT:
            def transcribe_with_confidence(self, path):
                return STTResult("всё хорошо", 0.92)

        class _FakeTTS:
            def ready(self):
                return True

            def health(self):
                return True, None

            def generate(self, text):
                return _wav_bytes()

        serve = Serve(_Args())
        serve.stt = _FakeSTT()
        serve.tts = _FakeTTS()
        try:
            self.assertTrue(serve.pg_available)
            # recorder is Postgres-backed (file recorder replaced)
            ctx = serve.get_call(serve.new_call(caller_id="mom1"))
            self.assertIsInstance(ctx, CallContext)
            cid = ctx.call_id
            p = _tmp_wav()
            try:
                r = serve.process_turn(p, call_id=cid)
                self.assertEqual(r["transcript"], "всё хорошо")
            finally:
                os.remove(p)
            done = serve.end_call(cid)
            self.assertEqual(done["outcome"]["status"], "ok")
            # durable rows written
            turns = serve.pg.turns(cid)
            self.assertGreaterEqual(len(turns), 2)
            self.assertEqual(turns[0]["confidence"], 0.92)
            verdict = serve.pg._exec(
                "SELECT verdict FROM call_results WHERE call_id = %s",
                (cid,), fetch="val")
            self.assertEqual(verdict, "ok")
            self.assertEqual(serve.pg._exec(
                "SELECT count(*) FROM outbox_messages WHERE topic='call.result' "
                "AND dedup_key = %s", (f"call:{cid}",), fetch="val"), 1)
            self.assertEqual(serve.pg._exec(
                "SELECT status FROM call_sessions WHERE call_id = %s",
                (cid,), fetch="val"), "completed")
        finally:
            if serve.outbox is not None:
                serve.outbox.stop()
            serve.pg.close()

    # ------------------------------------------------------------------ #
    # G8 retention: expired-by-TTL purge leaves no content, only an audit row
    # ------------------------------------------------------------------ #
    def test_retention_purges_expired_call_and_leaves_audit(self):
        from workers.retention_worker_main import run_once
        pg = self.pg
        # create an OLD terminal call (well past its retention window)
        pg.new_call("c-ret", retention_days=0)
        pg.add_turn("c-ret", "user", "привет", source="stt",
                    audio_key="calls/c-ret/user-0001.wav")
        pg.add_turn("c-ret", "assistant", "пока", source="llm",
                    audio_key="calls/c-ret/reply-0001.wav")
        pg.finalize_call("c-ret", "ok", notes=["done"])
        # backdate ended_at so it is instantly expired
        pg._exec("UPDATE call_sessions SET ended_at = now() - interval '10 days' "
                 "WHERE call_id = 'c-ret'")
        # a FRESH call must NOT be purged
        pg.new_call("c-fresh", retention_days=90)
        pg._exec("UPDATE call_sessions SET ended_at = now() "
                 "WHERE call_id = 'c-fresh'")

        keys = pg.audio_keys_for("c-ret")
        self.assertEqual(
            sorted(keys),
            ["calls/c-ret/reply-0001.wav", "calls/c-ret/user-0001.wav"])

        outdir = os.path.join(_HERE, "_tmp_ret")
        os.makedirs(os.path.join(outdir, "c-ret"), exist_ok=True)
        open(os.path.join(outdir, "c-ret", "user-0001.wav"), "w").close()
        open(os.path.join(outdir, "c-ret", "reply-0001.wav"), "w").close()

        n = run_once(pg, outdir, log=lambda *a, **k: None)
        self.assertEqual(n, 1)  # exactly the expired call, not c-fresh
        # content rows gone
        self.assertEqual(pg.turns("c-ret"), [])
        self.assertIsNone(pg._exec(
            "SELECT verdict FROM call_results WHERE call_id = 'c-ret'",
            fetch="val"))
        # local WAV cache removed
        self.assertFalse(os.path.exists(os.path.join(outdir, "c-ret")))
        # fresh call untouched
        self.assertEqual(pg._exec(
            "SELECT count(*) FROM call_sessions WHERE call_id = 'c-fresh'",
            fetch="val"), 1)
        # a durable audit marker remains (call_id only, no content)
        audit = pg._exec(
            "SELECT count(*) FROM audit_log WHERE action = "
            "'data.retention.purged' AND entity_id = 'c-ret'",
            fetch="val")
        self.assertEqual(audit, 1)

    def test_retention_holds_metadata_while_s3_down_then_purges(self):
        """rev-4 Gate C: when S3 is configured but down, retention must NOT
        purge Postgres (the metadata holds the object keys) — it holds for a
        retry; once deletion is confirmed the purge completes."""
        from workers import retention_worker_main as rw
        pg = self.pg
        pg.new_call("c-s3down", retention_days=0)
        pg.add_turn("c-s3down", "user", "привет", source="stt",
                    audio_key="calls/c-s3down/user-0001.wav")
        pg.finalize_call("c-s3down", "ok")
        pg._exec("UPDATE call_sessions SET ended_at = now() - interval '10 days' "
                 "WHERE call_id = 'c-s3down'")

        # Make the worker believe S3 is configured (so it must confirm deletes)
        env_keys = ("MOSS_S3_ENDPOINT", "MOSS_S3_ACCESS_KEY", "MOSS_S3_SECRET_KEY")
        saved = {k: os.environ.get(k) for k in env_keys}
        os.environ["MOSS_S3_ENDPOINT"] = "http://127.0.0.1:9"
        os.environ["MOSS_S3_ACCESS_KEY"] = "x"
        os.environ["MOSS_S3_SECRET_KEY"] = "y"

        real_delete = rw.delete_objects
        outdir = os.path.join(_HERE, "_tmp_ret_s3")
        try:
            # Phase 1: S3 unreachable -> deletion not confirmed -> hold
            rw.delete_objects = lambda keys: 0
            n = rw.run_once(pg, outdir, log=lambda *a, **k: None)
            self.assertEqual(n, 0, "nothing purged while S3 deletion pending")
            # metadata (and therefore the object keys) must SURVIVE the hold
            self.assertEqual(pg.audio_keys_for("c-s3down"),
                             ["calls/c-s3down/user-0001.wav"])
            self.assertEqual(pg._exec(
                "SELECT count(*) FROM call_sessions "
                "WHERE call_id = 'c-s3down'", fetch="val"), 1)

            # Phase 2: S3 recovers -> confirmed -> retry purges everything
            rw.delete_objects = lambda keys: len(keys)
            n = rw.run_once(pg, outdir, log=lambda *a, **k: None)
            self.assertEqual(n, 1, "retry with confirmed delete purges the call")
            self.assertEqual(pg.audio_keys_for("c-s3down"), [])
            self.assertEqual(pg._exec(
                "SELECT count(*) FROM call_sessions "
                "WHERE call_id = 'c-s3down'", fetch="val"), 0)
            audit = pg._exec(
                "SELECT count(*) FROM audit_log WHERE action = "
                "'data.retention.purged' AND entity_id = 'c-s3down'",
                fetch="val")
            self.assertEqual(audit, 1)
        finally:
            rw.delete_objects = real_delete
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            import shutil
            shutil.rmtree(outdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)