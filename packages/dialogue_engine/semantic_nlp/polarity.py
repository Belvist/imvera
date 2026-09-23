"""Runtime wrapper for the polarity classifier v1.

positive/negative/uncertain wellness valence. Candidate-only, same hierarchy
as the act classifier: rules decide first; the model speaks ONLY where rules
abstain (polarity None); deterministic validator supreme; any error/timeout
→ None (existing fallback chain, never a guess).

Artifact: models/semantic_nlp/polarity_v1/{head.pt, labels.json, metrics.json}.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

ARTIFACT_VERSION = "polarity_v1"
LATENCY_BUDGET_MS = 300.0
# Same bar as act (0.55): fires on live shapes (покушала 0.75, ничего 0.67),
# abstains on hedges (так себе 0.52 → existing judge chain).
CONFIDENCE_THRESHOLD = 0.55


_GREETING_PREFIX = re.compile(
    r"^(привет|здравствуйте|добрый\s+(день|вечер)|доброе\s+утро)[\s,.!]*",
    re.I,
)


def _strip_leading_greeting(text: str) -> str:
    """Greetings carry no valence («Здравствуйте. Самочувствие хорошее» kept
    misfiring on the hello). Strip one leading greeting clause."""
    return _GREETING_PREFIX.sub("", text or "", count=1)


@dataclass(frozen=True)
class PolarityCandidate:
    polarity: str
    confidence: float
    latency_ms: float


class PolarityModel:
    """Singleton polarity classifier. Call PolarityModel.get().predict()."""

    _instance: PolarityModel | None = None

    def __init__(self, version: str = ARTIFACT_VERSION) -> None:
        import torch
        import torch.nn as nn
        from transformers import AutoModel, AutoTokenizer

        from packages.dialogue_engine.semantic_nlp.labels import MODEL_ID

        root = Path(__file__).resolve().parent.parent.parent.parent
        artifact = root / "models" / "semantic_nlp" / version
        labels = json.loads((artifact / "labels.json").read_text(encoding="utf-8"))
        self._labels: list[str] = list(labels["labels"])
        assert self._labels == ["negative", "positive", "uncertain"], (
            "artifact labels drifted from schema"
        )
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
        head = nn.Linear(self._encoder.config.hidden_size, len(self._labels))
        head.load_state_dict(
            torch.load(artifact / "head.pt", map_location=device, weights_only=True)
        )
        head.to(device)
        head.eval()
        self._head = head
        self.predict("Всё хорошо.")

    @classmethod
    def get(cls) -> PolarityModel:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def predict(self, text: str) -> PolarityCandidate | None:
        """Return polarity candidate or None (abstain / error / over budget)."""
        cleaned = _strip_leading_greeting(text)
        if not cleaned.strip():
            return None
        started = time.monotonic()
        try:
            torch = self._torch
            with torch.no_grad():
                batch = self._tokenizer(
                    f"[U] {cleaned.strip()}",
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
                polarity = self._labels[int(probs.argmax())]
        except Exception:
            return None
        latency_ms = (time.monotonic() - started) * 1000.0
        if latency_ms > LATENCY_BUDGET_MS:
            return None
        if confidence < CONFIDENCE_THRESHOLD:
            return None
        return PolarityCandidate(
            polarity=polarity, confidence=confidence, latency_ms=latency_ms
        )
