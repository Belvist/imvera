"""NLP candidate mapping: model proposes, rules stay supreme."""

from __future__ import annotations

import pytest

from packages.dialogue_engine.semantic import SemanticAct
from packages.dialogue_engine.semantic_nlp import candidate as cand_mod
from packages.dialogue_engine.semantic_nlp.model import ActCandidate

pytestmark = pytest.mark.dialogue_engine


class _FakeNLP:
    def __init__(self, result):
        self._result = result

    def predict(self, question, text):
        return self._result


def _patch(monkeypatch: pytest.MonkeyPatch, result) -> None:
    monkeypatch.setattr(cand_mod.SemanticNLP, "get", classmethod(lambda cls: _FakeNLP(result)))


def test_used_mapping_backchannel(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, ActCandidate(act="backchannel", confidence=0.95, latency_ms=5.0))
    turn, used, info = cand_mod.nlp_candidate_turn("Как дела?", "Ага.", "wellness")
    assert used and info["used"] is True
    assert turn is not None and turn.act == SemanticAct.BACKCHANNEL
    assert turn.target_slot == "wellness"


def test_safety_acts_never_used(monkeypatch: pytest.MonkeyPatch) -> None:
    for act in ("stop", "user_question"):
        _patch(monkeypatch, ActCandidate(act=act, confidence=0.99, latency_ms=5.0))
        turn, used, _info = cand_mod.nlp_candidate_turn("Как дела?", "Отстань.", "wellness")
        assert turn is None and used is False


def test_low_confidence_falls_through(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, ActCandidate(act="answer", confidence=0.40, latency_ms=5.0))
    turn, used, _info = cand_mod.nlp_candidate_turn("Когда началось?", "Вчера.", "onset")
    assert turn is None and used is False


def test_model_error_falls_through(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Boom:
        def predict(self, question, text):
            raise RuntimeError("no backend")

    monkeypatch.setattr(cand_mod.SemanticNLP, "get", classmethod(lambda cls: _Boom()))
    turn, used, info = cand_mod.nlp_candidate_turn("?", "Привет.", None)
    assert turn is None and used is False


def test_model_error_traced_for_live_diagnosis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live fs-8a64bac9 turn 1: 6.3 s inside predict, no latency recorded.
    The failure must name itself in info (traced via interpret.nlp_candidate)."""

    class _SlowBoom:
        def predict(self, question, text):
            raise TimeoutError("mps stall")

    monkeypatch.setattr(
        cand_mod.SemanticNLP, "get", classmethod(lambda cls: _SlowBoom())
    )
    turn, used, info = cand_mod.nlp_candidate_turn("?", "Привет.", None)
    assert turn is None and used is False
    assert info.get("nlp_error") == "TimeoutError"
    assert float(info.get("nlp_get_ms", -1)) >= 0


def test_correction_flag_and_polarity(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, ActCandidate(act="correction", confidence=0.9, latency_ms=5.0))
    turn, used, _info = cand_mod.nlp_candidate_turn("Как дела?", "Плохо… хотя нет.", "wellness")
    assert used and turn is not None
    assert turn.act == SemanticAct.ANSWER and turn.correction is True
    _patch(monkeypatch, ActCandidate(act="decline", confidence=0.9, latency_ms=5.0))
    turn2, used2, _info2 = cand_mod.nlp_candidate_turn("Подробнее?", "Не надо.", "wellness")
    assert used2 and turn2 is not None and turn2.polarity == "negative"
