"""Deterministic Observer v1 — re-interpret each turn before policy."""
from __future__ import annotations

import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Tuple

from conversation_system.domain.pending_question import (
    PendingQuestion,
    PendingQuestionType,
    infer_pending_from_prompt,
    validate_pending_answer,
)
from conversation_system.domain.understanding import MemoryPatch, SpeechAct, TurnUnderstanding
from conversation_system.observer.state_contract import ConversationState
from conversation_system.turn._classifiers import is_text_question
from conversation_system.turn.analyzer import (
    extract_correction_focus,
    extract_symptom_focus,
    mentions_symptom,
)

if TYPE_CHECKING:
    from conversation_system.memory.state import ConversationMemory


@dataclass(frozen=True)
class ObserverPatch:
    """Structured output from one observe_turn pass."""

    corrections: Tuple[str, ...] = ()
    contradictions: Tuple[str, ...] = ()
    unanswered_user_questions: Tuple[str, ...] = ()
    next_directive: str = ""
    memory_patches: Tuple[MemoryPatch, ...] = ()
    pending_invalid: bool = False
    llm_enriched: bool = False
    supervisor_overrides: Tuple[str, ...] = ()


_CORRECTION_RE = re.compile(
    r"(?:^|\s)(?:не\s+)?(?:имел|имела)\s+в\s+виду|"
    r"нет\s*[,]?\s*не\s+(?:то|так|голова|спина|болит)|"
    r"не\s+(?:голова|спина|болит|то|так)\s*[,]?\s*(?:а\s+)?|"
    r"исправлю\s*:|я\s+имел\s+в\s+виду|"
    r"не\s+голова\s*[,]?\s*спина|не\s+спина\s*[,]?\s*голова",
    re.IGNORECASE,
)

_CONTRADICTION_RE = re.compile(
    r"(?:на\s+самом\s+деле|вообще\s+то|а\s+на\s+самом\s+деле|"
    r"нет\s*[,]?\s*(?:наоборот|на\s+самом\s+деле))",
    re.IGNORECASE,
)

_WHY_CALL_RE = re.compile(
    r"(зачем\s+(?:вы|ты)\s+звон|почему\s+звон|зачем\s+этот\s+звон|"
    r"кто\s+вы|что\s+за\s+сервис|что\s+такое\s+имвера)",
    re.IGNORECASE,
)

_PRIVACY_RE = re.compile(
    r"(записыва|слуша|прослуш|конфиденц|личн\w+\s+данн|"
    r"кто\s+услышит|кто\s+увидит|переда\w+\s+родн)",
    re.IGNORECASE,
)


class Observer:
    """Turn observer — deterministic v1 with optional LLM enrichment."""

    _worker_pool: ThreadPoolExecutor | None = None
    _worker_lock = threading.Lock()

    def __init__(self, llm=None) -> None:
        from conversation_system.observer.llm_enricher import LlmObserverEnricher
        from conversation_system.observer.supervisor import ObserverSupervisor

        self._llm_enricher = LlmObserverEnricher(llm)
        self._supervisor = ObserverSupervisor()
        with Observer._worker_lock:
            if Observer._worker_pool is None:
                Observer._worker_pool = ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix="observer-llm")

    def submit_async_enrich(self, callback) -> None:
        """P1 scaffold: run LLM enrich off hot path (non-blocking default)."""
        pool = Observer._worker_pool
        if pool is not None:
            pool.submit(callback)

    def set_llm(self, llm) -> None:
        """Wire LLM client for optional enrichment (orchestrator path)."""
        self._llm_enricher.set_llm(llm)

    def observe_turn(
        self,
        memory: "ConversationMemory",
        understanding: TurnUnderstanding,
        *,
        last_exchange: Tuple[str, str] = ("", ""),
    ) -> ObserverPatch:
        base = self._observe_deterministic(
            memory, understanding, last_exchange=last_exchange)
        from conversation_system.observer.llm_enricher import (
            observer_llm_blocking_enabled,
        )
        if not observer_llm_blocking_enabled():
            return base
        enrichment = self._llm_enricher.enrich(
            memory,
            understanding,
            base_directive=base.next_directive,
        )
        if enrichment is None:
            return base
        merged = self._merge_llm_enrichment(
            base, enrichment, memory, understanding)
        return self._supervisor.review(
            merged,
            memory=memory,
            understanding=understanding,
            base_patch=base,
            llm_used=True,
        )

    def _observe_deterministic(
        self,
        memory: "ConversationMemory",
        understanding: TurnUnderstanding,
        *,
        last_exchange: Tuple[str, str] = ("", ""),
    ) -> ObserverPatch:
        state = memory.observer_state
        user_text = understanding.clean_text or ""
        last_user, last_agent = last_exchange
        patches: list[MemoryPatch] = []
        corrections: list[str] = []
        contradictions: list[str] = []
        unanswered: list[str] = list(state.unanswered_user_questions)

        if memory.last_question:
            inferred = infer_pending_from_prompt(
                memory.last_question, turn_no=memory.turn_no)
            if inferred is not None and (
                    state.pending_question is None
                    or state.pending_question.kind == PendingQuestionType.OPEN
                    and inferred.kind != PendingQuestionType.OPEN):
                state.pending_question = inferred
                memory.pending_question = inferred

        pending_invalid = False
        if user_text and state.pending_question is not None:
            valid, reason = validate_pending_answer(
                state.pending_question, user_text)
            if not valid and reason in ("choice_needs_pick", "yes_no_only"):
                pending_invalid = True
                patches.append(MemoryPatch(
                    append_note=f"pending_invalid:{reason}",
                ))

        if user_text and _CORRECTION_RE.search(user_text):
            corrections.append(user_text.strip())
            state.corrections.append(user_text.strip())
            superseded, new_focus = extract_correction_focus(user_text)
            if superseded:
                state.mark_contradicted(superseded)
                if memory.active_symptom and memory.active_symptom == superseded:
                    patches.append(MemoryPatch(
                        set_field={"active_symptom": new_focus or ""},
                    ))
            if new_focus:
                patches.append(MemoryPatch(
                    set_field={"active_symptom": new_focus},
                    add_fact=f"исправление: {new_focus}",
                ))
                state.add_fact(f"симптом: {new_focus}", turn_no=memory.turn_no)
            elif superseded and memory.active_symptom == superseded:
                patches.append(MemoryPatch(set_field={"active_symptom": ""}))

        if user_text and _CONTRADICTION_RE.search(user_text):
            contradictions.append(user_text.strip())
            if memory.active_symptom:
                state.mark_contradicted(memory.active_symptom)

        if understanding.speech_act == SpeechAct.REPAIR:
            pass  # repair requests must not enter unanswered_user_questions
        elif understanding.speech_act == SpeechAct.QUESTION or is_text_question(user_text):
            q = user_text.strip()
            answered = set(state.answered_user_questions)
            if q and q not in unanswered and q not in answered:
                unanswered.append(q)
                state.unanswered_user_questions.append(q)

        if user_text and mentions_symptom(user_text):
            focus = extract_symptom_focus(user_text) or "симптом"
            state.add_fact(f"жалоба: {focus}", turn_no=memory.turn_no)
            patches.append(MemoryPatch(add_fact=f"жалоба: {focus}"))

        if understanding.symptom_resolved:
            state.add_fact("симптом: улучшилось", turn_no=memory.turn_no)
            patches.append(MemoryPatch(
                set_field={"symptom_resolved": True},
                add_fact="симптом: улучшилось",
            ))

        effective_symptom = memory.active_symptom
        for patch in patches:
            if "active_symptom" in patch.set_field:
                effective_symptom = str(patch.set_field["active_symptom"] or "")

        next_directive = self._build_directive(
            memory,
            understanding,
            state,
            corrections=corrections,
            contradictions=contradictions,
            unanswered=unanswered,
            pending_invalid=pending_invalid,
            active_symptom=effective_symptom,
        )
        state.next_directive = next_directive
        memory.next_directive = next_directive
        memory.unanswered_user_questions = list(unanswered)
        memory.corrections = list(state.corrections)
        memory.answered_user_questions = list(state.answered_user_questions)

        if corrections:
            patches.append(MemoryPatch(append_note="correction:ack"))

        return ObserverPatch(
            corrections=tuple(corrections),
            contradictions=tuple(contradictions),
            unanswered_user_questions=tuple(unanswered),
            next_directive=next_directive,
            memory_patches=tuple(patches),
            pending_invalid=pending_invalid,
            llm_enriched=False,
            supervisor_overrides=(),
        )

    def _merge_llm_enrichment(
        self,
        base: ObserverPatch,
        enrichment,
        memory: "ConversationMemory",
        understanding: TurnUnderstanding,
    ) -> ObserverPatch:
        from conversation_system.observer.llm_enricher import LlmEnrichment

        assert isinstance(enrichment, LlmEnrichment)
        state = memory.observer_state
        patches: list[MemoryPatch] = list(base.memory_patches)
        corrections = list(base.corrections)
        contradictions = list(base.contradictions)

        for fact in enrichment.facts:
            state.add_fact(fact, turn_no=memory.turn_no)
            patches.append(MemoryPatch(add_fact=fact))

        for corr in enrichment.corrections:
            if corr not in corrections:
                corrections.append(corr)
                state.corrections.append(corr)

        for contra in enrichment.contradictions:
            if contra not in contradictions:
                contradictions.append(contra)

        directive = base.next_directive
        hint = (enrichment.next_directive_hint or "").strip()
        if hint:
            directive = f"{directive} {hint}".strip() if directive else hint

        if corrections and not base.corrections:
            patches.append(MemoryPatch(append_note="correction:ack"))

        return ObserverPatch(
            corrections=tuple(corrections),
            contradictions=tuple(contradictions),
            unanswered_user_questions=base.unanswered_user_questions,
            next_directive=directive,
            memory_patches=tuple(patches),
            pending_invalid=base.pending_invalid,
            llm_enriched=True,
            supervisor_overrides=(),
        )

    def _build_directive(
        self,
        memory: "ConversationMemory",
        understanding: TurnUnderstanding,
        state: ConversationState,
        *,
        corrections: list[str],
        contradictions: list[str],
        unanswered: list[str],
        pending_invalid: bool,
        active_symptom: str = "",
    ) -> str:
        parts: list[str] = []

        if unanswered:
            last_q = unanswered[-1]
            if _WHY_CALL_RE.search(last_q):
                parts.append(
                    "Коротко объясни зачем звонишь (Имвера, забота, "
                    "запись для близких). Не добавляй вопрос по повестке.")
            elif _PRIVACY_RE.search(last_q):
                parts.append(
                    "Успокой: записываешь для близких по согласию, "
                    "не обещай звонков/врачей.")
            else:
                parts.append(
                    f"Ответь на вопрос абонента: «{last_q[:120]}».")

        if corrections:
            parts.append(
                "Признай исправление («поняла, спина, не голова») "
                "и уточни по новому симптому одним вопросом.")

        if contradictions:
            parts.append(
                "Есть противоречие с прошлым — мягко переспроси, "
                "что верно сейчас.")

        if pending_invalid:
            parts.append(
                "Короткий ответ «да» не подходит — переспроси варианты "
                "или уточни выбор.")

        if understanding.speech_act == SpeechAct.REPAIR:
            parts.append("Повтори свою последнюю фразу чуть иначе, без новой темы.")

        if understanding.is_narrative:
            parts.append(
                "Откликнись на рассказ по существу.")

        if active_symptom or memory.active_symptom:
            focus = active_symptom or memory.active_symptom
            parts.append(f"Активный симптом: {focus}.")

        facts = state.active_facts()
        if facts:
            parts.append("Факты: " + "; ".join(facts[-4:]))

        if memory.last_reply:
            parts.append(f"Ты только что сказала: «{memory.last_reply[:100]}».")

        return " ".join(parts).strip()
