"""Offline regression tests for the ESL core: buffered framing (batches and
split bodies must never drop bytes), parsing of text/event-plain (fields in
the body, URL-encoded values), text/event-json bodies, and the full
EslClient round-trip against a scripted fake FreeSWITCH ESL server.

Run:  python3 -m unittest voice_runtime.test_esl_client -v
 or:  python3 voice_runtime/test_esl_client.py -v
"""
import json
import os
import socket
import sys
import threading
import time
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from esl_client import (  # noqa: E402
    EslStream, EslClient, parse_event, ESLProtocolError,
)


def _frame(headers, body=b""):
    """Build one raw ESL message (headers + optional body)."""
    head = "".join("%s: %s\n" % (k, v) for k, v in headers.items()).encode()
    return head + b"\n" + body  # single \n so caller decides the \n\n


def _command_reply(text):
    return (b"Content-Type: command/reply\nReply-Text: "
            + text.encode() + b"\n\n")


def _api_response(body):
    b = body.encode() if not isinstance(body, bytes) else body
    return (b"Content-Type: api/response\nContent-Length: "
            + str(len(b)).encode() + b"\n\n" + b)


def _plain_event(fields):
    body = "".join("%s: %s\n" % (k, v) for k, v in fields.items()).encode()
    return (b"Content-Type: text/event-plain\nContent-Length: "
            + str(len(body)).encode() + b"\n\n" + body)


def _json_event(obj):
    body = json.dumps(obj).encode()
    return (b"Content-Type: text/event-json\nContent-Length: "
            + str(len(body)).encode() + b"\n\n" + body)


UUID1 = "abc12345-0000-0000-0000-000000000001"


class EslStreamTests(unittest.TestCase):
    """EslStream framing: no byte ever dropped, even with batches."""

    def test_batched_messages_in_one_recv(self):
        a, b = socket.socketpair()
        try:
            stream = EslStream(a)
            msg1 = _plain_event({"Event-Name": "CHANNEL_ANSWER",
                                 "Unique-ID": UUID1})
            msg2 = _plain_event({"Event-Name": "PLAYBACK_STOP",
                                 "Unique-ID": UUID1})
            b.sendall(msg1 + msg2)  # ONE TCP segment, two messages
            h1, b1 = stream.read_message(timeout=2)
            h2, b2 = stream.read_message(timeout=2)
            self.assertEqual(h1["Content-Type"], "text/event-plain")
            self.assertIn(b"CHANNEL_ANSWER", b1)
            self.assertIn(b"PLAYBACK_STOP", b2)  # NOT dropped
        finally:
            a.close()
            b.close()

    def test_body_split_across_reads(self):
        a, b = socket.socketpair()
        try:
            stream = EslStream(a)
            body = ("Event-Name: CHANNEL_HANGUP\nUnique-ID: %s\n"
                    % UUID1).encode()
            head = (b"Content-Type: text/event-plain\nContent-Length: "
                    + str(len(body)).encode() + b"\n\n")
            b.sendall(head + body[:10])

            def send_rest():
                time.sleep(0.2)
                b.sendall(body[10:])
            threading.Thread(target=send_rest, daemon=True).start()

            h, b1 = stream.read_message(timeout=3)
            self.assertEqual(b1, body)
        finally:
            a.close()
            b.close()

    def test_headers_arriving_in_pieces(self):
        a, b = socket.socketpair()
        try:
            stream = EslStream(a)
            b.sendall(b"Content-Type: text/event-plain\nContent-Len")
            b.sendall(b"gth: 5\n\nHELLO")
            h, body = stream.read_message(timeout=2)
            self.assertEqual(h["Content-Type"], "text/event-plain")
            self.assertEqual(body, b"HELLO")
        finally:
            a.close()
            b.close()


class ParseEventTests(unittest.TestCase):
    """Field extraction from plain / json event bodies."""

    def test_plain_body_fields_are_extracted(self):
        headers = {"Content-Type": "text/event-plain"}
        body = ("Event-Name: CHANNEL_ANSWER\n"
                "Unique-ID: %s\n"
                "Caller-Destination-Number: 4400\n" % UUID1).encode()
        ev = parse_event(headers, body)
        self.assertEqual(ev["Event-Name"], "CHANNEL_ANSWER")
        self.assertEqual(ev["Unique-ID"], UUID1)
        self.assertEqual(ev["Caller-Destination-Number"], "4400")
        self.assertIn("_body", ev)

    def test_url_encoded_values_are_decoded(self):
        headers = {"Content-Type": "text/event-plain"}
        body = (b"Event-Name: CHANNEL_CREATE\n"
                b"FreeSWITCH-IPv6: %3A%3A1\n"
                b"Caller-Username: %D0%92%D0%B5%D1%80%D0%B0\n")
        ev = parse_event(headers, body)
        self.assertEqual(ev["FreeSWITCH-IPv6"], "::1")
        self.assertEqual(ev["Caller-Username"], "Вера")

    def test_json_event_body_is_merged(self):
        headers = {"Content-Type": "text/event-json"}
        ev = parse_event(headers, json.dumps(
            {"Event-Name": "CHANNEL_HANGUP", "Unique-ID": UUID1}).encode())
        self.assertEqual(ev["Event-Name"], "CHANNEL_HANGUP")
        self.assertEqual(ev["Unique-ID"], UUID1)

    def test_headers_preserved_on_top_level(self):
        ev = parse_event({"Content-Type": "text/event",
                          "Content-Length": "0"}, b"")
        self.assertEqual(ev["Content-Type"], "text/event")


class FakeEslServer(threading.Thread):
    """Scripted ESL endpoint: welcome/auth both connections, answer API
    commands on the first, and push a batch of events on the second."""

    def __init__(self, events_batch=b"", api_replies=None):
        super().__init__(daemon=True)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]
        self.host = "127.0.0.1"
        self.events_batch = events_batch
        self.api_replies = api_replies or {}
        self.received = []

    @staticmethod
    def _recv_line(c):
        buf = b""
        while b"\n\n" not in buf:
            chunk = c.recv(65536)
            if not chunk:
                return None
            buf += chunk
        return buf

    def run(self):
        self.sock.settimeout(10)
        try:
            # cmd connection must be served as soon as it is accepted —
            # the client blocks for the greeting BEFORE it opens the second
            # (event) socket.
            c1, _ = self.sock.accept()
            threading.Thread(target=self._cmd_conn, args=(c1,),
                             daemon=True).start()
            c2, _ = self.sock.accept()
            threading.Thread(target=self._event_conn, args=(c2,),
                             daemon=True).start()
        finally:
            self.sock.close()

    def _welcome(self, c):
        c.sendall(b"Content-Type: auth/request\nContent-Length: 0\n\n")
        auth = self._recv_line(c)
        if auth is None:
            return False
        self.received.append(auth.decode(errors="replace"))
        c.sendall(_command_reply("+OK accepted"))
        return True

    def _cmd_conn(self, c):
        try:
            if not self._welcome(c):
                return
            while True:
                msg = self._recv_line(c)
                if msg is None:
                    return
                first = msg.split(b"\n", 1)[0].decode(errors="replace")
                self.received.append(first)
                if first.startswith("api "):
                    text = first[4:].strip()
                    if text in self.api_replies:
                        c.sendall(_api_response(self.api_replies[text]))
                    else:
                        c.sendall(_api_response("+OK fake"))
                else:
                    c.sendall(_command_reply("-ERR unknown"))
        finally:
            c.close()

    def _event_conn(self, c):
        try:
            if not self._welcome(c):
                return
            sub = self._recv_line(c)
            if sub is None:
                return
            self.received.append(sub.decode(errors="replace"))
            c.sendall(_command_reply("+OK accepted"))
            if self.events_batch:
                # one sendall: the batch must survive a single recv on the
                # client side without any trailing message being dropped
                c.sendall(self.events_batch)
            time.sleep(4)  # keep open while the reader consumes the batch
        finally:
            c.close()


class EslClientTests(unittest.TestCase):
    BATCH = (
        _plain_event({"Event-Name": "CHANNEL_ANSWER",
                      "Unique-ID": UUID1,
                      "Caller-Destination-Number": "4400"})
        + _plain_event({"Event-Name": "PLAYBACK_STOP",
                        "Unique-ID": UUID1})
        + _plain_event({"Event-Name": "CHANNEL_CREATE",
                        "Unique-ID": UUID1,
                        "FreeSWITCH-IPv6": "%3A%3A1"})
        + _json_event({"Event-Name": "CHANNEL_HANGUP",
                       "Unique-ID": UUID1})
    )

    def _collect(self, client, n, timeout=5.0):
        events = []
        deadline = time.time() + timeout
        while len(events) < n and time.time() < deadline:
            ev = client.next_event(timeout=0.5)
            if ev:
                events.append(ev)
        return events

    def test_api_commands_get_replies(self):
        srv = FakeEslServer(api_replies={
            "show channels as json":
                '{"rows": [{"uuid": "u1", "dest": "4400", '
                '"name": "Softphone", "direction": "inbound"}]}',
            "status": "+OK fake",
        })
        srv.start()
        client = EslClient(srv.host, srv.port, "secret")
        try:
            self.assertEqual(client.api("status"), "+OK fake")
            raw = client.api("show channels as json")
            self.assertTrue(raw.lstrip().startswith("{"))
            self.assertIn("u1", raw)
            # uuid_* must go through the api wrapper (server logs 'api ...')
            self.assertEqual(client.uuid_record_start(
                UUID1, "/tmp/t.wav"), "+OK fake")
            self.assertTrue(any(
                r.startswith("api uuid_record ") for r in srv.received))
        finally:
            client.close()
            srv.join(timeout=2)

    def test_all_events_from_batch_are_delivered(self):
        srv = FakeEslServer(events_batch=self.BATCH)
        srv.start()
        client = EslClient(srv.host, srv.port, "secret")
        try:
            events = self._collect(client, 4)
            names = [ev.get("Event-Name") for ev in events]
            self.assertEqual(names, ["CHANNEL_ANSWER", "PLAYBACK_STOP",
                                     "CHANNEL_CREATE", "CHANNEL_HANGUP"])
            for ev in events:
                self.assertEqual(ev.get("Unique-ID"), UUID1)
            ans = next(e for e in events
                       if e["Event-Name"] == "CHANNEL_ANSWER")
            self.assertEqual(ans["Caller-Destination-Number"], "4400")
            create = next(e for e in events
                          if e["Event-Name"] == "CHANNEL_CREATE")
            self.assertEqual(create["FreeSWITCH-IPv6"], "::1")
        finally:
            client.close()
            srv.join(timeout=2)

    def test_socket_close_emits_disconnect(self):
        srv = FakeEslServer(events_batch=_plain_event(
            {"Event-Name": "CHANNEL_ANSWER", "Unique-ID": UUID1}))
        srv.start()
        client = EslClient(srv.host, srv.port, "secret")
        try:
            events = self._collect(client, 2, timeout=8)  # batch + disconnect
            # P3 (2026-08-29): the disconnect must carry Event-Name so the
            # runtime can detect the drop (it watches ev["Event-Name"]) —
            # Content-Type alone was invisible and left esl_ok=True.
            disconnects = [ev for ev in events
                           if ev.get("Event-Name") == "disconnect"]
            self.assertEqual(len(disconnects), 1,
                             "expected exactly one Event-Name=disconnect")
        finally:
            client.close()
            srv.join(timeout=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)