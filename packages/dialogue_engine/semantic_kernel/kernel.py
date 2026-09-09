"""Turn Semantic Kernel — STT final → RichUserTurn meaning."""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from packages.dialogue_engine.issue_mention_extract import (
    detect_correction,
    detect_user_question,
    extract_goal_facts,
)
from packages.dialogue_engine.semantic_kernel.ml_fallback import ml_enhance_spans
from packages.dialogue_engine.semantic_kernel.observation_memory import (
    build_observations,
    observations_to_issue_mentions,
)
from packages.dialogue_engine.semantic_kernel.reference_resolver import resolve_references
from packages.dialogue_engine.semantic_kernel.relation_parser import parse_relations
from packages.dialogue_engine.semantic_kernel.span_parser import parse_spans
from packages.dialogue_engine.semantic_kernel.subject_resolver import resolve_subject
from packages.dialogue_engine.semantic_kernel.types import (
    CorrectionRecord,
    SemanticKernelResult,
    SpanType,
)

if TYPE_CHECKING:
    from packages.dialogue_engine.state import EngineState

_USER_QUESTION = re.compile(
    r"(кто\s+вы|зачем\s+звон|почему\s+звон|а\s+вы\s+кто|что\s+вы\s+хотите)",
    re.I,
)
_CORRECTION = re.compile(r"\b(нет,?\s+не|я\s+же\s+говорил\w*|говорил\w*\s+же)\b", re.I)
_VAGUE_ISSUE = re.compile(r"\bчто-то\s+там\b|\bопять\s+прихватил\w*\b", re.I)


def _level0_control(text: str) -> str | None:
    norm = text.strip().lower()
    from packages.dialogue_engine.semantic_kernel.lexicon import CONTROL_EXACT

    for phrase, control in sorted(CONTROL_EXACT.items(), key=lambda x: -len(x[0])):
        if norm == phrase or norm.startswith(phrase + " "):
            return control
    return None


def _parse_corrections(text: str) -> tuple[CorrectionRecord, ...]:
    records: list[CorrectionRecord] = []
    m = re.search(
        r"нет,?\s+не\s+([^.;]+?)(?:\.|;|$|\s+со\s+)",
        text,
        re.I,
    )
    if m:
        old_part = m.group(1).strip()
        new_m = re.search(r"(со\s+вчера|с\s+вчера|вчера|с\s+утра)", text[m.end() :], re.I)
        if new_m:
            records.append(
                CorrectionRecord(
                    target="onset",
                    old_evidence=old_part,
                    new_evidence=new_m.group(0),
                )
            )
    return tuple(records)


def interpret(
    text: str,
    *,
    utterance_id: str,
    engine_state: EngineState | None = None,
    answer_slot: str | None = None,
) -> SemanticKernelResult:
    started = time.perf_counter()
    raw = text.strip()
    if not raw:
        return SemanticKernelResult(
            raw_text=raw,
            utterance_id=utterance_id,
            confidence=0.0,
            ambiguity=("empty",),
            level=0,
            route="kernel_empty",
        )

    control = _level0_control(raw)
    if control:
        act = "backchannel" if control == "backchannel" else "answer"
        elapsed = (time.perf_counter() - started) * 1000
        return SemanticKernelResult(
            raw_text=raw,
            utterance_id=utterance_id,
            dialogue_act=act,
            control=control,
            confidence=1.0,
            level=0,
            route="kernel_l0",
            elapsed_ms=elapsed,
        )

    spans = parse_spans(raw)
    spans = ml_enhance_spans(raw, spans)
    relations = list(parse_relations(spans))
    subject, subj_rels = resolve_subject(raw, spans)
    relations.extend(subj_rels)
    relations.extend(resolve_references(raw, spans, engine_state))
    span_tuple = tuple(spans)
    rel_tuple = tuple(relations)

    corrections = _parse_corrections(raw)
    user_q = detect_user_question(raw)
    if user_q is None and _USER_QUESTION.search(raw):
        user_q = raw.strip()

    dialogue_act = "answer"
    if detect_correction(raw) or corrections:
        dialogue_act = "correction"
    elif user_q:
        dialogue_act = "question"

    ambiguity: list[str] = []
    confidence = 0.85
    if _VAGUE_ISSUE.search(raw.lower()) and not any(
        s.type == SpanType.BODY_SITE for s in span_tuple
    ):
        ambiguity.append("vague_issue")
        confidence = 0.35

    if not span_tuple and not user_q and answer_slot:
        confidence = min(confidence, 0.5)

    partial = SemanticKernelResult(
        raw_text=raw,
        utterance_id=utterance_id,
        dialogue_act=dialogue_act,
        spans=span_tuple,
        relations=rel_tuple,
        user_question=user_q,
        corrections=corrections,
        confidence=confidence,
        ambiguity=tuple(ambiguity),
        level=1 if confidence >= 0.5 else 3,
        route="kernel_l1" if confidence >= 0.5 else "kernel_l3_clarify",
    )
    observations = build_observations(partial)
    elapsed = (time.perf_counter() - started) * 1000
    return partial.model_copy(
        update={"observations": observations, "elapsed_ms": elapsed}
    )


def kernel_to_rich_turn(result: SemanticKernelResult):
    from packages.dialogue_engine.turn_understanding import RichUserTurn

    mentions = observations_to_issue_mentions(result.observations, result.raw_text)
    from packages.dialogue_engine.issue_mention_extract import extract_issue_mentions

    legacy = extract_issue_mentions(result.raw_text)
    if legacy and (not mentions or len(legacy) >= 2):
        mentions = legacy
    elif legacy and not mentions:
        mentions = legacy
    if not mentions and result.spans:
        from packages.dialogue_engine.issue_mention_extract import extract_issue_mentions

        mentions = extract_issue_mentions(result.raw_text)

    needs_clarify = result.level >= 3 or "vague_issue" in result.ambiguity
    goal_facts = extract_goal_facts(result.raw_text)
    return RichUserTurn(
        utterance_id=result.utterance_id,
        raw_text=result.raw_text,
        dialogue_act=result.dialogue_act,
        control=result.control,
        answers_pending_question=result.dialogue_act == "answer" and not needs_clarify,
        needs_clarification=needs_clarify,
        user_question=result.user_question,
        goal_facts=goal_facts,
        issue_mentions=mentions,
        correction=result.dialogue_act == "correction" or bool(result.corrections),
        semantic_spans=result.spans,
        semantic_relations=result.relations,
        observations=result.observations,
        kernel_confidence=result.confidence,
        kernel_ambiguities=result.ambiguity,
        kernel_level=result.level,
        kernel_route=result.route,
        kernel_elapsed_ms=result.elapsed_ms,
        kernel_corrections=result.corrections,
    )


def clarify_text(result: SemanticKernelResult) -> str:
    return "Уточните, пожалуйста, что именно сейчас беспокоит?"
