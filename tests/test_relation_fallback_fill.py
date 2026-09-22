"""Relation fallback fill: model rescues answers normal fill drops."""

from __future__ import annotations

import pytest

from packages.contracts.enums import SlotStatus
from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.state import Question, QuestionPhase

pytestmark = pytest.mark.dialogue_engine


class _FakeScorer:
    def __init__(self, score: float):
        self._score = score

    def score_all(self, question, utterance, goals):
        from packages.dialogue_engine.semantic_nlp.relation import GoalScore

        return (
            [GoalScore(goal_id=goals[0]["goal_id"], score=self._score)],
            5.0,
        )


def _engine_with_pending() -> DialogueEngine:
    engine = DialogueEngine(call_id="relfill", elder_display_name="Тест")
    engine.start()
    engine.state.delivered_question = Question(
        question_id="q1",
        slot="wellness",
        text="Как вы себя чувствуете?",
        phase=QuestionPhase.DELIVERED,
        intent="check_wellness",
        goal_id="wellness",
    )
    return engine


def test_relation_fill_rescues_dropped_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    import packages.dialogue_engine.reducer as reducer_mod
    from packages.dialogue_engine.semantic_nlp import relation as relation_mod

    monkeypatch.setattr(
        relation_mod.RelationScorer, "get", classmethod(lambda cls: _FakeScorer(0.85))
    )
    engine = _engine_with_pending()
    filled = reducer_mod._relation_fallback_fill(
        engine.state, "Чувствую себя вполне прилично.", "wellness"
    )
    assert filled == ["wellness"]
    assert engine.state.slot_values["wellness"] == "Чувствую себя вполне прилично."


def test_relation_fill_abstains_below_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    import packages.dialogue_engine.reducer as reducer_mod
    from packages.dialogue_engine.semantic_nlp import relation as relation_mod

    monkeypatch.setattr(
        relation_mod.RelationScorer, "get", classmethod(lambda cls: _FakeScorer(0.40))
    )
    engine = _engine_with_pending()
    assert (
        reducer_mod._relation_fallback_fill(engine.state, "Эм.", "wellness") == []
    )
    assert engine.state.slots.get("wellness") != SlotStatus.FILLED


def test_relation_fill_skips_probes_and_safety(monkeypatch: pytest.MonkeyPatch) -> None:
    import packages.dialogue_engine.reducer as reducer_mod
    from packages.dialogue_engine.semantic_nlp import relation as relation_mod

    monkeypatch.setattr(
        relation_mod.RelationScorer, "get", classmethod(lambda cls: _FakeScorer(0.99))
    )
    engine = _engine_with_pending()
    engine.state.delivered_question = Question(
        question_id="q2",
        slot="wellness",
        text="Что беспокоит?",
        phase=QuestionPhase.DELIVERED,
        intent="probe_concern",
        goal_id="wellness",
    )
    assert (
        reducer_mod._relation_fallback_fill(engine.state, "Голова.", "wellness") == []
    )
    engine2 = _engine_with_pending()
    engine2.state.risk_handling = True
    assert (
        reducer_mod._relation_fallback_fill(engine2.state, "Хорошо.", "wellness")
        == []
    )
