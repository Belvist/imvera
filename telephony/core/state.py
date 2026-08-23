"""Call session state (P0-SESSION-001)."""

from dataclasses import dataclass, field
import threading
import time

from core.dialogue import Agent
from adapters.postgres_results import Recorder


DEFAULT_GREETING = "Здравствуйте! Это Имвэра. Как вы себя чувствуете?"

# When a call has been idle for this long it is garbage-collected.
SESSION_TTL_SEC = 60 * 60


@dataclass
class CallContext:
    """Everything needed to run ONE phone call independently.

    P0-SESSION-001: a call's dialogue state (Agent), conversation recording
    (Recorder) and safety/dialogue scratch state live here, not in globals.
    Two concurrent calls never share or reset each other's state.

    AUDIT FIX: ``lock`` serialises every mutation of agent/recorder state for
    this call (two overlapping /turn requests were racing and corrupting
    result.json); ``turn_in_progress`` lets a second concurrent turn be
    rejected with HTTP 429 instead of interleaving with the first one.
    """
    call_id: str
    agent: Agent = field(default_factory=Agent)
    recorder: Recorder = field(default_factory=lambda: Recorder(""))
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    caller_id: str | None = None
    finished: bool = False
    safety_state: dict = field(default_factory=dict)
    dialogue_state: dict = field(default_factory=dict)
    outcome: dict = field(default_factory=dict)
    streaming: bool = False
    cancel_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    # SHORT lock guarding only the turn-in-progress flag: begin_turn must not
    # block on `lock` (which the running turn holds for the whole turn incl.
    # TTS generation), otherwise a second request would queue behind the first
    # instead of being rejected.
    turn_lock: threading.Lock = field(default_factory=threading.Lock)
    turn_in_progress: bool = False
    # AUDIT FIX: id of the TTS stream currently generating this call's reply,
    # so /stream-cancel can abort it server-side (not just client-side).
    stream_id: str = ""


class CallBusyError(Exception):
    """A turn for this call is already being processed."""

    def __init__(self, call_id):
        super().__init__(f"call {call_id} is busy")
        self.call_id = call_id


class AdmissionError(Exception):
    """System at hard capacity: new calls are REJECTED, not degraded.

    Load shedding (Google SRE): better to refuse call N+1 than to slow
    every active conversation until the pipeline collapses."""

    def __init__(self, active, limit):
        super().__init__(f"capacity: {active}/{limit} concurrent calls")
        self.active = active
        self.limit = limit