"""Review quarantine — human gate against garbage entering training.

Abstains (anchor miss + classifier unsure) land in
.run/quarantine/slot_abstain.jsonl. Nothing trains on them automatically.
Review grouped candidates, then for each real miss:
  python3 tools/voice_lab/add_quote.py --slot onset --label answer --text "…"
Garbage stays out. Retrain runs bench+fuzz gates before promotion.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

PATH = ROOT / ".run" / "quarantine" / "slot_abstain.jsonl"


def main() -> int:
    if not PATH.exists():
        print("quarantine empty — nothing to review")
        return 0
    groups: dict[tuple[str, str], int] = Counter()
    for line in PATH.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            groups[(row.get("slot", "?"), row.get("text", "?"))] += 1
        except Exception:
            continue
    print(f"{len(groups)} distinct abstains:")
    for (slot, text), n in groups.most_common(50):
        print(f"  [{slot}] x{n}: {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
