"""Perception layer — capture, echo gate, turn boundary, text echo filter.

Single owner for uplink perception before STT. Transport (SIP/RTP) stays in telephony;
dialogue/STT orchestration stays in CallActor.
"""

from packages.voice_perception.config import PerceptionConfig, perception_config_from_env
from packages.voice_perception.echo_ref_gate import (
    DownlinkEchoRef,
    EchoRefConfig,
    EchoVerdict,
    echo_ref_gate_enabled,
    lab_barge_in_enabled,
    apply_echo_ref_env,
)
from packages.voice_perception.playback_reference import EchoClassification, PlaybackReference
from packages.voice_perception.session import PerceptionSession, UplinkDecision
from packages.voice_perception.text_echo import (
    is_text_echo_of_bot,
    normalize_speech_text,
    text_echo_similarity,
)
from packages.voice_perception.turn_fsm import (
    ConversationPhase,
    TurnManager,
    TurnPolicy,
    TurnPolicyKind,
    policy_for_intent,
)

__all__ = [
    "ConversationPhase",
    "DownlinkEchoRef",
    "EchoClassification",
    "EchoRefConfig",
    "EchoVerdict",
    "PerceptionConfig",
    "PerceptionSession",
    "PlaybackReference",
    "TurnManager",
    "TurnPolicy",
    "TurnPolicyKind",
    "UplinkDecision",
    "apply_echo_ref_env",
    "echo_ref_gate_enabled",
    "is_text_echo_of_bot",
    "lab_barge_in_enabled",
    "normalize_speech_text",
    "perception_config_from_env",
    "policy_for_intent",
    "text_echo_similarity",
]
