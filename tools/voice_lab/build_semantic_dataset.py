"""Mine semantic-NLU dataset v1: live traces + act seeds + hard negatives.

Row schema (reviewer spec, adapted):
  question, goal {goal_id, description, answer_type}, utterance,
  relevant bool|null, value, act, subject, correction, certainty,
  evidence_span [start,end] char offsets into utterance or null,
  source (live_trace | act_seed | hard_negative | rule_corpus).

Output: datasets/semantic_nlu/v1.jsonl (gitignored, regenerable).
Human review queue: rows with relevant=null.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "datasets" / "semantic_nlu" / "v1.jsonl"

DAILY_GOALS: dict[str, dict[str, str]] = {
    "wellness": {
        "goal_id": "wellness",
        "description": "How the person feels overall right now",
        "answer_type": "enum",
    },
    "mood": {
        "goal_id": "mood",
        "description": "Current mood of the person",
        "answer_type": "enum",
    },
    "sleep": {
        "goal_id": "sleep",
        "description": "How the person slept",
        "answer_type": "enum",
    },
    "plans": {
        "goal_id": "plans",
        "description": "Plans for today / whereabouts",
        "answer_type": "enum",
    },
    "onset": {
        "goal_id": "onset",
        "description": "When a symptom started",
        "answer_type": "free_text",
    },
}

# (question_substring | "" , text_substring, goal_id autonomously assigned)
SEED_GOAL_MAP: list[tuple[str, str, str, str | None]] = [
    # (question_hint, text_hint, goal_id, value)
    ("Когда начал", "вчера", "onset", "yesterday"),
    ("Когда начал", "с утра", "onset", "morning"),
    ("Когда начал", "не помню", "onset", "unknown"),
    ("Когда начал", "не знаю", "onset", "unknown"),
    ("Давление", "сто сорок", "wellness", None),
    ("Таблетки", "выпил", "wellness", None),
    ("Таблетки", "забыл", "wellness", None),
    ("Спите", "спал", "sleep", None),
    ("Спите", "не спал", "sleep", None),
    ("Настроение", "настроение", "mood", None),
    ("Дома?", "дома", "plans", None),
    ("Дома?", "гуляю", "plans", None),
]


def _evidence_span(utterance: str, hint: str) -> list[int] | None:
    low = utterance.lower()
    key = hint.lower().split()[0]
    start = low.find(key)
    if start < 0:
        return None
    return [start, start + len(hint)]


def mine_live_traces() -> list[dict]:
    """(vera prior, user text) pairs awaiting human review."""
    import glob

    rows = []
    for path in glob.glob(str(ROOT / ".run" / "traces" / "fs-*.jsonl")):
        last_vera = ""
        try:
            for line in open(path, encoding="utf-8"):
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload = row.get("payload", {})
                if not isinstance(payload, dict):
                    continue
                if row.get("type") == "renderer.phrase_ready" and payload.get("text"):
                    last_vera = payload["text"]
                elif row.get("type") == "stt.final" and payload.get("text"):
                    rows.append(
                        {
                            "question": last_vera,
                            "goal": None,
                            "utterance": payload["text"],
                            "relevant": None,
                            "value": None,
                            "act": None,
                            "subject": "speaker",
                            "correction": False,
                            "certainty": None,
                            "evidence_span": None,
                            "source": "live_trace",
                        }
                    )
        except OSError:
            continue
    return rows


def mine_act_seeds() -> list[dict]:
    """Map act-seed rows to goal bindings where determinable."""
    seed_path = ROOT / "packages" / "dialogue_engine" / "semantic_nlp" / "seed.jsonl"
    rows = []
    for line in seed_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        seed = json.loads(line)
        question, text, act = seed["question"], seed["text"], seed["act"]
        goal = None
        value = None
        relevant: bool | None = None
        for q_hint, t_hint, goal_id, val in SEED_GOAL_MAP:
            if q_hint.lower() in question.lower() and t_hint in text.lower():
                goal = dict(DAILY_GOALS[goal_id])
                value = val
                relevant = True
                break
        if act in ("greeting", "goodbye", "backchannel", "stop", "repeat_request"):
            relevant = False if goal is None else relevant
        rows.append(
            {
                "question": question,
                "goal": goal,
                "utterance": text,
                "relevant": relevant,
                "value": value,
                "act": act,
                "subject": "speaker",
                "correction": act == "correction",
                "certainty": None,
                "evidence_span": _evidence_span(text, text),
                "source": "act_seed",
            }
        )
    return rows


def mine_hard_negatives(utterances: list[str]) -> list[dict]:
    """Cross unrelated goals x utterances: model must learn to abstain."""
    goals = [
        {
            "goal_id": "medications_taken",
            "description": "Whether the person took their medicine",
            "answer_type": "bool",
        },
        {
            "goal_id": "utilities_paid",
            "description": "Whether utility bills are paid",
            "answer_type": "bool",
        },
        {
            "goal_id": "daughter_visit",
            "description": "Whether the daughter will visit",
            "answer_type": "bool",
        },
    ]
    unrelated = [
        "Голова сильно болит со вчера.",
        "Спал нормально.",
        "До свидания.",
        "Ага.",
        "Не помню.",
    ]
    rows = []
    for goal in goals:
        for text in unrelated:
            rows.append(
                {
                    "question": "",
                    "goal": goal,
                    "utterance": text,
                    "relevant": False,
                    "value": None,
                    "act": None,
                    "subject": "speaker",
                    "correction": False,
                    "certainty": None,
                    "evidence_span": None,
                    "source": "hard_negative",
                }
            )
    return rows


def main() -> None:
    seeds = mine_act_seeds()
    live = mine_live_traces()
    negatives = mine_hard_negatives([r["utterance"] for r in seeds])
    all_rows = seeds + live + negatives
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in all_rows) + "\n",
        encoding="utf-8",
    )
    review = sum(1 for r in all_rows if r["relevant"] is None)
    print(
        f"wrote {len(all_rows)} rows ({len(seeds)} seeds, {len(live)} live, "
        f"{len(negatives)} negatives); review queue: {review}"
    )


if __name__ == "__main__":
    main()
