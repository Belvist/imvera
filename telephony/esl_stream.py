#!/usr/bin/env python3
"""MossVoice step-5 / LINE-STREAMING: ESL media bridge.

Connects to FreeSWITCH's event socket as an inbound listener, and for each
answered call attaches a `uuid_record` (live audio tap — audio is available
WHILE the call is running, not only after a silence-detected turn file). The
growing WAV is tail-read in real time and fed to a StreamingSTT, which
transcribes in non-overlapping hops so interim text arrives during the call.

This is the transport backbone of true streaming STT. It runs PARALLEL to the
existing record->WAV->HTTP Lua path; replacing that path with this stream as
the primary input is a follow-up step, done with a live (non-loopback) media
call so accuracy/latency are real.

Design
------
* ``LiveWavReader`` tail-reads a `uuid_record` output WAV, returning the NEW
  int16 PCM samples since the last read. `uuid_record` writes a standard WAV
  with a fixed 44-byte header, so we only ever read bytes after it.
* ``StreamingSttBridge`` feeds those samples into ``StreamingSTT`` on a
  cadence (median over the last HOP window) and calls ``finish()`` on hangup
  for the authoritative whole-turn transcript.
* ``EslBridge`` is the event loop: subscribe CHANNEL_ANSWER, attach the
  record, and on CHANNEL_HANGUP stop and finalize.

No dialplan change is required: ES is a consumer-side listener. ``uuid_record``
is only meaningful on a channel that actually transports media (a real caller,
not a silent loopback), which is why live verification needs a real SIP leg.
"""

import argparse
import os
import re
import socket
import struct
import sys
import time

from core.events import StreamingSTT  # type: ignore
from adapters.stt import STTEngine   # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

ESL_HOST = os.environ.get("MOSS_ESL_HOST", "127.0.0.1")
ESL_PORT = int(os.environ.get("MOSS_ESL_PORT", "8021"))
# Hardened 2026-08-21 after port audit: ESL was reachable on all interfaces
# with the default ClueCon password. FS event_socket.conf.xml now binds
# 127.0.0.1 + strong password; keep them in sync via MOSS_ESL_PASSWORD.
ESL_PASSWORD = os.environ.get("MOSS_ESL_PASSWORD",
                              "d7f78342b2e6de534defacd372ed9f89")
SAMPLE_RATE = 16000
HOP_SECONDS = 3.0      # must match StreamingSTT default; keep explicit
FEED_INTERVAL = 0.25   # tail-read cadence (seconds) - 4 reads/sec
PCM_CHUNK = 3200       # ~0.2 s of 16k mono 16-bit


class ESLProtocolError(RuntimeError):
    pass


class EslConnection:
    """Minimal FreeSWITCH event-socket client (inbound side).

    Framing: each reply/event is headers terminated by a blank line, then an
    optional Content-Length binary body. We accept the simple framing used for
    the commands we issue; events are consumed whole.
    """

    def __init__(self, host=ESL_HOST, port=ESL_PORT, password=ESL_PASSWORD):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(60)
        self._conn = self._sock  # keep name stable for callers
        self._sock.connect((host, port))
        self._auth(password)

    def _recv_until(self, marker=b"\n\n"):
        buf = b""
        while marker not in buf:
            chunk = self._conn.recv(8192)
            if not chunk:
                raise ESLProtocolError("ESL closed while reading headers")
            buf += chunk
        return buf

    def _auth(self, password):
        greeting = self._recv_until()
        if b"auth/request" not in greeting:
            raise ESLProtocolError("unexpected greeting: %r" % greeting[:80])
        self._conn.sendall(b"auth %b\n\n" % password.encode())
        ack = self._recv_until()
        if b"+OK accepted" not in ack:
            raise ESLProtocolError("auth failed: %r" % ack[:80])

    def command(self, cmd):
        """Send a command, return the reply headers bytes (single message)."""
        self._conn.sendall(cmd)
        time.sleep(0.15)  # FS replies quickly; keep small drain gap
        return self._recv_until()

    def send(self, data):
        self._conn.sendall(data)

    def recv_headers(self):
        return self._recv_until()

    def close(self):
        try:
            self._conn.close()
        except Exception:  # noqa: BLE001
            pass


def _parse_event(body):
    """Parse ESL header block into a dict (values are raw bytes decoded)."""
    out = {}
    for line in body.split(b"\n"):
        if line.startswith(b"Content-Type:"):
            out["_type"] = line.split(b":", 1)[1].strip().decode()
            continue
        if b":" in line:
            k, v = line.split(b":", 1)
            out[k.strip().decode()] = v.strip().decode()
    return out


class LiveWavReader:
    """Tail-read a growing WAV written by ``uuid_record``.

    Only returns PCM after the 44-byte header; returns int16 mono samples
    (LEFT channel when the recording is stereo — record_stereo) for the NEW
    region since the last call. Safe for a single reader thread.
    """

    def __init__(self, path, sample_rate=SAMPLE_RATE):
        self.path = path
        self.rate = sample_rate
        self._pos = 0
        self._header_seen = False
        self._channels = 1

    def read_new(self):
        try:
            size = os.path.getsize(self.path)
        except OSError:
            return []
        if size <= 0:
            return []
        # First read: skip the WAV header (44 bytes for standard PCM) and
        # detect the channel count (offset 22 in a standard fmt chunk).
        if not self._header_seen:
            if size < 44:
                return []
            with open(self.path, "rb") as f:
                head = f.read(44)
            try:
                self._channels = struct.unpack("<H", head[22:24])[0] or 1
            except struct.error:
                self._channels = 1
            self._header_seen = True
            self._pos = 44
        data = None
        with open(self.path, "rb") as f:
            f.seek(self._pos)
            data = f.read(size - self._pos)
        self._pos = size
        if not data:
            return []
        # int16 frames; drop any trailing partial frame (safety)
        frame = 2 * self._channels
        data = data[: len(data) - (len(data) % frame)]
        vals = struct.unpack("<%dh" % (len(data) // 2), data)
        if self._channels == 2:
            # record_stereo: LEFT = caller, RIGHT = Vera's playback
            vals = vals[0::2]
        return list(vals)


class StreamingSttBridge:
    """Feed live PCM into StreamingSTT; emit interim, finalize on finish."""

    def __init__(self, engine=None, sample_rate=SAMPLE_RATE, cid="esl"):
        self.engine = engine or STTEngine()
        self.sstt = StreamingSTT(
            self.engine, sample_rate=sample_rate, hop_seconds=HOP_SECONDS
        )
        self.cid = cid
        self.interim = ""

    def feed(self, samples):
        if not samples:
            return
        hop, interim = self.sstt.feed(samples)
        self.interim = interim
        if hop:
            print("[esl:%s] interim: %s" % (self.cid, hop), flush=True)

    def finalize(self):
        text = self.sstt.finish()
        print("[esl:%s] DONE transcript: %r" % (self.cid, text), flush=True)
        return text


class EslBridge:
    """Event loop: for each answered call attach a live record + stream STT."""

    def __init__(self, conn, out_dir=None):
        self.conn = conn
        self.out_dir = out_dir or "/tmp/mossvoice"
        os.makedirs(self.out_dir, exist_ok=True)

    def _attach(self, uuid, cid):
        target = os.path.join(self.out_dir, "esl_%s.wav" % cid)
        # record_stereo: LEFT = caller (read stream), RIGHT = what we play
        # (Vera). Without this, uuid_record mixes both directions and the
        # STT bridge would transcribe Vera's own playback as user speech
        # (same bug as the chunked path, fixed 2026-08-22).
        self.conn.command(b"uuid_setvar %b record_stereo true\n\n" % uuid.encode())
        # start live tap; reply is the next message after the command
        self.conn.command(
            b"uuid_record %b start %b\n\n" % (uuid.encode(), target.encode())
        )
        return target

    def run(self, seconds=None):
        deadline = (time.time() + seconds) if seconds else None
        while True:
            if deadline and time.time() > deadline:
                break
            try:
                msg = self.conn.recv_headers()
            except ESLProtocolError:
                print("[esl] connection closed", file=sys.stderr)
                break
            ev = _parse_event(msg)
            etype = ev.get("_type", "")
            if "CHANNEL_ANSWER" in etype:
                uuid = ev.get("Unique-ID")
                dest = ev.get("Caller-Destination-Number", "")
                if not uuid:
                    continue
                print("[esl] ANSWER uuid=%s dest=%s" % (uuid, dest), flush=True)
                cid = uuid[:8]
                target = self._attach(uuid, cid)
                bridge = StreamingSttBridge(cid=cid)
                reader = LiveWavReader(target)
                self._consume_until_hangup(uuid, bridge, reader)
            elif "CHANNEL_HANGUP" in etype:
                print("[esl] HANGUP", flush=True)

    def _consume_until_hangup(self, uuid, bridge, reader):
        """Read live audio and feed STT until the channel hangs up."""
        start = time.time()
        while True:
            try:
                msg = self.conn.recv_headers()
            except (ESLProtocolError, socket.timeout):
                # channel likely gone or idle; try reading a final slice
                bridge.feed(reader.read_new()[:PCM_CHUNK])
                bridge.finalize()
                return
            # drain any events while we sample audio
            ev = _parse_event(msg)
            if "CHANNEL_HANGUP" in ev.get("_type", ""):
                bridge.feed(reader.read_new()[:PCM_CHUNK])
                bridge.finalize()
                print("[esl] %s finalized (%.1fs)" % (bridge.cid,
                                                       time.time() - start),
                      flush=True)
                # stop this channel's record
                try:
                    self.conn.command(b"uuid_record %b stop\n\n" % uuid.encode())
                except Exception:  # noqa: BLE001
                    pass
                return
            # read a window of newly-written audio and feed it
            samples = reader.read_new()[:PCM_CHUNK]
            if samples:
                bridge.feed(samples)


def main():
    ap = argparse.ArgumentParser(description="FreeSWITCH ESL streaming-STT bridge")
    ap.add_argument("--host", default=ESL_HOST)
    ap.add_argument("--port", type=int, default=ESL_PORT)
    ap.add_argument("--out-dir", default="/tmp/mossvoice")
    ap.add_argument("--seconds", type=float, default=None,
                    help="run for this many seconds, then exit")
    ap.add_argument("--no-stt", action="store_true",
                    help="attach live recording only, skip transcription")
    args = ap.parse_args()

    conn = EslConnection(args.host, args.port, ESL_PASSWORD)
    conn.command(b"event plain CHANNEL_ANSWER CHANNEL_HANGUP\n\n")
    print("[esl] connected to %s:%d" % (args.host, args.port), flush=True)

    try:
        if args.no_stt and args.seconds is None:
            args.seconds = 120
        EslBridge(conn, args.out_dir).run(seconds=args.seconds)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())