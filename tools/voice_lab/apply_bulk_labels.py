"""Bulk expert labels for frequent live (question, utterance) pairs.

Each rule below is a human labeling decision (engineer-reviewed 2026-09-21),
not a model output. Format: (question_sub, utterance_exact_or_sub, goal_id,
value, act). Run: python3 tools/voice_lab/apply_bulk_labels.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from tools.voice_lab.build_semantic_dataset import GOALS

DATA = ROOT / "datasets" / "semantic_nlu" / "v2.jsonl"

# (question_substring, utterance_match, goal_id|None, value|None, act|None)
# utterance_match: exact= prefix means full normalized match.
RULES: list[tuple[str, str, str | None, str | None, str | None]] = [
    ("как вы себя чувствуете", "exact:хорошо.", "wellness", None, "answer"),
    ("как вы себя чувствуете", "exact:плохо.", "wellness", None, "answer"),
    ("как вы себя чувствуете", "exact:ужасно.", "wellness", None, "answer"),
    ("как вы себя чувствуете", "exact:нормально.", "wellness", None, "answer"),
    ("как вы себя чувствуете", "чувствую себя хорошо", "wellness", None, "answer"),
    ("как вы себя чувствуете", "чувствую себя плохо", "wellness", None, "answer"),
    ("как вы себя чувствуете", "отвратительно", "wellness", None, "answer"),
    ("как вы себя чувствуете", "привет. не знаю.", "wellness", "unknown", "answer"),
    ("как настроение", "exact:плохое.", "mood", None, "answer"),
    ("как настроение", "exact:хорошая.", "mood", None, "answer"),
    ("как настроение", "настроение", "mood", None, "answer"),
    ("как вы спали", "exact:плохо.", "sleep", None, "answer"),
    ("как вы спали", "нормально пойдёт", "sleep", None, "answer"),
    ("как вы спали", "спал", "sleep", None, "answer"),
    ("покушать сегодня", "exact:успели.", None, None, "confirm"),
    ("поесть", "exact:кушал.", None, None, "answer"),
    ("лекарства", "exact:каждый день.", "medications_taken", "yes", "answer"),
    ("лекарства", "выпил", "medications_taken", "yes", "answer"),
    ("лекарства", "не пил", "medications_taken", "no", "answer"),
    ("планы на сегодня", "планов нет", "plans", None, "answer"),
    ("планы на сегодня", "дома", "plans", None, "answer"),
    ("что-то важное", "живот болит", None, None, "complaint"),
    ("что-то важное", "ничего", None, None, "decline"),
    ("ещё что-то", "да, сижу дома", None, None, "answer"),
    ("хотите ещё что-то", "exact:да.", None, None, "confirm"),
    ("спасибо, даниил. на се", "exact:да.", None, None, "confirm"),
    ("не получается разобрать", "exact:да.", None, None, "backchannel"),
    ("", "exact:да", None, None, "backchannel"),
    ("", "exact:да.", None, None, "backchannel"),
    ("", "exact:нет.", None, None, "decline"),
    ("", "exact:нет, нет.", None, None, "decline"),
    ("", "exact:привет.", None, None, "greeting"),
    ("", "exact:алло.", None, None, "greeting"),
    ("", "exact:ага.", None, None, "backchannel"),
    ("", "exact:угу.", None, None, "backchannel"),
    ("", "exact:до свидания.", None, None, "goodbye"),
    ("", "exact:пока.", None, None, "goodbye"),
    ("колено болит", "колено", None, None, "complaint"),
    ("головная", "головная боль сейчас прошла, но болит колено", None, None, "correction"),
    ("началась головная", "не помню", "onset", "unknown", "not_recalled"),
    ("когда", "не знаю", "onset", "unknown", "not_recalled"),
    ("когда", "вчера", "onset", "yesterday", "answer"),
    ("когда", "с утра", "onset", "morning", "answer"),
    ("что случилось", "упал", None, None, "complaint"),
    ("что случилось", "температура", None, None, "complaint"),
    ("передать родственникам", "передать", None, None, "answer"),
    ("просто: хорошо, нормально или", "наверное, среднее", "wellness", None, "uncertain"),
    ("просто: хорошо, нормально или", "пойдёт", "wellness", None, "uncertain"),
    ("не расслышала", "не знаю, не могу сказать", "wellness", "unknown", "not_recalled"),
]


def main() -> None:
    lines = [ln for ln in DATA.read_text(encoding="utf-8").splitlines() if ln.strip()]
    rows = [json.loads(ln) for ln in lines]
    changed = 0
    for row in rows:
        if row["source"] != "live_trace" or (
            row["relevant"] is not None and row["act"] is not None
        ):
            continue
        q = (row["question"] or "").lower()
        u = row["utterance"].strip().lower()
        for q_sub, u_match, goal_id, value, act in RULES:
            if q_sub and q_sub not in q:
                continue
            if u_match.startswith("exact:"):
                if u != u_match[len("exact:"):]:
                    continue
            elif u_match not in u:
                continue
            if goal_id:
                row["goal"] = dict(GOALS[goal_id])
                row["relevant"] = True
            elif act in ("greeting", "goodbye", "backchannel", "decline", "confirm"):
                row["relevant"] = False
            if value is not None:
                row["value"] = value
            if act is not None:
                row["act"] = act
            changed += 1
            break
    DATA.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    remaining = sum(1 for r in rows if r["relevant"] is None and r["act"] is None)
    print(f"bulk-labeled rows touched; remaining unlabeled: {remaining}")


if __name__ == "__main__":
    main()
