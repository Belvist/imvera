"""Paraphrase loop — the anti-patch process (use instead of regex edits).

When a live quote misses the anchors:
  1. python3 tools/voice_lab/add_quote.py --slot onset --label answer --text "…"
  2. it appends to LIVE_QUOTES, retrains slot_answer_clf, runs bench+fuzz
  3. green → done. No regex touched.

Rules:
  - closed classes (weekdays, pain verbs, scale synonyms) may extend lists
  - open paraphrases go ONLY here, never into regex
  - bench + fuzz must stay green after retrain, or quote is re-labeled
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

TRAINER = ROOT / "tools" / "voice_lab" / "train_slot_answer_clf.py"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", required=True, choices=["onset", "duration", "severity", "current"])
    ap.add_argument("--label", required=True, choices=["answer", "skip", "garbage"])
    ap.add_argument("--text", required=True)
    args = ap.parse_args()

    src = TRAINER.read_text(encoding="utf-8")
    row = f'    ("{args.slot}", "{args.text.strip().lower()}", "{args.label}"),\n'
    marker = "    # --- LIVE_QUOTES: append every anchor-miss with its true label ---"
    assert marker in src, "trainer marker moved"
    src = src.replace(marker, marker + "\n" + row.rstrip("\n"), 1)
    TRAINER.write_text(src, encoding="utf-8")
    print(f"appended: {row.strip()}")

    import subprocess

    r1 = subprocess.run(
        [sys.executable, str(ROOT / "tools/voice_lab/train_slot_answer_clf.py")],
        cwd=ROOT, capture_output=True, text=True,
    )
    print(r1.stdout.strip() or r1.stderr.strip()[-500:])
    if r1.returncode != 0:
        return 1
    r2 = subprocess.run(
        [sys.executable, str(ROOT / "tools/voice_lab/ambiguity_bench.py")],
        cwd=ROOT, capture_output=True, text=True,
    )
    print(r2.stdout.strip().splitlines()[0] if r2.stdout.strip() else r2.stderr.strip()[-500:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
