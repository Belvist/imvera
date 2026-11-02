"""Long source speech must not exceed the bounded fact-value contract."""

import pytest

from packages.dialogue_engine.engine import DialogueEngine

pytestmark = pytest.mark.dialogue_engine


@pytest.mark.parametrize(
    "text",
    [
        "Спала плохо. " + "Вчера мы вспоминали фотографии и сад. " * 20,
        "Вчера мы вспоминали фотографии и сад. " * 20 + "Спала плохо.",
        "Спала плохо и " + "часто просыпалась и " * 40 + "была усталой.",
    ],
    ids=["sleep-first", "sleep-last", "long-sleep-clause"],
)
def test_long_sleep_report_stays_source_grounded_without_crashing(monkeypatch, text):
    monkeypatch.setenv("IMVERA_LLM_INTERPRET", "0")
    monkeypatch.setenv("IMVERA_MISSION_LLM_INTERPRET", "0")
    engine = DialogueEngine(call_id="long-care")
    engine.start()
    while (speech := engine.pop_speak_effect()) is not None:
        engine.on_playout_completed(speech.generation, speech.question_id)
    turn = engine.build_rich_turn(text, utterance_id="long")
    fact = next(f for f in turn.goal_facts if f.field == "sleep")
    assert len(fact.value) <= 500
    assert fact.value in text
    assert text[fact.evidence.start : fact.evidence.end] == fact.evidence.quote
    engine.on_user_turn("long", text, rich_turn=turn)
    assert engine.state.slot_records["sleep"].source_turn_id == "long"


def test_long_narrative_does_not_load_or_run_a_truncated_polarity_vote(monkeypatch):
    from packages.dialogue_engine.semantic_kernel.observation_memory import _polarity_model_vote
    from packages.dialogue_engine.semantic_nlp.polarity import PolarityModel

    calls = []

    def unavailable():
        calls.append("load")
        raise RuntimeError("must not enter a model for an unbounded narrative")

    monkeypatch.setattr(PolarityModel, "get", unavailable)
    assert _polarity_model_vote("Вчера смотрели фотографии. " * 30) is None
    assert not calls


def test_bounded_sleep_fact_does_not_discard_late_complaints(monkeypatch):
    monkeypatch.setenv("IMVERA_LLM_INTERPRET", "0")
    monkeypatch.setenv("IMVERA_MISSION_LLM_INTERPRET", "0")
    text = ("Спала хорошо. " + "Вчера вспоминали фотографии и сад. " * 30
            + "Голова болит со вчера, живот болит с утра.")
    engine = DialogueEngine(call_id="long-multiple-complaints")
    engine.start()
    while (speech := engine.pop_speak_effect()) is not None:
        engine.on_playout_completed(speech.generation, speech.question_id)
    turn = engine.build_rich_turn(text, utterance_id="long")
    sites = {mention.body_site for mention in turn.issue_mentions}
    assert {"голова", "живот"} <= sites
    for mention in turn.issue_mentions:
        if mention.body_site in {"голова", "живот"}:
            assert mention.evidence.start > 500
            assert text[mention.evidence.start:mention.evidence.end] == mention.evidence.quote
    engine.on_user_turn("long", text, rich_turn=turn)
    assert {"голова", "живот"} <= {ep.body_site for ep in engine.state.issue_episodes.values()}
    assert len(engine.state.slot_records["sleep"].value) <= 500
