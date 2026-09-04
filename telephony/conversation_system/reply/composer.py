"""ReplyComposer — ResponseGoal to guarded spoken text (pools first)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, List, Sequence

from conversation_system.agenda.manager import AgendaManager
from conversation_system.domain.understanding import ResponseGoal, ResponseGoalKind
from conversation_system.memory.state import ConversationMemory
from conversation_system.reply import guards
from conversation_system.reply.pools import (
    BAD_SYMPTOM_PROBE_POOL,
    BACKGROUND_BLEED_POOL,
    ECHO_REPEAT_POOL,
    GOOD_PROBE_POOL,
    HELP_EMPATHY_POOL,
    MINIMAL_FALLBACK,
    RECORD_NOTIFY_EXPLAIN_POOL,
    RECORD_NOTIFY_POOL,
    SAFETY_ACTIVE_POOL,
    SAFETY_CONFIRM_POOL,
    SHORT_ACK_POOL,
    SIDE_QUESTION_ANSWERS,
    HELLO_BACK_POOL,
    NARRATIVE_ACK_POOL,
    SILENCE_ANCHOR_POOL,
    SILENCE_QUIET_HOLD_POOL,
    SILENCE_REPEAT_POOL,
    WARM_ACK_POOL,
    goodbye_pool_for_band,
    pick_from_pool,
)
from conversation_system.domain.wellness import WellnessBand
from conversation_system.variety.dedupe import DedupeGuard, VarietyEngine, reply_too_similar


@dataclass
class ComposedReply:
    """Final guarded reply ready for TTS."""

    text: str
    segments: List[str] = field(default_factory=list)
    source: str = "pool"
    guarded: bool = True


class ReplyComposer:
    """Scripted-first composer — LLM only when explicitly allowed."""

    def __init__(
        self,
        variety: VarietyEngine | None = None,
        dedupe: DedupeGuard | None = None,
    ) -> None:
        self._variety = variety or VarietyEngine()
        self._dedupe = dedupe or DedupeGuard(self._variety)

    @property
    def variety(self) -> VarietyEngine:
        return self._variety

    def compose(
        self,
        goal: ResponseGoal,
        memory: ConversationMemory,
        agenda: AgendaManager,
        *,
        allow_llm: bool = False,
        llm_stream: Iterator[str] | None = None,
    ) -> ComposedReply:
        if goal.allow_llm and allow_llm and llm_stream is not None:
            text = "".join(llm_stream)
            text = guards.sanitize_reply(text, fallback=MINIMAL_FALLBACK)
            return ComposedReply(text=text, segments=[text], source="llm")

        raw = self._script_for_goal(goal, memory, agenda)
        skip_dedupe = (
            goal.kind in (ResponseGoalKind.REPAIR, ResponseGoalKind.GREET)
            or (goal.kind == ResponseGoalKind.ACKNOWLEDGE
                and goal.topic == "narrative")
            or (goal.kind == ResponseGoalKind.CLARIFY
                and memory.last_input_reason == "off_agenda")
        )
        if skip_dedupe:
            text = guards.sanitize_reply(raw, fallback=MINIMAL_FALLBACK)
        else:
            text = self._dedupe.dedupe(
                raw,
                last_reply=memory.last_reply,
                last_question=memory.last_question,
                topic=goal.topic or agenda.current_topic_key(),
                pool=self._pool_for_goal(goal, agenda),
                pool_key=goal.kind.value,
            )
            text = guards.sanitize_reply(text, fallback=MINIMAL_FALLBACK)
        if guards.reply_falsely_claims_hearing(
                text, memory.last_input_reason):
            text = self._clarify_line(
                memory, echo=memory.last_input_reason == "echo")
            text = guards.sanitize_reply(text, fallback=MINIMAL_FALLBACK)
        if guards.reply_contradicts_bad_wellness(
                text, memory.wellness_band):
            fallback = agenda.spoken_prompt_for_current()
            if not fallback:
                fallback = self._variety.pick_from_pool(
                    BAD_SYMPTOM_PROBE_POOL, pool_key="bad_symptom_guard")
            text = guards.sanitize_reply(fallback, fallback=MINIMAL_FALLBACK)
        self._variety.remember(text)
        return ComposedReply(text=text, segments=[text], source="pool")

    def stream_segments(
        self,
        goal: ResponseGoal,
        memory: ConversationMemory,
        agenda: AgendaManager,
        *,
        allow_llm: bool = False,
    ) -> Iterator[str]:
        reply = self.compose(goal, memory, agenda, allow_llm=allow_llm)
        for seg in reply.segments:
            yield seg

    def _script_for_goal(
        self,
        goal: ResponseGoal,
        memory: ConversationMemory,
        agenda: AgendaManager,
    ) -> str:
        kind = goal.kind
        if kind == ResponseGoalKind.GREET:
            if memory.flags.hello_back_done:
                return self._variety.pick_from_pool(
                    HELLO_BACK_POOL, pool_key="hello_back")
            return agenda.greeting_text()
        if kind == ResponseGoalKind.REPAIR:
            if agenda.record_notified or self._last_reply_was_notify(memory):
                return self._variety.pick_from_pool(
                    RECORD_NOTIFY_EXPLAIN_POOL,
                    pool_key="record_notify_explain",
                )
            if memory.last_question:
                return memory.last_question
            return memory.last_reply or pick_from_pool(WARM_ACK_POOL)
        if kind == ResponseGoalKind.CLARIFY:
            echo = memory.last_input_reason == "echo"
            return self._clarify_line(memory, echo=echo)
        if kind == ResponseGoalKind.ANSWER_SIDE:
            return self._variety.pick_from_pool(
                SIDE_QUESTION_ANSWERS, pool_key="side")
        if kind == ResponseGoalKind.HELP_OFFER:
            return self._variety.pick_from_pool(
                HELP_EMPATHY_POOL, pool_key="help_offer")
        if kind == ResponseGoalKind.SAFETY_CONFIRM:
            return self._variety.pick_from_pool(
                SAFETY_CONFIRM_POOL, pool_key="safety_confirm")
        if kind == ResponseGoalKind.SAFETY_ACTIVE:
            return self._variety.pick_from_pool(
                SAFETY_ACTIVE_POOL, pool_key="safety_active")
        if kind == ResponseGoalKind.SYMPTOM_FOLLOWUP:
            if memory.corrections or any("исправлен" in f for f in memory.facts):
                focus = memory.active_symptom or goal.symptom_focus or "симптом"
                return (
                    f"Поняла, {focus}, спасибо что уточнили. "
                    f"Как {focus} сейчас — терпимо или сильно?"
                )
            pq = memory.pending_question
            if pq is not None and pq.kind.value == "choice" and memory.last_question:
                if any("pending_invalid:choice_needs_pick" in n for n in memory.notes):
                    return memory.last_question
            prompt = agenda.spoken_prompt_for_current()
            if prompt:
                return prompt
            if goal.symptom_focus:
                from conversation_system.reply.pools import SYMPTOM_CHECKS
                return self._variety.pick_from_pool(
                    SYMPTOM_CHECKS, pool_key="symptom_check")
            return self._variety.pick_from_pool(
                BAD_SYMPTOM_PROBE_POOL, pool_key="bad_symptom")
        if kind == ResponseGoalKind.WRAP_UP:
            return agenda.record_notify_text() or self._variety.pick_from_pool(
                RECORD_NOTIFY_POOL, pool_key="record_notify")
        if kind == ResponseGoalKind.CLOSE:
            try:
                band = WellnessBand(memory.wellness_band)
            except ValueError:
                band = agenda.wellness_band
            pool = goodbye_pool_for_band(band)
            return self._variety.pick_from_pool(pool, pool_key=f"goodbye_{band.value}")
        if kind == ResponseGoalKind.ACKNOWLEDGE:
            if goal.topic == "narrative":
                return self._variety.pick_from_pool(
                    NARRATIVE_ACK_POOL, pool_key="narrative_ack")
            return self._variety.pick_from_pool(SHORT_ACK_POOL, pool_key="ack")
        if kind == ResponseGoalKind.ASK_TOPIC:
            prompt = agenda.spoken_prompt_for_current()
            if prompt and memory.last_question and reply_too_similar(
                    prompt, memory.last_question):
                prompt = ""
            if prompt:
                return prompt
            return self._variety.pick_from_pool(
                GOOD_PROBE_POOL, pool_key="good_probe")
        return MINIMAL_FALLBACK

    def _clarify_line(self, memory: ConversationMemory, *, echo: bool) -> str:
        """Tapered VUI ladder — repeat, then anchor, then quiet hold."""
        if memory.last_input_reason == "off_agenda":
            # Do not engage with overheard TV/room speech — repeat the open question.
            if memory.last_question:
                return memory.last_question
            return self._variety.pick_from_pool(
                BACKGROUND_BLEED_POOL, pool_key="background_bleed")
        n = memory.empty_turn_count
        if echo:
            if n <= 1:
                return self._variety.pick_from_pool(
                    ECHO_REPEAT_POOL, pool_key="echo_repeat")
            if n == 2:
                return self._variety.pick_from_pool(
                    SILENCE_ANCHOR_POOL, pool_key="anchor")
            return self._variety.pick_from_pool(
                SILENCE_QUIET_HOLD_POOL, pool_key="quiet")
        if n <= 1:
            return self._variety.pick_from_pool(
                SILENCE_REPEAT_POOL, pool_key="repeat")
        if n == 2:
            return self._variety.pick_from_pool(
                SILENCE_ANCHOR_POOL, pool_key="anchor")
        if n == 3:
            return self._variety.pick_from_pool(
                SILENCE_REPEAT_POOL, pool_key="repeat_hear")
        return self._variety.pick_from_pool(
            SILENCE_QUIET_HOLD_POOL, pool_key="quiet")

    def _pool_for_goal(
        self,
        goal: ResponseGoal,
        agenda: AgendaManager,
    ) -> Sequence[str]:
        kind = goal.kind
        if kind == ResponseGoalKind.CLARIFY:
            return SILENCE_ANCHOR_POOL
        if kind == ResponseGoalKind.SAFETY_CONFIRM:
            return SAFETY_CONFIRM_POOL
        if kind == ResponseGoalKind.SAFETY_ACTIVE:
            return SAFETY_ACTIVE_POOL
        if kind == ResponseGoalKind.WRAP_UP:
            return RECORD_NOTIFY_POOL
        if kind == ResponseGoalKind.CLOSE:
            return goodbye_pool_for_band(agenda.wellness_band)
        if kind == ResponseGoalKind.ANSWER_SIDE:
            return SIDE_QUESTION_ANSWERS
        if kind == ResponseGoalKind.HELP_OFFER:
            return HELP_EMPATHY_POOL
        if kind == ResponseGoalKind.SYMPTOM_FOLLOWUP:
            return BAD_SYMPTOM_PROBE_POOL
        if kind == ResponseGoalKind.ASK_TOPIC:
            return GOOD_PROBE_POOL
        return WARM_ACK_POOL

    def _last_reply_was_notify(self, memory: ConversationMemory) -> bool:
        last = (memory.last_reply or "").lower()
        if not last:
            return False
        markers = (
            "записал",
            "записала",
            "приложен",
            "родн",
            "близк",
            "семь",
        )
        return any(m in last for m in markers)
