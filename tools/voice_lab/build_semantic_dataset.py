"""Mine semantic-NLU dataset v2: fixed contract (reviewer order).

Row schema:
  question, goal {goal_id, description_ru, answer_type, allowed_values},
  utterance, relevant bool|null, value, act, subject, polarity,
  correction bool, certainty, ood bool, evidence_span [start,end]|null,
  split_group (call_id or 'seed'), source.

Rules: Russian goal descriptions (encoder is Russian); production
answer_type/allowed_values (daily goals are free_text, NOT enum);
act-only seeds never pretend to be goal examples (goal=null unless
explicitly bound); missing labels stay null and must mask loss.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "datasets" / "semantic_nlu" / "v2.jsonl"

GOALS: dict[str, dict] = {
    "wellness": {
        "goal_id": "wellness",
        "description": "Как человек себя чувствует в целом прямо сейчас",
        "answer_type": "free_text",
        "allowed_values": [],
    },
    "mood": {
        "goal_id": "mood",
        "description": "Какое настроение у человека",
        "answer_type": "free_text",
        "allowed_values": [],
    },
    "sleep": {
        "goal_id": "sleep",
        "description": "Как человек спал",
        "answer_type": "free_text",
        "allowed_values": [],
    },
    "plans": {
        "goal_id": "plans",
        "description": "Какие планы на день, где находится",
        "answer_type": "free_text",
        "allowed_values": [],
    },
    "onset": {
        "goal_id": "onset",
        "description": "Когда начался симптом",
        "answer_type": "free_text",
        "allowed_values": [],
    },
    "medications_taken": {
        "goal_id": "medications_taken",
        "description": "Принял ли человек лекарства",
        "answer_type": "bool",
        "allowed_values": ["yes", "no", "unknown"],
    },
    "blood_pressure": {
        "goal_id": "blood_pressure",
        "description": "Какое давление у человека",
        "answer_type": "free_text",
        "allowed_values": [],
    },
    "daughter_visit": {
        "goal_id": "daughter_visit",
        "description": "Придёт ли дочь сегодня",
        "answer_type": "bool",
        "allowed_values": ["yes", "no", "unknown"],
    },
    "utilities_paid": {
        "goal_id": "utilities_paid",
        "description": "Оплачены ли коммунальные услуги",
        "answer_type": "bool",
        "allowed_values": ["yes", "no", "unknown"],
    },
}

# (question_hint, text_hint, goal_id, value or None)
SEED_GOAL_MAP: list[tuple[str, str, str, str | None]] = [
    ("Когда начал", "вчера", "onset", "yesterday"),
    ("Когда начал", "с утра", "onset", "morning"),
    ("Когда начал", "не помню", "onset", "unknown"),
    ("Когда начал", "не знаю", "onset", "unknown"),
    ("Давление", "сто сорок", "blood_pressure", None),
    ("Давление", "сто двадцать", "blood_pressure", None),
    ("Таблетки", "выпил", "medications_taken", "yes"),
    ("Таблетки", "забыл", "medications_taken", "no"),
    ("Таблетки", "не буду", "medications_taken", "no"),
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


def _base(question: str, utterance: str, split_group: str, source: str) -> dict:
    return {
        "question": question,
        "goal": None,
        "utterance": utterance,
        "relevant": None,
        "value": None,
        "act": None,
        "subject": "speaker",
        "polarity": None,
        "correction": False,
        "certainty": None,
        "ood": False,
        "evidence_span": None,
        "split_group": split_group,
        "source": source,
    }


def mine_act_seeds() -> list[dict]:
    seed_path = ROOT / "packages" / "dialogue_engine" / "semantic_nlp" / "seed.jsonl"
    rows = []
    for line in seed_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        seed = json.loads(line)
        question, text, act = seed["question"], seed["text"], seed["act"]
        row = _base(question, text, "seed", "act_seed")
        row["act"] = act
        row["correction"] = act == "correction"
        for q_hint, t_hint, goal_id, val in SEED_GOAL_MAP:
            if q_hint.lower() in question.lower() and t_hint in text.lower():
                row["goal"] = dict(GOALS[goal_id])
                row["value"] = val
                row["relevant"] = True
                row["evidence_span"] = _evidence_span(text, text)
                break
        rows.append(row)
    return rows


def mine_live_traces() -> list[dict]:
    import glob

    rows = []
    for path in glob.glob(str(ROOT / ".run" / "traces" / "fs-*.jsonl")):
        call_id = Path(path).stem
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
                    entry = _base(last_vera, payload["text"], call_id, "live_trace")
                    rows.append(entry)
        except OSError:
            continue
    return rows


def mine_hard_negatives() -> list[dict]:
    """True hard negatives: topically close but NOT answering the goal."""
    pairs = [
        ("medications_taken", "Таблетки купила вчера.", "bool"),
        ("medications_taken", "Дочь привезёт лекарства вечером.", "bool"),
        ("daughter_visit", "Дочь утром звонила.", "bool"),
        ("daughter_visit", "С дочкой всё хорошо.", "bool"),
        ("utilities_paid", "Квитанции достала, вечером разберусь.", "bool"),
        ("utilities_paid", "Платёжки на тумбочке лежат.", "bool"),
        ("blood_pressure", "Давление не мерила.", "free_text"),
        ("onset", "Болит уже давно.", "free_text"),
    ]
    goal_defs = {
        "medications_taken": "Принял ли человек лекарства",
        "daughter_visit": "Придёт ли дочь сегодня",
        "utilities_paid": "Оплачены ли коммунальные услуги",
        "blood_pressure": "Какое давление у человека",
        "onset": "Когда начался симптом",
    }
    rows = []
    for goal_id, text, answer_type in pairs:
        row = _base("", text, "hardneg", "hard_negative")
        row["goal"] = {
            "goal_id": goal_id,
            "description": goal_defs[goal_id],
            "answer_type": answer_type,
            "allowed_values": ["yes", "no", "unknown"]
            if answer_type == "bool"
            else [],
        }
        row["relevant"] = False
        rows.append(row)
    return rows


def main() -> None:
    seeds = mine_act_seeds()
    live = mine_live_traces()
    negatives = mine_hard_negatives()
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
