"""Voice Gateway — WebSocket PCM ingress for FreeSWITCH mod_audio_fork."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from voice_runtime.voice_gateway.server import VoiceGatewayServer
    from voice_runtime.voice_gateway.smart_turn import SmartTurnAnalyzer

__all__ = ["VoiceGatewayServer", "SmartTurnAnalyzer"]


def __getattr__(name: str):
    if name == "VoiceGatewayServer":
        from voice_runtime.voice_gateway.server import VoiceGatewayServer

        return VoiceGatewayServer
    if name == "SmartTurnAnalyzer":
        from voice_runtime.voice_gateway.smart_turn import SmartTurnAnalyzer

        return SmartTurnAnalyzer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
