"""Conversation system v2 — phased replacement for dialogue Agent path.

Phase 1: domain types, TurnAnalyzer, ConversationMemory, AgendaManager.
Phase 2: CallPhaseMachine, SafetyBridge, IntentResolver, ReplyComposer, Facade.
Phase 4 (2026-09-03): orchestrator uses ConversationFacade exclusively
via core/conversation_v2_bridge.py (legacy dialogue removed).
"""

from conversation_system.agenda.manager import AgendaManager
from conversation_system.domain.api import (
    CallSummary,
    SessionHandle,
    TurnCommit,
    TurnPlanV2,
)
from conversation_system.integration.facade import ConversationFacade, get_conversation_facade
from conversation_system.domain.understanding import (
    AgendaCommand,
    ConfidenceBand,
    MemoryPatch,
    PolicyDecision,
    ResponseGoalKind,
    SpeechAct,
    SttReason,
    TurnUnderstanding,
)
from conversation_system.memory.state import ConversationMemory
from conversation_system.policy.fsm import CallPhaseMachine
from conversation_system.policy.resolver import IntentResolver
from conversation_system.reply.composer import ReplyComposer
from conversation_system.runtime.session import ConversationSession, TurnPipeline
from conversation_system.safety.bridge import SafetyBridge
from conversation_system.turn.analyzer import TurnAnalyzer

from conversation_system.domain.wellness import WellnessBand, classify_wellness
from conversation_system.reply.pools import (
    GREETING_POOL,
    goodbye_pool_for_band,
    pool_counts,
)

__all__ = [
    "AgendaCommand",
    "AgendaManager",
    "CallPhaseMachine",
    "CallSummary",
    "ConfidenceBand",
    "ConversationFacade",
    "ConversationMemory",
    "ConversationSession",
    "GREETING_POOL",
    "IntentResolver",
    "MemoryPatch",
    "PolicyDecision",
    "ReplyComposer",
    "ResponseGoalKind",
    "SafetyBridge",
    "SessionHandle",
    "SpeechAct",
    "SttReason",
    "TurnAnalyzer",
    "TurnCommit",
    "TurnPipeline",
    "TurnPlanV2",
    "TurnUnderstanding",
    "WellnessBand",
    "classify_wellness",
    "get_conversation_facade",
    "goodbye_pool_for_band",
    "pool_counts",
]
