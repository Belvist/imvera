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


if __name__ == "__main__":
    unittest.main(verbosity=2)