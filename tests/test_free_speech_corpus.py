"""Deterministic free-speech corpus — Phase 2 dialogue invariants without live SIP."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from packages.contracts.enums import SlotStatus
from packages.contracts.semantic import Evidence, IssueMention, SemanticPayload
from packages.dialogue_engine.events import CallStarted, User
from packages.dialogue_engine.issue_memory import ingest_rich_turn
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.state import EngineState
from packages.dialogue_engine.turn_understanding import (
    build_rich_turn_from_payload,
    build_rich_turn_from_text,
)

pytestmark = pytest.mark.dialogue_engine


@dataclass(frozen=True)
class CorpusCase:
    id: str
    category: str
    steps: tuple[str, ...]
    forbid_intents: tuple[str, ...] = ()
    require_any_intent_prefix: tuple[str, ...] = ()
    control: str | None = None


def _control_user(control: str, text: str) -> User:
    payload = SemanticPayload(
        dialogue_act="answer",
        control=control,
        control_evidence=Evidence(start=0, end=len(text), quote=text),
        consent_answer="not_applicable",
        answers_pending_question=False,
        needs_clarification=False,
    )
    return User(
        text=text,
        rich_turn=build_rich_turn_from_payload(
            payload,
            utterance_id=f"u-{control}",
            raw_text=text,
        ),
    )


def _runner() -> ScenarioRunner:
    return ScenarioRunner(call_id="fs-corpus", elder_display_name="Тест")


def _mention(quote: str, label: str, *, body_site: str | None = None) -> IssueMention:
    return IssueMention(
        mention_id=f"m-{label[:6]}",
        kind="symptom",
        label=label,
        role="primary",
        body_site=body_site,
        temporal_scope="now",
        status="active",
        evidence={"start": 0, "end": len(quote), "quote": quote},
    )


_NO_ABDOMEN = ("topic_abdominal_pain_current",)

CORPUS: tuple[CorpusCase, ...] = (
    CorpusCase(
        "multi-headache-nausea",
        "multi_symptom",
        ("Голова болит и тошнит.",),
        forbid_intents=_NO_ABDOMEN,
    ),
    CorpusCase(
        "ear-blocked",
        "new_body_site",
        ("Ухо заложило",),
        forbid_intents=_NO_ABDOMEN,
    ),
    CorpusCase(
        "throat-scratch",
        "generic_issue",
        ("Першит горло",),
        forbid_intents=_NO_ABDOMEN,
    ),
    CorpusCase("finger-numb", "new_body_site", ("Онемел палец",), ()),
    CorpusCase("back-pull", "new_body_site", ("Спину тянет",), ()),
    CorpusCase("heart-morning", "multi_symptom", ("Сердце с утра болит",), ()),
    CorpusCase("unknown-chest", "unknown_answer", ("Не знаю, но грудь давит.",), ()),
    CorpusCase("ok-forgot-pills", "background_goals", ("Да нормально, только таблетки забыл",), ()),
    CorpusCase(
        "who-are-you",
        "user_question",
        ("А кто вы вообще?",),
        require_any_intent_prefix=("answer_user_question",),
    ),
    CorpusCase("correction", "correction", ("Я же говорил, что болит",), ()),
    CorpusCase("improving", "resolved", ("Сейчас уже почти прошло",), ()),
    CorpusCase("backchannel", "backchannel", ("Угу",), ()),
    CorpusCase("unknown-onset", "unknown_answer", ("Не помню",), ()),
    CorpusCase("onset-time", "partial_answer", ("С десяти утра",), ()),
    CorpusCase("sleep-dizzy", "topic_switch", ("Ночью плохо спал, сейчас голова кружится",), ()),
    CorpusCase("wellness-bad", "wellness", ("мне плохо",), ()),
    CorpusCase("wellness-good", "wellness", ("Хорошо себя чувствую",), ()),
    CorpusCase("mood-bad", "mood", ("Настроение ужасное",), ()),
    CorpusCase("plans-none", "plans", ("Планов никаких",), ()),
    CorpusCase("sleep-bad", "sleep", ("Почти не спал",), ()),
    CorpusCase(
        "stop-call",
        "control",
        ("Не хочу больше разговаривать",),
        require_any_intent_prefix=("goodbye",),
        control="stop_call",
    ),
    CorpusCase(
        "defer",
        "control",
        ("Позвоните позже",),
        require_any_intent_prefix=("defer",),
        control="defer",
    ),
    CorpusCase(
        "wrong-person",
        "control",
        ("Вы ошиблись номером",),
        require_any_intent_prefix=("wrong_person",),
        control="wrong_person",
    ),
    CorpusCase(
        "mixed-wellness",
        "multi_symptom",
        ("Состояние не очень, голова болит и тошнит.",),
        forbid_intents=_NO_ABDOMEN,
    ),
    CorpusCase("chest-pressure", "new_body_site", ("Давит в груди",), ()),
    CorpusCase("knee-pain", "new_body_site", ("Колено болит",), ()),
    CorpusCase("toothache", "new_body_site", ("Зуб болит",), ()),
    CorpusCase("cough", "generic_issue", ("Кашляю",), ()),
    CorpusCase("fever", "generic_issue", ("Температура",), ()),
    CorpusCase("dizzy-alone", "generic_issue", ("Голова кружится",), ()),
    CorpusCase("nausea-alone", "associated", ("Тошнит",), ()),
    CorpusCase(
        "abdominal-explicit",
        "topic_switch",
        ("Болит живот",),
        # old transport: topic_abdominal_pain_* → canonical: IssueEpisode + onset probe
        require_any_intent_prefix=("episode_",),
    ),
    CorpusCase(
        "sleep-topic",
        "topic_switch",
        ("Плохо спал",),
        # old transport: topic_sleep_* → canonical: sleep slot + sleep_problem episode
        require_any_intent_prefix=("check_mood", "episode_"),
    ),
    CorpusCase("repair-hearing", "user_question", ("Повторите, пожалуйста",), ()),
    CorpusCase(
        "goodbye",
        "control",
        ("До свидания",),
        require_any_intent_prefix=("goodbye",),
        control="stop_call",
    ),
    CorpusCase("yes-confirm", "backchannel", ("Да",), ()),
    CorpusCase("no-answer", "unknown_answer", ("Не знаю",), ()),
    CorpusCase("complex-mixed", "multi_symptom", ("Голова болит, и ещё першит горло",), ()),
    CorpusCase("medication-forgot", "background_goals", ("Забыл таблетки выпить",), ()),
    CorpusCase("mood-okay", "mood", ("Настроение нормальное",), ()),
    CorpusCase("plans-walk", "plans", ("Пойду гулять",), ()),
    CorpusCase("sleep-ok", "sleep", ("Спал хорошо",), ()),
    CorpusCase("wellness-so-so", "wellness", ("Так себе",), ()),
    CorpusCase("chest-unknown-mixed", "unknown_answer", ("Не знаю, но ещё грудь давит.",), ()),
    CorpusCase("onset-with-new", "partial_answer", ("С десяти утра, и ещё грудь давит.",), ()),
    CorpusCase("headache-onset", "partial_answer", ("С 10 утра",), ()),
    CorpusCase("severity", "partial_answer", ("Сильная",), ()),
    CorpusCase("improving-headache", "resolved", ("Голова уже легче",), ()),
    CorpusCase("associated-nausea", "associated", ("Голова болит и тошнит",), ()),
)


@pytest.mark.parametrize("case", CORPUS, ids=[c.id for c in CORPUS])
def test_free_speech_corpus_case(case: CorpusCase) -> None:
    runner = _runner()
    runner.run([CallStarted()])
    if case.id == "wellness-bad":
        runner.state.wellness_probes_enabled = False
    for step in case.steps:
        if case.control:
            runner.run([_control_user(case.control, step)])
        else:
            runner.run([step])
    speaks = [e for e in runner.effects if hasattr(e, "intent")]
    intents = [e.intent for e in speaks]
    for forbidden in case.forbid_intents:
        assert forbidden not in intents, f"{case.id}: forbidden {forbidden}"
    if case.require_any_intent_prefix:
        assert any(
            any(i.startswith(p) for p in case.require_any_intent_prefix) for i in intents
        ), f"{case.id}: expected one of {case.require_any_intent_prefix}, got {intents}"
    partial_close = any(i == "partial_unresolved_close" for i in intents)
    assert not partial_close or case.category == "control", (
        f"{case.id}: unexpected partial_unresolved_close"
    )


def test_unknown_chest_does_not_fill_headache_onset() -> None:
    state = EngineState(call_id="t", elder_display_name="Тест")
    ingest_rich_turn(
        state,
        build_rich_turn_from_text("Голова болит.", utterance_id="u-1"),
    )
    state.pending_episode_attribute = "onset"
    quote = "Не знаю, но ещё грудь давит."
    chest = _mention(quote, "давление в груди", body_site="грудь")
    ingest_rich_turn(
        state,
        build_rich_turn_from_payload(
            SemanticPayload(
                dialogue_act="answer",
                control="none",
                consent_answer="not_applicable",
                answers_pending_question=True,
                needs_clarification=False,
                issue_mentions=(chest,),
            ),
            utterance_id="u-2",
            raw_text=quote,
        ),
    )
    headache_id = next(iter(state.issue_episodes))
    assert state.issue_episodes[headache_id].known_attributes.get("onset") is None
    assert state.pending_episode_attribute == "onset"


def test_multi_slot_wellness_still_fills_ladder() -> None:
    runner = _runner()
    runner.run([CallStarted()])
    runner.state.wellness_probes_enabled = False
    result = runner.run(["Плохо сегодня, почти не спал, планов никаких."])
    assert result.state.slots["sleep"] == SlotStatus.FILLED
    assert result.state.slots["plans"] == SlotStatus.FILLED
    assert result.state.slots["mood"] == SlotStatus.OPEN
