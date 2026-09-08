"""Per-call effect outbox — typed indexes, explicit lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from packages.dialogue_engine.delivery.decision import Decision
from packages.dialogue_engine.delivery.scope import speak_scope_active, timer_scope_active
from packages.dialogue_engine.effects import (
    Effect,
    EndCallEffect,
    InterpretEffect,
    SpeakEffect,
    TimerEffect,
)
from packages.dialogue_engine.state import EngineState

MAX_REISSUES_PER_KEY = 2


class EffectStatus(StrEnum):
    EMITTED = "EMITTED"
    ACCEPTED = "ACCEPTED"
    DEFERRED = "DEFERRED"
    CLAIMED = "CLAIMED"
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    STALE = "STALE"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


_TERMINAL = frozenset(
    {
        EffectStatus.COMPLETED,
        EffectStatus.STALE,
        EffectStatus.CANCELLED,
        EffectStatus.FAILED,
    }
)


@dataclass
class EffectRecord:
    effect: Effect
    status: EffectStatus = EffectStatus.EMITTED
    created_revision: int = 0
    supersedes_effect_id: str = ""
    reissue_count: int = 0
    fail_stage: str | None = None
    fail_error: str | None = None


@dataclass
class EffectOutbox:
    call_id: str
    _records: dict[str, EffectRecord] = field(default_factory=dict)
    _pending_speaks: list[str] = field(default_factory=list)
    _pending_timers: list[str] = field(default_factory=list)
    _pending_hangups: list[str] = field(default_factory=list)
    _deferred_speak_id: str | None = None
    _reissue_counts: dict[str, int] = field(default_factory=dict)

    def accept_decision(self, decision: Decision) -> None:
        for eff in decision.effects:
            if isinstance(eff, InterpretEffect):
                continue
            if eff.effect_id and eff.effect_id in self._records:
                continue
            record = EffectRecord(
                effect=eff,
                status=EffectStatus.ACCEPTED,
                created_revision=decision.revision,
                supersedes_effect_id=getattr(eff, "supersedes_effect_id", "") or "",
                reissue_count=getattr(eff, "reissue_count", 0) or 0,
            )
            eid = eff.effect_id or self._synthetic_id(eff)
            record.effect = eff.model_copy(update={"effect_id": eid})
            self._records[eid] = record
            if isinstance(eff, SpeakEffect):
                self._pending_speaks.append(eid)
            elif isinstance(eff, TimerEffect):
                self._pending_timers.append(eid)
            elif isinstance(eff, EndCallEffect):
                self._pending_hangups.append(eid)

    def get_record(self, effect_id: str) -> EffectRecord | None:
        return self._records.get(effect_id)

    def claim_next_speak(self) -> SpeakEffect | None:
        while self._pending_speaks:
            eid = self._pending_speaks.pop(0)
            record = self._records.get(eid)
            if record is None or record.status in _TERMINAL:
                continue
            if record.status == EffectStatus.DEFERRED:
                continue
            record.status = EffectStatus.CLAIMED
            assert isinstance(record.effect, SpeakEffect)
            return record.effect
        return None

    def drain_speak_effects(self) -> list[SpeakEffect]:
        speaks: list[SpeakEffect] = []
        while True:
            speak = self.claim_next_speak()
            if speak is None:
                break
            speaks.append(speak)
        return speaks

    def claim_next_timer(self) -> TimerEffect | None:
        while self._pending_timers:
            eid = self._pending_timers.pop(0)
            record = self._records.get(eid)
            if record is None or record.status in _TERMINAL:
                continue
            record.status = EffectStatus.CLAIMED
            assert isinstance(record.effect, TimerEffect)
            return record.effect
        return None

    def claim_next_hangup(self) -> EndCallEffect | None:
        while self._pending_hangups:
            eid = self._pending_hangups.pop(0)
            record = self._records.get(eid)
            if record is None or record.status in _TERMINAL:
                continue
            record.status = EffectStatus.CLAIMED
            assert isinstance(record.effect, EndCallEffect)
            return record.effect
        return None

    def peek_pending_speaks(self) -> list[SpeakEffect]:
        out: list[SpeakEffect] = []
        for eid in self._pending_speaks:
            record = self._records.get(eid)
            if record and isinstance(record.effect, SpeakEffect):
                out.append(record.effect)
        if self._deferred_speak_id:
            record = self._records.get(self._deferred_speak_id)
            if record and isinstance(record.effect, SpeakEffect):
                out.append(record.effect)
        return out

    def defer_speak(self, effect_id: str) -> None:
        record = self._records.get(effect_id)
        if record is None:
            return
        record.status = EffectStatus.DEFERRED
        self._deferred_speak_id = effect_id
        if effect_id in self._pending_speaks:
            self._pending_speaks.remove(effect_id)

    def flush_deferred_speak(self) -> SpeakEffect | None:
        if not self._deferred_speak_id:
            return None
        eid = self._deferred_speak_id
        self._deferred_speak_id = None
        record = self._records.get(eid)
        if record is None or record.status != EffectStatus.DEFERRED:
            return None
        record.status = EffectStatus.ACCEPTED
        self._pending_speaks.insert(0, eid)
        return self.claim_next_speak()

    def clear_deferred_speak(self) -> None:
        self._deferred_speak_id = None

    def mark_started(self, effect_id: str) -> None:
        record = self._records.get(effect_id)
        if record and record.status not in _TERMINAL:
            record.status = EffectStatus.STARTED

    def mark_completed(self, effect_id: str) -> bool:
        record = self._records.get(effect_id)
        if record is None:
            return False
        if record.status in _TERMINAL:
            return False
        record.status = EffectStatus.COMPLETED
        return True

    def mark_stale(self, effect_id: str, *, reason: str = "") -> None:
        record = self._records.get(effect_id)
        if record is None or record.status in _TERMINAL:
            return
        record.status = EffectStatus.STALE
        record.fail_error = reason or None

    def mark_cancelled(self, effect_id: str, *, reason: str = "") -> None:
        record = self._records.get(effect_id)
        if record is None or record.status in _TERMINAL:
            return
        record.status = EffectStatus.CANCELLED
        record.fail_error = reason or None
        if effect_id in self._pending_timers:
            self._pending_timers.remove(effect_id)
        if effect_id in self._pending_speaks:
            self._pending_speaks.remove(effect_id)

    def mark_failed(self, effect_id: str, *, stage: str, error: str = "") -> None:
        record = self._records.get(effect_id)
        if record is None or record.status in _TERMINAL:
            return
        record.status = EffectStatus.FAILED
        record.fail_stage = stage
        record.fail_error = error

    def cancel_timer_by_id(self, timer_id: str) -> None:
        for eid in list(self._pending_timers):
            record = self._records.get(eid)
            if record and isinstance(record.effect, TimerEffect):
                if record.effect.timer_id == timer_id:
                    self.mark_cancelled(eid, reason="user_speech")

    def is_speak_valid(self, effect: SpeakEffect, state: EngineState) -> bool:
        record = self._records.get(effect.effect_id)
        if record and record.status in _TERMINAL:
            return False
        if effect.semantic_scope_id:
            if not speak_scope_active(effect, state):
                return False
        elif effect.revision != state.revision:
            return False
        if effect.generation != state.active_playout_generation:
            if effect.generation < state.active_playout_generation:
                return False
        return True

    def is_timer_valid(self, effect: TimerEffect, state: EngineState) -> bool:
        record = self._records.get(effect.effect_id)
        if record and record.status in _TERMINAL:
            return False
        return timer_scope_active(effect, state)

    def track_reissue(self, semantic_key: str) -> int:
        count = self._reissue_counts.get(semantic_key, 0) + 1
        self._reissue_counts[semantic_key] = count
        return count

    def reissue_allowed(self, semantic_key: str) -> bool:
        return self._reissue_counts.get(semantic_key, 0) < MAX_REISSUES_PER_KEY

    def active_non_terminal_count(self) -> int:
        return sum(1 for r in self._records.values() if r.status not in _TERMINAL)

    def pending_timer_ids(self) -> list[str]:
        return list(self._pending_timers)

    @staticmethod
    def _synthetic_id(effect: Effect) -> str:
        return f"{effect.kind}-{id(effect)}"
