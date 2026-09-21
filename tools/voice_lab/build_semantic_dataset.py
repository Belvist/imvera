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


def mine_curated_pairs() -> list[dict]:
    """Expert-labeled explicit pairs (XEnc V3): positives, same-topic and
    same-question negatives, multi-goal utterances labeled per goal.
    Every row reviewed by the engineer 2026-09-21 — no autogeneration."""
    goal = GOALS
    # (question, goal_id, utterance, relevant, value)
    pairs: list[tuple[str, str, str, bool, str | None]] = [
        # --- onset positives, varied Q ---
        ("Когда это началось?", "onset", "Вчера началось.", True, "yesterday"),
        ("Когда заболела голова?", "onset", "С утра.", True, "morning"),
        ("Давно болит?", "onset", "Уже третий день.", True, None),
        ("Когда началось?", "onset", "Пару часов назад.", True, None),
        ("Когда началось?", "onset", "Не помню.", True, "unknown"),
        ("Когда началось?", "onset", "Не знаю.", True, "unknown"),
        # --- onset same-question negatives ---
        ("Когда началось?", "wellness", "Хорошо.", False, None),
        ("Когда началось?", "sleep", "Спал нормально.", False, None),
        # --- wellness positives ---
        ("Как вы себя чувствуете?", "wellness", "Хорошо.", True, None),
        ("Как вы себя чувствуете?", "wellness", "Плохо.", True, None),
        ("Как вы себя чувствуете?", "wellness", "Так себе.", True, None),
        ("Как вы себя чувствуете?", "wellness", "Отвратительно.", True, None),
        # --- wellness same-question negatives ---
        ("Как вы себя чувствуете?", "wellness", "Дочь вечером приедет.", False, None),
        ("Как вы себя чувствуете?", "wellness", "Таблетки выпила.", False, None),
        # --- mood/sleep/plans positives ---
        ("Как настроение?", "mood", "Хорошее.", True, None),
        ("Как настроение?", "mood", "Плохое.", True, None),
        ("Как спали?", "sleep", "Плохо спал.", True, None),
        ("Как спали?", "sleep", "Всю ночь не спал.", True, None),
        ("Какие планы?", "plans", "Дома буду.", True, None),
        ("Какие планы?", "plans", "Гулять пойду.", True, None),
        # --- cross-slot negatives (similar goals) ---
        ("Как настроение?", "mood", "Голова болит.", False, None),
        ("Как спали?", "sleep", "Хорошо.", False, None),
        ("Какие планы?", "plans", "Спал нормально.", False, None),
        ("Как вы себя чувствуете?", "mood", "Плохо.", False, None),
        ("Как вы себя чувствуете?", "sleep", "Плохо.", False, None),
        # --- medications positives/negatives ---
        ("Таблетки приняли?", "medications_taken", "Да, утром выпил.", True, "yes"),
        ("Таблетки приняли?", "medications_taken", "Нет, забыл.", True, "no"),
        ("Таблетки приняли?", "medications_taken", "Какие таблетки?", False, None),
        # --- blood pressure ---
        ("Давление какое?", "blood_pressure", "Сто сорок на девяносто.", True, None),
        ("Давление какое?", "blood_pressure", "Не мерил.", True, "unknown"),
        ("Давление какое?", "blood_pressure", "Голова болит.", False, None),
    ]
    # --- multi-goal utterance, labeled per goal ---
    multi = "В целом нормально, таблетки утром выпила, а дочь вечером приедет."
    bad_night = "Плохо, голова болит, не спал."
    pairs.extend(
        [
            ("Как вы себя чувствуете?", "wellness", multi, True, None),
            ("Как вы себя чувствуете?", "medications_taken", multi, True, "yes"),
            ("Как вы себя чувствуете?", "daughter_visit", multi, True, "yes"),
            ("Как вы себя чувствуете?", "sleep", multi, False, None),
            ("Как вы себя чувствуете?", "wellness", bad_night, True, None),
            ("Как вы себя чувствуете?", "mood", bad_night, False, None),
            ("Как вы себя чувствуете?", "sleep", bad_night, False, None),
        ]
    )
    rows = []
    for question, goal_id, text, relevant, value in pairs:
        row = _base(question, text, "curated", "curated_pair")
        row["goal"] = dict(goal[goal_id])
        row["relevant"] = relevant
        row["value"] = value
        rows.append(row)
    return rows


def mine_curated_batch2() -> list[dict]:
    """Expert batch 2 (2026-09-21): multi-goal, cross-slot negatives,
    values, other-person. Every row hand-labeled."""
    goal = GOALS
    pairs: list[tuple[str, str, str, bool, str | None]] = [
        # --- multi-goal: one utterance, all goals labeled ---
        ("Что беспокоит?", "wellness", "Голова болит и тошнит.", True, None),
        ("Что беспокоит?", "mood", "Голова болит и тошнит.", False, None),
        ("Что беспокоит?", "sleep", "Голова болит и тошнит.", False, None),
        ("Как дела?", "wellness", "Нормально, выспался, настроение хорошее.", True, None),
        ("Как дела?", "sleep", "Нормально, выспался, настроение хорошее.", True, None),
        ("Как дела?", "mood", "Нормально, выспался, настроение хорошее.", True, None),
        ("Как дела?", "plans", "Нормально, выспался, настроение хорошее.", False, None),
        ("Расскажи как ты?", "wellness", "Плохо спал, голова болит, настроения нет.", True, None),
        ("Расскажи как ты?", "sleep", "Плохо спал, голова болит, настроения нет.", True, None),
        ("Расскажи как ты?", "mood", "Плохо спал, голова болит, настроения нет.", True, None),
        # --- other-person: never speaker goals ---
        ("Как вы себя чувствуете?", "wellness", "Муж плохо себя чувствует.", False, None),
        ("Как вы себя чувствуете?", "wellness", "У соседки давление скачет.", False, None),
        ("Таблетки приняли?", "medications_taken", "Муж свои выпил.", False, None),
        ("Таблетки приняли?", "medications_taken", "Дочке дала витамины.", False, None),
        ("Дочь сегодня будет?", "daughter_visit", "Сын вчера был.", False, None),
        # --- values yes/no/unknown mass ---
        ("Таблетки приняли?", "medications_taken", "Да.", True, "yes"),
        ("Таблетки приняли?", "medications_taken", "Нет.", True, "no"),
        ("Таблетки приняли?", "medications_taken", "Не помню.", True, "unknown"),
        ("Дочь сегодня будет?", "daughter_visit", "Да, приедет.", True, "yes"),
        ("Дочь сегодня будет?", "daughter_visit", "Нет, не приедет.", True, "no"),
        ("Дочь сегодня будет?", "daughter_visit", "Не знаю.", True, "unknown"),
        ("Коммунальные услуги оплачены?", "utilities_paid", "Да, всё оплатила.", True, "yes"),
        ("Коммунальные услуги оплачены?", "utilities_paid", "Нет, не успела.", True, "no"),
        ("Коммунальные услуги оплачены?", "utilities_paid", "Не знаю.", True, "unknown"),
        # --- onset values ---
        ("Когда началось?", "onset", "Три дня назад.", True, None),
        ("Когда началось?", "onset", "На прошлой неделе.", True, None),
        ("Когда началось?", "onset", "Сегодня утром.", True, None),
        ("Когда началось?", "onset", "Не могу сказать.", True, "unknown"),
        # --- same-question negatives ---
        ("Таблетки приняли?", "medications_taken", "Давление померила.", False, None),
        ("Дочь сегодня будет?", "daughter_visit", "Хорошо себя чувствую.", False, None),
        ("Коммунальные услуги оплачены?", "utilities_paid", "Дочь поможет.", False, None),
        ("Когда началось?", "onset", "Голова болит.", False, None),
        ("Когда началось?", "onset", "Таблетки выпила.", False, None),
        # --- wellness positives variety ---
        ("Как вы себя чувствуете?", "wellness", "Слабость.", True, None),
        ("Как вы себя чувствуете?", "wellness", "Тошнит.", True, None),
        ("Как вы себя чувствуете?", "wellness", "Кружится голова.", True, None),
        ("Как вы себя чувствуете?", "wellness", "Давление высокое.", True, None),
        # --- corrections with goals ---
        ("Как самочувствие?", "wellness", "Хорошо… нет, плохо.", True, None),
        ("Что болит?", "wellness", "Голова… то есть живот.", True, None),
        # --- uncertainty with goals ---
        ("Когда началось?", "onset", "Вроде вчера.", True, None),
        ("Когда началось?", "onset", "Может, с утра.", True, None),
        ("Как вы себя чувствуете?", "wellness", "Вроде нормально.", True, None),
        # --- blood pressure positives ---
        ("Давление какое?", "blood_pressure", "Сто шестьдесят на сто.", True, None),
        ("Давление какое?", "blood_pressure", "Низкое сегодня.", True, None),
        ("Давление какое?", "blood_pressure", "Нормальное.", True, None),
    ]
    rows = []
    for question, goal_id, text, relevant, value in pairs:
        row = _base(question, text, "curated2", "curated_pair")
        row["goal"] = dict(goal[goal_id])
        row["relevant"] = relevant
        row["value"] = value
        rows.append(row)
    return rows


def mine_hard_negatives() -> list[dict]:
    """True hard negatives AND counterfactuals killing Q/G shortcuts.

    Counterfactual design: same question or same keywords, different
    relation — the model cannot win from Q or topic alone. Includes
    positive examples for unseen-goal candidates (daughter_visit,
    utilities_paid) so the unseen split tests meaning, not emptiness.
    """
    goal_defs = {
        "medications_taken": ("Принял ли человек лекарства", "bool"),
        "daughter_visit": ("Придёт ли дочь сегодня", "bool"),
        "utilities_paid": ("Оплачены ли коммунальные услуги", "bool"),
        "blood_pressure": ("Какое давление у человека", "free_text"),
        "onset": ("Когда начался симптом", "free_text"),
        "wellness": (
            "Как человек себя чувствует в целом прямо сейчас",
            "free_text",
        ),
    }
    # (question, goal_id, utterance, relevant, value|None)
    pairs: list[tuple[str, str, str, bool, str | None]] = [
        # --- counterfactuals: same Q, different relation ---
        ("Как вы себя чувствуете?", "wellness", "Дочь вечером обещала приехать.", False, None),
        ("Как вы себя чувствуете?", "wellness", "Таблетки утром выпила.", False, None),
        ("Как вы себя чувствуете?", "wellness", "Квитанции лежат на тумбочке.", False, None),
        ("Лекарства сегодня приняли?", "medications_taken", "Таблетки лежат.", False, None),
        ("Лекарства сегодня приняли?", "medications_taken", "Да, выпила.", True, "yes"),
        ("Лекарства сегодня приняли?", "medications_taken", "Нет, забыла.", True, "no"),
        # --- same words, different relation ---
        ("", "daughter_visit", "Дочь звонила.", False, None),
        ("", "daughter_visit", "Обещала быть после работы.", True, "yes"),
        ("", "medications_taken", "Таблетки купил.", False, None),
        ("", "medications_taken", "Таблетки выпил.", True, "yes"),
        ("", "utilities_paid", "Квитанции забрала дочь.", False, None),
        ("", "utilities_paid", "Квитанции так и лежат, руки не дошли.", True, "no"),
        # --- unseen-goal positives (held out from train) ---
        ("", "daughter_visit", "Дочка сказала, что заедет вечером.", True, "yes"),
        ("", "daughter_visit", "Жду дочь, должна приехать.", True, "yes"),
        ("", "daughter_visit", "Дочь не приедет, занята.", True, "no"),
        ("", "utilities_paid", "За свет заплатила вчера.", True, "yes"),
        ("", "utilities_paid", "Всё оплачено.", True, "yes"),
        ("", "utilities_paid", "Пока не платила.", True, "no"),
        # --- classic hard negatives ---
        ("", "medications_taken", "Таблетки купила вчера.", False, None),
        ("", "medications_taken", "Дочь привезёт лекарства вечером.", False, None),
        ("", "daughter_visit", "Дочь утром звонила.", False, None),
        ("", "utilities_paid", "Платёжки на тумбочке лежат.", False, None),
        ("", "blood_pressure", "Давление не мерила.", False, None),
        ("", "onset", "Болит уже давно.", False, None),
    ]
    rows = []
    for question, goal_id, text, relevant, value in pairs:
        desc, answer_type = goal_defs[goal_id]
        row = _base(question, text, "hardneg", "hard_negative")
        row["goal"] = {
            "goal_id": goal_id,
            "description": desc,
            "answer_type": answer_type,
            "allowed_values": ["yes", "no", "unknown"]
            if answer_type == "bool"
            else [],
        }
        row["relevant"] = relevant
        row["value"] = value
        rows.append(row)
    return rows


def main() -> None:
    seeds = mine_act_seeds()
    live = mine_live_traces()
    negatives = mine_hard_negatives()
    curated = mine_curated_pairs()
    curated2 = mine_curated_batch2()
    all_rows = seeds + live + negatives + curated + curated2
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in all_rows) + "\n",
        encoding="utf-8",
    )
    review = sum(1 for r in all_rows if r["relevant"] is None)
    print(
        f"wrote {len(all_rows)} rows ({len(seeds)} seeds, {len(live)} live, "
        f"{len(negatives)} negatives, {len(curated) + len(curated2)} curated); "
        f"review queue: {review}"
    )


if __name__ == "__main__":
    main()
