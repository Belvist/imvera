"""Polarity v1: learned valence where rules abstain, candidate-only."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.dialogue_engine


def test_live_shapes() -> None:
    from packages.dialogue_engine.semantic_nlp.polarity import PolarityModel

    get = PolarityModel.get().predict
    cand = get("Ну хорошо, только что покушала.")
    assert cand is not None and cand.polarity == "positive", cand
    cand = get("Ничего меня не беспокоит.")
    assert cand is not None and cand.polarity == "positive", cand
    cand = get("Голова болит.")
    assert cand is not None and cand.polarity == "negative", cand
    assert all(c.latency_ms < 300 for c in [get("Плохо.")] if c)


def test_abstains_on_hedge_and_empty() -> None:
    from packages.dialogue_engine.semantic_nlp.polarity import PolarityModel

    get = PolarityModel.get().predict
    assert get("") is None
    assert get("Так себе.") is None or get("Так себе.").polarity == "uncertain"


def test_mission_fallback_uses_model_before_judge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fs-27a3ced4 chain: rules None → model positive (not judge→uncertain)."""
    import packages.dialogue_engine.semantic_kernel.observation_memory as om

    seen: list[str] = []
    orig_judge = None
    try:
        from packages.dialogue_engine import slotclf as slotclf_mod

        orig_judge = slotclf_mod.judge

        def spy_judge(slot, text):
            seen.append(text)
            return orig_judge(slot, text)

        monkeypatch.setattr(slotclf_mod, "judge", spy_judge)
    except ImportError:
        pass
    assert om._polarity_model_vote("Ну хорошо, только что покушала.") == "positive"
    assert seen == [], seen
