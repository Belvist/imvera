"""Runtime wrapper for the semantic-NLP act classifier (v1).

Live by default (owner order: no off switches) with hard hierarchy:
the model proposes a candidate act + confidence; the deterministic
validator owns every decision and safety always wins. Latency budget
enforced — on timeout/error the path degrades to deterministic-only,
never to a guess.

Artifact: models/semantic_nlp/<version>/{head.pt, labels.json}.
Encoder weights are the pinned upstream repo (no local encoder fork in
v1); only the head is versioned.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from packages.dialogue_engine.semantic_nlp.labels import ACTS, MODEL_ID

ARTIFACT_VERSION = "v2"
# Live default head version. Override with IMVERA_ACT_HEAD_VERSION only for
# shadow/eval runs; production promotion is a gated decision, not an env
# flip. Unknown versions fall back to the default WITH a loud warning
# (warmup must never take the bridge down over a typo).
LIVE_DEFAULT_VERSION = "v2"
LATENCY_BUDGET_MS = 300.0
# 0.55: model is underconfident on short phrases (correct at 0.55+);
# safety acts are excluded from override regardless of confidence.
CONFIDENCE_THRESHOLD = 0.55


@dataclass(frozen=True)
class ActCandidate:
    act: str
    confidence: float
    latency_ms: float


class SemanticNLP:
    """Singleton act classifier. Call SemanticNLP.get() then .predict()."""

    _instances: dict[str, SemanticNLP] = {}

    def __init__(self, version: str = ARTIFACT_VERSION) -> None:
        import torch
        import torch.nn as nn
        from transformers import AutoModel, AutoTokenizer

        root = Path(__file__).resolve().parent.parent.parent.parent
        artifact = root / "models" / "semantic_nlp" / version
        labels = json.loads((artifact / "labels.json").read_text(encoding="utf-8"))
        self._acts: list[str] = list(labels["acts"])
        assert self._acts == list(ACTS), "artifact labels drifted from schema"
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        self._device = device
        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(
            MODEL_ID, trust_remote_code=False
        )
        self._encoder = AutoModel.from_pretrained(
            MODEL_ID, trust_remote_code=False
        ).to(device)
        self._encoder.eval()
        for param in self._encoder.parameters():
            param.requires_grad = False
        head = nn.Linear(self._encoder.config.hidden_size, len(self._acts))
        head.load_state_dict(
            torch.load(artifact / "head.pt", map_location=device, weights_only=True)
        )
        head.to(device)
        head.eval()
        self._head = head
        # Warmup with a REAL forward pass (first Metal call compiles; an
        # empty-text call would return early and warm nothing).
        self.predict("Как вы себя чувствуете?", "Хорошо.")

    @classmethod
    def get(cls, version: str | None = None) -> SemanticNLP:
        import logging
        import os

        ver = (
            version
            or os.environ.get("IMVERA_ACT_HEAD_VERSION", "").strip()
            or LIVE_DEFAULT_VERSION
        )
        if ver not in cls._instances:
            try:
                cls._instances[ver] = cls(version=ver)
            except Exception as exc:
                logging.getLogger("imvera.nlp").warning(
                    "act head %r failed to load (%s); falling back to %r",
                    ver,
                    exc,
                    LIVE_DEFAULT_VERSION,
                )
                if LIVE_DEFAULT_VERSION not in cls._instances:
                    cls._instances[LIVE_DEFAULT_VERSION] = cls(
                        version=LIVE_DEFAULT_VERSION
                    )
                return cls._instances[LIVE_DEFAULT_VERSION]
        return cls._instances[ver]

    def predict(self, question: str, text: str) -> ActCandidate | None:
        """Return act candidate or None (over budget / empty / error)."""
        if not text.strip():
            return None
        started = time.monotonic()
        try:
            torch = self._torch
            with torch.no_grad():
                batch = self._tokenizer(
                    f"[Q] {question} [U] {text}",
                    return_tensors="pt",
                    truncation=True,
                    max_length=128,
                )
                mask = batch["attention_mask"].to(self._device)
                batch = {k: v.to(self._device) for k, v in batch.items()}
                hidden = self._encoder(**batch).last_hidden_state
                pooled = (hidden * mask.unsqueeze(-1)).sum(1) / mask.sum(1).unsqueeze(-1)
                logits = self._head(pooled)
                probs = torch.softmax(logits, dim=1).squeeze()
                confidence = float(probs.max())
                act = self._acts[int(probs.argmax())]
        except Exception:
            return None
        latency_ms = (time.monotonic() - started) * 1000.0
        if latency_ms > LATENCY_BUDGET_MS:
            return None
        return ActCandidate(act=act, confidence=confidence, latency_ms=latency_ms)
