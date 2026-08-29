#!/usr/bin/env python3
"""Loopback self-test of the FULL VoiceRuntime path (read.md G3 self-test).

Requirements: the whole stack is up (moss_supervisor: tts :9600, llm :9500,
agent :9400, runtime :9700) and the dialplan has 4400 -> answer + park and
4402 -> answer + sleep (the loopback self-test leg). Reload the dialplan
first if you just added it:

    fs_cli -x reloadxml
    python3 voice_runtime/loopback_test.py

Verifies, on real FreeSWITCH + real agent, the runtime's own wiring:
  1. originate loopback/4400 -> the runtime picks the B-leg, POST /calls and
     attaches the stereo tape (record_stereo: LEFT=caller, RIGHT=played);
  2. the greeting is actually broadcast (RIGHT channel gains energy; LEFT
     stays silent — loopback carries no inbound speech);
  3. B-leg = the ONE the runtime tracks (/ready calls_active == 1);
  4. uuid_break during playback -> PLAYBACK_STOP <= 300 ms (barge-in);
  5. on hangup the runtime POSTs /calls/<id>/end (call leaves the agent's
     active list) and removes its workdir.

The voice turn itself (VAD -> STT -> turn_stream) needs REAL inbound RTP,
which loopback cannot produce — that is exactly Zoiper acceptance test #1.
"""
import json
import os
import socket
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

ESL_HOST = "127.0.0.1"
ESL_PORT = int(os.environ.get("MOSS_ESL_PORT", "8021"))
# SECURITY (2026-08-29): never a hardcoded default — the operator's
# FreeSWITCH password must come from the environment, exactly like the
# production supervisor does. No password, no self-test.
ESL_PWD = os.environ.get("MOSS_ESL_PASSWORD")
if not ESL_PWD:
    print("FAIL: set MOSS_ESL_PASSWORD (your FreeSWITCH ESL password) "
          "before running the loopback self-test", flush=True)
    sys.exit(1)
AGENT_PORT = int(os.environ.get("MOSS_AGENT_PORT", "9400"))
RUNTIME_PORT = int(os.environ.get("MOSS_RUNTIME_PORT", "9700"))
WORKDIR = "/tmp/mossvoice/runtime"
RMS_GATE = 300.0          # same ENERGY_THRESHOLD as the VAD
BREAK_LATENCY = 0.300     # acceptance: barge-in must stop audio <= 300 ms

PASS = "PASS"
SKIP = "SKIP"
FAIL = "FAIL"
checks = []


def check(name, ok, note=""):
    status = PASS if ok else FAIL
    checks.append((name, status))
    print("  [%s] %s %s" % (status, name, note), flush=True)
    return ok


def http_get(port, path, timeout=5):
    with urllib.request.urlopen(
            "http://127.0.0.1:%d%s" % (port, path), timeout=timeout) as r:
        return json.loads(r.read().decode())


def agent_calls():
    return {c.get("call_id") for c in http_get(AGENT_PORT, "/calls")["calls"]}


def rms(vals):
    if not vals:
        return 0.0
    s = sum(x * x for x in vals)
    return (s / len(vals)) ** 0.5


def tap_energy(path, side):
    """side='left'|'right' -> (rms, channels) of that channel of the tape."""
    import wave
    import struct
    with wave.open(path, "rb") as w:
        nch = w.getnchannels()
        frames = w.readframes(w.getnframes())
    vals = struct.unpack("<%dh" % (len(frames) // 2), frames)
    if nch == 2:
        vals = vals[0::2] if side == "left" else vals[1::2]
    return rms(vals), nch


def main():
    print("== preconditions ==", flush=True)
    ok_h = False
    ok_a = False
    try:
        ok_h = bool(http_get(RUNTIME_PORT, "/ready", 4).get("ready"))
    except Exception as e:  # noqa: BLE001
        print("  runtime /ready unreachable: %s" % e, flush=True)
    try:
        ok_a = bool(http_get(AGENT_PORT, "/ready", 4).get("ready"))
    except Exception as e:  # noqa: BLE001
        print("  agent /ready unreachable: %s" % e, flush=True)
    if not check("preconditions: runtime+agent ready", ok_h and ok_a):
        print("start the stack first: telephony/moss_supervisor.py start",
              flush=True)
        return 1

    before = agent_calls()

    # ---- ESL control connection (independent from the runtime's) ----------
    s = socket.create_connection((ESL_HOST, ESL_PORT), timeout=6)


    def kill_own_legs():
        """Teardown ONLY the legs this self-test created. Never `hupall` —
        that would hang up unrelated live calls (patients on the line)."""
        for leg in (A, b_uuid):
            if not leg:
                continue
            try:
                api("uuid_kill %s" % leg, t=5)
            except Exception as e:  # noqa: BLE001
                print("  leg cleanup %s failed: %s" % (leg[:8], e),
                      flush=True)


    def until(marker=b"\n\n", t=15):
        s.settimeout(t)
        buf = b""
        while marker not in buf:
            c = s.recv(262144)
            if not c:
                raise RuntimeError("ESL closed")
            buf += c
        return buf


    def api(cmd, t=15):
        # ONE socket carries both the event stream and command replies, so
        # skip any event messages that land between the command and its
        # reply and return only the api/response body.
        s.sendall(("api %s\n\n" % cmd).encode())
        deadline = time.time() + t
        while time.time() < deadline:
            buf = until(marker=b"\n\n", t=deadline - time.time())
            head, _, rest = buf.partition(b"\n\n")
            ctype, cl = b"", 0
            for line in head.split(b"\n"):
                low = line.lower()
                if low.startswith(b"content-type:"):
                    ctype = line.split(b":", 1)[1].strip()
                if low.startswith(b"content-length:"):
                    cl = int(line.split(b":", 1)[1].strip() or 0)
            while len(rest) < cl:
                rest += s.recv(262144)
            if ctype == b"api/response":
                return rest[:cl]
            # stray event — drop it and keep waiting for the real reply
        raise RuntimeError("api timeout: %s" % cmd)


    until()  # greeting
    s.sendall(b"auth %s\n\n" % ESL_PWD.encode())
    assert b"+OK accepted" in until(), "auth failed"
    s.sendall(b"event plain CHANNEL_ANSWER CHANNEL_HANGUP "
              b"PLAYBACK_START PLAYBACK_STOP\n\n")
    until()

    print("== 1. originate loopback/4402 ==", flush=True)
    A = api("create_uuid").decode().strip()
    # The proven recipe: the A-leg holds a
    # LONG-playing app so the loopback pair stays up while the B-leg (4402)
    # answers and holds in a long sleep. NB: tone_stream://%(...);loops=-1
    # does NOT work as an originate &app — the nested paren in %(400,...)
    # breaks the originate app parse and the ';loops=-1' is lost, so the
    # tone plays once and the leg hangs up. silence_stream has no parens.
    # loopback legs are pre-answered, never emit CHANNEL_ANSWER, and die
    # instantly if parked as an originate app — park() on the B-leg tears
    # the pair down too (mod_loopback), so 4402 uses answer+sleep instead
    # of the real-call 4400 answer+park.
    # default_password=override silences the stock example 'global'
    # extension's sleep(10000) nag that would delay answer by 10 s.
    tone = "silence_stream://600000"
    s.sendall(("api originate {default_password=override,origination_uuid=%s}"
               "loopback/4402 &playback(%s)\n\n" % (A, tone)).encode())
    time.sleep(2.0)
    s.settimeout(1.5)
    try:
        while True:
            if not s.recv(262144):
                break
    except socket.timeout:
        pass

    raw = api("show channels as json", t=15)
    if b"{" not in raw:
        print("DEBUG raw=%r %r" % (raw[:200], A), flush=True)
    rows = json.loads(raw[raw.index(b"{"):].decode(errors="replace")
                         ).get("rows", [])
    b_uuid = None
    for c in rows:
        if c.get("uuid") != A and c.get("dest") in ("4402",):
            b_uuid = c.get("uuid")
    check("B-leg 4402 found", b_uuid is not None, "A=%s" % A[:8])
    if not b_uuid:
        kill_own_legs()
        s.close()
        return 1

    # ---- 2. runtime picks it up: POST /calls + stereo tape ----------------
    print("== 2. runtime attaches the call ==", flush=True)
    new_call = None
    deadline = time.time() + 30
    while time.time() < deadline:
        now = agent_calls()
        if (now - before):
            new_call = next(iter(now - before))
            break
        time.sleep(0.5)
    check("agent got a new call (POST /calls)", bool(new_call),
          "call_id=%s" % new_call)

    tap = os.path.join(WORKDIR, b_uuid[:12], "tap.wav")
    deadline = time.time() + 10
    while time.time() < deadline and not os.path.exists(tap):
        time.sleep(0.2)
    check("tap.wav exists (uuid_record stereo)", os.path.exists(tap),
          tap)

    time.sleep(1.5)  # let the header + first frames land
    try:
        right_rms, nch = tap_energy(tap, "right")
        left_rms, _ = tap_energy(tap, "left")
    except Exception as e:  # noqa: BLE001
        right_rms = left_rms = 0.0
        nch = 1
        print("  tap read failed: %s" % e, flush=True)
    check("tape is stereo (record_stereo)",
          nch == 2,
          "channels=%d" % nch)

    # ---- 3. greeting broadcast: RIGHT gains energy, LEFT stays quiet -------
    print("== 3. greeting playback reaches the leg ==", flush=True)
    got_speech = False
    deadline = time.time() + 150   # first render of TTS can be cold
    while time.time() < deadline:
        try:
            right_rms, _ = tap_energy(tap, "right")
            left_rms, _ = tap_energy(tap, "left")
        except Exception:  # noqa: BLE001
            time.sleep(1)
            continue
        if right_rms >= RMS_GATE:
            got_speech = True
            break
        time.sleep(1)
    check("greeting audio on RIGHT channel (played)", got_speech,
          "right_rms=%.0f" % right_rms)
    check("LEFT channel silent (no inbound on loopback)",
          left_rms < RMS_GATE, "left_rms=%.0f" % left_rms)

    status = http_get(RUNTIME_PORT, "/ready", 4)
    check("runtime tracks exactly this call (calls_active=1)",
          status.get("calls_active") == 1,
          "calls_active=%s" % status.get("calls_active"))

    # ---- 4. barge-in: uuid_break stops playback <= 300 ms ------------------
    print("== 4. barge-in latency ==", flush=True)
    t0 = time.time()
    r = api("uuid_break %s all" % b_uuid)
    stop_at = None
    deadline = time.time() + 3
    while time.time() < deadline and stop_at is None:
        try:
            buf = until(t=3)
        except socket.timeout:
            break
        if b"PLAYBACK_STOP" in buf:
            stop_at = time.time() - t0
    lat_ms = (stop_at or 99) * 1000
    check("PLAYBACK_STOP <= 300 ms after uuid_break",
          stop_at is not None and lat_ms * 0.001 <= BREAK_LATENCY,
          "latency=%.0f ms" % lat_ms)

    # ---- 5. hangup -> runtime finalizes the call ---------------------------
    print("== 5. hangup finalization ==", flush=True)
    kill_own_legs()
    gone = False
    deadline = time.time() + 10
    while time.time() < deadline:
        if new_call and new_call not in agent_calls():
            gone = True
            break
        time.sleep(0.5)
    check("call removed from agent (POST /calls/<id>/end)", bool(new_call) and gone)
    check("runtime workdir cleaned", not os.path.isdir(
        os.path.join(WORKDIR, b_uuid[:12])))

    s.close()
    print("", flush=True)
    failed = [n for n, st in checks if st == FAIL]
    for n, st in checks:
        print("  %-4s %s" % (st, n), flush=True)
    if failed:
        print("RESULT: FAIL (%s)" % ", ".join(failed), flush=True)
        return 1
    print("RESULT: PASS", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())