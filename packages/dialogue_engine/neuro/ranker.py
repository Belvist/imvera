"""Ranker training primitives (ADR-024 slice 5, pre-traffic stage).

No production wiring: loss, feature gating, and a synthetic/frozen
evaluator so the whole learning loop exists and is tested BEFORE traffic
outcomes arrive. Training on real outcomes without this harness is
forbidden by the same module that enables it.
"""

from __future__ import annotations

import torch
import torch.nn as nn

from packages.dialogue_engine.proof_bundle import (
    BANNED_RANKER_FEATURES_V1,
    check_ranker_features,
    select_from_legal,
)

FEATURE_ALLOWLIST_NOTE = (
    "Ranker v1 sees semantic features only (site mentioned, verb class, "
    "polarity, act). Banned: timestamp, weekday, durations, user/call ids."
)


def masked_cross_entropy(
    logits: torch.Tensor, legal_mask: torch.Tensor, target: torch.Tensor
) -> torch.Tensor:
    """Cross-entropy over the legal set only.

    Illegal logits are masked to -inf BEFORE softmax: the model cannot
    assign probability outside the protocol, during training or inference.
    Shapes: logits (B, A), legal_mask (B, A) bool, target (B,) long.
    """
    if legal_mask.dim() != 2 or logits.shape != legal_mask.shape:
        raise ValueError("logits and legal_mask shape mismatch")
    if target.dim() != 1 or target.shape[0] != logits.shape[0]:
        raise ValueError("target batch mismatch")
    masked = logits.masked_fill(~legal_mask, float("-inf"))
    return nn.functional.cross_entropy(masked, target)


class TinyRanker(nn.Module):
    """Linear head over frozen-encoder-style features (synthetic/test scale).

    Production heads will hang off the shared frozen encoder; this module
    proves the loss, the masking, and the evaluator on synthetic data.
    """

    def __init__(self, in_dim: int, n_actions: int) -> None:
        super().__init__()
        self.head = nn.Linear(in_dim, n_actions)

    def forward(
        self, features: torch.Tensor, legal_mask: torch.Tensor
    ) -> torch.Tensor:
        return self.head(features).masked_fill(~legal_mask, float("-inf"))


def gate_feature_bundle(features: dict) -> list[str]:
    """Reject banned v1 features before they reach any ranker. Returns hits."""
    return check_ranker_features(features)


def train_tiny_ranker(
    model: TinyRanker,
    batches: list[tuple[torch.Tensor, torch.Tensor, torch.Tensor]],
    steps: int = 50,
    lr: float = 0.1,
) -> list[float]:
    """Supervised loop on synthetic batches. Returns per-step losses."""
    opt = torch.optim.SGD(model.parameters(), lr=lr)
    losses: list[float] = []
    for _ in range(steps):
        total = torch.zeros(())
        for features, legal_mask, target in batches:
            opt.zero_grad()
            loss = masked_cross_entropy(model.head(features), legal_mask, target)
            loss.backward()
            opt.step()
            total = total + loss.detach()
        losses.append(float(total) / max(len(batches), 1))
    return losses


def evaluate_ranker(
    model: TinyRanker,
    batches: list[tuple[torch.Tensor, torch.Tensor, torch.Tensor]],
    action_ids: list[str],
) -> dict[str, float]:
    """Frozen evaluation: accuracy + illegal-selection rate (must be 0)."""
    correct = 0
    total = 0
    illegal = 0
    model.eval()
    with torch.no_grad():
        for features, legal_mask, target in batches:
            logits = model(features, legal_mask)
            pred = int(torch.argmax(logits, dim=1)[0])
            legal_idx = [i for i, ok in enumerate(legal_mask[0].tolist()) if ok]
            if pred not in legal_idx:
                illegal += 1
                continue
            total += 1
            if pred == int(target[0]):
                correct += 1
    return {
        "accuracy": (correct / total) if total else 0.0,
        "illegal_rate": illegal / max(len(batches), 1),
        "n": float(len(batches)),
    }


def select_ranked(
    scores: dict[str, float], legal_action_ids: list[str]
) -> str:
    """Production selection entry point: scores in, legal id out."""
    return select_from_legal(legal_action_ids, scores=scores)


__all__ = [
    "BANNED_RANKER_FEATURES_V1",
    "TinyRanker",
    "evaluate_ranker",
    "gate_feature_bundle",
    "masked_cross_entropy",
    "select_ranked",
    "train_tiny_ranker",
]
