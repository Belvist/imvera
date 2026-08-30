"""Call lifecycle FSM (read.md): NEW -> ACTIVE -> ENDING -> CLOSED."""
from __future__ import annotations


class CallFSM:
    NEW = "NEW"
    ACTIVE = "ACTIVE"
    ENDING = "ENDING"
    CLOSED = "CLOSED"

    def __init__(self, log=None):
        self.log = log or (lambda _m: None)
        self.state = self.NEW

    def admit(self):
        if self.state == self.NEW:
            self.state = self.ACTIVE
            self.log("call_fsm NEW -> ACTIVE")

    def end(self):
        if self.state in (self.NEW, self.ACTIVE):
            self.state = self.ENDING
            self.log("call_fsm -> ENDING")

    def close(self):
        self.state = self.CLOSED
        self.log("call_fsm -> CLOSED")
