from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from packages.dialogue_engine.effects import EndCallEffect, SpeakEffect
from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.mission_result import build_mission_result
from tests.corpus.conversation_eval import ConversationRunner

pytestmark = pytest.mark.dialogue_engine


@dataclass(frozen=True)
class Turn:
    text: str
    intent: str
    status: str = "FILLED"
    polarity: str | None = None
    temporal: bool = False
    current: str | None = None
    correction: bool = False


@dataclass(frozen=True)
class Conversation:
    id: str
    turns: tuple[Turn, ...]
    unknown: str | None = None


CLOSE = (Turn("Нет, ничего.", "summary"), Turn("Нет, ничего.", "goodbye_final"))
ROUTINE = (
    Turn("Поела.", "background_medication"),
    Turn("Нет.", "background_mood"),
    Turn("Нормальное.", "background_sleep"),
    Turn("Выспалась.", "important_to_share"),
    Turn("Дома буду.", "summary"),
    Turn("Нет, ничего.", "goodbye_final"),
)
SCENARIOS = (
    Conversation("ambiguous-recovery", (
        Turn("Не знаю.", "clarify_wellness", "OPEN"),
        Turn("Хорошо.", "background_nutrition", polarity="positive"),
        *ROUTINE,
    )),
    Conversation("last-attempt-recovery", (
        Turn("Абракадабра.", "clarify_wellness", "OPEN"),
        Turn("Белиберда.", "clarify_wellness", "OPEN"),
        Turn("Хорошо.", "background_nutrition", polarity="positive"),
        *ROUTINE,
    )),
    *(Conversation(f"exhausted-{name}", (
        Turn(text, "clarify_wellness", "OPEN"),
        Turn(text, "clarify_wellness", "OPEN"),
        Turn(text, "wellness_unknown", "UNRESOLVED"),
        Turn(text, "important_to_share", "UNRESOLVED"),
        Turn("Дома буду.", "summary", "UNRESOLVED"),
        Turn("Нет, ничего.", "goodbye_final", "UNRESOLVED"),
    ), unknown=text) for name, text in (("unknown", "Не знаю."), ("noise", "Абракадабра."))),
    Conversation("correction-to-negative", (
        Turn("Не знаю.", "clarify_wellness", "OPEN"),
        Turn("Хорошо.", "background_nutrition", polarity="positive"),
        Turn("Нет, мне плохо.", "probe_concern", polarity="negative", correction=True),
        Turn("До свидания.", "goodbye_final", polarity="negative"),
    )),
    Conversation("correction-to-positive", (
        Turn("Не знаю.", "clarify_wellness", "OPEN"),
        Turn("Плохо.", "probe_concern", polarity="negative"),
        Turn("Нет, я хорошо себя чувствую.", "background_nutrition",
             polarity="positive", correction=True),
        *ROUTINE,
    )),
    Conversation("temporal-current-resolution", (
        Turn("Живот болит.", "episode_onset"),
        Turn("С утра.", "episode_current", temporal=True),
        Turn("Уже не болит.", "important_to_share", current="resolved"),
        *CLOSE,
    )),
    Conversation("explicit-topic-completion", (
        Turn("Меня знобит.", "episode_onset"),
        Turn("С 10 утра", "important_to_share", temporal=True),
        *CLOSE,
    )),
    Conversation("anaphoric-topic-completion", (
        Turn("Меня знобит.", "episode_onset"),
        Turn("С 10 утра", "important_to_share", temporal=True),
        Turn("Только это было.", "summary"),
        Turn("Нет, ничего.", "goodbye_final"),
    )),
)


@pytest.fixture(scope="session", autouse=True)
def _ensure_slot_answer_model() -> None:
    model = Path(__file__).resolve().parents[2] / "models" / "slot_answer_clf.pkl"
    assert model.is_file(), "Offline eval requires the existing classifier; training is forbidden"


@pytest.fixture
def runner(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, request) -> ConversationRunner:
    from packages.dialogue_engine import caller_memory

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
    monkeypatch.setattr(caller_memory, "_store_dir", lambda: tmp_path / "phrase_memory")
    result = ConversationRunner(call_id=request.node.name)
    opening = result.run([CallStarted()])
    assert opening.opening_count == 1
    assert result.engine.answer_context_slot() == "wellness"
    return result


@pytest.mark.parametrize("answer_slot", ["wellness", "mood"])
def test_bare_negative_mood_fact_requires_mood_context(answer_slot: str) -> None:
    from packages.dialogue_engine.issue_mention_extract import extract_goal_facts

    facts = {fact.field: fact for fact in extract_goal_facts("Плохо.", answer_slot=answer_slot)}
    assert facts["wellness"].value == "negative"
    assert ("mood" in facts) == (answer_slot == "mood")
    for fact in facts.values():
        assert fact.evidence.quote == "Плохо."
        assert fact.subject == "speaker"


def test_positive_correction_does_not_answer_mood(runner: ConversationRunner) -> None:
    for text in ("Не знаю.", "Плохо.", "Нет, я хорошо себя чувствую."):
        runner.run([text])
        assert runner.state.slots["mood"].value == "OPEN"
        assert runner.state.goals["mood"].status.value == "OPEN"
        assert runner.state.background_goal_status["mood"] == "unseen"
        assert "mood" not in runner.state.slot_records
        assert all(fact.field != "mood" for fact in runner.last_turn.goal_facts)
    wellness = runner.state.slot_records["wellness"]
    assert wellness.polarity == "positive"
    assert wellness.source_text == "Нет, я хорошо себя чувствую."
    assert wellness.source_turn_id == "u-3"
    assert runner.state.slot_corrections[-1] == {
        "slot": "wellness", "old": "Плохо.", "new": "positive", "source_turn": "u-3",
    }
    runner.run(["Поела."])
    result = runner.run(["Нет."])
    assert [effect.intent for effect in result.speak_effects] == ["background_mood"]
    runner.run(["Плохое."])
    mood = runner.state.slot_records["mood"]
    assert runner.state.slots["mood"].value == "FILLED"
    assert mood.polarity == "negative"
    assert mood.source_text == "Плохое."
    assert mood.source_turn_id == "u-6"


@pytest.mark.parametrize("mood_text", ["Настроение плохое.", "Настроение хорошее."])
def test_wellness_correction_preserves_explicit_mood(
    runner: ConversationRunner, mood_text: str,
) -> None:
    runner.run(["Мне плохо, " + mood_text.lower()])
    mood = runner.state.slot_records["mood"].model_copy(deep=True)
    assert mood.source_turn_id == "u-1"
    assert mood_text.lower() in mood.source_text
    runner.run(["Нет, я хорошо себя чувствую."])
    assert runner.state.slot_records["wellness"].polarity == "positive"
    assert runner.state.slot_records["mood"] == mood
    assert runner.state.slots["mood"].value == "FILLED"


def test_wellness_correction_preserves_complaint_and_urgent_routing(
    runner: ConversationRunner,
) -> None:
    runner.run(["Живот болит."])
    before = runner.state.model_copy(deep=True)
    assert len(before.issue_episodes) == 1
    runner.run(["Нет, я хорошо себя чувствую."])
    assert runner.state.slot_records["wellness"].polarity == "positive"
    assert runner.state.issue_episodes.keys() == before.issue_episodes.keys()
    for episode_id, episode in before.issue_episodes.items():
        retained = runner.state.issue_episodes[episode_id]
        assert retained.mentions == episode.mentions
        assert retained.evidence_turn_ids == episode.evidence_turn_ids == ["u-1"]
        assert retained.known_attributes["current"] == "active"
    for observation_id, observation in before.observations.items():
        assert runner.state.observations[observation_id] == observation
    result = runner.run(["Я упала и не могу встать."])
    assert [effect.intent for effect in result.speak_effects] == ["urgent_close"]
    assert runner.state.call_closed
    assert runner.state.closing_reason == "urgent"
    assert any(isinstance(effect, EndCallEffect) for effect in result.effects)


@pytest.mark.parametrize("text", [
    "Только это было.", "Лишь это было.", "Было только это.",
    "Только это.", "Лишь это.", "Только оно было.",
])
def test_its_exclusive_reference_preserves_complaint(
    runner: ConversationRunner, text: str,
) -> None:
    from packages.dialogue_engine.conversation_policy import _classify_important_to_share_answer
    from packages.dialogue_engine.semantic_kernel.kernel import interpret, kernel_to_rich_turn

    runner.run(["Меня знобит.", "С 10 утра"])
    before = runner.state.model_copy(deep=True)
    assert before.delivered_question.slot == "important_to_share"
    parsed = interpret(text, utterance_id="u-3", engine_state=before,
                       answer_slot="important_to_share")
    turn = kernel_to_rich_turn(parsed, engine_state=before, answer_slot="important_to_share")
    assert any(rel.target_span_id == before.active_episode_id for rel in turn.semantic_relations)
    assert _classify_important_to_share_answer(turn, text, before) == "TOPIC_COMPLETE"
    result = runner.run([text])
    assert [effect.intent for effect in result.speak_effects] == ["summary"]
    assert runner.state.important_to_share_resolved
    assert runner.state.issue_episodes == before.issue_episodes
    assert runner.state.observations == before.observations
    assert runner.state.slot_records == before.slot_records
    episode = runner.state.issue_episodes[before.active_episode_id]
    assert episode.known_attributes["current"] == "active"
    assert episode.evidence_turn_ids == ["u-1"]
    assert runner.last_turn.consent_answer == "not_applicable"
    assert not runner.last_turn.observations
    assert not runner.state.call_closed
    result = runner.run(["Нет, ничего."])
    assert [effect.intent for effect in result.speak_effects] == ["goodbye_final"]
    assert sum(isinstance(effect, EndCallEffect) for effect in runner.effects) == 1


@pytest.mark.parametrize("text", [
    "Это было.", "Только там было.", "Только это было?", "Не только это было.",
    "Наверное, только это было.", "Только это было, не знаю.",
    "Только это было вчера.", "Только это было и ещё что-то.",
    "Только это было, живот болит.", "Только это было. Я упала и не могу встать.",
])
def test_its_reference_negative_controls(runner: ConversationRunner, text: str) -> None:
    from packages.dialogue_engine.conversation_policy import _classify_important_to_share_answer
    from packages.dialogue_engine.semantic_kernel.kernel import interpret, kernel_to_rich_turn

    runner.run(["Меня знобит.", "С 10 утра"])
    before = runner.state.model_copy(deep=True)
    parsed = interpret(text, utterance_id="u-3", engine_state=before,
                       answer_slot="important_to_share")
    turn = kernel_to_rich_turn(parsed, engine_state=before, answer_slot="important_to_share")
    assert _classify_important_to_share_answer(turn, text, before) != "TOPIC_COMPLETE"
    result = runner.run([text])
    assert all(effect.intent not in ("summary", "goodbye_final") for effect in result.speak_effects)
    if "не могу встать" in text:
        assert [effect.intent for effect in result.speak_effects] == ["urgent_close"]
        assert runner.state.closing_reason == "urgent"
    elif "живот болит" in text:
        assert runner.last_turn.issue_mentions
        assert len(runner.state.issue_episodes) > len(before.issue_episodes)
        assert not runner.state.call_closed
    else:
        assert not runner.state.important_to_share_resolved
        assert runner.state.delivered_question.slot == "important_to_share"
        assert runner.state.issue_episodes == before.issue_episodes
        assert not runner.state.call_closed


@pytest.mark.parametrize("context", [
    "no_state", "no_episode", "missing_active", "ambiguous", "no_evidence",
    "unknown_subject", "other_subject", "no_delivery", "playing", "planned",
    "answered", "other_slot", "medication", "pending_attribute", "no_relations",
])
def test_its_completion_requires_grounded_delivered_context(
    runner: ConversationRunner, context: str,
) -> None:
    from packages.dialogue_engine.conversation_policy import _classify_important_to_share_answer
    from packages.dialogue_engine.semantic_kernel.kernel import interpret, kernel_to_rich_turn
    from packages.dialogue_engine.state import QuestionPhase

    runner.run(["Меня знобит.", "С 10 утра"])
    state = runner.state.model_copy(deep=True)
    episode = state.issue_episodes[state.active_episode_id]
    if context == "no_state":
        state = None
    elif context == "no_episode":
        state.issue_episodes.clear()
    elif context == "missing_active":
        state.active_episode_id = None
    elif context == "ambiguous":
        other = episode.model_copy(deep=True, update={"episode_id": "other"})
        state.issue_episodes["other"] = other
    elif context == "no_evidence":
        episode.evidence_turn_ids.clear()
        episode.mentions.clear()
    elif context in ("unknown_subject", "other_subject"):
        episode.subject = "unknown" if context == "unknown_subject" else "other_person"
    elif context == "no_delivery":
        state.delivered_question = None
    elif context in ("playing", "planned", "answered"):
        phase = QuestionPhase(context.upper())
        state.delivered_question = state.delivered_question.model_copy(update={"phase": phase})
    elif context == "other_slot":
        state.delivered_question = state.delivered_question.model_copy(update={"slot": "mood"})
    elif context == "medication":
        state.delivered_question = state.delivered_question.model_copy(
            update={"intent": "medication_status_today"},
        )
    elif context == "pending_attribute":
        state.pending_episode_attribute = "onset"
    text = "Только это было."
    slot = state.answer_context_slot() if state else None
    parsed = interpret(text, utterance_id="u-3", engine_state=state, answer_slot=slot)
    turn = kernel_to_rich_turn(parsed, engine_state=state, answer_slot=slot)
    if context == "no_relations":
        turn = turn.model_copy(update={"semantic_relations": ()})
    assert _classify_important_to_share_answer(turn, text, state) == "UNCLEAR"


def _intent(intent: str) -> str:
    if intent.startswith("episode_"):
        return f"episode_{intent.rsplit('_', 1)[-1]}"
    return intent


@pytest.mark.parametrize("scenario", [
    pytest.param(scenario, id=scenario.id) for scenario in SCENARIOS
])
def test_conversation(scenario: Conversation, runner: ConversationRunner) -> None:
    transcript: list[str] = []
    intents: list[str] = []
    for index, expected in enumerate(scenario.turns, 1):
        before = runner.state.model_copy(deep=True)
        assert not before.call_closed, transcript
        result = runner.run([expected.text])
        state = runner.state
        actual = [_intent(effect.intent) for effect in result.speak_effects]
        intents.extend(actual)
        transcript.append(f"{index}: {expected.text!r} -> {actual}")
        diagnostic = "\n".join(transcript)
        assert state.slots["wellness"].value == expected.status, diagnostic
        assert state.goals["wellness"].status.value == expected.status, diagnostic
        if expected.status == "OPEN":
            assert state.goals["wellness"].lifecycle.value == "ANSWER_PENDING", diagnostic
            assert "wellness" not in state.slot_records, diagnostic
            assert not runner.last_turn.goal_answers, diagnostic
            assert state.answer_context_slot() == before.answer_context_slot() == "wellness"
        elif expected.status == "UNRESOLVED":
            assert state.goals["wellness"].lifecycle.value == "UNCLEAR", diagnostic
            assert state.goals["wellness"].answer is None, diagnostic
            assert "wellness" not in state.slot_records, diagnostic
            assert state.observations["wellness_unknown"] == scenario.unknown, diagnostic
        else:
            assert state.goals["wellness"].lifecycle.value == "SATISFIED", diagnostic
        if expected.temporal:
            assert state.issue_episodes.keys() == before.issue_episodes.keys(), diagnostic
            for episode_id, episode in state.issue_episodes.items():
                previous = before.issue_episodes[episode_id].known_attributes
                assert episode.known_attributes["onset"] == expected.text, diagnostic
                for attribute in ("current", "severity"):
                    assert (
                        episode.known_attributes.get(attribute) == previous.get(attribute)
                    ), diagnostic
                assert "severity" not in episode.known_attributes, diagnostic
        if expected.current:
            assert len(state.issue_episodes) == len(before.issue_episodes) == 1, diagnostic
            episode = next(iter(state.issue_episodes.values()))
            assert episode.known_attributes["current"] == expected.current, diagnostic
            assert "severity" not in episode.known_attributes, diagnostic
        if expected.polarity:
            record = state.slot_records["wellness"]
            assert record.polarity == expected.polarity, diagnostic
            if expected.correction:
                assert record.polarity != before.slot_records["wellness"].polarity, diagnostic
                assert record.source_text == expected.text, diagnostic
                assert record.source_turn_id == f"u-{index}", diagnostic
        assert actual == [expected.intent], diagnostic
        assert intents.count("clarify_wellness") <= 2, diagnostic
        if expected.intent == "summary":
            assert state.important_to_share_resolved, diagnostic
        for record in state.slot_records.values():
            assert record.source_text in [turn.text for turn in scenario.turns[:index]], diagnostic
        assert state.call_closed == (index == len(scenario.turns)), diagnostic
    assert intents[-1] == "goodbye_final", transcript
    assert "partial_unresolved_close" not in intents, transcript
    assert sum(isinstance(effect, EndCallEffect) for effect in runner.effects) == 1
    assert sum(
        isinstance(effect, SpeakEffect) and effect.intent == "goodbye_final"
        for effect in runner.effects
    ) == 1
    snapshot = build_mission_result(runner.state)
    if scenario.unknown:
        wellness = next(goal for goal in snapshot.goals if goal.goal_id == "wellness")
        assert wellness.lifecycle == "UNCLEAR"
        assert wellness.value is None and wellness.evidence == []
        assert snapshot.status == "PARTIAL"
        assert f"wellness_unknown:{scenario.unknown}" in snapshot.observations
    closed_state = runner.state.model_dump()
    assert runner.run(["До свидания."]).effects == []
    assert runner.state.model_dump() == closed_state
