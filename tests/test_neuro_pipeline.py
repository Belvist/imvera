"""Neuro pipeline skeleton (ADR-024 slices 3/5, pre-model stage).

Proves the pipeline is complete and honest BEFORE any model exists:

- generator proposes variants that differ from canonical;
- validator composition is veto-only (neural approval alone denies);
- ranker loss trains on synthetic separable data and never assigns
  probability outside the legal set (illegal_rate == 0);
- feature gating rejects leaky v1 features;
- shadow scoring logs disagreements and never raises, disabled by default.
"""

from __future__ import annotations

import pytest
import torch

from packages.dialogue_engine.neuro.interfaces import RankScores
from packages.dialogue_engine.neuro.paraphrase import (
    ABSTAIN_VERSION,
    POOL_VERSION,
    AbstainingChecker,
    PoolGenerator,
    compose_proposal,
)
from packages.dialogue_engine.neuro.ranker import (
    TinyRanker,
    evaluate_ranker,
    gate_feature_bundle,
    masked_cross_entropy,
    select_ranked,
    train_tiny_ranker,
)
from packages.dialogue_engine.neuro.shadow import score_shadow, shadow_enabled

pytestmark = pytest.mark.dialogue_engine


def test_pool_generator_is_honestly_not_a_model() -> None:
    gen = PoolGenerator()
    assert gen.version == POOL_VERSION
    assert "pool" in gen.version
    out = gen.propose("Живот болит?", "Живот болит?")
    assert out
    assert all(p.generator_version == POOL_VERSION for p in out)
    assert all(p.text != "Живот болит?" for p in out)


def test_compose_falls_back_when_validator_denies() -> None:
    text, fallback = compose_proposal(
        "Живот болит?", "Живот болит?", deterministic_pass=lambda t: False
    )
    assert (text, fallback) == ("Живот болит?", True)


def test_compose_prefers_allowed_variant() -> None:
    text, fallback = compose_proposal(
        "Живот болит?",
        "Живот болит?",
        deterministic_pass=lambda t: "подскажите" in t.lower(),
    )
    assert fallback is False
    assert "подскажите" in text.lower()


def test_abstaining_checker_never_approves() -> None:
    checker = AbstainingChecker()
    assert checker.version == ABSTAIN_VERSION
    assert checker.check("x", "y") is None


def test_masked_loss_ignores_illegal_logits() -> None:
    logits = torch.tensor([[100.0, 0.0, 0.0]])
    legal = torch.tensor([[False, True, True]])
    target = torch.tensor([1])
    loss = masked_cross_entropy(logits, legal, target)
    assert float(loss) < 1.0  # illegal 100.0 must not leak into softmax


def test_masked_loss_rejects_shape_mismatch() -> None:
    with pytest.raises(ValueError):
        masked_cross_entropy(
            torch.zeros(1, 2),
            torch.ones(1, 3, dtype=torch.bool),
            torch.zeros(1, dtype=torch.long),
        )


def test_tiny_ranker_learns_synthetic_split() -> None:
    torch.manual_seed(7)
    actions = ["a", "b", "c"]
    # Separable by first feature; legal set excludes "c" on even rows.
    batches = []
    for i in range(12):
        x = torch.tensor([[float(i % 2), float(i // 2)]])
        mask = torch.tensor([[True, True, i % 2 == 1]])
        y = torch.tensor([i % 2])
        batches.append((x, mask, y))
    model = TinyRanker(2, 3)
    losses = train_tiny_ranker(model, batches, steps=60, lr=0.2)
    assert losses[-1] < losses[0]
    report = evaluate_ranker(model, batches, actions)
    assert report["illegal_rate"] == 0.0
    assert report["accuracy"] >= 0.9


def test_feature_gate_rejects_leaks() -> None:
    assert gate_feature_bundle({"site_mentioned": 1.0}) == []
    hits = gate_feature_bundle({"timestamp": 1, "user_id": "x", "polarity": 0.5})
    assert set(hits) == {"timestamp", "user_id"}


def test_select_ranked_never_leaves_legal() -> None:
    assert select_ranked({"a": 0.1, "zzz": 0.9}, ["a", "b"]) == "a"
    with pytest.raises(Exception):
        select_ranked({"zzz": 1.0}, ["a"])


def test_shadow_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("IMVERA_NEURO_SHADOW", raising=False)
    assert shadow_enabled() is False
    assert (
        score_shadow(
            signature="s",
            canonical_text="c",
            heuristic_choice="a",
            legal_action_ids=["a", "b"],
        )
        is None
    )


def test_shadow_logs_disagreement(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("IMVERA_NEURO_SHADOW", "1")
    monkeypatch.setenv("IMVERA_PROOF_DIR", str(tmp_path))
    assert shadow_enabled() is True
    row = score_shadow(
        signature="Живот болит?",
        canonical_text="Живот болит?",
        heuristic_choice="ask_onset",
        legal_action_ids=["ask_onset", "ask_severity"],
        rank_scores=RankScores(
            scores={"ask_onset": 0.2, "ask_severity": 0.8},
            ranker_version="synth-v0",
            legal_action_ids=("ask_onset", "ask_severity"),
        ),
        call_id="fs-t",
        turn_id="t-1",
    )
    assert row is not None
    assert row["agreed"] is False
    assert row["ranker_choice"] == "ask_severity"
    from datetime import date

    proof_file = tmp_path / f"proof-{date.today().isoformat()}.jsonl"
    assert any("neuro_shadow" in line for line in proof_file.read_text().splitlines())
