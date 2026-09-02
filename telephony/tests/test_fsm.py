"""Unit tests for the generic state machine (core/fsm.py).

These assert the ENGINEERING CONTRACT of a disciplined state machine
(UML/Harel principles): guards are pure and order-independent, an event with
no matching transition raises (never silently swallows), run-to-completion
dispatch, and the "*" source factors out common behavior.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.fsm import StateMachine, UnhandledEvent  # noqa: E402


class _Ctx:
    def __init__(self):
        self.log = []
        self.health = 100


class StateMachineContractTests(unittest.TestCase):
    def _machine(self):
        m = StateMachine("test", "idle")
        m.add("idle", "go", "running",
              action=lambda c, e: c.log.append(("go", e)))
        m.add("running", "fire", "broken",
              guard=lambda c, e: c.health < 50,
              action=lambda c, e: c.log.append(("fire", e)))
        m.add("running", "fire", "running",
              action=lambda c, e: c.log.append(("go-safe", e)))
        m.add("*", "stop", "idle",
              action=lambda c, e: c.log.append(("stop", e)))
        m.add("*", "panic", "broken",
              action=lambda c, e: c.log.append(("panic", e)))
        return m

    def test_transitions_and_guard(self):
        m, c = self._machine(), _Ctx()
        self.assertEqual(m.handle(c, "go"), None)
        self.assertEqual(m.state, "running")
        # guard False -> next candidate fires
        m.handle(c, "fire")
        self.assertEqual(m.state, "running")
        # lever flipped -> guarded transition fires
        c.health = 10
        m.handle(c, "fire")
        self.assertEqual(m.state, "broken")
        self.assertIn(("fire", "fire"), c.log)

    def test_any_state_transition_fires_from_any_state(self):
        m, c = self._machine(), _Ctx()
        m.handle(c, "go")           # idle -> running
        m.handle(c, "panic")        # running -> broken (via *)
        self.assertEqual(m.state, "broken")
        m.handle(c, "stop")         # broken -> idle (via *)
        self.assertEqual(m.state, "idle")

    def test_unhandled_event_raises(self):
        m, c = self._machine(), _Ctx()
        # "go" only valid from idle; "fire" after "go" (running) IS valid, but
        # a fresh machine in broken with no matching transition must raise.
        m.handle(c, "go")
        m.handle(c, "panic")        # -> broken
        with self.assertRaises(UnhandledEvent):
            m.handle(c, "go")       # no (broken, go) transition

    def test_run_to_completion_single_result(self):
        # one event -> exactly one transition action runs (no fan-out)
        m, c = self._machine(), _Ctx()
        n = len(c.log)
        m.handle(c, "go")
        m.handle(c, "stop")         # stop from running via *
        self.assertEqual(c.log[n:], [("go", "go"), ("stop", "stop")])

    def test_local_wildcard_is_more_specific_than_global_event(self):
        """A state's own "*" fallback is more specific than a global event.

        This keeps an active side-question's resume/reask logic intact while
        the total-machine catch-all still guarantees every event is handled.
        """
        m, c = self._machine(), _Ctx()
        m.add("idle", "*", "idle",
              action=lambda ctx, event: ctx.log.append(("local", event)))

        m.handle(c, "panic")

        self.assertEqual(m.state, "idle")
        self.assertEqual(c.log, [("local", "panic")])


class DialogueMachineTotalityTests(unittest.TestCase):
    """The dialogue FSM must be TOTAL: every (state, event) pair either has
    a specific transition or lands on the explicit ("*","*") catch-all — it
    never raises UnhandledEvent and never goes silent on the hot path."""

    def test_all_state_event_pairs_have_a_candidate(self):
        """Totality of the transition TABLE: every (state, event) pair has
        at least one candidate transition (the ("*","*") catch-all
        guarantees it), and no specific transition is shadowed by the
        catch-all (the catch-all is always the LAST candidate)."""
        import sys
        sys.path.insert(0, os.path.join(
            os.path.dirname(os.path.abspath(__file__)), ".."))
        from core.dialogue import DialogueFSM

        D = DialogueFSM
        states = [D.IDLE, D.CHECKIN, D.SIDE_QUESTION, D.CLARIFY,
                  D.SAFETY_CONFIRM, D.SAFETY_ACTIVE, D.HELP, D.WORRY,
                  D.GOODBYE_CONFIRM, D.CLOSING, D.DONE]
        events = [D.E_DONE, D.E_REPAIR, D.E_DANGER, D.E_FROZEN,
                  D.E_GOODBYE, D.E_GOODBYE_DIRECT, D.E_CONFIRM, D.E_QUESTION,
                  D.E_HELP, D.E_WORRY, D.E_SYMPTOM, D.E_UNCERTAIN, D.E_OK,
                  D.E_HEARD, D.E_EMPTY, D.E_GREETING, D.E_REFUSE,
                  D.E_UNKNOWN]

        t = DialogueFSM()
        for st in states:
            for ev in events:
                t.sm.state = st
                cands = t.sm._candidates(ev)
                self.assertTrue(cands, f"no candidate for {st} <- {ev}")
                # the catch-all must always be last (never shadow specifics)
                self.assertEqual(
                    cands[-1].src, "*" if True else None)
                self.assertEqual(cands[-1].event, "*",
                                 f"catch-all not last for {st} <- {ev}")

    def test_catch_all_is_last_row(self):
        from core.dialogue import DialogueFSM
        t = DialogueFSM()
        rows = t.sm._transitions
        self.assertEqual(rows[-1].src, "*")
        self.assertEqual(rows[-1].event, "*",
                         "the catch-all must be the LAST declared row")

    def test_unhandled_action_returns_warm_ack(self):
        from core.dialogue import DialogueFSM, Agent
        f = DialogueFSM()
        agent = Agent(llm=None)
        plan = f._a_unhandled(agent, "unknown-event")
        self.assertIsInstance(plan, dict)
        self.assertTrue((plan.get("fallback") or "").strip())
        self.assertIsNotNone(plan.get("intent"))


if __name__ == "__main__":
    unittest.main(verbosity=2)