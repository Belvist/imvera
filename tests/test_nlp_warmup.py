"""NLP models are always hot: warmup loads + exercises, blockers refuse cold."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.dialogue_engine


def test_warmup_all_hot() -> None:
    from packages.dialogue_engine.semantic_nlp.warmup import nlp_blockers, warmup_all

    report = warmup_all()
    assert [m.name for m in report.models] == ["act", "relation_cpu"]
    assert report.all_hot, [(m.name, m.error) for m in report.models]
    assert all(m.latency_ms > 0 for m in report.models)
    assert not _with_report(report, nlp_blockers)


def _with_report(report, fn):
    import packages.dialogue_engine.semantic_nlp.warmup as warmup_mod

    saved = warmup_mod._report
    warmup_mod._report = report
    try:
        return fn()
    finally:
        warmup_mod._report = saved


def test_blockers_when_never_ran() -> None:
    from packages.dialogue_engine.semantic_nlp import warmup as warmup_mod

    saved = warmup_mod._report
    warmup_mod._report = None
    try:
        assert warmup_mod.nlp_blockers() == ["nlp: warmup never ran"]
    finally:
        warmup_mod._report = saved


def test_blockers_report_cold_model() -> None:
    from packages.dialogue_engine.semantic_nlp.warmup import (
        ModelWarmth,
        WarmupReport,
        nlp_blockers,
    )

    report = WarmupReport(
        models=[
            ModelWarmth(name="act", ok=True, latency_ms=15.0, device="mps"),
            ModelWarmth(name="relation_cpu", ok=False, latency_ms=1.0, error="boom"),
        ]
    )
    assert not report.all_hot
    blockers = _with_report(report, nlp_blockers)
    assert len(blockers) == 1 and "relation_cpu" in blockers[0]
