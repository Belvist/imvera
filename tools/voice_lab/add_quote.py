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
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

TRAINER = ROOT / "tools" / "voice_lab" / "train_slot_answer_clf.py"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--slot",
        required=True,
        choices=["onset", "duration", "severity", "current", "wellness"],
    )
    ap.add_argument("--label", required=True, choices=["answer", "skip", "garbage"])
    ap.add_argument("--text", required=True)
    args = ap.parse_args()
    text = args.text.strip().lower()
    if not text:
        ap.error("--text must not be blank")

    src = TRAINER.read_text(encoding="utf-8")
    row = f"    {(args.slot, text, args.label)!r},\n"
    marker = "    # --- LIVE_QUOTES: append every anchor-miss with its true label ---"
    assert marker in src, "trainer marker moved"
    src = src.replace(marker, marker + "\n" + row.rstrip("\n"), 1)
    TRAINER.write_text(src, encoding="utf-8")
    print(f"appended: {row.strip()}")

    stages = [
        ("trainer", [sys.executable, str(TRAINER)], os.environ.copy()),
        (
            "bench (coverage=1)",
            [sys.executable, str(ROOT / "tools/voice_lab/ambiguity_bench.py")],
            {**os.environ, "IMVERA_COVERAGE_LADDER": "1"},
        ),
    ]
    for coverage in ("0", "1"):
        stages.append((
            f"fuzz (coverage={coverage})",
            [sys.executable, str(ROOT / "scripts/dialogue_behavior_fuzz.py"),
             "--n", "1000", "--seed", "7"],
            {**os.environ, "IMVERA_COVERAGE_LADDER": coverage},
        ))
    for name, command, env in stages:
        result = subprocess.run(
            command, cwd=ROOT, env=env, capture_output=True, text=True,
        )
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        if result.returncode != 0:
            print(f"{name} failed (exit {result.returncode})", file=sys.stderr)
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
