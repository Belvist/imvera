"""Semantic Kernel — adversarial corpus and property invariants."""

from __future__ import annotations

import itertools

import pytest

from packages.dialogue_engine.semantic_kernel.kernel import interpret, kernel_to_rich_turn
from packages.dialogue_engine.semantic_kernel.span_parser import parse_spans
from packages.dialogue_engine.semantic_kernel.subject_resolver import resolve_subject
from packages.dialogue_engine.semantic_kernel.types import SpanType, SubjectKind
from packages.dialogue_engine.turn_understanding import build_rich_turn_from_text

pytestmark = pytest.mark.dialogue_engine

# --- generators: constructions, not symptom enums ---

PARAPHRASE_ISSUES = [
    "локоть ноет",
    "онемел палец",
    "шею тянет",
    "першит в горле",
    "ухо заложило",
    "тяжесть в груди",
    "колено второй день тянет",
    "поясницу ломит",
    "виски стреляют",
    "живот урчит и болит",
]

MULTI_ISSUE = [
    "Голова болит и тошнит",
    "Голова болит и тошнит, ещё живот ноет",
    "Ухо заложило после самолёта, но уже почти прошло",
    "Нормально. А вы кто? И колено второй день тянет.",
]

TEMPORAL = [
    "болит сейчас",
    "болело вчера",
    "утром болело, сейчас прошло",
    "третий день болит",
    "с десяти утра",
    "иногда болит",
    "Вчера болела голова, сегодня нормально",
]

SUBJECT = [
    "У меня болит сердце",
    "У мужа болит сердце",
    "Мама плохо спит",
    "Мне врач сказал, что давление высокое",
]

CORRECTION = [
    "Нет, не с утра. Со вчера.",
    "Я же говорил, что болит",
]

VAGUE = [
    "Что-то там опять прихватило",
    "не знаю",
]

CONTROLS = ["угу", "да", "нет", "повторите", "стоп", "позже"]

ASR_GARBAGE = [
    "болит калено с утре",
    "голову болит с утра",
]

USER_QUESTIONS = [
    "А вы кто?",
    "Зачем вы звоните?",
]

BACKCHANNEL = ["угу", "ага"]

RESOLVED = [
    "уже не болит",
    "почти прошло",
    "сегодня нормально",
]

ALL_CASES = list(
    itertools.islice(
        itertools.cycle(
            PARAPHRASE_ISSUES
            + MULTI_ISSUE
            + TEMPORAL
            + SUBJECT
            + CORRECTION
            + VAGUE
            + CONTROLS
            + ASR_GARBAGE
            + USER_QUESTIONS
            + BACKCHANNEL
            + RESOLVED
        ),
        220,
    )
)


@pytest.mark.parametrize("text", ALL_CASES, ids=[f"c{i}" for i in range(len(ALL_CASES))])
def test_kernel_never_crashes_and_has_route(text: str) -> None:
    result = interpret(text, utterance_id="u-corpus")
    assert result.route
    assert result.elapsed_ms >= 0
    turn = kernel_to_rich_turn(result)
    assert turn.raw_text == text.strip()


def test_arbitrary_body_site_without_named_regex_branch() -> None:
    """Sites not in legacy issue_mention_extract must still get BODY_SITE span."""
    for text in ("локоть ноет", "онемел палец", "першит в горле"):
        spans = parse_spans(text)
        assert any(s.type == SpanType.BODY_SITE for s in spans), text
        assert any(s.type == SpanType.ISSUE for s in spans), text


def test_other_person_not_speaker() -> None:
    subject, _ = resolve_subject("У мужа болит сердце", parse_spans("У мужа болит сердце"))
    assert subject == SubjectKind.OTHER_PERSON


def test_vague_triggers_clarification() -> None:
    result = interpret("Что-то там опять прихватило", utterance_id="u-vague")
    turn = kernel_to_rich_turn(result)
    assert turn.needs_clarification or result.level >= 3


def test_meaningful_turn_produces_speech_via_rich_turn() -> None:
    turn = build_rich_turn_from_text("Голова болит с утра", utterance_id="u-1")
    assert turn.issue_mentions or turn.semantic_spans


def test_never_invent_diagnosis_label() -> None:
    turn = build_rich_turn_from_text("голова болит", utterance_id="u-d")
    for m in turn.issue_mentions:
        assert m.label.lower() not in {"мигрень", "гастрит", "артрит"}


def test_temporal_yesterday_not_current_now() -> None:
    result = interpret("Вчера болела голова, сегодня нормально", utterance_id="u-t")
    for obs in result.observations:
        if obs.temporal.onset and "вчера" in obs.temporal.onset.lower():
            assert obs.temporal.current is not True


def test_level0_controls_fast() -> None:
    result = interpret("угу", utterance_id="u-bc")
    assert result.level == 0
    assert result.elapsed_ms < 50


def test_property_no_empty_evidence_on_spans() -> None:
    result = interpret("колено второй день тянет", utterance_id="u-ev")
    for sp in result.spans:
        assert sp.text
        assert sp.end > sp.start


def test_kernel_latency_p95_under_50ms_on_sample() -> None:
    import time

    samples = PARAPHRASE_ISSUES * 20
    times = []
    for i, text in enumerate(samples):
        t0 = time.perf_counter()
        interpret(text, utterance_id=f"u-perf-{i}")
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    p95 = times[int(len(times) * 0.95)]
    assert p95 < 50, f"p95={p95:.1f}ms"
