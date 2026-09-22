"""Process-wide NLP warmup: models must be hot before any call.

Both live models are lazy singletons (SemanticNLP act classifier on MPS,
RelationScorer CPU instance for shadow). First touch used to happen mid-call
on turn 1 (measured 6.2 s interpret hole, fs-1b34dc2b). This module loads them
once at bridge startup — synchronously on the loop thread (MPS-safe: the Metal
backend aborts in worker threads) — plus one real forward each.

Either hot or honestly refusing: startup failure leaves warmth() cold and
readiness/inference blockers reject calls instead of serving a 6 s hole.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

_WARM_QUESTION = "Как вы себя чувствуете?"
_WARM_UTTERANCE = "Спасибо, хорошо."


@dataclass
class ModelWarmth:
    name: str
    ok: bool
    latency_ms: float = 0.0
    device: str = ""
    error: str = ""


@dataclass
class WarmupReport:
    models: list[ModelWarmth] = field(default_factory=list)

    @property
    def all_hot(self) -> bool:
        return bool(self.models) and all(m.ok for m in self.models)


_report: WarmupReport | None = None


def warmup_all() -> WarmupReport:
    """Load + exercise every live NLP model. Never raises. Idempotent-ish
    (singletons; second call only re-runs the cheap forwards)."""
    global _report
    models: list[ModelWarmth] = []

    started = time.monotonic()
    try:
        from packages.dialogue_engine.semantic_nlp.model import SemanticNLP

        inst = SemanticNLP.get()
        inst.predict(_WARM_QUESTION, _WARM_UTTERANCE)
        models.append(
            ModelWarmth(
                name="act",
                ok=True,
                latency_ms=(time.monotonic() - started) * 1000.0,
                device=str(getattr(inst, "_device", "?")),
            )
        )
    except Exception as exc:  # noqa: BLE001 — warmth must never break startup
        models.append(
            ModelWarmth(
                name="act",
                ok=False,
                latency_ms=(time.monotonic() - started) * 1000.0,
                error=f"{type(exc).__name__}: {exc}"[:300],
            )
        )

    started = time.monotonic()
    try:
        from packages.dialogue_engine.semantic_nlp.relation import RelationScorer

        cpu = RelationScorer.get_cpu()
        cpu.score_all(
            _WARM_QUESTION,
            _WARM_UTTERANCE,
            [{"goal_id": "wellness", "description": "x"}],
        )
        models.append(
            ModelWarmth(
                name="relation_cpu",
                ok=True,
                latency_ms=(time.monotonic() - started) * 1000.0,
                device=str(getattr(cpu, "_device", "?")),
            )
        )
    except Exception as exc:  # noqa: BLE001 — warmth must never break startup
        models.append(
            ModelWarmth(
                name="relation_cpu",
                ok=False,
                latency_ms=(time.monotonic() - started) * 1000.0,
                error=f"{type(exc).__name__}: {exc}"[:300],
            )
        )

    _report = WarmupReport(models=models)
    return _report


def warmth() -> WarmupReport | None:
    """Last warmup report, or None if warmup never ran."""
    return _report


def nlp_blockers() -> list[str]:
    """Honest readiness: empty when every live model is hot."""
    report = warmth()
    if report is None:
        return ["nlp: warmup never ran"]
    return [
        f"nlp: {m.name} cold ({m.error})" for m in report.models if not m.ok
    ]
