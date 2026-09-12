"""Post-STT turn admission — echo vs fragment vs accept.

Semantic/context relevance blocks text overlap drops.
Text similarity alone never hard-drops user speech.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from packages.voice_perception.echo_match import EchoTextMatch, best_echo_text_match
from packages.voice_perception.echo_ref_gate import EchoVerdict
from packages.voice_perception.fragment_fsm import FRAGMENT_HOLD_TIMEOUT_MS
from packages.voice_perception.text_echo import is_repair_phrase, normalize_speech_text

if TYPE_CHECKING:
    from packages.dialogue_engine.semantic_kernel.types import SemanticKernelResult

FRAGMENT_HOLD_TIMEOUT_S = FRAGMENT_HOLD_TIMEOUT_MS / 1000.0

_VALID_SHORT_ANSWERS = frozenset(
    {
        "да",
        "нет",
        "стоп",
        "позже",
        "сильно",
        "слабо",
        "терпимая",
        "терпимо",
        "не знаю",
        "хорошо",
        "плохо",
        "нормально",
        "не очень",
        "отлично",
        "так себе",
        "угу",
        "ага",
        "мм",
        "ммм",
        "четыре часа",
        "со вчера",
        "давно",
    }
)

# Bare polarity only — HIGH-risk for echo/bleed phantoms (fs-bf61f52b: LOW "Да").
_BARE_POLARITY = frozenset(
    {
        "да",
        "нет",
        "ага",
        "угу",
        "неа",
        "да да",
        "нет нет",
        "ну да",
        "ну нет",
    }
)

# Guard after claimed playout end: LOW bare polarity is treated as phantom.
_LOW_POLARITY_GUARD_MS = 1500

_FRAGMENT_STARTERS = re.compile(
    r"^(но|а|и|ну|же|ли|если|потому что|и ещё|и еще|а ещё|а еще|"
    r"только|хотя|даже|ну я|я же|ну вот|в общем|короче)(\s|$|\.\.\.|…)",
    re.I,
)

_GENERIC_ISSUE_NOUNS = frozenset({"боль", "боли", "болью"})


class TurnAdmissionVerdict(StrEnum):
    ACCEPT = "ACCEPT"
    DROP_ECHO = "DROP_ECHO"
    HOLD_FRAGMENT = "HOLD_FRAGMENT"


@dataclass(frozen=True)
class AssistantPlayoutRef:
    generation_id: str
    text: str
    intent: str = ""
    started_at_mono: float | None = None
    completed_at_mono: float | None = None


@dataclass
class PostSTTContext:
    user_text: str
    last_bot_text: str
    bot_candidates: tuple[str, ...] = ()
    candidate_generation_ids: tuple[str, ...] = ()
    candidate_intents: tuple[str, ...] = ()
    last_playout_generation: str | None = None
    playback_active: bool = False
    milliseconds_since_playout_end: int | None = None
    echo_tail_active: bool = False
    acoustic_echo_score: float = 0.0
    acoustic_echo_verdict: str | None = None
    answer_slot: str | None = None
    pending_episode_attribute: str | None = None
    semantic_result: SemanticKernelResult | None = None
    merged_from_fragment: bool = False
    asr_quality: str | None = None


@dataclass(frozen=True)
class SemanticNoveltySignals:
    has_control: bool
    has_question: bool
    has_correction: bool
    has_repair: bool
    issue_count: int
    body_site_count: int
    duration: bool
    severity: bool
    temporal: bool
    status: bool
    semantic_novelty: bool
    answer_relevance: bool


@dataclass(frozen=True)
class TurnAdmissionDecision:
    verdict: TurnAdmissionVerdict
    confidence: float
    reason: str
    echo_match: EchoTextMatch | None = None
    text_similarity: dict[str, float | bool | str] = field(default_factory=dict)
    acoustic_score: float = 0.0
    semantic_novelty: dict[str, object] = field(default_factory=dict)
    fragment: dict[str, object] = field(default_factory=dict)


def analyze_semantic_novelty(
    result: SemanticKernelResult | None,
    *,
    answer_slot: str | None,
    pending_episode_attribute: str | None,
) -> SemanticNoveltySignals:
    if result is None:
        return SemanticNoveltySignals(
            has_control=False,
            has_question=False,
            has_correction=False,
            has_repair=False,
            issue_count=0,
            body_site_count=0,
            duration=False,
            severity=False,
            temporal=False,
            status=False,
            semantic_novelty=False,
            answer_relevance=False,
        )

    from packages.dialogue_engine.question_context import QuestionNeed
    from packages.dialogue_engine.semantic_kernel.types import SpanType

    spans = result.spans
    has_control = result.control not in ("none", "", None)
    has_question = bool(result.user_question)
    has_correction = bool(result.corrections) or result.dialogue_act == "correction"
    has_repair = result.dialogue_act == "repair"

    issue_count = sum(1 for s in spans if s.type == SpanType.ISSUE)
    body_site_count = sum(1 for s in spans if s.type == SpanType.BODY_SITE)
    duration = any(s.type == SpanType.DURATION for s in spans)
    severity = any(s.type == SpanType.SEVERITY for s in spans)
    temporal = any(s.type in (SpanType.TIME, SpanType.DURATION) for s in spans)
    status = any(s.type == SpanType.STATUS for s in spans)

    obs_attrs = {o.attribute for o in result.observations}
    semantic_novelty = bool(
        has_control
        or has_question
        or has_correction
        or has_repair
        or duration
        or severity
        or temporal
        or status
        or obs_attrs
        or issue_count > 0
        or body_site_count > 0
    )

    answer_relevance = False
    if pending_episode_attribute:
        need = QuestionNeed.for_attribute(pending_episode_attribute.lower())
        if any(
            name in need.accepted_semantics
            and (
                (name in ("duration", "onset") and (temporal or duration))
                or (name == "severity" and severity)
                or (name in ("current", "status") and (status or obs_attrs))
            )
            for name in need.accepted_semantics
        ):
            answer_relevance = True
    if answer_slot and (semantic_novelty or result.observations):
        answer_relevance = True

    if not semantic_novelty:
        semantic_novelty = answer_relevance

    return SemanticNoveltySignals(
        has_control=has_control,
        has_question=has_question,
        has_correction=has_correction,
        has_repair=has_repair,
        issue_count=issue_count,
        body_site_count=body_site_count,
        duration=duration,
        severity=severity,
        temporal=temporal,
        status=status,
        semantic_novelty=semantic_novelty,
        answer_relevance=answer_relevance,
    )


def is_incomplete_fragment(
    user_text: str,
    novelty: SemanticNoveltySignals,
) -> bool:
    normalized = normalize_speech_text(user_text)
    if not normalized:
        return False
    if novelty.semantic_novelty or novelty.answer_relevance:
        return False
    if novelty.has_control or novelty.has_question or novelty.has_correction or novelty.has_repair:
        return False
    if normalized in _VALID_SHORT_ANSWERS:
        return False
    if is_repair_phrase(normalized):
        return False
    if normalized.endswith("...") or normalized.endswith("…"):
        return True
    tokens = normalized.split()
    if len(tokens) == 1 and tokens[0] in {"но", "а", "и", "ну", "же", "ли"}:
        return True
    if _FRAGMENT_STARTERS.match(normalized) and len(tokens) <= 4:
        return True
    if len(tokens) <= 2 and _FRAGMENT_STARTERS.match(normalized):
        return True
    return False


def _acoustic_echo_strong(ctx: PostSTTContext) -> bool:
    verdict = ctx.acoustic_echo_verdict
    if verdict == EchoVerdict.ECHO or verdict == str(EchoVerdict.ECHO):
        return True
    if ctx.playback_active and ctx.acoustic_echo_score >= 0.7:
        return True
    if (
        ctx.echo_tail_active
        and ctx.milliseconds_since_playout_end is not None
        and ctx.milliseconds_since_playout_end < 500
        and ctx.acoustic_echo_score >= 0.85
    ):
        return True
    return False


def _is_probable_playback_echo(match: EchoTextMatch, ctx: PostSTTContext) -> bool:
    if not _near_exact_reproduction(match):
        return False
    if not _acoustic_echo_strong(ctx):
        return False
    return True


def _short_valid_pending_answer(user_text: str) -> bool:
    tokens = normalize_speech_text(user_text).split()
    return 0 < len(tokens) <= 3


def _near_exact_reproduction(match: EchoTextMatch) -> bool:
    if match.exact_match:
        return True
    return (
        match.user_coverage >= 0.95
        and match.bot_coverage >= 0.9
        and match.ordered_similarity >= 0.9
    )


def _is_bare_polarity(user_text: str) -> bool:
    return normalize_speech_text(user_text) in _BARE_POLARITY


def _asr_quality_weak(quality: str | None) -> bool:
    if not quality:
        return False
    q = quality.strip().upper()
    return q in {"LOW", "UNUSABLE", "ASRQUALITY.LOW", "ASRQUALITY.UNUSABLE"}


def _near_playout_guard(ctx: PostSTTContext) -> bool:
    if ctx.playback_active or ctx.echo_tail_active:
        return True
    if ctx.milliseconds_since_playout_end is None:
        return False
    return ctx.milliseconds_since_playout_end < _LOW_POLARITY_GUARD_MS


def _low_quality_bare_polarity_phantom(ctx: PostSTTContext) -> bool:
    """fs-bf61f52b: LOW 'Да' accepted via default_accept while opening still audible."""
    if not _asr_quality_weak(ctx.asr_quality):
        return False
    if not _is_bare_polarity(ctx.user_text):
        return False
    return _near_playout_guard(ctx)


def evaluate_post_stt_turn(ctx: PostSTTContext) -> TurnAdmissionDecision:
    """Admission order: empty → fragment → semantic relevance → acoustic echo → accept."""
    novelty = analyze_semantic_novelty(
        ctx.semantic_result,
        answer_slot=ctx.answer_slot,
        pending_episode_attribute=ctx.pending_episode_attribute,
    )
    echo_match = best_echo_text_match(
        ctx.user_text,
        ctx.bot_candidates,
        primary_bot=ctx.last_bot_text,
        generation_ids=ctx.candidate_generation_ids,
        intents=ctx.candidate_intents,
    )
    metrics = echo_match.as_dict() if echo_match else {}

    fragment_info: dict[str, object] = {
        "incomplete": False,
        "held": False,
        "merged_with_next": ctx.merged_from_fragment,
        "timeout_ms": FRAGMENT_HOLD_TIMEOUT_MS,
    }

    if is_incomplete_fragment(ctx.user_text, novelty) and not ctx.merged_from_fragment:
        fragment_info["incomplete"] = True
        fragment_info["held"] = True
        return TurnAdmissionDecision(
            verdict=TurnAdmissionVerdict.HOLD_FRAGMENT,
            confidence=0.85,
            reason="incomplete_fragment",
            echo_match=echo_match,
            text_similarity=metrics,
            acoustic_score=ctx.acoustic_echo_score,
            semantic_novelty=_novelty_payload(novelty),
            fragment=fragment_info,
        )

    if _low_quality_bare_polarity_phantom(ctx):
        return TurnAdmissionDecision(
            verdict=TurnAdmissionVerdict.DROP_ECHO,
            confidence=0.9,
            reason="low_quality_bare_polarity_near_playout",
            echo_match=echo_match,
            text_similarity=metrics,
            acoustic_score=ctx.acoustic_echo_score,
            semantic_novelty=_novelty_payload(novelty),
            fragment=fragment_info,
        )

    if novelty.answer_relevance and echo_match and _is_probable_playback_echo(echo_match, ctx):
        if not _short_valid_pending_answer(ctx.user_text):
            novelty = SemanticNoveltySignals(
                **{**novelty.__dict__, "answer_relevance": False}
            )

    if novelty.answer_relevance or novelty.has_repair:
        return TurnAdmissionDecision(
            verdict=TurnAdmissionVerdict.ACCEPT,
            confidence=0.98,
            reason="semantic_answer_relevance",
            echo_match=echo_match,
            text_similarity=metrics,
            acoustic_score=ctx.acoustic_echo_score,
            semantic_novelty=_novelty_payload(novelty),
            fragment=fragment_info,
        )

    if echo_match is not None and _is_probable_playback_echo(echo_match, ctx):
        return TurnAdmissionDecision(
            verdict=TurnAdmissionVerdict.DROP_ECHO,
            confidence=0.92,
            reason="exact_echo_with_acoustic",
            echo_match=echo_match,
            text_similarity=metrics,
            acoustic_score=ctx.acoustic_echo_score,
            semantic_novelty=_novelty_payload(novelty),
            fragment=fragment_info,
        )

    if novelty.semantic_novelty:
        return TurnAdmissionDecision(
            verdict=TurnAdmissionVerdict.ACCEPT,
            confidence=0.95,
            reason="semantic_novelty",
            echo_match=echo_match,
            text_similarity=metrics,
            acoustic_score=ctx.acoustic_echo_score,
            semantic_novelty=_novelty_payload(novelty),
            fragment=fragment_info,
        )

    if novelty.has_control or novelty.has_question:
        return TurnAdmissionDecision(
            verdict=TurnAdmissionVerdict.ACCEPT,
            confidence=0.9,
            reason="meaningful_speech",
            echo_match=echo_match,
            text_similarity=metrics,
            acoustic_score=ctx.acoustic_echo_score,
            semantic_novelty=_novelty_payload(novelty),
            fragment=fragment_info,
        )

    if is_repair_phrase(normalize_speech_text(ctx.user_text)):
        return TurnAdmissionDecision(
            verdict=TurnAdmissionVerdict.ACCEPT,
            confidence=0.8,
            reason="repair_phrase",
            echo_match=echo_match,
            text_similarity=metrics,
            acoustic_score=ctx.acoustic_echo_score,
            semantic_novelty=_novelty_payload(novelty),
            fragment=fragment_info,
        )

    return TurnAdmissionDecision(
        verdict=TurnAdmissionVerdict.ACCEPT,
        confidence=0.75,
        reason="default_accept",
        echo_match=echo_match,
        text_similarity=metrics,
        acoustic_score=ctx.acoustic_echo_score,
        semantic_novelty=_novelty_payload(novelty),
        fragment=fragment_info,
    )


def _novelty_payload(novelty: SemanticNoveltySignals) -> dict[str, object]:
    return {
        "has_control": novelty.has_control,
        "has_question": novelty.has_question,
        "has_correction": novelty.has_correction,
        "has_repair": novelty.has_repair,
        "issue_count": novelty.issue_count,
        "body_site_count": novelty.body_site_count,
        "duration": novelty.duration,
        "severity": novelty.severity,
        "temporal": novelty.temporal,
        "status": novelty.status,
        "semantic_novelty": novelty.semantic_novelty,
        "answer_relevance": novelty.answer_relevance,
    }


def filter_phantom_generic_issues(
    mentions: tuple,
    *,
    active_episode_id: str | None,
    pending_episode_attribute: str | None,
) -> tuple:
    """Drop generic pain-noun episodes when answering a pending attribute."""
    if not active_episode_id or not pending_episode_attribute:
        return mentions
    filtered = []
    for mention in mentions:
        label = (mention.label or "").strip().lower()
        if label in _GENERIC_ISSUE_NOUNS and not mention.body_site:
            continue
        filtered.append(mention)
    return tuple(filtered)
