from __future__ import annotations

import pytest

from tests.corpus.conversation_eval import ConversationRunner

GOOD = "Плохо… хотя нет, хорошо."
BAD = "Хорошо… хотя нет, плохо."


@pytest.fixture
def runner(monkeypatch: pytest.MonkeyPatch, request) -> ConversationRunner:
    for key, value in {
        "IMVERA_DIALOGUE_ENGINE": "1",
        "IMVERA_VOICE_DIRECT_WELLNESS_OPENING": "1",
        "IMVERA_COVERAGE_LADDER": "1",
        "IMVERA_LLM_INTERPRET": "0",
        "IMVERA_MISSION_LLM_INTERPRET": "0",
        "IMVERA_SEMANTIC_ML": "0",
        "IMVERA_ACTION_POLICY_MODE": "off",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("IMVERA_TINYLLM_MODEL", raising=False)
    return ConversationRunner(call_id=request.node.name)


def test_fast_good_direction_positive_with_correction() -> None:
    from packages.dialogue_engine.fast_interpreter import fast_interpret_semantic

    sem, confident = fast_interpret_semantic(GOOD, answer_slot="wellness")
    assert confident
    assert sem.target_slot == "wellness"
    assert sem.polarity == "positive"
    assert sem.correction is True
    assert sem.source_quote == GOOD
    assert sem.value == GOOD


def test_fast_bad_direction_negative_with_correction() -> None:
    from packages.dialogue_engine.fast_interpreter import fast_interpret_semantic

    sem, confident = fast_interpret_semantic(BAD, answer_slot="wellness")
    assert confident
    assert sem.target_slot == "wellness"
    assert sem.polarity == "negative"
    assert sem.correction is True
    assert sem.source_quote == BAD
    assert sem.value == BAD


def test_extract_goal_facts_good_direction() -> None:
    from packages.dialogue_engine.issue_mention_extract import extract_goal_facts

    facts = {
        f.field: f
        for f in extract_goal_facts(GOOD, answer_slot="wellness")
    }
    assert facts["wellness"].value == "positive"
    assert facts["wellness"].evidence.quote == GOOD
    assert "mood" not in facts


def test_extract_goal_facts_bad_direction() -> None:
    from packages.dialogue_engine.issue_mention_extract import extract_goal_facts

    facts = {
        f.field: f
        for f in extract_goal_facts(BAD, answer_slot="wellness")
    }
    assert facts["wellness"].value == "negative"
    assert facts["wellness"].evidence.quote == BAD
    assert "mood" not in facts


def test_rich_turn_positive_with_full_quote() -> None:
    from packages.dialogue_engine.semantic_kernel.kernel import (
        interpret,
        kernel_to_rich_turn,
    )

    result = interpret(GOOD, utterance_id="u-1")
    turn = kernel_to_rich_turn(result, answer_slot="wellness")
    facts = {f.field: f for f in turn.goal_facts}
    assert facts["wellness"].value == "positive"
    assert facts["wellness"].evidence.quote == GOOD
    assert not turn.issue_mentions


def test_conversation_runner_good_self_correction(runner: ConversationRunner) -> None:
    from packages.dialogue_engine.events import CallStarted

    runner.run([CallStarted()])
    result = runner.run([GOOD])
    assert runner.state.slots["wellness"].value == "FILLED"
    record = runner.state.slot_records["wellness"]
    assert record.polarity == "positive"
    assert record.source_text == GOOD
    assert [e.intent for e in result.speak_effects] == ["background_nutrition"]
    assert not runner.state.issue_episodes


def test_conversation_runner_matches_plain_positive() -> None:
    from packages.dialogue_engine.events import CallStarted

    def _first_intents(text: str) -> list[str]:
        direct = ConversationRunner(call_id="parity")
        direct.run([CallStarted()])
        outcome = direct.run([text])
        return [e.intent for e in outcome.speak_effects]

    assert _first_intents(GOOD) == _first_intents("Хорошо.")
    assert _first_intents(BAD) == _first_intents("Плохо.")


def test_conversation_runner_bad_self_correction(runner: ConversationRunner) -> None:
    from packages.dialogue_engine.events import CallStarted

    runner.run([CallStarted()])
    result = runner.run([BAD])
    assert runner.state.slots["wellness"].value == "FILLED"
    record = runner.state.slot_records["wellness"]
    assert record.polarity == "negative"
    assert record.source_text == BAD
    assert [e.intent for e in result.speak_effects] == ["probe_concern"]


def test_delivered_concern_probe_consuming_answer_fixes_concern(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Semantic path: probe_concern delivery creates a concern obligation.
    The complaint answer must ground wellness_concern via the shared
    check_path contract — including the duration follow-up, like rich."""
    for key, value in {
        "IMVERA_DIALOGUE_ENGINE": "1",
        "IMVERA_VOICE_DIRECT_WELLNESS_OPENING": "1",
        "IMVERA_COVERAGE_LADDER": "0",
        "IMVERA_LLM_INTERPRET": "0",
        "IMVERA_MISSION_LLM_INTERPRET": "0",
        "IMVERA_SEMANTIC_ML": "0",
        "IMVERA_ACTION_POLICY_MODE": "off",
    }.items():
        monkeypatch.setenv(key, value)
    from packages.dialogue_engine.corpus.generator import _build_scenario
    from packages.dialogue_engine.corpus.runner import CorpusRunner
    from packages.dialogue_engine.corpus.schema import FAMILY_NAMES

    scenario = _build_scenario(
        "bad", "self_correction", FAMILY_NAMES.index("self_correction"), 0
    )
    runner = CorpusRunner(scenario)
    runner._start_call()
    runner._user_turn(BAD, delayed=False)
    assert [e.intent for e in runner._pending_speaks] == ["probe_concern"]
    probe = runner._pending_speaks.pop(0)
    runner._deliver_speak(probe)
    runner._user_turn("Голова болит.", delayed=False)
    intents = [e.intent for e in runner._pending_speaks]
    assert "probe_concern_options" not in intents
    assert runner.engine.state.wellness_concern == "Голова болит."
    assert intents == ["probe_duration"]
    duration = runner._pending_speaks.pop(0)
    runner._deliver_speak(duration)
    runner._user_turn("Вчера началось.", delayed=False)
    assert [e.intent for e in runner._pending_speaks] == ["probe_severity"]
    severity = runner._pending_speaks.pop(0)
    runner._deliver_speak(severity)
    runner._user_turn("Терпимая.", delayed=False)
    assert [e.intent for e in runner._pending_speaks] == ["important_to_share"]


def _concern_runner(monkeypatch: pytest.MonkeyPatch):
    for key, value in {
        "IMVERA_DIALOGUE_ENGINE": "1",
        "IMVERA_VOICE_DIRECT_WELLNESS_OPENING": "1",
        "IMVERA_COVERAGE_LADDER": "0",
        "IMVERA_LLM_INTERPRET": "0",
        "IMVERA_MISSION_LLM_INTERPRET": "0",
        "IMVERA_SEMANTIC_ML": "0",
        "IMVERA_ACTION_POLICY_MODE": "off",
    }.items():
        monkeypatch.setenv(key, value)
    from packages.dialogue_engine.corpus.generator import _build_scenario
    from packages.dialogue_engine.corpus.runner import CorpusRunner
    from packages.dialogue_engine.corpus.schema import FAMILY_NAMES

    scenario = _build_scenario(
        "bad", "self_correction", FAMILY_NAMES.index("self_correction"), 0
    )
    runner = CorpusRunner(scenario)
    runner._start_call()
    runner._user_turn(BAD, delayed=False)
    assert [e.intent for e in runner._pending_speaks] == ["probe_concern"]
    probe = runner._pending_speaks.pop(0)
    runner._deliver_speak(probe)
    return runner


def test_answer_act_non_complaint_reaches_net(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ANSWER-act non-complaint falls through to the scheduler net → options."""
    runner = _concern_runner(monkeypatch)
    runner._user_turn("Нормально.", delayed=False)
    assert runner.engine.state.wellness_concern == ""
    assert [e.intent for e in runner._pending_speaks] == ["probe_concern_options"]


def test_vague_first_probe_answer_goes_to_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-complaint after probe_concern re-probes (mirrors rich path)."""
    runner = _concern_runner(monkeypatch)
    runner._user_turn("Поел.", delayed=False)
    assert runner.engine.state.wellness_concern == ""
    assert runner.engine.state.observations.get("concern_declined") is None
    assert [e.intent for e in runner._pending_speaks] == ["probe_concern_options"]


def test_refusal_first_probe_answer_goes_to_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _concern_runner(monkeypatch)
    runner._user_turn("Не скажу.", delayed=False)
    assert [e.intent for e in runner._pending_speaks] == ["probe_concern_options"]


def test_hostile_after_options_escalates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Options-stage decline falls through: hostile escalates unspecified."""
    runner = _concern_runner(monkeypatch)
    runner._user_turn("Не скажу.", delayed=False)
    assert [e.intent for e in runner._pending_speaks] == ["probe_concern_options"]
    options = runner._pending_speaks.pop(0)
    runner._deliver_speak(options)
    runner._user_turn("Отстань.", delayed=False)
    assert runner.engine.state.observations.get("concern_status") == "unspecified"
    assert [e.intent for e in runner._pending_speaks] == ["urgent_close"]


def test_calm_after_options_declines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Options-stage calm substantive answer declines, ladder continues."""
    runner = _concern_runner(monkeypatch)
    runner._user_turn("Не скажу.", delayed=False)
    options = runner._pending_speaks.pop(0)
    runner._deliver_speak(options)
    runner._user_turn("Пойдёт.", delayed=False)
    assert runner.engine.state.observations.get("concern_declined") == "1"
    assert [e.intent for e in runner._pending_speaks] == ["important_to_share"]


def test_unrelated_complaint_still_extracts() -> None:
    from packages.dialogue_engine.issue_mention_extract import extract_issue_mentions

    mentions = extract_issue_mentions("Живот болит.")
    assert mentions
    assert mentions[0].body_site == "живот"
