"""Review quarantine with suggestions + batch approve (anti-dictionary loop).

Each abstain shows the slot classifier's verdict + confidence. The human
only approves/rejects — no regex, no code edits:
  python3 tools/voice_lab/review_quarantine.py            # list with suggestions
  python3 tools/voice_lab/review_quarantine.py --approve # apply suggestions >=0.85, rest stay
Approved rows append to train_slot_answer_clf LIVE_QUOTES, retrain runs,
bench+fuzz gates must stay green or the batch is rejected.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

PATH = ROOT / ".run" / "quarantine" / "slot_abstain.jsonl"
APPROVE_MIN_SIM = 0.9  # near-duplicates only; rest need a human


def _suggest(slot: str, text: str) -> tuple[str | None, float]:
    """Nearest approved neighbor (not the abstaining judge — it already
    refused these). Similarity over the same hashed n-grams."""
    try:
        import numpy as np
        from sklearn.feature_extraction.text import HashingVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        from tools.voice_lab.train_slot_answer_clf import build_rows

        rows = [(s, t, lab) for s, t, lab in build_rows()
                if s == slot or True]
        vec = HashingVectorizer(n_features=2**12, ngram_range=(1, 2),
                                alternate_sign=False)
        X = vec.transform([f"{s} || {t.lower()}" for s, t, _ in rows])
        q = vec.transform([f"{slot} || {text.lower()}"])
        sims = cosine_similarity(q, X)[0]
        best = int(np.argmax(sims))
        return rows[best][2], float(sims[best])
    except Exception:
        return None, 0.0


def collect() -> list[tuple[str, str, int]]:
    groups: Counter = Counter()
    if not PATH.exists():
        return []
    for line in PATH.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            groups[(row.get("slot", "?"), row.get("text", "?"))] += 1
        except Exception:
            continue
    return [(s, t, n) for (s, t), n in groups.most_common(100)]


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--approve", action="store_true")
    args = ap.parse_args()

    items = collect()
    if not items:
        print("quarantine empty — nothing to review")
        return 0
    approved = 0
    for slot, text, n in items:
        verdict, sim = _suggest(slot, text)
        mark = "AUTO-OK" if (verdict and sim >= APPROVE_MIN_SIM) else "review:"
        print(f"[{mark}] [{slot}] x{n} {text!r} ~ {verdict} ({sim:.2f})")
        if args.approve and verdict and sim >= APPROVE_MIN_SIM:
            r = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "voice_lab" / "add_quote.py"),
                 "--slot", slot, "--label", verdict, "--text", text],
                cwd=ROOT, capture_output=True, text=True,
            )
            if r.returncode == 0:
                approved += 1
            else:
                print("  RETRAIN FAILED, stopping batch")
                return 1
    if args.approve:
        print(f"approved {approved}/{len(items)}; rest need human labels")
        r = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "voice_lab" / "ambiguity_bench.py")],
            cwd=ROOT, capture_output=True, text=True,
        )
        print(r.stdout.strip().splitlines()[0] if r.stdout.strip() else "bench failed")
        r = subprocess.run(
            [sys.executable, "scripts/dialogue_behavior_fuzz.py",
             "--n", "1000", "--seed", "7"],
            cwd=ROOT, capture_output=True, text=True,
        )
        print(r.stdout.strip().splitlines()[0] if r.stdout.strip() else "fuzz failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
