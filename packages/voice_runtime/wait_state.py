"""Answer-wait contract (spec §6.1) — CallActor-owned timers, not a second FSM."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum


class WaitReason(StrEnum):
    ANSWER = "answer"
    PAUSE = "pause"


@dataclass(frozen=True)
class DialogueTimingProfile:
    answer_wait_ms: int = 7000
    backchannel_extra_ms: int = 2000
    pause_wait_ms: int = 30000
    max_pause_wait_ms: int = 60000


@dataclass
class WaitState:
    wait_id: str
    goal_id: str | None
    question_id: str | None
    control_epoch: int
    deadline_mono: float
    reason: WaitReason
    backchannel_extra_applied: bool = False
    speech_paused: bool = False
    created_mono: float = field(default_factory=time.monotonic)

    @classmethod
    def start_answer_wait(
        cls,
        *,
        goal_id: str | None,
        question_id: str | None,
        control_epoch: int,
        profile: DialogueTimingProfile,
        now_mono: float | None = None,
    ) -> WaitState:
        now = now_mono if now_mono is not None else time.monotonic()
        return cls(
            wait_id=f"wait-{uuid.uuid4().hex[:12]}",
            goal_id=goal_id,
            question_id=question_id,
            control_epoch=control_epoch,
            deadline_mono=now + profile.answer_wait_ms / 1000.0,
            reason=WaitReason.ANSWER,
            created_mono=now,
        )

    @classmethod
    def start_pause_wait(
        cls,
        *,
        control_epoch: int,
        profile: DialogueTimingProfile,
        duration_ms: int | None = None,
        now_mono: float | None = None,
    ) -> WaitState:
        now = now_mono if now_mono is not None else time.monotonic()
        wait_ms = duration_ms if duration_ms is not None else profile.pause_wait_ms
        wait_ms = min(wait_ms, profile.max_pause_wait_ms)
        return cls(
            wait_id=f"wait-{uuid.uuid4().hex[:12]}",
            goal_id=None,
            question_id=None,
            control_epoch=control_epoch,
            deadline_mono=now + wait_ms / 1000.0,
            reason=WaitReason.PAUSE,
            created_mono=now,
        )

    def is_current(self, wait_id: str | None, control_epoch: int) -> bool:
        return wait_id == self.wait_id and control_epoch == self.control_epoch

    def remaining_ms(self, now_mono: float | None = None) -> int:
        now = now_mono if now_mono is not None else time.monotonic()
        return max(0, int((self.deadline_mono - now) * 1000))

    def apply_backchannel_extra(
        self,
        profile: DialogueTimingProfile,
        now_mono: float | None = None,
    ) -> bool:
        if self.backchannel_extra_applied or self.reason != WaitReason.ANSWER:
            return False
        now = now_mono if now_mono is not None else time.monotonic()
        self.backchannel_extra_applied = True
        self.deadline_mono += profile.backchannel_extra_ms / 1000.0
        self.deadline_mono = max(self.deadline_mono, now)
        return True

    def pause_for_speech(self, now_mono: float | None = None) -> None:
        now = now_mono if now_mono is not None else time.monotonic()
        self.speech_paused = True
        self.deadline_mono = max(self.deadline_mono, now)

    def resume_after_speech(self) -> None:
        self.speech_paused = False

    def rebind_control(self, control_epoch: int) -> None:
        """Re-attach wait to current control epoch after speech onset bumped it."""
        self.control_epoch = control_epoch
        self.wait_id = f"wait-{uuid.uuid4().hex[:12]}"

    def should_fire(self, now_mono: float | None = None) -> bool:
        if self.speech_paused:
            return False
        now = now_mono if now_mono is not None else time.monotonic()
        return now >= self.deadline_mono
