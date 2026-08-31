"""MossVoice VoiceRuntime — main process (read.md G3).

Listens on FreeSWITCH Event Socket; for every answered channel whose
destination is a runtime extension (4400 = production, 4402 = loopback
self-test) it starts a ``CallSession`` (continuous stereo tape + always-on
VAD + barge-in + turn_stream), serves a supervisor-facing /ready, and cleans
up on hangup.

Run (with the telephony stack up):
    python3 voice_runtime/runtime.py --workdir /tmp/mossvoice/runtime

The dialplan (4400/4402) only answers + parks/sleeps: the channel legs then
carry media and are driven entirely from here via ESL (uuid_record /
uuid_broadcast / uuid_break). No Lua; 4401 was retired in G1.
"""
import argparse
import json
import logging
import os
import re
import signal
import socket
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from .agent_http import AgentClient, AGENT_PORT
    from .call_session import CallSession
    from .esl_client import EslClient, ESLProtocolError
except ImportError:  # run as a plain script (python3 voice_runtime/...py)
    from agent_http import AgentClient, AGENT_PORT
    from call_session import CallSession
    from esl_client import EslClient, ESLProtocolError

# G1 cutover 2026-08-30 (P5): live dialplan now routes 4400 -> park
# (mossvoice.xml), Lua retired. Runtime drives both 4400 (production) and
# 4402 (loopback self-test). See scripts/install_freeswitch.sh.
RUNTIME_EXTENSIONS = re.compile(r"^44(0[012])$")
SERVICE_NAME = "mossvoice-runtime"
PROTOCOL_VERSION = 1
TICK = 0.05            # main-loop cadence (s): tap drain + segment poll
IDLE_TIMEOUT = 7200    # force-stop a session stuck this long
AGENT_START_GRACE = 240
ESL_RETRY_SECONDS = 3  # reconnect backoff when the ESL event socket drops


def _setup_logging(verbose=False):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return logging.getLogger("moss.runtime")


class Runtime:
    def __init__(self, esl, agent, workdir, log=None,
                 esl_host=None, esl_port=None):
        self.esl = esl
        self.agent = agent
        self.workdir = workdir
        self.esl_host = esl_host or os.environ.get("MOSS_ESL_HOST", "127.0.0.1")
        self.esl_port = int(esl_port or os.environ.get("MOSS_ESL_PORT", "8021"))
        self.log = log or (lambda m: None)
        self.sessions = {}          # fs_uuid -> CallSession
        self.stopped = False
        self.esl_ok = True
        self.started = time.monotonic()
        self._scan_tick = 0
        self._last_reconnect = 0.0
        os.makedirs(workdir, exist_ok=True)

    # ---- supervisor health ------------------------------------------------
    def ready(self):
        return self.esl_ok and self.agent.health()

    def status(self):
        return {
            "ready": self.ready(),
            "service": SERVICE_NAME,
            "protocol_version": PROTOCOL_VERSION,
            "uptime_s": int(time.monotonic() - self.started),
            "calls_active": len(self.sessions),
            "esl_connected": self.esl_ok,
            "agent_ok": self.agent.health(timeout=2),
        }

    # ---- event loop ---------------------------------------------------------
    def run(self):
        self.log("runtime: waiting for channels (%s)" % self.workdir)
        while not self.stopped:
            ev = self.esl.next_event(timeout=TICK)
            now = time.monotonic()
            if ev is not None:
                self._dispatch(ev)
            # ESL drop is NOT a crash: keep serving /ready (503 while
            # disconnected) and restore the connection on a backoff.
            if not self.esl_ok and now - self._last_reconnect >= \
                    ESL_RETRY_SECONDS:
                self._last_reconnect = now
                self._try_reconnect()
            # Belt-and-suspenders discovery: loopback legs never emit
            # CHANNEL_ANSWER (they are pre-answered), and a call that started
            # before we booted needs attaching too. Scan every ~1 s.
            self._scan_tick += 1
            if self._scan_tick * TICK >= 1.0:
                self._scan_tick = 0
                self._scan_channels()
            for uuid in list(self.sessions):
                sess = self.sessions[uuid]
                sess.on_tick(now)
                if now - sess.started > IDLE_TIMEOUT:
                    self._teardown(uuid, "idle-timeout")

    def _try_reconnect(self):
        """Restore a lost ESL connection (new command+event sockets, fresh
        subscription). Old sessions stay tracked; the next channel scan
        reconciles them with what FreeSWITCH actually has."""
        self.log("ESL reconnect attempt...")
        try:
            esl = EslClient(self.esl_host, self.esl_port)
        except Exception as e:  # noqa: BLE001
            self.log("ESL reconnect failed: %s" % e)
            return
        try:
            self.esl.close()
        except Exception:  # noqa: BLE001
            pass
        self.esl = esl
        self.esl_ok = True
        self.log("ESL reconnected %s:%d" % (self.esl_host, self.esl_port))

    def _scan_channels(self):
        if not self.esl_ok:
            return
        try:
            raw = self.esl.api("show channels as json", timeout=5)
        except Exception as e:  # noqa: BLE001
            self.log("channel scan failed: %s" % e)
            return
        try:
            rows = json.loads(raw[raw.index("{"):]).get("rows", [])
        except (ValueError, IndexError):
            return
        live = set()
        for row in rows:
            dest = row.get("dest") or ""
            uuid = row.get("uuid")
            name = row.get("name") or ""
            direction = row.get("direction") or ""
            if not uuid or not RUNTIME_EXTENSIONS.match(dest):
                continue
            live.add(uuid)
            if uuid in self.sessions:
                continue
            # The loopback self-test originates a pair: A-leg (outbound,
            # loopback/4402-a) runs the originate &playback app; B-leg
            # (inbound, loopback/4402-b) runs OUR dialplan (answer+hold).
            # The B-leg is the one that represents a real inbound SIP call,
            # so attach exactly that leg for both loopback and real callers.
            if direction != "inbound":
                continue
            caller = (row.get("caller_id_number") or
                      row.get("cid_num") or "").strip() or None
            self._attach_channel(uuid, dest, caller_id=caller)
        # SESSION SYNC (2026-08-29): a lost CHANNEL_HANGUP/DESTROY event
        # must not leave a session running forever (stale workdir, phantom
        # agent call). This scan is also our hangup backstop: any tracked
        # uuid that FreeSWITCH no longer lists gets torn down. Only when
        # the scan itself succeeded — never on a scan error.
        for uuid in list(self.sessions):
            if uuid not in live:
                self._teardown(uuid, "channel-gone")

    def _dispatch(self, ev):
        name = ev.get("Event-Name")
        if name == "disconnect":
            self.esl_ok = False
            self.log("ESL event connection closed — will retry in run loop")
            return
        if name == "CHANNEL_ANSWER":
            self._on_answer(ev)
            return
        uuid = ev.get("Unique-ID")
        sess = self.sessions.get(uuid)
        if sess is None:
            return
        if name in ("CHANNEL_HANGUP", "DESTROY"):
            self._teardown(uuid, name)
            return
        sess.handle_event(ev)

    def _on_answer(self, ev):
        uuid = ev.get("Unique-ID")
        dest = ev.get("Caller-Destination-Number", "")
        direction = ev.get("Caller-Direction", "") or \
            ev.get("Channel-Direction", "")
        # BUG FIX (2026-08-29): loopback A-legs DO emit CHANNEL_ANSWER in
        # this FreeSWITCH build — without the inbound filter the runtime
        # attached the OUTBOUND originate leg (dest also matches 44xx) and
        # drove the wrong side of the pair. Only inbound legs represent a
        # real SIP caller.
        if direction and direction not in ("inbound",):
            return
        if not uuid or not RUNTIME_EXTENSIONS.match(dest):
            return
        if uuid in self.sessions:
            return
        caller = (ev.get("Caller-Caller-ID-Number") or "").strip() or None
        self._attach_channel(uuid, dest, caller_id=caller)

    def _attach_channel(self, uuid, dest, caller_id=None):
        if uuid in self.sessions:
            return
        workdir = os.path.join(self.workdir, uuid[:12])
        sess = CallSession(uuid, self.esl, self.agent, workdir,
                           caller_id=caller_id, log=self.log)
        ok = sess.start()
        if not ok:
            self.log("attach %s: session start failed" % uuid[:8])
            return
        self.sessions[uuid] = sess
        self.log("ATTACH uuid=%s dest=%s call=%s caller=%s" %
                 (uuid[:8], dest, sess.call_id, caller_id or "-"))

    def _teardown(self, uuid, why):
        sess = self.sessions.pop(uuid, None)
        if sess is None:
            return
        self.log("HANGUP(%s) uuid=%s call=%s" % (why, uuid[:8], sess.call_id))
        sess.stop()

    def shutdown(self):
        self.stopped = True
        for uuid in list(self.sessions):
            self._teardown(uuid, "shutdown")


def make_handler(runtime):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/health", "/ready"):
                code = 200 if runtime.ready() else 503
                self._send(code, runtime.status())
            else:
                self._send(404, {"error": "not found"})

        def log_message(self, *a):  # keep supervisor log clean
            pass
    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--esl-host", default=os.environ.get("MOSS_ESL_HOST",
                                                         "127.0.0.1"))
    ap.add_argument("--esl-port", type=int,
                    default=int(os.environ.get("MOSS_ESL_PORT", "8021")))
    ap.add_argument("--agent-host", default="127.0.0.1")
    ap.add_argument("--agent-port", type=int,
                    default=int(os.environ.get("MOSS_AGENT_PORT", AGENT_PORT)))
    ap.add_argument("--http-port", type=int,
                    default=int(os.environ.get("MOSS_RUNTIME_PORT", "9700")))
    ap.add_argument("--workdir", default="/tmp/mossvoice/runtime")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    log = _setup_logging(args.verbose)
    agent = AgentClient(args.agent_host, args.agent_port)

    # wait for the agent once (it may still be loading Whisper); do not
    # crash-loop the supervisor afterwards — accepted by adoption below.
    deadline = time.time() + AGENT_START_GRACE
    while time.time() < deadline and not agent.health():
        log.info("waiting for agent :%d ...", args.agent_port)
        time.sleep(2)
    log.info("agent ready=%s" % agent.health())

    # reconnect ESL until the connection sticks (FS may be (re)starting)
    esl = None
    while esl is None:
        try:
            esl = EslClient(args.esl_host, args.esl_port)
        except (OSError, ESLProtocolError) as e:
            log.error("ESL connect failed: %s (retry in 2s)", e)
            time.sleep(2)
    log.info("ESL connected %s:%d", args.esl_host, args.esl_port)

    runtime = Runtime(esl, agent, args.workdir, log=log.info,
                      esl_host=args.esl_host, esl_port=args.esl_port)
    httpd = ThreadingHTTPServer(("127.0.0.1", args.http_port),
                                make_handler(runtime))
    import threading
    threading.Thread(target=httpd.serve_forever, name="health", daemon=True
                     ).start()
    log.info("health/ready on 127.0.0.1:%d" % args.http_port)

    def _sig(*_):
        runtime.shutdown()
        httpd.shutdown()
    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)

    try:
        runtime.run()
    finally:
        httpd.server_close()
        esl.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())