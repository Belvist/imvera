"""Real fs-2baf87ec and neighbouring meanings, independent of telephony."""

import pytest

from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.turn_understanding import build_rich_turn_from_text

pytestmark = pytest.mark.dialogue_engine


@pytest.mark.parametrize("text", [
    "Ой, поел нормально? Вот у меня что-то голова болит и руки ноют.",
    "Поел нормально. Голова болит и руки ноют.",
    "Руки ноют и голова болит. Поел нормально.",
    "Спал нормально! Голова болит.",
    "Поел нормально но голова болит.",
    "Поел нормально и руки ноют.",
])
def test_other_sentence_normal_does_not_resolve_complaint(text):
    turn = build_rich_turn_from_text(text, utterance_id="mixed")
    assert turn.issue_mentions
    assert all(m.status == "active" for m in turn.issue_mentions)
    assert not any(o.attribute == "current" and o.temporal.current is False
                   for o in turn.observations)


@pytest.mark.parametrize("text", [
    "Голова болит и руки ноют.", "Руки ноют и голова болит.",
])
def test_one_mention_per_actual_pain_site(text):
    turn = build_rich_turn_from_text(text, utterance_id="two")
    assert sorted(m.body_site for m in turn.issue_mentions) == ["голова", "рука"]
    assert all("рука ноют" not in m.label.lower() for m in turn.issue_mentions)


def test_same_site_distinct_symptoms_both_survive_ingest_and_summary():
    from packages.dialogue_engine.questions import concern_summary_phrase

    r = ScenarioRunner()
    r.run([CallStarted(), "Руки болят и трясутся."])
    labels = [m.label.lower() for ep in r.state.issue_episodes.values() for m in ep.mentions]
    assert any("бол" in label for label in labels)
    assert any("тряс" in label for label in labels)
    assert "тряс" in concern_summary_phrase(r.state)


def test_past_complaint_is_not_resolved_by_normal_in_another_sentence():
    turn = build_rich_turn_from_text("Голова болела вчера. Поел нормально.", utterance_id="past")
    assert any(m.body_site == "голова" for m in turn.issue_mentions)
    assert not any(m.status == "resolved" for m in turn.issue_mentions)


def test_past_report_does_not_invent_improvement_in_speech():
    r = ScenarioRunner()
    result = r.run([CallStarted(), "Живот утром немного поболел."])
    assert any(e.intent.startswith("episode_") for e in result.speak_effects)
    assert not any("полегчало, рада" in e.text.lower() or "проходит, хорошо" in e.text.lower()
                   for e in result.speak_effects)


def test_explicit_improvement_still_receives_appropriate_ack():
    from packages.dialogue_engine.conversation_policy import _grounded_ack_for_mentions

    turn = build_rich_turn_from_text("Голова почти не болит.", utterance_id="better")
    assert turn.issue_mentions
    ack = _grounded_ack_for_mentions(turn)
    assert "полегчало" in ack or "проходит" in ack


@pytest.mark.parametrize("text", [
    "Руки постоянно трясутся.", "Рука трясётся.",
    "Жалобы, руки постоянно трясутся и кровят.", "У меня дрожат руки.",
])
def test_tremor_is_preserved_as_speaker_evidence(text):
    turn = build_rich_turn_from_text(text, utterance_id="tremor")
    tremors = [m for m in turn.issue_mentions if m.body_site == "рука"]
    assert tremors
    assert any("тряс" in m.label.lower() or "дрож" in m.label.lower() for m in tremors)
    assert all(m.subject == "speaker" for m in tremors)
    if "кровят" in text:
        assert any("кровят" in m.evidence.quote for m in tremors)
        assert not any("кровотеч" in m.label.lower() for m in turn.issue_mentions)


@pytest.mark.parametrize("text", ["У мужа руки трясутся.", "Трясу коврик."])
def test_tremor_subject_and_nonmedical_action_are_not_speaker_complaints(text):
    turn = build_rich_turn_from_text(text, utterance_id="other")
    assert not any(m.subject == "speaker" for m in turn.issue_mentions)


@pytest.mark.parametrize("duration", [
    "Это уже две недели продолжается так.", "Уже три дня.", "Это длится 2 недели.",
])
def test_pending_temporal_answer_has_real_duration_evidence(duration):
    r = ScenarioRunner()
    r.run([CallStarted(), "Руки ноют."])
    assert r.state.pending_episode_attribute in ("onset", "duration")
    ep_id = r.state.active_episode_id
    r.run([duration])
    ep = r.state.issue_episodes[ep_id]
    assert ep.known_attributes.get("duration")
    durations = [o for o in r.state.observations.values()
                 if hasattr(o, "attribute") and o.attribute == "duration"]
    assert durations
    assert all(o.evidence in duration and o.value != "Это" for o in durations)
    assert not any(hasattr(o, "attribute") and o.attribute == "onset"
                   and o.value.lower() == "это" for o in r.state.observations.values())


def test_reference_alone_does_not_invent_temporal_fact():
    r = ScenarioRunner()
    r.run([CallStarted(), "Руки ноют.", "Это."])
    ep = next(iter(r.state.issue_episodes.values()))
    assert not ep.known_attributes.get("duration")
    assert not ep.known_attributes.get("onset")


@pytest.mark.parametrize("answer", ["Сейчас не беспокоит.", "Не знаю две недели или нет."])
def test_current_or_unknown_answer_never_becomes_duration(answer):
    r = ScenarioRunner()
    r.run([CallStarted(), "Руки ноют.", answer])
    assert all(not ep.known_attributes.get("duration")
               for ep in r.state.issue_episodes.values())


def test_duration_out_of_order_is_preserved_without_answering_severity():
    r = ScenarioRunner()
    r.run([CallStarted(), "Голова болит с утра."])
    assert r.state.pending_episode_attribute == "severity"
    ep_id = r.state.active_episode_id
    r.run(["Уже две недели."])
    ep = r.state.issue_episodes[ep_id]
    assert ep.known_attributes["duration"] == "две недели"
    assert not ep.known_attributes.get("severity")
    assert r.state.pending_episode_attribute == "severity"
    assert any(hasattr(o, "attribute") and o.attribute == "duration"
               and o.evidence == "две недели" for o in r.state.observations.values())


@pytest.mark.parametrize("answer", [
    "Таблетки принимаю две недели.", "Две недели буду дома.",
    "Это две недели буду дома.",
    "У мужа спина болит две недели.",
])
def test_other_predicate_duration_does_not_belong_to_pending_headache(answer):
    r = ScenarioRunner()
    r.run([CallStarted(), "Голова болит с утра."])
    ep_id = r.state.active_episode_id
    assert r.state.pending_episode_attribute == "severity"
    r.run([answer])
    assert not r.state.issue_episodes[ep_id].known_attributes.get("duration")
    assert not any(hasattr(o, "attribute") and o.attribute == "duration"
                   and o.episode_id == ep_id and o.source_turn_id == "u-2"
                   for o in r.state.observations.values())


def test_out_of_order_quantity_does_not_overwrite_recorded_duration():
    r = ScenarioRunner()
    r.run([CallStarted(), "Голова болит уже два дня."])
    ep_id = r.state.active_episode_id
    before = r.state.issue_episodes[ep_id].known_attributes.get("duration")
    assert before
    r.run(["Это две недели."])
    assert r.state.issue_episodes[ep_id].known_attributes["duration"] == before


@pytest.mark.parametrize("answer", ["Таблетки принимаю две недели.", "Это две недели буду дома."])
def test_foreign_quantity_does_not_answer_pending_temporal_question(answer):
    r = ScenarioRunner()
    r.run([CallStarted(), "Руки ноют."])
    ep_id = r.state.active_episode_id
    r.run([answer])
    ep = r.state.issue_episodes[ep_id]
    assert not ep.known_attributes.get("onset")
    assert not ep.known_attributes.get("duration")


@pytest.mark.parametrize("personal_memory", [False, True])
def test_proposed_answer_cannot_turn_new_symptom_into_headache_severity(
    monkeypatch, personal_memory,
):
    from packages.dialogue_engine import caller_memory, slotclf

    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "1")
    monkeypatch.setattr(slotclf, "judge", lambda *args: "answer")
    monkeypatch.setattr(caller_memory, "resolve", lambda *args: "answer")
    r = ScenarioRunner()
    r.run([CallStarted(), "Голова болит с утра."])
    if personal_memory:
        r.state.client_id = "regression-client"
    ep_id = r.state.active_episode_id
    r.run(["Руки постоянно трясутся."])
    assert not r.state.issue_episodes[ep_id].known_attributes.get("severity")
    assert any("тряс" in m.label.lower() for ep in r.state.issue_episodes.values()
               for m in ep.mentions)


@pytest.mark.parametrize("personal_memory", [False, True])
def test_untyped_answer_vote_does_not_invent_clinical_severity(monkeypatch, personal_memory):
    from packages.dialogue_engine import caller_memory, slotclf

    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "1")
    monkeypatch.setattr(slotclf, "judge", lambda *args: "answer")
    monkeypatch.setattr(caller_memory, "resolve", lambda *args: "answer")
    r = ScenarioRunner()
    r.run([CallStarted(), "Голова болит с утра."])
    if personal_memory:
        r.state.client_id = "regression-client"
    ep_id = r.state.active_episode_id
    r.run(["Конкретнись и по поводу первого."])
    assert not r.state.issue_episodes[ep_id].known_attributes.get("severity")


@pytest.mark.parametrize("clarification", [
    "Конкретнись и по поводу первого.", "Уточните ваш вопрос.", "Конкретизируйте, о чём вопрос.",
])
def test_clarification_request_repairs_without_filling_clinical_answer(clarification):
    r = ScenarioRunner()
    r.run([CallStarted(), "Голова болит с утра."])
    ep_id = r.state.active_episode_id
    result = r.run([clarification])
    assert any(e.intent == "repair_repeat" for e in result.speak_effects)
    assert not r.state.issue_episodes[ep_id].known_attributes.get("severity")
    assert r.state.pending_episode_attribute == "severity"


def test_clarification_word_does_not_erase_same_turn_symptom():
    turn = build_rich_turn_from_text(
        "Уточните вопрос, у меня сильно болит голова.", utterance_id="mixed",
    )
    assert any(m.body_site == "голова" for m in turn.issue_mentions)


def test_live_answer_does_not_fill_interrupted_food_question(monkeypatch):
    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "1")
    r = ScenarioRunner()
    r.run([CallStarted(), "Я чувствую себя хорошо."])
    assert r.state.pending_coverage_domain == "nutrition"
    r.run(["Ой, поел нормально? Вот у меня что-то голова болит и руки ноют."])
    assert r.state.pending_coverage_domain is None
    r.run(["Это уже две недели продолжается так."])
    assert "coverage_nutrition" not in r.state.observations


def test_known_complaint_does_not_return_to_general_concern_probe():
    r = ScenarioRunner()
    r.run([CallStarted(), "Руки ноют."])
    result = r.run(["Это уже две недели продолжается так."])
    assert not any(e.intent in ("probe_concern", "probe_concern_options")
                   for e in result.speak_effects)


def test_new_vague_deterioration_can_still_request_concern():
    r = ScenarioRunner()
    r.run([CallStarted(), "Руки ноют.", "Две недели."])
    result = r.run(["А теперь мне ещё очень плохо."])
    assert any(e.intent in ("probe_concern", "probe_concern_options", "urgent_close")
               or e.intent.startswith("episode_") for e in result.speak_effects)


def test_full_recorded_call_preserves_symptoms_and_avoids_concern_loop(monkeypatch):
    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "1")
    r = ScenarioRunner(elder_display_name="Тамара Юрьевна")
    r.run([CallStarted(), "Я чувствую себя хорошо."])
    r.run(["Ой, поел нормально? Вот у меня что-то голова болит и руки ноют."])
    head = next(ep for ep in r.state.issue_episodes.values() if ep.body_site == "голова")
    assert head.known_attributes.get("current") != "resolved"
    duration_result = r.run(["Это уже две недели продолжается так."])
    assert not any(e.intent in ("probe_concern", "probe_concern_options")
                   for e in duration_result.speak_effects)
    tremor_result = r.run(["Жалобы, руки постоянно трясутся и кровят."])
    assert any("тряс" in m.label.lower() for ep in r.state.issue_episodes.values()
               for m in ep.mentions)
    assert not head.known_attributes.get("severity")
    assert not any(e.intent in ("probe_concern", "probe_concern_options")
                   for e in tremor_result.speak_effects)
    result = r.run(["Конкретнись и по поводу первого.", "Нет.", "До свидания."])
    assert r.state.call_closed
    assert not head.known_attributes.get("severity")
    # Exact caller inputs no longer contain a severity answer. Keep the
    # frozen honest exhaustion close instead of manufacturing completion.
    endings = [e for e in result.speak_effects
               if e.intent in ("goodbye_final", "partial_unresolved_close")]
    assert len(endings) == 1
    assert "до свидания" in endings[0].text.lower()
    assert all("рука ноют" not in e.text.lower() for e in r.effects if hasattr(e, "text"))
