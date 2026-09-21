"""Review CLI for semantic dataset v2: label live queue turns.

Usage: python3 tools/voice_lab/review_semantic_data.py [--auto-only] [--limit N]
- --auto-only: apply strict high-precision trivial-act labels, save, exit.
- interactive: show question + utterance + goals, accept labels per turn.

Writes back datasets/semantic_nlu/v2.jsonl in place (keeps order).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / "datasets" / "semantic_nlu" / "v2.jsonl"

TRIVIAL: list[tuple[str, str]] = [
    (r"^(привет|здравствуй(те)?|добрый (день|вечер|утро)|алло|приветик|здорово)[.!]?$", "greeting"),
    (r"^(пока|до свидания|до свиданья|прощайте?|всего доброго|до встречи)[.!]?$", "goodbye"),
    (r"^(ага|угу|мгм|да-да|так|понятно|слушаю)\.?$", "backchannel"),
    (r"^(повтори(те)?|не расслышал(а)?|что-что|говори громче|не слышу)\.?$", "repeat_request"),
]


def auto_label(rows: list[dict]) -> int:
    changed = 0
    for row in rows:
        if row["source"] != "live_trace" or row["act"] is not None:
            continue
        text = row["utterance"].strip().lower()
        if len(text) > 40:
            continue
        for pattern, act in TRIVIAL:
            if re.match(pattern, text):
                row["act"] = act
                row["relevant"] = False
                changed += 1
                break
    return changed


def main() -> None:
    lines = [ln for ln in DATA.read_text(encoding="utf-8").splitlines() if ln.strip()]
    rows = [json.loads(ln) for ln in lines]
    if "--auto-only" in sys.argv:
        changed = auto_label(rows)
        DATA.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
            encoding="utf-8",
        )
        review = sum(1 for r in rows if r["relevant"] is None and r["act"] is None)
        print(f"auto-labeled {changed}; remaining unlabeled: {review}")
        return
    limit = None
    for arg in sys.argv[1:]:
        if arg.startswith("--limit="):
            limit = int(arg.split("=", 1)[1])
    pending = [r for r in rows if r["relevant"] is None and r["act"] is None]
    print(f"pending: {len(pending)}")
    done = 0
    for row in pending:
        if limit is not None and done >= limit:
            break
        print("=" * 60)
        print("Q:", (row["question"] or "")[:160])
        print("U:", row["utterance"][:200])
        print("commands: goal=<goal_id> value=<v> | act=<act> | neg | skip | quit")
        try:
            cmd = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nstopped")
            break
        if cmd == "quit":
            break
        if cmd == "skip" or not cmd:
            continue
        if cmd == "neg":
            row["relevant"] = False
            done += 1
            continue
        for part in cmd.split():
            if part.startswith("goal="):
                from tools.voice_lab.build_semantic_dataset import GOALS

                gid = part.split("=", 1)[1]
                if gid in GOALS:
                    row["goal"] = dict(GOALS[gid])
                    row["relevant"] = True
            elif part.startswith("value="):
                row["value"] = part.split("=", 1)[1]
            elif part.startswith("act="):
                row["act"] = part.split("=", 1)[1]
        done += 1
    DATA.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    print(f"labeled {done}, saved")


if __name__ == "__main__":
    main()
