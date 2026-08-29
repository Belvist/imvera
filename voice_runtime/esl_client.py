"""Minimal but correct FreeSWITCH Event Socket client (inbound side).

Two connections, deliberately split:
  * command connection — a single thread-safe channel for `api` / `uuid_*`
    commands. Replies are the ONLY messages on this connection, so a command
    reader never blocks waiting for an unrelated event.
  * event connection  — one subscriber feeding parsed events into a queue;
    the runtime loop consumes it with a timeout.

Fixes over the step-5 POC (`esl_stream.py`) and the first runtime client:
  * no `time.sleep(0.15)` drain hack — every message is read to its
    Content-Length boundary, so replies are immediate;
  * one client can serve many calls (command lock + shared event queue);
  * event parsing is done here, once, instead of ad-hoc per consumer;
  * **buffered framing** — this FreeSWITCH build sends several ESL messages
    concatenated in one TCP segment and may split a body across reads;
    ``EslStream`` keeps a persistent buffer so trailing bytes of a batch are
    NEVER dropped (the old parser silently lost them, which made
    PLAYBACK_STOP / CHANNEL_HANGUP / DESTROY disappear and wedged sessions);
  * **plain events are parsed** — FS `text/event-plain` messages carry every
    event field in the BODY as `K: V` lines with URL-encoded values; they are
    merged into the event dict (plus `text/event-json` bodies) so consumers
    read ``ev["Event-Name"]``, ``ev["Unique-ID"]``, ... directly.
"""
import argparse
import json
import os
import queue
import socket
import threading
import time
from urllib.parse import unquote

ESL_HOST = os.environ.get("MOSS_ESL_HOST", "127.0.0.1")
ESL_PORT = int(os.environ.get("MOSS_ESL_PORT", "8021"))
# SECURITY (2026-08-29): the FreeSWITCH ESL password is a live credential
# and must NEVER have a hardcoded default (it previously shipped as
# d7f78342... in the repo and leaked into release archives). The operator
# provides it via MOSS_ESL_PASSWORD; an empty password fails authentication
# fast instead of silently using a stale default.
ESL_PASSWORD = os.environ.get("MOSS_ESL_PASSWORD", "")
EVENT_TYPES = ("CHANNEL_ANSWER CHANNEL_HANGUP DESTROY "
               "PLAYBACK_START PLAYBACK_STOP RECORD_START RECORD_STOP")


class ESLProtocolError(RuntimeError):
    pass


class EslStream:
    """Buffered reader for ONE ESL connection.

    ESL is a length-prefixed protocol, but on the FreeSWITCH build this
    project targets messages arrive BATCHED (several per TCP segment) and a
    body may be split across reads. A persistent buffer is therefore
    essential: every byte consumed from the socket is either returned as part
    of the current message or kept for the next one — nothing is dropped.
    """

    def __init__(self, sock):
        self._sock = sock
        self._buf = b""
        self._closed = False

    def _fill(self, timeout):
        if timeout is not None:
            self._sock.settimeout(timeout)
        chunk = self._sock.recv(65536)
        if not chunk:
            raise ESLProtocolError("ESL connection closed")
        self._buf += chunk

    def read_message(self, timeout=None):
        """Read exactly ONE message → ``(headers_dict, body_bytes)``.

        Reads until the header block (terminated by ``\\n\\n``) is complete,
        then until ``Content-Length`` body bytes are available. Any bytes
        beyond that boundary stay buffered for the next call.
        """
        if timeout is not None:
            self._sock.settimeout(timeout)
        while b"\n\n" not in self._buf:
            self._fill(timeout)
        head, _, self._buf = self._buf.partition(b"\n\n")
        headers = {}
        for line in head.split(b"\n"):
            if b":" not in line:
                continue
            k, _, v = line.partition(b":")
            headers[k.strip().decode(errors="replace")] = (
                v.strip().decode(errors="replace"))
        clen = int(headers.get("Content-Length") or 0)
        # NOTE: the fill loop must grow self._buf (which holds the body of
        # this message — and possibly the NEXT messages too), otherwise a
        # body split across reads would never complete.
        while len(self._buf) < clen:
            self._fill(timeout)
        body, self._buf = self._buf[:clen], self._buf[clen:]
        return headers, body


def parse_event(headers, body):
    """Build a single event dict from a raw message.

    On this FS build, plain events carry every event field in the BODY as
    ``K: V`` lines (values URL-encoded) and json events carry a JSON object.
    Those are merged on top of the transport headers so consumers can read
    ``ev["Event-Name"]`` etc. directly. The raw body is kept in ``ev["_body"]``.
    """
    ev = dict(headers)
    ctype = headers.get("Content-Type", "").split(";")[0].strip()
    if ctype == "text/event-json":
        try:
            ev.update(json.loads(body.decode(errors="replace")))
        except (ValueError, TypeError):
            pass
    elif ctype.startswith("text/event"):
        text = body.decode(errors="replace")
        for line in text.split("\n"):
            if ":" not in line:
                continue
            k, _, v = line.partition(":")
            key = k.strip()
            if not key:
                continue
            ev[key] = unquote(v.strip())
    ev["_body"] = body.decode(errors="replace")
    return ev


class EslClient:
    def __init__(self, host=ESL_HOST, port=ESL_PORT, password=ESL_PASSWORD,
                 event_types=EVENT_TYPES, events=None):
        self.host = host
        self.port = port
        self.password = password
        self.events = events or queue.Queue(maxsize=2000)
        self._cmd_lock = threading.Lock()
        self._cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._cmd_sock.settimeout(20)
        self._cmd_sock.connect((host, port))
        self._cmd_stream = EslStream(self._cmd_sock)
        self._auth(self._cmd_sock, self._cmd_stream)

        self._ev_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._ev_sock.settimeout(20)
        self._ev_sock.connect((host, port))
        self._ev_stream = EslStream(self._ev_sock)
        self._auth(self._ev_sock, self._ev_stream)
        self._subscribe()
        self._reader = threading.Thread(target=self._read_events,
                                        name="esl-events", daemon=True)
        self._reader.start()

    # ---- low level ------------------------------------------------------
    @staticmethod
    def _msg_text(headers, body):
        """Full message text: headers (Reply-Text etc.) + body. FS 1.11 puts
        "+OK accepted" in the Reply-Text HEADER (empty body) and sends
        "auth/request" as the greeting's Content-Type — never inspect only
        the body like the step-5 POC did."""
        return body.decode(errors="replace") + "\n" + \
            "\n".join("%s: %s" % (k, v) for k, v in headers.items())

    def _auth(self, sock, stream):
        greeting = stream.read_message(timeout=10)
        if "auth/request" not in self._msg_text(*greeting):
            raise ESLProtocolError(
                "unexpected greeting: %r" % greeting[1][:80])
        sock.sendall(b"auth %b\n\n" % self.password.encode())
        ack = stream.read_message(timeout=10)
        if "+OK accepted" not in self._msg_text(*ack):
            raise ESLProtocolError(
                "auth failed: %r" % self._msg_text(*ack)[:80])

    def _subscribe(self):
        self._ev_sock.sendall(("event plain %s\n\n" % EVENT_TYPES).encode())
        # The +OK reply arrives before the event stream starts. Any event
        # bytes that arrived in the same TCP segment stay buffered in
        # self._ev_stream and are picked up by _read_events.
        self._ev_stream.read_message(timeout=10)

    def _read_events(self):
        while True:
            try:
                headers, body = self._ev_stream.read_message(timeout=60)
            except ESLProtocolError:
                # FIX (2026-08-29, FIXES_PLAN P3): the disconnect event must
                # carry Event-Name=disconnect or the runtime can never see
                # the drop (it watches ev["Event-Name"]) and /ready keeps
                # reporting healthy while the whole realtime loop is deaf.
                self.events.put(parse_event(
                    {"Content-Type": "connection/disconnect",
                     "Event-Name": "disconnect"}, b""))
                return
            except socket.timeout:
                continue
            ctype = headers.get("Content-Type", "").split(";")[0].strip()
            if ctype == "text/disconnect-notice" or \
                    headers.get("Event-Subclass") == "disconnect":
                ev = parse_event(headers, body)
                ev.setdefault("Event-Name", "disconnect")
                self.events.put(ev)
                return
            if ctype not in ("text/event", "text/event-plain",
                             "text/event-json"):
                continue
            ev = parse_event(headers, body)
            # NO-DROP QUEUE (2026-08-29, FIXES_PLAN P3): dropping events at
            # maxsize once lost a CHANNEL_HANGUP/DESTROY and left a zombie
            # session recording into a dead channel for up to 2h (the
            # channel scan is only a backstop). Block with backpressure
            # instead — the runtime drains every tick, and if it ever
            # falls behind the socket reader stalling is the correct signal
            # instead of silently losing lifecycle events.
            while True:
                try:
                    self.events.put(ev, timeout=1.0)
                    break
                except queue.Full:
                    continue

    # ---- commands (thread-safe) ------------------------------------------
    def _cmd(self, command, timeout=20):
        """Send a raw command on the command connection, return reply text.

        FS 1.11 replies to commands with the result in the Reply-Text
        HEADER (body stays empty); api/response messages carry it in the
        body. Return whichever is non-empty so callers see +OK/-ERR."""
        with self._cmd_lock:
            self._cmd_sock.sendall(command)
            headers, body = self._cmd_stream.read_message(timeout=timeout)
        body_txt = body.decode(errors="replace").strip()
        if body_txt:
            return body_txt
        return (headers.get("Reply-Text") or "").strip()

    def api(self, cmd, timeout=20):
        return self._cmd(b"api %b\n\n" % cmd.encode(), timeout=timeout)

    def api_break(self, uuid):
        return self.api("uuid_break %s all" % uuid)

    def uuid_setvar(self, uuid, name, value):
        # uuid_* are API commands (mod_commands): on the ESL inbound socket
        # they MUST be invoked as 'api uuid_...' — sent bare, FS replies
        # '-ERR command not found' (fs_cli hides this by wrapping).
        return self.api("uuid_setvar %s %s %s" % (uuid, name, value))

    def uuid_record_start(self, uuid, path):
        return self.api("uuid_record %s start %s" % (uuid, path))

    def uuid_record_stop(self, uuid):
        try:
            return self.api("uuid_record %s stop" % uuid)
        except (ESLProtocolError, OSError):
            return ""

    def play(self, uuid, path):
        """Play a file on the channel's audio leg (fire-and-forget async)."""
        return self.api("uuid_broadcast %s playback::%s aleg" % (uuid, path))

    def next_event(self, timeout=None):
        try:
            return self.events.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self):
        try:
            self._cmd_sock.close()
        except OSError:
            pass
        try:
            self._ev_sock.close()
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default=ESL_HOST)
    ap.add_argument("--port", type=int, default=ESL_PORT)
    ap.add_argument("--seconds", type=float, default=None)
    args = ap.parse_args()
    client = EslClient(args.host, args.port, ESL_PASSWORD)
    print("[esl] connected, waiting events...", flush=True)
    deadline = time.time() + args.seconds if args.seconds else None
    try:
        while deadline is None or time.time() < deadline:
            ev = client.next_event(timeout=1)
            if ev:
                print(ev.get("Event-Name"), ev.get("Unique-ID", "")[:8],
                      ev.get("Caller-Destination-Number", ""))
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())