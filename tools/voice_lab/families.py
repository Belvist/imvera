"""Family IDs for training rows — no-leakage splits (reviewer item 1).

A family = one source example; all its variants (fillers, case, punctuation)
inherit the source's ID. GroupKFold splits by family so variants of one
phrase never land in train and control simultaneously. Grouping by LABEL
(e.g. `answer`) is forbidden — it proves nothing.

Held-out CONVERSATIONS (multi-turn, never tuned on) live separately in
tools/voice_lab/heldout_conversations.py (item 4 fixtures).
"""

from __future__ import annotations

import re

_FILLER_PREFIXES = ("ну ", "да ", "вот ", "прям ", "это ", "ну вот ")


def family_of(text: str, slot: str = "") -> str:
    t = (text or "").strip().lower().rstrip(".!?…")
    for prefix in sorted(_FILLER_PREFIXES, key=len, reverse=True):
        if t.startswith(prefix):
            t = t[len(prefix):]
            break
    t = re.sub(r"\s+", " ", t).strip()
    return f"{slot}||{t}" if slot else t


def group_report(groups: list[str]) -> dict:
    from collections import Counter

    counts = Counter(groups)
    return {
        "families": len(counts),
        "rows": len(groups),
        "singletons": sum(1 for v in counts.values() if v == 1),
    }
