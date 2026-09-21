"""Build calibration_dev_v1: ~120 labeled pairs independent of train/eval.

Source: live-trace pool rows NOT used as positives elsewhere. Labels by
strict documented patterns (expert-authored); ambiguous cases are SKIPPED,
never guessed. Used ONLY for threshold/Platt fitting — never for training,
never mixed with eval_v2.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from tools.voice_lab.build_semantic_dataset import GOALS

OUT = ROOT / "datasets" / "semantic_nlu" / "calibration_dev_v1.jsonl"

# (utterance_pattern, goal_id, relevant, value) — strict, high-precision.
RULES: list[tuple[str, str, bool, str | None]] = [
    (r"^(хорошо|нормально|отлично)\.?$", "wellness", True, None),
    (r"^(плохо|ужасно|отвратительно)\.?$", "wellness", True, None),
    (r"^(хорошее|плохое|нормальное)\.?$", "mood", True, None),
    (r"спал[аи]? (хорошо|нормально|плохо)", "sleep", True, None),
    (r"^(дома|гуляю|в поликлинике)\.?$", "plans", True, None),
    (r"выпил(а)? (утром|вечером|после)", "medications_taken", True, "yes"),
    (r"^(да|ага|конечно)\.?$", "medications_taken", False, None),
    (r"^(нет|неа|не надо)\.?$", "medications_taken", False, None),
    (r"^(привет|здравствуй|алло)\.?$", "wellness", False, None),
    (r"^(пока|до свидания)\.?$", "wellness", False, None),
    (r"^(ага|угу)\.?$", "wellness", False, None),
    (r"голова болит", "mood", False, None),
    (r"голова болит", "sleep", False, None),
    (r"живот болит", "mood", False, None),
    (r"не помню", "onset", True, "unknown"),
    (r"вчера", "onset", True, None),
    (r"с утра", "onset", True, None),
]


def main() -> None:
    pool: list[dict] = []
    for line in open(ROOT / "datasets" / "semantic_nlu" / "v2.jsonl", encoding="utf-8"):
        row = json.loads(line)
        if row["source"] == "live_trace" and row["relevant"] is None:
            pool.append(row)
    rows = []
    for row in pool:
        text = row["utterance"].strip().lower()
        for pattern, goal_id, relevant, value in RULES:
            if re.search(pattern, text):
                rows.append(
                    {
                        "question": row["question"] or "",
                        "goal": dict(GOALS[goal_id]),
                        "utterance": row["utterance"],
                        "relevant": relevant,
                        "value": value,
                        "act": None,
                        "subject": "speaker",
                        "polarity": None,
                        "correction": False,
                        "certainty": None,
                        "ood": False,
                        "evidence_span": None,
                        "split_group": "calib_dev",
                        "source": "calibration_rule",
                    }
                )
                break
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    pos = sum(1 for r in rows if r["relevant"])
    print(f"wrote {len(rows)} calibration pairs ({pos} pos / {len(rows) - pos} neg)")


if __name__ == "__main__":
    main()
