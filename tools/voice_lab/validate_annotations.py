"""Validate annotated turns (reviewer item 4): schema + span integrity."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from tools.voice_lab.annotation_schema import (  # noqa: E402
    KINDS,
    LINKS,
    POLARITIES,
    SUBJECTS,
    TIMES,
)


def main() -> int:
    path = Path(__file__).resolve().parent / "annotated_turns.jsonl"
    bad = 0
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        n += 1
        for f in row["facts"]:
            s, e = f["span"]
            if row["text"][s:e].lower() != f["quote"].lower():
                print(f"SPAN {row['id']}: {f['quote']!r}")
                bad += 1
            for key, allowed in (("kind", KINDS), ("subject", SUBJECTS),
                                 ("polarity", POLARITIES), ("time", TIMES)):
                if f[key] not in allowed:
                    print(f"ENUM {row['id']}: {key}={f[key]!r}")
                    bad += 1
            link = f.get("link")
            if link is not None and link.get("type") not in [x for x in LINKS if x]:
                print(f"LINK {row['id']}")
                bad += 1
    print(f"rows={n} errors={bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
