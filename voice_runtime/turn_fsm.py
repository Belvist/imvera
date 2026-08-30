"""Turn lifecycle FSM (read.md): IDLE -> USER_SPEAKING -> PROCESSING ->
ASSISTANT_SPEAKING -> IDLE, with INTERRUPTING on barge-in.

Owns the ``playing`` / ``streaming`` / ``suppress`` flags so wedged states
are visible and illegal transitions are logged instead of silently corrupting
the session loop.
"""
from __future__ import annotations


class TurnFSM:
    IDLE = "IDLE"
    USER_SPEAKING = "USER_SPEAKING"
    PROCESSING = "PROCESSING"
    ASSISTANT_SPEAKING = "ASSISTANT_SPEAKING"
    INTERRUPTING = "INTERRUPTING"

    def __init__(self, log=None):
        self.log = log or (lambda _m: None)
        self.state = self.IDLE
        self.playing = False
        self.streaming = False
        self.suppress = False

    def _trans(self, dst, why):
        if self.state != dst:
            self.log("turn_fsm %s -> %s (%s)" % (self.state, dst, why))
            self.state = dst

    def on_playback_start(self):
        self.playing = True
        self._trans(self.ASSISTANT_SPEAKING, "playback")

    def on_playback_stop(self):
        self.playing = False
        if self.streaming:
            self._trans(self.PROCESSING, "playback_stop while streaming")
        else:
            self._trans(self.IDLE, "playback_stop")

    def on_playback_watchdog(self):
        self.playing = False
        if self.streaming:
            self._trans(self.PROCESSING, "playback watchdog")
        else:
            self._trans(self.IDLE, "playback watchdog")

    def on_turn_submitted(self):
        self.streaming = True
        self.suppress = False
        self._trans(self.PROCESSING, "turn_stream submitted")

    def on_stream_finished(self):
        self.streaming = False
        self.suppress = False
        if self.playing:
            self._trans(self.ASSISTANT_SPEAKING, "stream done, still playing")
        else:
            self._trans(self.IDLE, "stream done")

    def on_stream_failed(self):
        self.streaming = False
        self.suppress = False
        if self.playing:
            self._trans(self.ASSISTANT_SPEAKING, "stream failed, still playing")
        else:
            self._trans(self.IDLE, "stream failed")

    def on_barge_in(self):
        if self.playing:
            self.playing = False
            self._trans(self.INTERRUPTING, "barge-in")
        if self.streaming:
            self.suppress = True

    def on_stream_cancel(self):
        self.suppress = True
        if self.playing:
            self._trans(self.INTERRUPTING, "stream cancel while playing")
        elif self.state == self.PROCESSING:
            self._trans(self.INTERRUPTING, "stream cancel")

    def on_user_turn_complete(self):
        if self.state in (self.IDLE, self.INTERRUPTING, self.USER_SPEAKING):
            self._trans(self.USER_SPEAKING, "vad turn")
