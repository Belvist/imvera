"""Turn and call FSM unit tests."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from turn_fsm import TurnFSM  # noqa: E402
from call_fsm import CallFSM  # noqa: E402


class TurnFSMTests(unittest.TestCase):
    def test_stream_done_unblocks(self):
        f = TurnFSM()
        f.on_turn_submitted()
        self.assertTrue(f.streaming)
        f.on_stream_finished()
        self.assertFalse(f.streaming)
        self.assertEqual(f.state, TurnFSM.IDLE)

    def test_barge_in_sets_suppress(self):
        f = TurnFSM()
        f.on_turn_submitted()
        f.on_playback_start()
        f.on_barge_in()
        self.assertTrue(f.suppress)
        self.assertFalse(f.playing)

    def test_playback_stop_while_streaming(self):
        f = TurnFSM()
        f.on_turn_submitted()
        f.on_playback_start()
        f.on_playback_stop()
        self.assertEqual(f.state, TurnFSM.PROCESSING)


class CallFSMTests(unittest.TestCase):
    def test_lifecycle(self):
        c = CallFSM()
        self.assertEqual(c.state, CallFSM.NEW)
        c.admit()
        self.assertEqual(c.state, CallFSM.ACTIVE)
        c.end()
        c.close()
        self.assertEqual(c.state, CallFSM.CLOSED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
