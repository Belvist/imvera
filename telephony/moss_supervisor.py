#!/usr/bin/env python3
"""MossVoice production supervisor — one process tree, four services.

Services (each independent, restarts on crash):
  1. voice    — tts_server.py          127.0.0.1:9600  (TTS only)
  2. answers  — llm_server.py          127.0.0.1:9500  (LLM reply generation)
  3. telephony— call_agent.py          127.0.0.1:9400  (legacy STT + dialogue)
  4. runtime  — voice_runtime.py       127.0.0.1:9700  (VoiceRuntime / G3)

Readiness model (2026-08-29): a service is "alive" while it ANSWERS our
identity contract on its port — HTTP 503 with a body IS an answer ("I am
mossvoice-*, model still loading"), not a crash and not a conflict. The
supervisor waits for /ready and only restarts services that truly stopped
answering. A stranger (a process answering a DIFFERENT identity on our
port) is still a ConfigConflict (fail fast).

Usage:
  moss_supervisor.py start [--daemon]   start all services (foreground or bg)
  moss_supervisor.py stop               graceful shutdown of the whole tree
  moss_supervisor.py status             health of every managed service
  moss_supervisor.py restart            stop + start

The supervisor itself never loads a model: it only keeps child processes
alive and reports their health. A crashed child is restarted with
exponential backoff (1s..60s), reset after 2 min of stable uptime.
"""
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

TEL = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TEL)
RUNTIME = os.path.expanduser("~/Library/Application Support/MossVoice/runtime")
PIDFILE = os.path.join(TEL, "moss_supervisor.pid")
STATUSFILE = os.path.join(TEL, "moss_supervisor.json")

TTS_PORT = int(os.environ.get("MOSS_TTS_PORT", "9600"))
LLM_PORT = int(os.environ.get("MOSS_LLM_PORT", "9500"))
AGENT_PORT = int(os.environ.get("MOSS_AGENT_PORT", "9400"))
RUNTIME_PORT = int(os.environ.get("MOSS_RUNTIME_PORT", "9700"))

# read.md rev-3 G4: identity contract. Each managed service answers /health
# (or /ready) with service + protocol_version; the supervisor only ADOPTS /
# accepts an endpoint that self-identifies as the expected service on a
# compatible protocol version. A stranger on our port (wrong or missing
# identity) is NOT adopted — it is a ConfigConflict (fail fast).
PROTOCOL_VERSION = 1
SERVICE_TELEPHONY = "mossvoice-telephony"
SERVICE_LLM = "mossvoice-llm"
SERVICE_TTS = "mossvoice-tts"
SERVICE_RUNTIME = "mossvoice-runtime"


def python_bin():
    env = os.environ.get("MOSS_PY")
    if env:
        return env
    repo_venv = os.path.join(REPO, "runtime", "qwen-venv", "bin", "python")
    if os.path.exists(repo_venv):
        return repo_venv
    venv = os.path.join(RUNTIME, "qwen-venv", "bin", "python")
    if os.path.exists(venv):
        return venv
    return sys.executable


REF = os.path.join(REPO, "refs", "ref_native_48k.wav")
if not os.path.exists(REF):
    REF = os.path.join(REPO, "refs", "ref_vera_female.wav")
if not os.path.exists(REF):
    REF = os.path.join(TEL, "refs", "sample.wav")


def services():
    py = python_bin()
    llm_runtime = os.environ.get("MOSS_LLM_RUNTIME", "llama").strip().lower()
    if llm_runtime in ("llama", "llama.cpp", "openai", "stage_a"):
        answers_cmd = [
            "bash",
            os.path.join(REPO, "scripts", "run_llm_host.sh"),
        ]
    else:
        answers_cmd = [
            py,
            os.path.join(TEL, "llm_server.py"),
            "--port",
            str(LLM_PORT),
        ]
    return [
        {
            "name": "answers",
            "cmd": answers_cmd,
            "health": f"http://127.0.0.1:{LLM_PORT}/health",
            "ready_key": "ready",
            "service": SERVICE_LLM,
            "startup_grace": 180,   # model load time before "unhealthy" reports
        },
        {
            "name": "voice",
            "cmd": [py, os.path.join(REPO, "runtime", "scripts", "tts_server.py"),
                    "--runtime", RUNTIME, "--port", str(TTS_PORT), "--threads", "2",
                    "--allow-ref-dir", os.path.join(TEL, "refs"),
                    "--allow-ref-dir", os.path.join(REPO, "refs"),
                    # read.md rev-3: STT lives in telephony (phone path) — do
                    # NOT double-load Whisper here. TTS only.
                    "--no-stt"],
            "health": f"http://127.0.0.1:{TTS_PORT}/health",
            "ready_key": "ready",
            "service": SERVICE_TTS,
            "startup_grace": 900,   # TTS cold load can take many minutes
        },
        {
            "name": "telephony",
            "cmd": [py, os.path.join(TEL, "call_agent.py"),
                    "--port", str(AGENT_PORT), "--tts-port", str(TTS_PORT),
                    "--outdir", os.path.join(TEL, "calls"), "--ref", REF],
            # TRUTHFUL READINESS (2026-08-27): gate on /ready (STT+TTS truly
            # usable), not on the old /health that answered "ok": True no
            # matter what.
            "health": f"http://127.0.0.1:{AGENT_PORT}/ready",
            "ready_key": "ready",
            "service": SERVICE_TELEPHONY,
            "startup_grace": 240,
        },
        {
            # read.md G3: VoiceRuntime — continuous-media path on top of the
            # legacy agent (dialplan 4401 answers+parks; runtime drives the
            # leg via ESL: stereo tape, VAD, barge-in, turn_stream playback).
            "name": "runtime",
            "cmd": [py, os.path.join(REPO, "voice_runtime", "runtime.py"),
                    "--agent-port", str(AGENT_PORT),
                    "--http-port", str(RUNTIME_PORT),
                    "--workdir", "/tmp/mossvoice/runtime"],
            "health": f"http://127.0.0.1:{RUNTIME_PORT}/ready",
            "ready_key": "ready",
            "service": SERVICE_RUNTIME,
            "startup_grace": 240,
        },
    ]


class ConfigConflict(Exception):
    """Service port is held by a process that does NOT answer our health
    contract. Adopting it as "external" would hide a real configuration
    conflict and route traffic to the wrong process — fail fast instead."""


class Child:
    def __init__(self, spec):
        self.spec = spec
        self.proc = None
        self.started_at = 0.0
        self.tries = 0
        self.last_exit = None
        # When True the endpoint is already served by an external/orphaned
        # process: we ADOPT it (treat as running) instead of spawning our own
        # child and instigating a bind-fail/restart storm.
        self.external = False

    @property
    def name(self):
        return self.spec["name"]

    def alive(self):
        if self.external:
            # Adopted endpoint: alive while its health endpoint answers.
            return self._probe_healthy()
        return self.proc is not None and self.proc.poll() is None

    def _probe_healthy(self):
        try:
            with urllib.request.urlopen(self.spec["health"], timeout=3) as r:
                obj = json.loads(r.read().decode())
        except Exception:  # noqa: BLE001
            return False
        # read.md rev-3 G4: identity contract — an endpoint is only "ours"
        # to adopt/accept when it self-identifies as the expected SERVICE on
        # a compatible protocol_version. A stranger on our port (wrong or
        # missing identity) is NOT adopted: the caller turns that into a
        # ConfigConflict instead of silently routing traffic to it.
        if int(obj.get("protocol_version", 1)) > PROTOCOL_VERSION:
            return False
        svc = self.spec.get("service")
        if svc and obj.get("service") != svc:
            return False
        key = self.spec.get("ready_key")
        if key:
            return bool(obj.get(key))
        return bool(obj.get("ok"))

    def _port_occupied(self):
        """True when the health endpoint's TCP port is already listening
        (regardless of whether it answers OUR health contract)."""
        import urllib.parse as _up
        try:
            hp = _up.urlparse(self.spec["health"])
            host = hp.hostname or "127.0.0.1"
            port = hp.port or (443 if hp.scheme == "https" else 80)
        except Exception:  # noqa: BLE001
            return False
        import socket as _s
        s = _s.socket(_s.AF_INET, _s.SOCK_STREAM)
        s.settimeout(1.0)
        try:
            s.connect((host, port))
            return True
        except Exception:  # noqa: BLE001
            return False
        finally:
            s.close()

    def start(self):
        # ADOPT-OR-SPAWN (2026-08-27): before touching subprocess, probe the
        # configured health endpoint. If a compatible service already answers,
        # another launcher / an orphaned process owns these ports — spawning a
        # duplicate only makes it die with EADDRINUSE and loop forever.
        if self._probe_healthy():
            self._adopt("already healthy")
            return
        if self._port_occupied():
            # FIX 2026-08-27: a STRANGER owns our port. The old code adopted
            # it as "degraded external", which hid a real config conflict —
            # the wrong process could answer and traffic silently went to the
            # wrong service. Fail fast: no health contract, no adoption.
            raise ConfigConflict(
                f"{self.name}: port at {self.spec['health']} is occupied by "
                f"a process that does NOT answer our health contract")
        log = open(os.path.join(TEL, f"{self.name}.supervisor.log"), "ab")
        self.proc = subprocess.Popen(
            self.spec["cmd"],
            stdout=log, stderr=subprocess.STDOUT,
            cwd=TEL,
            env=dict(os.environ, PYTHONUNBUFFERED="1"),
        )
        self.started_at = time.time()
        print(f"[supervisor] {self.name}: started pid={self.proc.pid}", flush=True)

    def _adopt(self, reason):
        self.external = True
        print(f"[supervisor] {self.name}: adopting ({reason}) — "
              f"not spawning", flush=True)
        self.started_at = time.time()

    def backoff(self):
        return min(2 ** min(self.tries, 6), 60)

    def healthy(self):
        """True/False from the health endpoint; False (never a grace-period
        True) while the service is still loading its model — the caller's
        timeout decides how long that is acceptable."""
        if self.external:
            return self._probe_healthy()
        if not self.alive():
            return None
        return self._probe_healthy()


class Supervisor:
    def __init__(self, only=None):
        specs = services()
        if only:
            specs = [s for s in specs if s["name"] == only]
            if not specs:
                raise SystemExit("unknown service: %s" % only)
        self.children = [Child(s) for s in specs]
        self.stop = False

    def _on_signal(self, signum, frame):
        self.stop = True

    def _wait_healthy(self, c, timeout):
        """Wait until a child reports healthy before starting the next one.

        Boot ordering matters: MLX deadlocks when two processes load models
        concurrently, so services come up one at a time (answers -> voice ->
        telephony) and each model finishes loading before the next begins.
        """
        deadline = time.time() + timeout
        while time.time() < deadline and not self.stop:
            h = c.healthy()
            if h is True:
                return True
            if not c.alive():
                return False
            time.sleep(1)
        return False

    def run(self):
        signal.signal(signal.SIGTERM, self._on_signal)
        signal.signal(signal.SIGINT, self._on_signal)
        with open(PIDFILE, "w") as f:
            f.write(str(os.getpid()))
        for c in self.children:
            try:
                c.start()
            except ConfigConflict as e:
                # FIX 2026-08-27: a foreign process owns the port. Continuing
                # would hide the conflict; stop the tree so the operator can
                # resolve it instead of silently serving wrong traffic.
                print(f"[supervisor] FATAL CONFIGURATION CONFLICT: {e}",
                      flush=True)
                self.shutdown()
                return
            if not self._wait_healthy(c, c.spec["startup_grace"]):
                print(f"[supervisor] {c.name}: not healthy in time; "
                      "continuing (restart loop will recover it)", flush=True)
            self.write_status()
        print("[supervisor] initial start complete", flush=True)
        while not self.stop:
            self.write_status()
            for c in self.children:
                if c.alive():
                    if time.time() - c.started_at > 120:
                        c.tries = 0
                    continue
                code = c.proc.poll() if c.proc else None
                c.last_exit = code
                c.tries += 1
                delay = c.backoff()
                print(f"[supervisor] {c.name}: exited ({code}); "
                      f"restart in {delay}s (try {c.tries})", flush=True)
                self.write_status()
                deadline = time.time() + delay
                while time.time() < deadline and not self.stop:
                    time.sleep(0.2)
                if not self.stop:
                    try:
                        c.start()
                    except ConfigConflict as e:
                        print(f"[supervisor] FATAL CONFIGURATION CONFLICT: "
                              f"{e}", flush=True)
                        self.stop = True
                        break
                    self._wait_healthy(c, c.spec["startup_grace"])
            time.sleep(1)
        self.shutdown()

    def shutdown(self):
        print("[supervisor] stopping all services...", flush=True)
        for c in self.children:
            # Adopted endpoints are not ours to kill — another owner manages them.
            if c.external or not c.alive():
                continue
            c.proc.terminate()
        deadline = time.time() + 10
        for c in self.children:
            if c.external or not c.alive():
                continue
            wait = max(0.1, deadline - time.time())
            try:
                c.proc.wait(timeout=wait)
            except subprocess.TimeoutExpired:
                c.proc.kill()
        try:
            os.remove(PIDFILE)
        except OSError:
            pass
        self.write_status(running=False)
        print("[supervisor] all services stopped", flush=True)

    def write_status(self, running=True):
        state = {
            "supervisor_pid": os.getpid() if running else None,
            "running": running,
            "ts": time.time(),
            "services": {},
        }
        for c in self.children:
            alive = c.alive()
            state["services"][c.name] = {
                "pid": c.proc.pid if (c.proc and alive) else None,
                "alive": alive,
                "healthy": c.healthy(),
                "external": c.external,
                "restarts": max(0, c.tries),
                "uptime_s": int(time.time() - c.started_at) if c.started_at else 0,
            }
        try:
            with open(STATUSFILE, "w") as f:
                json.dump(state, f, indent=2)
        except OSError:
            pass


def _daemon_pid():
    try:
        with open(PIDFILE) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def cmd_start(daemon, only=None):
    if _daemon_pid():
        print(f"[supervisor] already running (pid {_daemon_pid()})")
        return 0
    if daemon:
        if os.fork() > 0:
            time.sleep(0.5)
            print("[supervisor] starting in background — "
                  f"tail {os.path.join(TEL, '*.supervisor.log')}")
            return 0
        os.setsid()
        pid = _daemon_pid()
        if pid:
            print(f"[supervisor] running as pid {pid}")
            return 0
        Supervisor(only=only).run()
        return 0
    Supervisor(only=only).run()
    return 0


def cmd_stop():
    pid = _daemon_pid()
    if not pid:
        print("[supervisor] not running")
        return 0
    os.kill(pid, signal.SIGTERM)
    for _ in range(40):
        if _daemon_pid() is None:
            print("[supervisor] stopped")
            return 0
        time.sleep(0.5)
    # The supervisor itself is wedged: terminate the children directly so
    # nothing survives orphaned, then reap the supervisor.
    try:
        with open(STATUSFILE) as f:
            state = json.load(f)
        for info in state.get("services", {}).values():
            cpid = info.get("pid")
            if cpid:
                try:
                    os.kill(cpid, signal.SIGTERM)
                except OSError:
                    pass
    except Exception:  # noqa: BLE001
        pass
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    print("[supervisor] killed (children terminated)")
    return 0


def cmd_status():
    print(f"python : {python_bin()}")
    pid = _daemon_pid()
    print(f"supervisor: {'running pid=' + str(pid) if pid else 'NOT running'}")
    try:
        with open(STATUSFILE) as f:
            state = json.load(f)
    except Exception:  # noqa: BLE001
        state = None
    for s in services():
        name = s["name"]
        line = f"  {name:<10} {s['health']}"
        try:
            with urllib.request.urlopen(s["health"], timeout=5) as r:
                obj = json.loads(r.read().decode())
            key = s.get("ready_key") or "ok"
            line += f"  -> ok={obj.get('ok')} ready={obj.get(key)}"
        except Exception as e:  # noqa: BLE001
            line += f"  -> down ({e})"
        if state:
            info = state.get("services", {}).get(name, {})
            line += f"  pid={info.get('pid')} restarts={info.get('restarts')} " \
                    f"uptime={info.get('uptime_s')}s"
        print(line)
    return 0


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "start"
    only = None
    if "--service" in args:
        i = args.index("--service")
        only = args[i + 1] if i + 1 < len(args) else None
    if cmd == "start":
        return cmd_start("--daemon" in args, only=only)
    if cmd == "stop":
        return cmd_stop()
    if cmd == "status":
        return cmd_status()
    if cmd == "restart":
        cmd_stop()
        return cmd_start("--daemon" in args or True, only=only)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
