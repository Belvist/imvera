"""Slot-answer judge — second tier after lexical anchors (pilot only).

When extract_grounded_*_value misses, instead of immediately counting the
turn as ungrounded (repeat → divert → partial), ask the slot classifier:
answer (record the user's own words, capped) / skip (advance, no value) /
garbage (existing clarify path).

Same contract as tinyllm: validator-clamped, probability threshold 0.6,
fail-open, never invents values. Enabled with the pilot pack flag
(IMVERA_COVERAGE_LADDER=1); frozen path never calls this module.
"""

from __future__ import annotations

import pickle
from pathlib import Path

THRESHOLD = 0.6
LABELS = ("answer", "skip", "garbage")

_clf = None


def _load() -> object:
    global _clf
    if _clf is None:
        path = (
            Path(__file__).resolve().parent.parent.parent
            / "models"
            / "slot_answer_clf.pkl"
        )
        with open(path, "rb") as f:
            _clf = pickle.load(f)
    return _clf


def judge(slot: str, text: str) -> str | None:
    """answer|skip|garbage, or None (disabled / abstain / any failure)."""
    from packages.dialogue_engine.runtime import coverage_ladder_enabled

    if not coverage_ladder_enabled():
        return None
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        clf = _load()
        feats = [f"{slot} || {raw.lower()}"]
        proba = clf.predict_proba(feats)[0]
        best = max(range(len(proba)), key=lambda i: proba[i])
        label = clf.classes_[best]
        if proba[best] < THRESHOLD or label not in LABELS:
            _quarantine(slot, raw)
            return None
        return str(label)
    except Exception:  # noqa: BLE001 — fail open to the ungrounded path
        return None


def judge_proba(slot: str, text: str) -> float | None:
    """Top-class probability (for the learning gate), or None."""
    from packages.dialogue_engine.runtime import coverage_ladder_enabled

    if not coverage_ladder_enabled():
        return None
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        clf = _load()
        proba = clf.predict_proba([f"{slot} || {raw.lower()}"])[0]
        return float(max(proba))
    except Exception:  # noqa: BLE001
        return None


def _quarantine(slot: str, text: str) -> None:
    """Abstains go to review, never to training (anti-bred gate).

    tools/voice_lab/review_quarantine.py shows grouped candidates;
    only human-approved quotes enter via add_quote.
    """
    import json
    import time

    try:
        path = (
            Path(__file__).resolve().parent.parent.parent
            / ".run"
            / "quarantine"
            / "slot_abstain.jsonl"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "slot": slot,
                     "text": text[:120]},
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:  # noqa: BLE001 — telemetry never breaks dialogue
        pass
