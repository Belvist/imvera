"""Relation shadow scorer: all-goal cross-encoder scoring, log-only.

Loads the xenc artifact (encoder fork if present, else pinned base +
heads). score_all() returns per-goal relevance WITHOUT deciding anything:
the deterministic path owns all decisions. Shadow evidence (goal scores
vs deterministic outcome) feeds the next data batch.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from packages.dialogue_engine.semantic_nlp.labels import MODEL_ID

ARTIFACT_VERSION = "xenc_v3"
LATENCY_BUDGET_MS = 2000.0


@dataclass(frozen=True)
class GoalScore:
    goal_id: str
    score: float
    value: str | None = None


class RelationScorer:
    """Singleton. Call RelationScorer.get() then .score_all().

    MPS Metal inference must stay on the main thread (worker threads
    abort). Background/shadow callers MUST use get_cpu().
    """

    _instance: RelationScorer | None = None
    _instance_cpu: RelationScorer | None = None

    def __init__(self, version: str = ARTIFACT_VERSION, device: str | None = None) -> None:
        import torch
        import torch.nn as nn
        from transformers import AutoModel, AutoTokenizer

        root = Path(__file__).resolve().parent.parent.parent.parent
        artifact = root / "models" / "semantic_nlp" / version
        labels = json.loads((artifact / "labels.json").read_text(encoding="utf-8"))
        self._values: list[str] = list(labels["values"])
        device = device or ("mps" if torch.backends.mps.is_available() else "cpu")
        self._device = device
        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(
            MODEL_ID, trust_remote_code=False
        )
        encoder_dir = artifact / "encoder"
        if encoder_dir.is_dir():
            self._encoder = AutoModel.from_pretrained(str(encoder_dir)).to(device)
        else:
            self._encoder = AutoModel.from_pretrained(
                MODEL_ID, trust_remote_code=False
            ).to(device)
        self._encoder.eval()
        for param in self._encoder.parameters():
            param.requires_grad = False
        with open(artifact / "heads.pt", "rb") as fh:
            state = torch.load(fh, map_location=device, weights_only=True)
        dim = self._encoder.config.hidden_size
        self._head_rel = nn.Linear(dim, 1).to(device)
        self._head_val = nn.Linear(dim, len(self._values)).to(device)
        self._head_rel.load_state_dict(
            {k.removeprefix("rel."): v for k, v in state.items() if k.startswith("rel.")}
            or {k: v for k, v in state.items() if "rel" in k},
            strict=False,
        )
        self._head_val.load_state_dict(
            {k.removeprefix("val."): v for k, v in state.items() if k.startswith("val.")},
            strict=False,
        )
        self._head_rel.eval()
        self._head_val.eval()
        # Warmup with a real forward (never empty — see model.py lesson).
        self.score_all(
            "Как вы себя чувствуете?",
            "Хорошо.",
            [{"goal_id": "wellness", "description": "x"}],
        )

    @classmethod
    def get(cls) -> RelationScorer:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def get_cpu(cls) -> RelationScorer:
        """Thread-safe CPU instance for background/shadow scoring."""
        if cls._instance_cpu is None:
            cls._instance_cpu = cls(device="cpu")
        return cls._instance_cpu

    def score_all(
        self, question: str, utterance: str, goals: list[dict]
    ) -> tuple[list[GoalScore], float]:
        """Score every goal. Returns (scores, latency_ms). Never raises."""
        started = time.monotonic()
        try:
            return self._score(question, utterance, goals), (time.monotonic() - started) * 1000.0
        except Exception:
            return [], (time.monotonic() - started) * 1000.0

    def _score(
        self, question: str, utterance: str, goals: list[dict]
    ) -> list[GoalScore]:
        torch = self._torch
        out: list[GoalScore] = []
        with torch.no_grad():
            for goal in goals:
                allowed = ""
                if goal.get("allowed_values"):
                    allowed = f" ({'/'.join(goal['allowed_values'])})"
                text = (
                    f"[Q] {question} [G] {goal['description']}{allowed} "
                    f"[U] {utterance}"
                )
                batch = self._tokenizer(
                    text, return_tensors="pt", truncation=True, max_length=192
                )
                mask = batch["attention_mask"].to(self._device)
                batch = {k: v.to(self._device) for k, v in batch.items()}
                hidden = self._encoder(**batch).last_hidden_state
                pooled = (hidden * mask.unsqueeze(-1)).sum(1) / mask.sum(1).unsqueeze(-1)
                score = float(torch.sigmoid(self._head_rel(pooled)).squeeze())
                val_idx = int(self._head_val(pooled).argmax())
                out.append(
                    GoalScore(
                        goal_id=goal["goal_id"],
                        score=round(score, 3),
                        value=self._values[val_idx],
                    )
                )
        return out
