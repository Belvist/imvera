"""Phase 3: Incident Engine + real outbox delivery drills (real Postgres).

Invariant under test (the user's product chain):

    call -> RED verdict -> durable incident -> Telegram down -> fallback
    -> family ACK -> terminal state -> full audit

Everything survives restarts, replayed webhooks and channel failures.
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

from adapters.pg import PgStore  # noqa: E402
from core.migrate import apply_migrations  # noqa: E402
from core.incidents import IncidentEngine  # noqa: E402
from core.delivery import DeliveryRouter  # noqa: E402

_TABLES = [
    "dialogue_answers", "dialogue_turns", "call_results", "call_attempts",
    "call_sessions", "provider_events", "outbox_messages", "incidents",
    "incident_actions", "consents", "person_memory", "audit_log",
]


class ScriptedChannel:
    """A channel that plays back a script of (ok, detail) results."""
    name = "telegram"

    def __init__(self, name, script):
        self.name = name
        self.script = list(script)

    def send(self, contact, text):
        return self.script.pop(0) if self.script else (False, "scripted:out")


def _engine(pg, script):
    router = DeliveryRouter([
        ScriptedChannel("telegram", script.get("telegram", [])),
        ScriptedChannel("sms", script.get("sms", [])),
        ScriptedChannel("call", script.get("call", [])),
    ])
    return IncidentEngine(pg, router)


def _open(engine, call_id="c-1", contacts=None, notes=None):
    engine.pg._exec(
        f"INSERT INTO call_sessions (call_id) VALUES ('{call_id}') "
        f"ON CONFLICT DO NOTHING")
    return engine.maybe_open(
        call_id, "alert", notes=notes or ["плохо"],
        contacts=contacts or {"telegram": "tg-1", "sms": "+7999",
                              "call": "+7999"})


@unittest.skipUnless(PG_URL, "MOSS_PG_URL not set (offline suite)")
class IncidentDrillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pg = PgStore(url=PG_URL)
        apply_migrations(PG_URL)

    def setUp(self):
        for t in _TABLES:
            self.pg._exec(f"TRUNCATE {t} CASCADE")
        self.pg._exec("ALTER SEQUENCE incident_actions_id_seq RESTART WITH 1")

    def _audit_actions(self, incident_id):
        return [r["action"] for r in self.pg._exec(
            "SELECT action FROM audit_log WHERE entity='incident' "
            "AND entity_id = %s ORDER BY id", (incident_id,), fetch="all")]

    # ------------------------------------------------------------------ #
    def test_red_verdict_opens_incident_with_ordered_plan(self):
        eng = _engine(self.pg, {})
        inc_id = _open(eng)
        self.assertIsNotNone(inc_id)
        self.assertEqual(self.pg.get_incident(inc_id)["status"], "open")
        acts = self.pg.actions_for(inc_id)
        self.assertEqual([a["channel"] for a in acts],
                         ["telegram", "sms", "call"])
        self.assertEqual([a["status"] for a in acts],
                         ["queued", "queued", "queued"])
        # notifier is enqueued (dedup) for the first action
        n = self.pg._exec(
            "SELECT count(*) FROM outbox_messages WHERE topic='incident.notify'",
            fetch="val")
        self.assertEqual(n, 1)
        # non-RED verdict never opens an incident
        self.assertIsNone(eng.maybe_open("c-2", "ok"))
        self.assertIsNone(eng.maybe_open("c-3", "attention"))

    def test_telegram_down_fallback_to_sms_ack_resolved(self):
        eng = _engine(self.pg, {"telegram": [(False, "tg down")],
                                "sms": [(True, "delivered")]})
        inc_id = _open(eng)
        acts = self.pg.actions_for(inc_id)
        self.assertEqual(eng.deliver(
            {"incident_id": inc_id, "action_id": acts[0]["id"]}), True)
        self.assertEqual(self.pg.get_action(acts[0]["id"])["status"], "failed")
        # fallback enqueued for sms (dedup incident:<id>:sms-action)
        self.assertEqual(eng.deliver(
            {"incident_id": inc_id, "action_id": acts[1]["id"]}), True)
        self.assertEqual(self.pg.get_action(acts[1]["id"])["status"], "sent")
        self.assertEqual(eng.ack(inc_id, "сын",
                                 action_id=acts[1]["id"], note="еду"), True)
        self.assertEqual(eng.resolve(inc_id, "сын", "всё ок"), True)
        inc = self.pg.get_incident(inc_id)
        self.assertEqual(inc["status"], "resolved")
        self.assertIsNotNone(inc["resolved_at"])
        # the confirming action is confirmed
        self.assertEqual(self.pg.get_action(acts[1]["id"])["status"],
                         "confirmed")
        # full audit trail
        self.assertEqual(self._audit_actions(inc_id), [
            "incident.opened",
            "incident.notify.failed",
            "incident.notify.sent",
            "incident.ack",
            "incident.checking",
            "incident.resolved",
        ])

    def test_ack_before_deadline_resolves_without_escalation(self):
        eng = _engine(self.pg, {"telegram": [(True, "ok")]})
        inc_id = _open(eng, contacts={"telegram": "tg-1"})
        acts = self.pg.actions_for(inc_id)
        eng.deliver({"incident_id": inc_id, "action_id": acts[0]["id"]})
        eng.ack(inc_id, "дочь", action_id=acts[0]["id"])
        eng.resolve(inc_id, "дочь", "ложная")
        inc = self.pg.get_incident(inc_id)
        self.assertEqual(inc["status"], "resolved")
        self.assertEqual(inc["escalation_level"], 0)

    def test_no_ack_within_deadline_escalates(self):
        eng = _engine(self.pg, {"telegram": [(True, "ok")]})
        inc_id = _open(eng, contacts={"telegram": "tg-1", "sms": "+7999"})
        acts = self.pg.actions_for(inc_id)
        eng.deliver({"incident_id": inc_id, "action_id": acts[0]["id"]})
        self.assertEqual(self.pg.get_action(acts[0]["id"])["status"], "sent")
        # telegram sent but family did NOT ack; ack deadline passed
        self.pg._exec(
            "UPDATE incidents SET opened_at = now() - interval '300 seconds' "
            "WHERE id = %s", (inc_id,))
        self.assertEqual(eng.tick(), 1)
        inc = self.pg.get_incident(inc_id)
        self.assertEqual(inc["escalation_level"], 1)
        # escalation moved forward to sms (new dedup key, new notifier)
        n = self.pg._exec(
            "SELECT count(*) FROM outbox_messages "
            "WHERE topic='incident.notify' AND dedup_key LIKE %s",
            (f"incident:{inc_id}:%",), fetch="val")
        self.assertEqual(n, 2)  # original + escalation
        sms = self.pg.next_queued_action(inc_id)
        self.assertEqual(sms["channel"], "sms")

    def test_double_notify_never_double_sends(self):
        eng = _engine(self.pg, {"telegram": [(True, "ok")]})
        inc_id = _open(eng, contacts={"telegram": "tg-1"})
        acts = self.pg.actions_for(inc_id)
        self.assertEqual(eng.deliver(
            {"incident_id": inc_id, "action_id": acts[0]["id"]}), True)
        # replay / duplicate outbox message
        self.assertEqual(eng.deliver(
            {"incident_id": inc_id, "action_id": acts[0]["id"]}), True)
        sent = self.pg._exec(
            "SELECT count(*) FROM incident_actions WHERE status='sent'",
            fetch="val")
        self.assertEqual(sent, 1)

    def test_restart_reconcile_redelivers_pending(self):
        # crash between enqueue and delivery: notifier pending, action queued
        eng1 = _engine(self.pg, {"telegram": [(True, "ok")]})
        inc_id = _open(eng1, contacts={"telegram": "tg-1"})
        pending = self.pg._exec(
            "SELECT count(*) FROM outbox_messages WHERE status='pending' "
            "AND topic='incident.notify'", fetch="val")
        self.assertEqual(pending, 1)
        # 'restart': fresh engine + worker delivers the pending notifier
        eng2 = _engine(self.pg, {"telegram": [(True, "ok")]})
        claimed = eng2.pg.claim_batch(worker_id="restart")
        self.assertEqual(len(claimed), 1)
        for row in claimed:
            self.assertEqual(eng2.deliver(row["payload"]), True)
        sent = self.pg._exec(
            "SELECT count(*) FROM incident_actions WHERE status='sent'",
            fetch="val")
        self.assertEqual(sent, 1)
        self.assertEqual(
            self.pg.get_incident(inc_id)["status"], "open")

    def test_false_alarm_terminal_state(self):
        eng = _engine(self.pg, {})
        inc_id = _open(eng)
        self.assertEqual(eng.false_alarm(inc_id, "оператор", "ложный"), True)
        self.assertEqual(self.pg.get_incident(inc_id)["status"], "false_alarm")
        # delivery on a terminal incident is a no-op
        self.assertEqual(eng.deliver(
            {"incident_id": inc_id, "action_id": 1}), True)

    def test_out_of_channels_escalates(self):
        eng = _engine(self.pg, {"telegram": [(False, "down")],
                                "sms": [(False, "down")],
                                "call": [(False, "down")]})
        inc_id = _open(eng)
        acts = self.pg.actions_for(inc_id)
        for a in acts:
            eng.deliver({"incident_id": inc_id, "action_id": a["id"]})
        inc = self.pg.get_incident(inc_id)
        self.assertEqual(inc["escalation_level"], 1)
        self.assertEqual(inc["status"], "open")

    def test_serve_wires_call_result_to_incident(self):
        """end_call of a RED call -> call.result outbox -> _dispatch_outbox
        -> durable incident (full wiring, no direct engine calls)."""
        os.environ["MOSS_NO_WARMUP"] = "1"
        from test_data_core import _FakeSilentSTT, _FakeTTS, _tmp_wav
        from conftest_or_paths import SAMPLE_REF
        from core.orchestrator import Serve

        class _Args:
            refs = [SAMPLE_REF]
            tts_port_file = None
            tts_port = None
            inference_steps = 6
            no_style = False
            outdir = os.path.join(_HERE, "_tmp_inc_calls")
            tts_host = None
            tmpdir = "/tmp/mossvoice_turns"

        serve = Serve(_Args())
        serve.stt = _FakeSilentSTT()
        serve.tts = _FakeTTS()
        try:
            cid = serve.new_call(caller_id="mom1")
            ctx = serve.get_call(cid)
            # force a RED verdict (agent.status feeds outcome)
            ctx.agent.status = "alert"
            ctx.agent.notes = ["плохое самочувствие"]
            done = serve.end_call(cid)
            self.assertEqual(done["outcome"]["status"], "alert")
            # drive the real worker: claim call.result -> dispatch -> incident
            claimed, delivered = serve.outbox.run_once()
            self.assertGreaterEqual(claimed, 1)
            incs = serve.incidents.pg.list_incidents()
            self.assertEqual(len(incs), 1)
            self.assertEqual(incs[0]["status"], "open")
            self.assertEqual(incs[0]["call_id"], cid)
            acts = serve.incidents.pg.actions_for(incs[0]["id"])
            self.assertGreaterEqual(len(acts), 1)
        finally:
            if serve.outbox is not None:
                serve.outbox.stop()
            serve.pg.close()

    def test_http_ack_route(self):
        """POST /incidents/<id>/ack over HTTP moves open -> checking."""
        from conftest_or_paths import SAMPLE_REF
        from core.orchestrator import Serve
        from legacy.call_agent_http import Handler, QuietHTTPServer

        class _Args:
            refs = [SAMPLE_REF]
            tts_port_file = None
            tts_port = None
            inference_steps = 6
            no_style = False
            outdir = os.path.join(_HERE, "_tmp_inc_http")
            tts_host = None
            tmpdir = "/tmp/mossvoice_turns"

        serve = Serve(_Args())
        try:
            inc_id = _open(serve.incidents, contacts={"telegram": "tg-1"})
            srv = QuietHTTPServer(("127.0.0.1", 0), Handler)
            srv.serve = serve
            import threading
            import urllib.request
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            port = srv.server_address[1]
            body = json.dumps({"actor": "сын", "note": "еду"}).encode()
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/incidents/{inc_id}/ack",
                data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                self.assertEqual(resp.status, 200)
            self.assertEqual(
                serve.incidents.pg.get_incident(inc_id)["status"], "checking")
            srv.shutdown()
        finally:
            if serve.outbox is not None:
                serve.outbox.stop()
            serve.pg.close()


if __name__ == "__main__":
    unittest.main()