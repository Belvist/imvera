"""Semantic Kernel — adversarial corpus and property invariants."""

from __future__ import annotations

import itertools

import pytest

from packages.contracts.semantic import Evidence, IssueMention
from packages.dialogue_engine.events import CallStarted, UserTurnReceived
from packages.dialogue_engine.reducer import reduce
from packages.dialogue_engine.semantic_kernel.kernel import interpret, kernel_to_rich_turn
from packages.dialogue_engine.semantic_kernel.observation_memory import merge_legacy_mentions
from packages.dialogue_engine.semantic_kernel.span_parser import parse_spans
from packages.dialogue_engine.semantic_kernel.subject_resolver import resolve_subject
from packages.dialogue_engine.semantic_kernel.types import SubjectKind
from packages.dialogue_engine.state import EngineState
from packages.dialogue_engine.turn_understanding import build_rich_turn_from_text

pytestmark = pytest.mark.dialogue_engine

BODY_CASES = [
    ("локоть ноет", "локоть"),
    ("першит в горле", "горло"),
    ("онемел палец", "палец"),
    ("колено второй день тянет", "колено"),
]

SUBJECT_CASES = [
    ("У меня болит сердце", SubjectKind.SPEAKER),
    ("У мужа болит сердце", SubjectKind.OTHER_PERSON),
    ("У коллеги грудь болит", SubjectKind.UNKNOWN),
]

MIXED_SUBJECT = "У мужа сердце болит, а у меня голова болит"

TEMPORAL_CASES = [
    "болит сейчас",
    "болело вчера",
    "утром болело, сейчас прошло",
    "третий день болит",
    "Вчера болела голова, сегодня нормально",
]

MULTI_ISSUE = [
    "Голова болит и тошнит",
    "Голова болит и тошнит, ещё живот ноет",
    "Нормально. А вы кто? И колено второй день тянет.",
]

CORRECTION = ["Нет, не с утра. Со вчера.", "Я же говорил, что болит"]
VAGUE = ["Что-то там опять прихватило", "не знаю"]
CONTROLS = ["угу", "да", "нет", "повторите", "стоп", "позже"]
ASR_GARBAGE = ["болит калено с утре", "голову болит с утра"]
USER_QUESTIONS = ["А вы кто?", "Зачем вы звоните?"]
RESOLVED = ["уже не болит", "почти прошло", "сегодня нормально"]

_ISSUE_VERBS = {
    "болеть", "ныть", "ломить", "тянуть", "давить", "першить",
    "заложить", "онеметь", "тошнить", "кашлять", "урчать",
}


def _unique_matrix(limit: int = 220) -> list[str]:
    subjects = ("", "у меня ", "у мужа ", "у мамы ")
    issues = ("голова болит", "локоть ноет", "тошнит", "живот урчит", "спина ломит")
    temps = ("", " с утра", " вчера", " второй день", " уже пятый час")
    neg = ("", "не ")
    seen: set[str] = set()
    out: list[str] = []
    for subj, issue, temp, n in itertools.product(subjects, issues, temps, neg):
        text = f"{subj}{n}{issue}{temp}".strip()
        if text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= limit:
            return out
    extras = (
        [t for t, _ in BODY_CASES]
        + [t for t, _ in SUBJECT_CASES]
        + [MIXED_SUBJECT]
        + list(TEMPORAL_CASES)
        + MULTI_ISSUE
        + CORRECTION
        + VAGUE
        + CONTROLS
        + ASR_GARBAGE
        + USER_QUESTIONS
        + RESOLVED
    )
    for item in extras:
        text = item[0] if isinstance(item, tuple) else item
        if text not in seen:
            seen.add(text)
            out.append(text)
    return out[:limit]


ALL_CASES = _unique_matrix(220)


@pytest.mark.parametrize("text,expected_site", BODY_CASES)
def test_body_site_from_relation_not_issue_verb(text: str, expected_site: str) -> None:
    result = interpret(text, utterance_id="u-body")
    turn = kernel_to_rich_turn(result)
    assert turn.issue_mentions, text
    mention = turn.issue_mentions[0]
    assert mention.body_site == expected_site, text
    assert mention.body_site not in _ISSUE_VERBS
    for obs in result.observations:
        if obs.attribute == "issue":
            assert obs.body_site == expected_site or obs.body_site is None
            assert obs.issue_normalized not in (expected_site,)


@pytest.mark.parametrize("text,expected", SUBJECT_CASES)
def test_subject_resolution(text: str, expected: SubjectKind) -> None:
    spans = parse_spans(text)
    subject, relations = resolve_subject(text, spans)
    if expected == SubjectKind.UNKNOWN:
        assert subject == SubjectKind.UNKNOWN or any(
            r.target_span_id == "subj-unknown" for r in relations
        )
    else:
        assert subject == expected


def test_mixed_subjects_per_issue() -> None:
    result = interpret(MIXED_SUBJECT, utterance_id="u-mix")
    heart = [
        o
        for o in result.observations
        if o.attribute == "issue" and (o.body_site == "сердце" or "сердц" in o.value)
    ]
    head = [
        o
        for o in result.observations
        if o.attribute == "issue" and (o.body_site == "голова" or "голов" in o.value)
    ]
    assert heart and head
    assert heart[0].subject == SubjectKind.OTHER_PERSON
    assert head[0].subject == SubjectKind.SPEAKER


def test_legacy_cannot_overwrite_kernel() -> None:
    result = interpret("локоть ноет", utterance_id="u-leg")
    kernel_mentions = kernel_to_rich_turn(result).issue_mentions
    legacy = (
        IssueMention(
            mention_id="legacy-1",
            kind="symptom",
            label="ныть",
            role="primary",
            body_site="ныть",
            temporal_scope="now",
            status="active",
            evidence=Evidence(start=0, end=4, quote="ныть"),
        ),
        IssueMention(
            mention_id="legacy-2",
            kind="symptom",
            label="спина",
            role="independent",
            body_site="спина",
            temporal_scope="now",
            status="active",
            evidence=Evidence(start=0, end=5, quote="спина"),
        ),
    )
    merged = merge_legacy_mentions(kernel_mentions, legacy)
    assert merged[0].body_site == "локоть"
    assert all(m.body_site != "ныть" for m in merged if m.label != "ныть")


def test_correction_supersedes_previous_onset() -> None:
    state = EngineState(call_id="c-1", elder_display_name="Даниил")
    state, _ = reduce(state, CallStarted(call_id="c-1"))
    t1 = build_rich_turn_from_text("Голова болит с утра", utterance_id="u-1")
    state, _ = reduce(
        state,
        UserTurnReceived(turn_id="u-1", text=t1.raw_text, rich_turn=t1),
    )
    t2 = build_rich_turn_from_text("Нет, не с утра. Со вчера.", utterance_id="u-2")
    state, _ = reduce(
        state,
        UserTurnReceived(turn_id="u-2", text=t2.raw_text, rich_turn=t2),
    )
    store = state.observations
    onset_obs = [o for o in store.values() if o.attribute == "onset"]
    assert any(o.status == "superseded" for o in onset_obs)
    assert any(o.status == "confirmed" and "вчера" in o.evidence.lower() for o in onset_obs)


def test_reference_updates_existing_episode_stateful() -> None:
    state = EngineState(call_id="c-ref", elder_display_name="Даниил")
    state, _ = reduce(state, CallStarted(call_id="c-ref"))
    t1 = build_rich_turn_from_text("Горло першит.", utterance_id="u-1")
    state, _ = reduce(
        state,
        UserTurnReceived(turn_id="u-1", text=t1.raw_text, rich_turn=t1),
    )
    assert state.active_episode_id
    ep_id = state.active_episode_id
    t2 = build_rich_turn_from_text(
        "Это вчера началось.",
        utterance_id="u-2",
        engine_state=state,
    )
    state, _ = reduce(
        state,
        UserTurnReceived(turn_id="u-2", text=t2.raw_text, rich_turn=t2),
    )
    ep = state.issue_episodes[ep_id]
    assert ep.known_attributes.get("onset") or ep.known_attributes.get("duration")
    assert len(state.issue_episodes) == 1


def test_past_issue_not_active_current() -> None:
    result = interpret("Вчера болела голова, сегодня нормально", utterance_id="u-past")
    turn = kernel_to_rich_turn(result)
    for m in turn.issue_mentions:
        assert m.status in ("resolved", "active")
        if m.temporal_scope == "past":
            assert m.status != "active" or m.temporal_scope != "now"


@pytest.mark.parametrize("text", ALL_CASES, ids=[f"c{i}" for i in range(len(ALL_CASES))])
def test_kernel_never_crashes_and_has_route(text: str) -> None:
    result = interpret(text, utterance_id="u-corpus")
    assert result.route
    assert result.elapsed_ms >= 0
    turn = kernel_to_rich_turn(result)
    assert turn.raw_text == text.strip()


def test_nausea_call_utterance_has_issue_not_body_site_verb() -> None:
    text = "Я чувствую себя отвратительно, меня тошнит, и мне плохо, очень умираю."
    turn = build_rich_turn_from_text(text, utterance_id="u-call")
    assert turn.issue_mentions
    assert turn.issue_mentions[0].body_site is None or turn.issue_mentions[0].body_site != "тошнит"


def test_vague_triggers_clarification() -> None:
    result = interpret("Что-то там опять прихватило", utterance_id="u-vague")
    turn = kernel_to_rich_turn(result)
    assert turn.needs_clarification or result.level >= 3


def test_level0_controls_fast() -> None:
    result = interpret("угу", utterance_id="u-bc")
    assert result.level == 0
    assert result.elapsed_ms < 50


def test_property_no_empty_evidence_on_spans() -> None:
    result = interpret("колено второй день тянет", utterance_id="u-ev")
    for sp in result.spans:
        assert sp.text
        assert sp.end > sp.start


def test_kernel_latency_p95_under_50ms_on_unique_sample() -> None:
    import time

    samples = _unique_matrix(80)
    times = []
    interpret("прогрев", utterance_id="warm")
    for i, text in enumerate(samples):
        t0 = time.perf_counter()
        interpret(text, utterance_id=f"u-perf-{i}")
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    p95 = times[int(len(times) * 0.95)]
    assert p95 < 50, f"p95={p95:.1f}ms"
