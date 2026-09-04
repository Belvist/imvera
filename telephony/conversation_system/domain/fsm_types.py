"""FSM domain types — phases, events, action results."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Tuple

from conversation_system.domain.understanding import MemoryPatch, ResponseGoal

if TYPE_CHECKING:
    from conversation_system.agenda.manager import AgendaManager
    from conversation_system.memory.state import ConversationMemory
    from conversation_system.domain.understanding import TurnUnderstanding
    from core.safety_engine import VerdictEvent


class CallPhase(str, Enum):
    """Qualitative call phase — product flow per FSM.md."""

    GREETING = "greeting"
    LISTEN = "listen"
    GOOD_PATH = "good_path"
    BAD_PATH = "bad_path"
    CRITICAL_PATH = "critical_path"
    RECORD_NOTIFY = "record_notify"
    CLOSING = "closing"
    CLARIFY = "clarify"
    SIDE_ANSWER = "side_answer"
    SAFETY_CONFIRM = "safety_confirm"
    SAFETY_ACTIVE = "safety_active"
    TERMINAL = "terminal"


class FsmEvent(str, Enum):
    """Input events for CallPhaseMachine."""

    E_CALL_START = "call_start"
    E_SPEECH = "speech"
    E_WELLNESS_GOOD = "wellness_good"
    E_WELLNESS_BAD = "wellness_bad"
    E_WELLNESS_CRITICAL = "wellness_critical"
    E_PROBE_DONE = "probe_done"
    E_PROBES_COMPLETE = "probes_complete"
    E_NOTIFY_DONE = "notify_done"
    E_CLOSING = "closing"
    E_CLOSING_DIRECT = "closing_direct"
    E_EMPTY = "empty"
    E_LOW_CONF = "low_conf"
    E_ECHO = "echo"
    E_STT_CONFIRM = "stt_confirm"
    E_SAFETY_CONFIRMED = "safety_confirmed"
    E_SAFETY_UNCERTAIN = "safety_uncertain"
    E_SAFETY_POSSIBLE = "safety_possible"
    E_SAFETY_CLEARED = "safety_cleared"
    E_SIDE_QUESTION = "side_question"
    E_NARRATIVE = "narrative"
    E_CORRECTION = "correction"
    E_REPAIR = "repair"
    E_REFUSAL = "refusal"
    E_GREETING = "greeting"
    E_HELP = "help"
    E_ACK = "ack"
    E_HANGUP = "hangup"
    E_UNHANDLED = "unhandled"


MAX_DISPATCH_DEPTH = 4


@dataclass
class FsmActionResult:
    """Action output — goal + explicit memory patches, never spoken text."""

    goal: ResponseGoal
    patches: Tuple[MemoryPatch, ...] = ()
    redispatch: FsmEvent | None = None
    terminal: bool = False
    verdict: str = "ok"
    safety_status: str = ""
    record_notes: Tuple[str, ...] = ()


@dataclass
class CallPhaseContext:
    """Extended state for FSM guards/actions (mutable during one dispatch)."""

    memory: "ConversationMemory"
    agenda: "AgendaManager"
    understanding: "TurnUnderstanding | None" = None
    safety: "VerdictEvent | None" = None
    dispatch_depth: int = 0
    hour: int | None = None
    echo_turn_count: int = 0
    safety_confirm_pending: bool = False
    last_result: FsmActionResult | None = None
    question_ledger: object | None = None

    def probes_remain(self) -> bool:
        from conversation_system.domain.wellness import (
            bad_path_probe_count,
            good_path_probe_count,
        )

        if self.agenda.on_good_path:
            return self.agenda.good_probe_index < good_path_probe_count()
        if self.agenda.on_bad_path:
            return self.agenda.bad_symptom_probe_index < bad_path_probe_count()
        return False
