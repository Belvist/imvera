"""Live-call regressions — «плохо» must never get positive narrative ack."""
from __future__ import annotations

import unittest

from conversation_system.integration.facade import get_conversation_facade
from conversation_system.reply.guards import reply_contradicts_bad_wellness


class BadWellnessRegressionTests(unittest.TestCase):
    def test_repeat_bad_complaint_not_kak_priyatno(self):
        facade = get_conversation_facade()
        handle, _ = facade.begin_call(
            call_id="reg-bad-1",
            caller_id="79001234567",
            greeting_played=True,
        )
        p1 = facade.plan_turn(handle, transcript="плохо", stt_confidence=0.9)
        self.assertIn("нехорошо", (p1.spoken_reply or "").lower())
        facade.commit_turn(handle, p1, p1.spoken_reply)

        text = "Плохо, вер, плохо мне, по самочувству, плохо."
        p2 = facade.plan_turn(handle, transcript=text, stt_confidence=0.9)
        reply = (p2.spoken_reply or "").lower()
        self.assertNotIn("как приятно", reply)
        self.assertFalse(
            reply_contradicts_bad_wellness(p2.spoken_reply or "", "bad"),
            msg=p2.spoken_reply,
        )

    def test_meta_hearing_confusion_is_repair_not_notify(self):
        facade = get_conversation_facade()
        handle, _ = facade.begin_call(
            call_id="reg-bad-2",
            caller_id="79001234567",
            greeting_played=True,
        )
        p1 = facade.plan_turn(
            handle, transcript="плохо", stt_confidence=0.9)
        facade.commit_turn(handle, p1, p1.spoken_reply)
        p2 = facade.plan_turn(
            handle,
            transcript="А что плохо слышно ты?",
            stt_confidence=0.9,
        )
        reply = (p2.spoken_reply or "").lower()
        self.assertNotIn("приложен", reply)
        self.assertNotIn("родн", reply)


if __name__ == "__main__":
    unittest.main()
