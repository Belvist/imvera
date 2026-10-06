"""Real fs-fd317c1c words: each complaint retains its own evidence and question."""
import pytest

from packages.dialogue_engine.check_path import build_call_metadata, episode_digest
from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.issue_memory import extract_grounded_onset_value
from packages.dialogue_engine.scenario_runner import ScenarioRunner

pytestmark = pytest.mark.dialogue_engine
COMPLAINTS = "Рука болит опухла, что-то давление ещё, и этот сахар поднялся."


@pytest.fixture(autouse=True)
def default_live(monkeypatch):
    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "1")
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "off")
    monkeypatch.setenv("IMVERA_LLM_INTERPRET", "0")
    monkeypatch.setenv("IMVERA_MISSION_LLM_INTERPRET", "0")


@pytest.mark.parametrize("answer", [
    "Понятно. В 12 вроде.", "В 12 вроде.", "В 12, кажется.",
    "Не знаю, как будто бы в 12:00 сегодня.",
    "Вроде бы в 12 сегодня.", "Как будто в двенадцать часов дня.",
])
def test_hedged_clock_answers_the_delivered_episode_without_guessing_certainty(answer):
    runner = ScenarioRunner(call_id="multi-clock")
    runner.run([CallStarted(), "Плохо.", COMPLAINTS])
    owner = runner.state.active_episode_id
    assert runner.state.pending_episode_attribute == "onset"
    result = runner.run([answer])
    episode = runner.state.issue_episodes[owner]
    assert episode.known_attributes.get("onset")
    assert "12" in episode.known_attributes["onset"] or "двенадцать" in answer
    assert runner.state.pending_episode_attribute != "onset"
    assert not any(s.intent == "summary" for s in result.speak_effects)
    for other in runner.state.issue_episodes.values():
        if other.episode_id != owner:
            assert not other.known_attributes.get("onset")


@pytest.mark.parametrize("answer", [
    "Принимаю таблетки в 12 вроде.", "Дочь приедет в 12, кажется.",
    "Не знаю, в 12 или в 16.", "Сахар купила в 12.", "В 12 буду гулять.",
    "Сахар купила утром.", "Утром принимала таблетки.",
])
def test_hedged_clock_with_another_owner_or_alternative_is_not_clinical_onset(answer):
    assert extract_grounded_onset_value(answer) is None


def test_first_response_reflects_all_grounded_complaints():
    runner = ScenarioRunner(call_id="multi-listen")
    result = runner.run([CallStarted(), "Плохо.", COMPLAINTS])
    speech = result.speak_effects[-1].text.lower()
    assert all(label in speech for label in ("рука", "давление", "сахар"))
    assert speech.count("?") == 1


def test_temporal_loop_budget_is_per_episode_not_three_different_complaints():
    runner = ScenarioRunner(call_id="three-generic")
    runner.run([CallStarted(), "Горло першит, нос заложен и ухо заложено."])
    asked = []
    for answer in ("С утра.", "Со вчера."):
        asked.append(runner.state.active_episode_id)
        assert runner.state.pending_episode_attribute in {"onset", "duration"}
        result = runner.run([answer])
        assert not any(s.intent in {"summary", "partial_unresolved_close"}
                       for s in result.speak_effects)
    assert len(set(asked + [runner.state.active_episode_id])) == 3
    assert runner.state.pending_episode_attribute in {"onset", "duration"}


def test_two_confused_answers_on_first_episode_do_not_abandon_unasked_complaints():
    runner = ScenarioRunner(call_id="multi-confusion")
    runner.run([CallStarted(), "Плохо.", COMPLAINTS])
    first = runner.state.active_episode_id
    result = runner.run(["Ну такое.", "Такое какое-то."])
    assert not any(s.intent == "summary" for s in result.speak_effects)
    assert not runner.state.issue_episodes[first].known_attributes.get("onset")
    assert runner.state.issue_episodes[first].unanswered_attributes.get("onset")
    assert runner.state.pending_episode_ids or runner.state.active_episode_id != first


def test_three_complaints_survive_existing_cross_call_digest():
    runner = ScenarioRunner(call_id="multi-memory")
    runner.run([CallStarted(), "Плохо.", COMPLAINTS])
    digest = episode_digest(runner.state)
    assert all(label in digest for label in ("рука", "давление", "сахар"))
    assert build_call_metadata(runner.state)["past_episodes"] == digest


def test_each_complaint_gets_its_own_short_need_without_inheriting_another_onset():
    runner = ScenarioRunner(call_id="multi-complete")
    runner.run([CallStarted(), "Плохо.", COMPLAINTS, "В 12 вроде.", "Терпимо."])
    hand = next(e for e in runner.state.issue_episodes.values() if e.body_site == "рука")
    assert hand.known_attributes.get("onset") and hand.known_attributes.get("severity")
    pressure = runner.state.issue_episodes[runner.state.active_episode_id]
    assert pressure.primary_label == "давление"
    result = runner.run(["Со вчера."])
    assert not any(s.intent == "summary" for s in result.speak_effects)
    sugar = runner.state.issue_episodes[runner.state.active_episode_id]
    assert sugar.primary_label == "сахар"
    assert not sugar.known_attributes.get("onset")
    runner.run(["Сегодня после обеда."])
    assert "вчера" in pressure.known_attributes["onset"]
    assert "обеда" in sugar.known_attributes["onset"]


@pytest.mark.parametrize("answer", ["Не помню.", "Не хочу отвечать."])
def test_unknown_or_declined_first_attribute_is_not_a_value_or_a_global_stop(answer):
    runner = ScenarioRunner(call_id="multi-unknown")
    runner.run([CallStarted(), "Плохо.", COMPLAINTS])
    first = runner.state.active_episode_id
    result = runner.run([answer])
    assert not runner.state.issue_episodes[first].known_attributes.get("onset")
    assert not runner.state.call_closed
    assert not any(effect.intent == "summary" for effect in result.speak_effects)
    assert runner.state.pending_episode_ids


@pytest.mark.parametrize("answer", ["До свидания.", "Не могу дышать."])
def test_control_or_safety_preempts_multi_complaint_queue(answer):
    runner = ScenarioRunner(call_id="multi-control")
    runner.run([CallStarted(), "Плохо.", COMPLAINTS])
    result = runner.run([answer])
    assert runner.state.call_closed or runner.state.red_state_pending
    first = runner.state.issue_episodes[next(iter(runner.state.issue_episodes))]
    assert not first.known_attributes.get("onset")
    assert result.speak_effects


def test_bounded_digest_retains_six_speaker_complaints_and_excludes_other_patient():
    from packages.dialogue_engine.state import EngineState, IssueEpisode

    state = EngineState(call_id="digest-budget")
    state.issue_episodes["other"] = IssueEpisode(
        episode_id="other", primary_label="Болит у дочери", kind="pain", subject="other_person")
    for index in range(8):
        state.issue_episodes[str(index)] = IssueEpisode(
            episode_id=str(index), primary_label=f"Жалоба {index}", kind="symptom",
            subject="speaker")
    digest = episode_digest(state)
    assert "дочери" not in digest and "Жалоба 5" in digest
    assert "Жалоба 6" not in digest
    assert len(digest.split(" | ")) == 6


def test_episode_scoped_probe_identity_survives_state_snapshot_roundtrip():
    from packages.dialogue_engine.state import EngineState

    runner = ScenarioRunner(call_id="multi-snapshot")
    runner.run([CallStarted(), "Плохо.", COMPLAINTS])
    identity = runner.state.last_temporal_probe
    assert identity and runner.state.active_episode_id in identity
    restored = EngineState.model_validate_json(runner.state.model_dump_json())
    assert restored.last_temporal_probe == identity
