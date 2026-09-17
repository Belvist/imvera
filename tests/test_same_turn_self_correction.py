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


def test_unrelated_complaint_still_extracts() -> None:
    from packages.dialogue_engine.issue_mention_extract import extract_issue_mentions

    mentions = extract_issue_mentions("Живот болит.")
    assert mentions
    assert mentions[0].body_site == "живот"
