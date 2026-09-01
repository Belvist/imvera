"""HTTP layer for the call agent (legacy localhost API).

The wire protocol is unchanged from the original call_agent.py: /turn,
/turn_stream, /new, /calls/*, /say, /health. Kept as its own module so the
orchestrator stays free of HTTP concerns; behaviour is identical.
"""

import base64
import hashlib
import hmac
import json
import os
import sys
import urllib.parse

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core.state import CallBusyError, AdmissionError
from core.family import (FamilyAccessError, FamilyAuthError,
                          FamilyValidationError)
from adapters.pg import PgUnavailable
from adapters.esl import originate_call, originate_to_number, kill_call

# Upper bound for any request body (audio turn chunks are ~128 KB; JSON
# turn_stream bodies carry base64 audio — MBs at worst). 8 MB is generous.
MAX_BODY_BYTES = 8 * 1024 * 1024


class QuietHTTPServer(ThreadingHTTPServer):
    """AUDIT FIX: streaming clients drop connections mid-stream on every
    barge-in/timeout. The stdlib server used to print a full traceback per
    peer reset (the ConnectionResetError spam in call_agent.log). Benign
    resets are now ignored; real handler exceptions still surface."""

    daemon_threads = True

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError,
                            ConnectionAbortedError, TimeoutError)):
            return
        import traceback
        traceback.print_exc(limit=5)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    # AUDIT FIX: keep-alive handler threads used to block forever in readline
    # waiting for a next request that never comes, pinning a thread per dead
    # socket. A generous but finite timeout lets them exit.
    timeout = 30

    def log_message(self, *a):
        pass

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _components(self):
        """Live status of the realtime components (never throws).

        STT/LLM are probed for "actually usable"; TTS goes through its own
        health endpoint. LLM NOT ready is a degraded mode (scripted replies),
        never a lie about the other two.
        """
        serve = self.server.serve
        stt_ok = bool(getattr(serve.stt, "ready", lambda: False)())
        llm_ok = bool(getattr(serve.llm, "ready", lambda: False)())
        tts_ok, tts_err = serve.tts.health()
        return {
            "stt": stt_ok,
            "llm": llm_ok,
            "tts": tts_ok,
            # read.md rev-4 gate D: schema compatibility is an explicit
            # readiness capability, not a silent console print.
            "schema": bool(getattr(serve, "schema_compatible", True)),
            "postgres": bool(getattr(serve, "pg_available", False)),
        }, tts_err

    def _ready(self):
        """Readiness gate: the voice pipeline must ACTUALLY work.

        200 when STT and TTS are usable (LLM may degrade to the scripted
        fallback — a real working mode); otherwise 503 with per-component
        status so an operator sees exactly what is broken. The response
        carries an explicit `mode`: "full" (LLM online) or "degraded"
        (LLM down, scripted fallback) — read.md rev-2 #14, and consumers
        (compose healthcheck) only look at `ready`.
        """
        comps, tts_err = self._components()
        # read.md rev-4 gate D: schema compatibility gates readiness too.
        ready = bool(comps["stt"] and comps["tts"] and comps["schema"])
        self._json({"ready": ready,
                    # read.md rev-3 G4: identity contract — the supervisor
                    # refuses to adopt a port that does not answer this
                    # service name + protocol_version.
                    "service": "mossvoice-telephony",
                    "protocol_version": 1,
                    "mode": "full" if (ready and comps["llm"])
                            else "degraded" if ready else "down",
                    "components": comps,
                    "error": None if ready else tts_err},
                    status=200 if ready else 503)

    @staticmethod
    def _call_page():
        return """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<title>IMVERA — Зво́нок</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
background:#0d1117;color:#e6edf3;min-height:100vh;display:flex;
align-items:center;justify-content:center}
.card{background:#161b22;border:1px solid #30363d;border-radius:16px;
padding:40px;max-width:420px;width:90%;text-align:center}
h1{font-size:1.4rem;margin-bottom:8px;color:#58a6ff}
p{color:#8b949e;margin-bottom:24px;font-size:.95rem;line-height:1.5}
.btn{background:#238636;color:#fff;border:none;border-radius:10px;
padding:16px 40px;font-size:1.1rem;cursor:pointer;
transition:background .2s,transform .1s;width:100%}
.btn:hover{background:#2ea043}
.btn:active{transform:scale(.97)}
.btn:disabled{background:#30363d;cursor:not-allowed}
.status{margin-top:16px;font-size:.85rem;min-height:1.4em}
.ok{color:#3fb950}.err{color:#f85149}
</style></head><body>
<div class="card">
<h1>🟢 IMVERA</h1>
<p>Введите номер для звонка (например, 89274685381):</p>
<input id="phone" type="tel" value="89274685381" style="padding:10px;font-size:1rem;border:1px solid #30363d;border-radius:8px;width:80%;margin-bottom:16px;background:#0d1117;color:#e6edf3;" />
<br/>
<button class="btn" id="btn" onclick="callPhone()">Позвонить</button>
<div class="status" id="status"></div>
<script>
async function callPhone(){
const btn=document.getElementById('btn');
const st=document.getElementById('status');
const phone=document.getElementById('phone').value;
btn.disabled=true;st.className='status';st.textContent='Звоним на ' + phone + '…';
try{
const r=await fetch('/call/phone',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({phone})});
const d=await r.json();
if(d.ok){st.className='status ok';st.textContent='✅ Звонок на ' + phone + ' идёт! Можете говорить.'}
else{st.className='status err';st.textContent='❌ '+d.error+(d.hint?' ('+d.hint+')':'')}
}catch(e){st.className='status err';st.textContent='❌ Ошибка сети: '+e.message}
btn.disabled=false;
}
function callMac(){
const st=document.getElementById('status');
st.className='status';st.textContent='Используйте поле выше для звонков на телефоны';
}
</script>
<div class="status" id="status"></div>
</div>
<script>
async function callMac(){
const btn=document.getElementById('btn');
const st=document.getElementById('status');
btn.disabled=true;st.className='status';st.textContent='Звоним…';
try{
const r=await fetch('/call',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({})});
const d=await r.json();
if(d.ok){st.className='status ok';st.textContent='✅ Звонок идёт! Можете говорить.'}
else{st.className='status err';st.textContent='❌ '+d.error+(d.hint?' ('+d.hint+')':'')}
}catch(e){st.className='status err';st.textContent='❌ Ошибка сети: '+e.message}
btn.disabled=false;
}
</script></body></html>"""

    def do_GET(self):
        serve = self.server.serve
        # Web "call my Mac" page
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(self._call_page().encode())
            return
        # TRUTHFUL READINESS (2026-08-27): /live only proves the process is
        # alive; /ready aggregates the ACTUAL realtime components (STT/LLM/TTS)
        # so a container is never "healthy" while the voice pipeline is broken
        # (the previous /health returned "ok": True unconditionally).
        if self.path.startswith("/live"):
            self._json({"ok": True})
            return
        if self.path.startswith("/ready"):
            self._ready()
            return
        if self.path.startswith("/health"):
            comps, tts_err = self._components()
            serve = self.server.serve
            with serve._sess_lock:
                active_calls = len(serve.sessions)
            try:
                max_calls = int(os.environ.get(
                    "MOSS_MAX_CONCURRENT_CALLS", "0") or 0)
            except ValueError:
                max_calls = 0
            # TRUTHFUL READINESS: "ok" is only true when the realtime
            # pipeline (STT + TTS) is ACTUALLY usable. Previously /health
            # returned "ok": True unconditionally — a broken STT/TTS still
            # looked healthy. LLM is reported but does not gate "ok" (the
            # scripted fallback is a real, working degraded mode).
            ok = bool(comps["stt"] and comps["tts"] and comps["schema"])
            self._json({
                # read.md rev-3 G4: identity contract (see /ready above).
                "service": "mossvoice-telephony",
                "protocol_version": 1,
                "ok": ok,
                "components": comps,
                "tts": comps["tts"],
                "error": tts_err,
                "pg": getattr(serve, "pg_available", False),
                "redis_degraded": getattr(serve.store, "degraded", False),
                "redis_requested": getattr(serve.store, "redis_requested",
                                           False),
                # admission control: live sessions vs hard cap (0 = no cap)
                "calls_active": active_calls,
                "calls_limit": max_calls,
            })
            return
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path.startswith("/calls"):
            if path == "/calls" or path == "/calls/":
                self.server.serve.sweep_expired()
                self._json({"ok": True, "calls": self.server.serve.list_calls()})
                return
            if path.startswith("/calls/"):
                call_id = path.split("/")[2]
                try:
                    ctx = self.server.serve.get_call(call_id)
                except KeyError:
                    self._json({"ok": False, "error": "call not found"}, 404)
                    return
                self._json({
                    "ok": True,
                    "call_id": ctx.call_id,
                    "created_at": ctx.created_at,
                    "last_seen": ctx.last_seen,
                    "finished": ctx.finished,
                    "outcome": ctx.agent.outcome,
                    "caller_id": ctx.caller_id,
                    "turns": ctx.recorder.call.get("turns", []) if ctx.recorder.call else [],
                })
                return
        if path == "/incidents":
            try:
                self._json({"ok": True,
                            "incidents": self.server.serve.list_incidents(
                                active_only=False)})
            except PgUnavailable:
                self._json({"ok": False,
                            "error": "postgres not configured"}, 503)
            return
        if path == "/family/questions":
            # iPhone family app: poll question statuses / answers.
            qs = urllib.parse.parse_qs(parsed.query)
            key = self.headers.get("X-Moss-Key", "")
            try:
                items = self.server.serve.family_list(
                    key, (qs.get("phone") or [""])[0])
                self._json({"ok": True, "questions": items})
            except FamilyAuthError as e:
                self._json({"ok": False, "error": str(e)}, 401)
            except FamilyAccessError as e:
                self._json({"ok": False, "error": str(e)}, 403)
            except FamilyValidationError as e:
                self._json({"ok": False, "error": str(e)}, 400)
            except PgUnavailable:
                self._json({"ok": False,
                            "error": "postgres not configured"}, 503)
            except Exception as e:  # noqa: BLE001
                self._json({"ok": False, "error": str(e)}, 500)
            return
        self._json({"ok": False, "error": "not found"}, 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # ---- P0-SESSION-001 API -------------------------------------------------
        if path == "/calls" or path == "/new":
            payload = self._read_json_body()
            caller_id = (payload or {}).get("caller_id")
            mode = (payload or {}).get("mode")
            try:
                call_id = self.server.serve.new_call(caller_id=caller_id,
                                                     mode=mode)
            except AdmissionError as e:
                self._json({"ok": False, "error": "capacity",
                            "active": e.active, "limit": e.limit}, 503)
                return
            except ValueError as e:
                # FIX 2026-08-27: invalid mode -> 400 (new_call now validates
                # the value against Agent.MODES instead of silently driving
                # the state machine into an unknown mode).
                self._json({"ok": False, "error": str(e)}, 400)
                return
            self._json({"ok": True, "call_id": call_id})
            return
        if path.startswith("/calls/"):
            rest = path[len("/calls/"):]
            segs = rest.split("/")
            call_id = segs[0]
            if len(segs) == 1 and segs[0] == "":
                call_id = self.server.serve.new_call()
                self._json({"ok": True, "call_id": call_id})
                return
            action = segs[1] if len(segs) > 1 else None
            if action == "has_speech":
                """Chunked-endpointing helper: does the TAIL of this recorded
                chunk contain real CALLER speech? Tail-only (last 1.2 s) +
                energy floor: a TV across the room loses to the near mic."""
                wav_path, is_temp = self.server.serve.save_upload(
                    self._read_raw_body(), self.headers.get("Content-Type", ""))
                if wav_path is None:
                    self._json({"ok": False, "error": "no wav"}, 400)
                    return
                try:
                    from tts_common import vad_speech_seconds
                    vad = vad_speech_seconds(wav_path, tail_s=1.2)
                    speech = bool(vad is None or vad >= 0.15)
                except Exception:  # noqa: BLE001
                    speech = True  # fail open
                finally:
                    if is_temp:
                        try:
                            os.remove(wav_path)
                        except OSError:
                            pass
                self._json({"ok": True, "speech": speech})
                return
            if action == "end":
                try:
                    result = self.server.serve.end_call(call_id)
                except KeyError:
                    self._json({"ok": False, "error": "call not found"}, 404)
                    return
                self._json(result)
                return
            if action == "hangup":
                result = kill_call(call_id)
                self._json(result)
                return
            if action in ("turn", None):
                result = self._handle_turn(call_id)
                if result is not None:
                    self._write_json(result)
                return
            if action == "turn_stream":
                self._handle_turn_stream(call_id)
                return
            if action == "turn_text":
                # WebApp->Agent->LLM text channel: POST {"text": ...}; the
                # agent produces a reply with no audio in the loop.
                payload = self._read_json_body()
                text = (payload or {}).get("text")
                if not isinstance(text, str) or not text.strip() \
                        or len(text) > 2000:
                    self._json({"ok": False,
                                "error": "text required, <=2000 chars"}, 400)
                    return
                try:
                    result = self.server.serve.process_text_turn(
                        text, call_id=call_id)
                except KeyError:
                    self._json({"ok": False, "error": "call not found"}, 404)
                    return
                except CallBusyError:
                    # FIX 2026-08-27: process_text_turn now enters through
                    # begin_turn; a text turn overlapping a voice turn is
                    # rejected with 429 like any other overlapping turn.
                    self._json({"ok": False, "error": "call busy"}, 429)
                    return
                self._json(result)
                return
            if action == "stream-cancel":
                try:
                    ctx = self.server.serve.get_call(call_id)
                except KeyError:
                    self._json({"ok": False, "error": "call not found"}, 404)
                    return
                ctx.cancel_event.set()
                # AUDIT FIX: abort on the TTS daemon too so a barge-in stops
                # the actual model work, not just our read loop.
                sid = ctx.stream_id
                if sid:
                    self.server.serve.tts.cancel_stream_by_id(sid)
                # ARCHITECTURE 2026-08-27: a cancelled generation is DEAD the
                # moment the cancel lands — any late LLM/TTS result tagged
                # with the old generation_id is discarded downstream before it
                # can reach the phone. turn_id stays, generation_id advances
                # (turn 14 can have generations 20 -> 21 after a barge-in).
                gen = ctx.invalidate_generation()
                self._json({"ok": True, "cancelled": bool(ctx.streaming),
                            "generation_id": gen})
                return
            self._json({"ok": False, "error": "not found"}, 404)
            return

        # ---- incident workflow (Phase 3) ------------------------------------
        if path.startswith("/incidents/"):
            segs = path[len("/incidents/"):].split("/")
            incident_id = segs[0]
            action = segs[1] if len(segs) > 1 else None
            payload = self._read_json_body() or {}
            actor = (payload.get("actor") or "family").strip()
            try:
                if action == "ack":
                    moved = self.server.serve.incident_ack(
                        incident_id, actor,
                        action_id=payload.get("action_id"),
                        note=payload.get("note"))
                    self._json({"ok": True, "moved": moved})
                    return
                if action == "resolve":
                    moved = self.server.serve.incident_resolve(
                        incident_id, actor, payload.get("reason") or "ok")
                    self._json({"ok": True, "moved": moved})
                    return
                if action == "false-alarm":
                    moved = self.server.serve.incident_false_alarm(
                        incident_id, actor,
                        payload.get("reason") or "false alarm")
                    self._json({"ok": True, "moved": moved})
                    return
            except PgUnavailable:
                self._json({"ok": False,
                            "error": "postgres not configured"}, 503)
                return
            self._json({"ok": False, "error": "not found"}, 404)
            return

        # ---- provider webhook inbox (Phase 2, idempotent) ----------------
        if path == "/webhook/provider":
            body = self._read_body()
            if body is None:
                self._json({"ok": False, "error": "bad body"}, 400)
                return
            # AUDIT FIX: the webhook drives attempt state machines, so an
            # unauthenticated caller could forge provider outcomes. When
            # MOSS_WEBHOOK_SECRET is set, require HMAC-SHA256 over the raw
            # body in X-Moss-Signature (same opt-in pattern as TG initData).
            secret = os.environ.get("MOSS_WEBHOOK_SECRET", "")
            if secret:
                expected = hmac.new(secret.encode("utf-8"), body,
                                    hashlib.sha256).hexdigest()
                got = self.headers.get("X-Moss-Signature", "")
                if not hmac.compare_digest(got, expected):
                    self._json({"ok": False, "error": "invalid signature"},
                               401)
                    return
            try:
                payload = json.loads(body.decode("utf-8"))
            except Exception:  # noqa: BLE001
                payload = {}
            try:
                result = self.server.serve.handle_provider_event(payload or {})
                self._json({"ok": True, **result})
            except KeyError as e:
                self._json({"ok": False, "error": f"missing field: {e}"}, 400)
            except PgUnavailable:
                self._json({"ok": False,
                            "error": "postgres not configured"}, 503)
            except Exception as e:  # noqa: BLE001
                self._json({"ok": False, "error": str(e)}, 500)
            return

        # ---- family app: questions for the next call ----------------------
        if path == "/family/questions":
            # iPhone family app writes a question; Vera asks it during the
            # next call to this phone. Auth via X-Moss-Key api key.
            payload = self._read_json_body() or {}
            key = self.headers.get("X-Moss-Key", "")
            try:
                res = self.server.serve.family_ask(
                    key, payload.get("phone"), payload.get("text"),
                    payload.get("author"))
                self._json({"ok": True, **res}, 201)
            except FamilyAuthError as e:
                self._json({"ok": False, "error": str(e)}, 401)
            except FamilyAccessError as e:
                self._json({"ok": False, "error": str(e)}, 403)
            except FamilyValidationError as e:
                self._json({"ok": False, "error": str(e)}, 400)
            except PgUnavailable:
                self._json({"ok": False,
                            "error": "postgres not configured"}, 503)
            except Exception as e:  # noqa: BLE001
                self._json({"ok": False, "error": str(e)}, 500)
            return

        # ---- legacy endpoints ---------------------------------------------------
        if path == "/say":
            payload = self._read_json_body()
            text = (payload.get("text") or "").strip()
            ok = bool(self.server.serve.tts.ready())
            path_ = self.server.serve.greeting_wav(None if not text else text)
            resp = {"ok": ok and path_ is not None, "wav_path": path_}
            # Docker: the caller may not share our filesystem — return the
            # greeting audio inline instead of a path.
            if payload.get("wav_b64") and path_:
                try:
                    with open(path_, "rb") as f:
                        resp["wav_b64"] = base64.b64encode(f.read()).decode("ascii")
                except OSError:
                    pass
            self._json(resp)
            return
        if path == "/turn":
            result = self._handle_turn()
            if result is not None:
                self._write_json(result)
            return
        if path == "/turn_stream":
            self._handle_turn_stream()
            return
        # ---- CALL TO PHONE NUMBER (web button) --------------------------------
        if path == "/call/phone":
            payload = self._read_json_body() or {}
            phone = payload.get("phone", "")
            if not phone:
                self._json({"ok": False, "error": "phone number required"}, 400)
                return
            result = originate_to_number(phone)
            if result["ok"]:
                self._json({"ok": True, "call_id": result["uuid"],
                            "phone": phone})
            else:
                self._json({"ok": False, "error": result["message"],
                            "hint": "Check SIP gateway credentials in FreeSWITCH"},
                           status=503)
            return

        # ---- CALL MY MAC (web button) -----------------------------------------
        if path == "/call":
            payload = self._read_json_body() or {}
            extension = payload.get("extension")
            result = originate_call(extension=extension)
            if result["ok"]:
                self._json({"ok": True, "call_id": result["uuid"],
                            "extension": extension or "brian"})
            else:
                self._json({"ok": False, "error": result["message"],
                            "hint": "Zoiper must be registered to FreeSWITCH"},
                           status=503)
            return
        self._json({"ok": False, "error": "not found"}, 404)

    def _read_body(self):
        """Read exactly Content-Length bytes, BOUNDED. Returns None when the
        header is malformed or the body exceeds the cap (caller answers 400).

        AUDIT FIX: without a cap a single huge Content-Length allocates
        unbounded memory in a handler thread; a negative length used to
        become rfile.read(-N) == read-until-EOF, pinning the keep-alive
        thread until the socket timeout."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            return None
        if length <= 0:
            return b""
        if length > MAX_BODY_BYTES:
            return None
        return self.rfile.read(length)

    def _read_raw_body(self):
        return self._read_body() or b""

    def _read_json_body(self):
        raw = self._read_raw_body()
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def _write_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_turn_wav(self):
        raw = self._read_raw_body()
        ctype = self.headers.get("Content-Type", "")
        return self.server.serve.save_upload(raw, ctype)

    def _get_ctx_opt(self, call_id):
        try:
            return self.server.serve.get_call(call_id)
        except KeyError:
            return None

    def _handle_turn(self, call_id=None):
        wav_path, is_temp = self._read_turn_wav()
        if wav_path is None:
            self._json({"ok": False, "error": "no wav in upload"}, 400)
            return None
        ctx = None
        try:
            try:
                ctx = self.server.serve.begin_turn(call_id)
            except CallBusyError:
                self._json({"ok": False, "error": "call busy"}, 429)
                return None
            return self.server.serve.process_turn(wav_path, call_id=ctx.call_id)
        except KeyError:
            return {"ok": False, "error": "call not found"}
        finally:
            if ctx is not None:
                self.server.serve.end_turn(ctx)
            if is_temp:
                try:
                    os.remove(wav_path)
                except OSError:
                    pass

    def _handle_turn_stream(self, call_id=None):
        # AUDIT FOLLOW-UP 2026-08-21: this handler previously did its own
        # unbounded rfile.read(length), bypassing MAX_BODY_BYTES — a single
        # huge Content-Length could OOM a handler thread. Route through the
        # bounded reader like every other endpoint.
        raw = self._read_body()
        if raw is None:
            self._json({"ok": False, "error": "body too large"}, 413)
            return
        body = {}
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001
            body = {}
        wav_path, is_temp = self.server.serve.save_upload(
            raw, self.headers.get("Content-Type", ""))
        if wav_path is None:
            self._json({"ok": False, "error": "no wav in upload"}, 400)
            return
        # PHONE PATH: optional directory for per-sentence wav files. Only
        # paths under the shared /tmp/mossvoice are accepted. realpath()
        # resolves any symlinks so a pre-planted link inside world-writable
        # /tmp cannot redirect writes outside the shared dir (defense in
        # depth on top of the literal ".." rejection).
        segment_dir = None
        sd = str(body.get("segment_dir") or "")
        try:
            base = os.path.realpath("/tmp/mossvoice")
            if sd.startswith("/tmp/mossvoice/") and \
                    os.path.realpath(sd).startswith(base + os.sep):
                segment_dir = sd
        except OSError:
            segment_dir = None
        ctx = None
        try:
            try:
                ctx = self.server.serve.begin_turn(call_id)
            except CallBusyError:
                self._json({"ok": False, "error": "call busy"}, 429)
                return
        except KeyError:
            self._json({"ok": False, "error": "call not found"}, 404)
            return
        cancel_event = ctx.cancel_event
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def write_frame(obj):
            payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            frame = len(payload).to_bytes(4, "big") + payload
            for i in range(0, len(frame), 48 * 1024):
                part = frame[i:i + 48 * 1024]
                self.wfile.write(b"%X\r\n" % len(part))
                self.wfile.write(part)
                self.wfile.write(b"\r\n")

        try:
            for frame in self.server.serve.process_turn_stream(
                    wav_path, call_id=call_id, cancel_event=cancel_event,
                    segment_dir=segment_dir):
                write_frame(frame)
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except KeyError:
            try:
                write_frame({"error": "call not found", "done": True})
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001
            try:
                write_frame({"error": str(exc), "done": True})
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except Exception:  # noqa: BLE001
                pass
        finally:
            self.server.serve.end_turn(ctx)
            if is_temp:
                try:
                    os.remove(wav_path)
                except OSError:
                    pass