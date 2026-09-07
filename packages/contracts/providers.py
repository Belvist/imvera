"""Provider protocols — voice-runtime does not import concrete models."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from packages.contracts.interpretation import TurnInterpretation
from packages.contracts.stt import STTPartial, STTResult


@dataclass(frozen=True)
class AudioChunk:
    pcm_s16le: bytes
    sample_rate: int
    sequence: int
    is_last: bool = False


class ProviderError(Exception):
    """Base provider error."""


class ProviderTimeout(ProviderError):
    pass


class ProviderUnavailable(ProviderError):
    pass


class ProviderCancelled(ProviderError):
    pass


class ProviderInvalidOutput(ProviderError):
    pass


@runtime_checkable
class STTProvider(Protocol):
    async def transcribe_partial(
        self,
        pcm_s16le: bytes,
        sample_rate: int,
        *,
        call_id: str,
        partial_id: str,
    ) -> STTPartial: ...

    async def transcribe_final(
        self,
        pcm_s16le: bytes,
        sample_rate: int,
        *,
        call_id: str,
        turn_id: int,
        deadline: float,
        utterance_id: str = "",
    ) -> STTResult: ...


@runtime_checkable
class TTSProvider(Protocol):
    async def synthesize(
        self,
        text: str,
        *,
        generation_id: str,
        phrase_id: str,
        deadline: float,
    ) -> AsyncIterator[AudioChunk]: ...

    async def cancel(self, generation_id: str) -> None: ...


@runtime_checkable
class InterpretationProvider(Protocol):
    """Semantic interpreter — proposes TurnInterpretation; policy commits facts."""

    async def interpret_turn(
        self,
        *,
        call_id: str,
        turn_id: int,
        user_text: str,
        planner_context: dict,
        state_version: int,
        deadline: float,
    ) -> TurnInterpretation: ...


@runtime_checkable
class RendererProvider(Protocol):
    async def render_stream(
        self,
        *,
        call_id: str,
        turn_id: int,
        generation_id: str,
        planner_context: dict,
        deadline: float,
    ) -> AsyncIterator[str]: ...

    async def cancel(self, generation_id: str) -> None: ...
