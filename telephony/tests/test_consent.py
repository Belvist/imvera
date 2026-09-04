"""ROADMAP E3: consent grant/revoke/proof + scheduler guard."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.consent import (  # noqa: E402
    CONSENT_SCRIPT_VERSION, CONSENT_VOICE_SCRIPT, CONSENT_DECLINE_ACK,
    grant_consent, revoke_consent, has_active_consent, export_proof,
    scheduler_may_call, classify_consent_reply, apply_consent_outcome,
)
from core.call_status import (  # noqa: E402
    CallStatus, from_agent_outcome, family_fields_for_finalize,
)
from core.call_mirror import CallMirror  # noqa: E402
from core.consent_call import plan_consent_turn, start_consent_call


class _FakePg:
    """In-memory consent store matching PgStore consent methods."""

    def __init__(self):
        self.rows = []
        self.audits = []

    def grant_consent(self, consent_id, person_id, method="voice",
                      kind="voice", proof_audio_key=None, proof_hash=None,
                      script_version=None, household_id=None, conn=None):
        self.rows.append({
            "id": consent_id,
            "person_id": person_id,
            "kind": kind,
            "method": method,
            "proof_audio_key": proof_audio_key,
            "proof_hash": proof_hash,
            "script_version": script_version,
            "household_id": household_id,
            "granted_at": "now",
            "revoked_at": None,
            "scope": {},
        })

    def revoke_consent(self, person_id, reason=None, conn=None):
        n = 0
        for row in self.rows:
            if row["person_id"] == person_id and row["revoked_at"] is None:
                row["revoked_at"] = "now"
                row["scope"] = {"revoke_reason": reason or ""}
                n += 1
        return n

    def has_active_consent(self, person_id):
        return any(
            r["person_id"] == person_id and r["revoked_at"] is None
            for r in self.rows)

    def export_consent_proof(self, person_id):
        return [dict(r) for r in self.rows if r["person_id"] == person_id]

    def audit(self, action, actor, entity=None, entity_id=None, detail=None,
              conn=None):
        self.audits.append({
            "action": action, "actor": actor, "entity": entity,
            "entity_id": entity_id, "detail": detail or {},
        })


class ConsentStoreTests(unittest.TestCase):
    def test_grant_revoke_has_active(self):
        pg = _FakePg()
        self.assertFalse(has_active_consent(pg, "elder-1"))
        self.assertFalse(scheduler_may_call(pg, "elder-1"))
        cid = grant_consent(
            pg, "elder-1", method="voice",
            proof_audio_key="calls/c1/consent.wav",
            script_version=CONSENT_SCRIPT_VERSION)
        self.assertTrue(cid.startswith("cns-"))
        self.assertTrue(has_active_consent(pg, "elder-1"))
        self.assertTrue(scheduler_may_call(pg, "elder-1"))
        proof = export_proof(pg, "elder-1")
        self.assertTrue(proof["active"])
        self.assertEqual(proof["person_id"], "elder-1")
        self.assertEqual(len(proof["consents"]), 1)
        self.assertEqual(proof["consents"][0]["method"], "voice")
        self.assertTrue(proof["consents"][0]["proof_hash"])
        n = revoke_consent(pg, "elder-1", reason="user request")
        self.assertEqual(n, 1)
        self.assertFalse(has_active_consent(pg, "elder-1"))
        self.assertFalse(scheduler_may_call(pg, "elder-1"))
        self.assertTrue(any(a["action"] == "consent.grant" for a in pg.audits))
        self.assertTrue(any(a["action"] == "consent.revoke" for a in pg.audits))

    def test_without_consent_may_call_false(self):
        pg = _FakePg()
        self.assertFalse(scheduler_may_call(pg, "nobody"))
        self.assertFalse(scheduler_may_call(pg, ""))

    def test_dtmf_and_written_methods(self):
        pg = _FakePg()
        grant_consent(pg, "e2", method="dtmf")
        grant_consent(pg, "e3", method="written")
        self.assertTrue(has_active_consent(pg, "e2"))
        self.assertTrue(has_active_consent(pg, "e3"))
        with self.assertRaises(ValueError):
            grant_consent(pg, "e4", method="telepathy")


class ConsentCallFlowTests(unittest.TestCase):
    def test_classify_grant_and_refuse(self):
        d, reply = classify_consent_reply(text="да, согласна")
        self.assertEqual(d, "granted")
        self.assertTrue(reply)
        d, reply = classify_consent_reply(text="нет, не надо")
        self.assertEqual(d, "declined")
        self.assertEqual(reply, CONSENT_DECLINE_ACK)

    def test_silence_on_consent_becomes_declined(self):
        d, reply = classify_consent_reply(text="", empty_turns=1)
        self.assertEqual(d, "pending")
        d, reply = classify_consent_reply(text="", empty_turns=2)
        self.assertEqual(d, "declined")
        self.assertEqual(reply, CONSENT_DECLINE_ACK)

    def test_agent_consent_silence_path(self):
        a = CallMirror(llm=None)
        script = start_consent_call(a)
        self.assertIn("Имвера", script)
        self.assertEqual(script, CONSENT_VOICE_SCRIPT)
        p1 = plan_consent_turn(a, "")
        self.assertFalse(a.done)
        p2 = plan_consent_turn(a, "")
        self.assertTrue(a.done)
        self.assertEqual(a.status, "declined")
        self.assertTrue(a._consent_declined)
        self.assertIn("отказ", " ".join(a.notes).lower())
        fields = family_fields_for_finalize(
            a.status, notes=a.notes, declined=True)
        self.assertEqual(fields["family_status"], CallStatus.DECLINED.value)
        self.assertEqual(from_agent_outcome("declined"), CallStatus.DECLINED)
        self.assertIn("не будем", p2["fallback"].lower())
        self.assertEqual(p2["fallback"], CONSENT_DECLINE_ACK)

    def test_agent_consent_grant_voice(self):
        a = CallMirror(llm=None)
        start_consent_call(a)
        p = plan_consent_turn(a, "согласна")
        self.assertTrue(a._consent_granted)
        self.assertEqual(a.status, "ok")
        self.assertTrue(a.done)
        self.assertIn("спасибо", p["fallback"].lower())

    def test_apply_consent_outcome_persists_to_pg(self):
        pg = _FakePg()
        a = CallMirror(llm=None)
        start_consent_call(a)
        a._pg = pg
        a._person_id = "elder-persist"
        apply_consent_outcome(
            a, "granted", pg=pg, person_id="elder-persist", method="voice")
        self.assertTrue(has_active_consent(pg, "elder-persist"))
        self.assertTrue(a._consent_granted)
        self.assertTrue(any(r["person_id"] == "elder-persist" for r in pg.rows))

    def test_agent_plan_reply_consent_writes_pg(self):
        pg = _FakePg()
        a = CallMirror(llm=None)
        start_consent_call(a)
        a._pg = pg
        a._person_id = "elder-voice"
        plan_consent_turn(a, "да, согласна")
        self.assertTrue(has_active_consent(pg, "elder-voice"))

    def test_apply_consent_outcome_declined(self):
        a = CallMirror(llm=None)
        apply_consent_outcome(a, "declined")
        self.assertEqual(a.status, "declined")
        self.assertTrue(a.done)


if __name__ == "__main__":
    unittest.main()
