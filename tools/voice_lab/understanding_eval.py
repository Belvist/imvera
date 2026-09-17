"""Understanding eval — false facts / misses on annotated turns (reviewer loop).

Scores the CURRENT deterministic pipeline against annotated_turns.jsonl:
  false_facts: speaker symptom mentions with no annotated speaker fact
  misses: annotated speaker symptom facts with no extracted mention
  subject_errors: mention present but wrong subject bucket
Used to compare versions (shadow loop gate): a new understanding module
must not raise false_facts or misses on this set.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import re  # noqa: E402

STOP = {"у", "меня", "вчера", "сегодня", "сейчас", "уже", "вот", "ну", "же",
        "то", "это", "как", "утра", "в", "с", "на", "и", "а"}


def _toks(s: str) -> set[str]:
    return {t for t in re.findall(r"[а-яё]+", s.lower()) if t not in STOP}


def _same(a: str, b: str) -> bool:
    if a in b or b in a:
        return True
    ta, tb = _toks(a), _toks(b)
    return len(ta & tb) >= 1 and (len(ta) <= 2 or len(tb) <= 2 or len(ta & tb) >= 2)


def main() -> int:
    from packages.dialogue_engine.turn_understanding import build_rich_turn_from_text

    path = Path(__file__).resolve().parent / "annotated_turns.jsonl"
    false_facts = misses = subj_err = total_sp = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        turn = build_rich_turn_from_text(row["text"], utterance_id=row["id"])
        got = {(m.label.lower(), (getattr(m, "subject", "unknown") or "unknown").lower())
               for m in turn.issue_mentions if m.kind == "symptom"}
        want = {(f["quote"].lower(), f["subject"]) for f in row["facts"]
                if f["kind"] == "symptom" and f["subject"] == "speaker"
                and f.get("mention_expected", True)}
        want_other = {f["quote"].lower() for f in row["facts"]
                      if f["kind"] == "symptom" and f["subject"] == "other_person"}
        total_sp += len(want)
        for quote, _ in want:
            matches = [(g, s) for g, s in got if _same(quote, g)]
            if not matches:
                misses += 1
            elif not any(s == "speaker" for _, s in matches):
                # Mention found, but attributed to the wrong subject bucket.
                subj_err += 1
        for g, s in got:
            if not any(_same(g, w) for w, _ in want):
                # other-person facts must not appear as speaker mentions
                if not any(_same(g, o) for o in want_other):
                    false_facts += 1
    print(f"speaker_facts={total_sp} misses={misses} false_facts={false_facts} "
          f"subject_errors={subj_err}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
