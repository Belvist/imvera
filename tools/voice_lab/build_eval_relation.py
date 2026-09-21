"""XEnc V4 eval set builder: permanent, untouched-by-training relation pairs.

Covers: unseen paraphrases, same-topic negatives, same-question negatives,
multi-goal turns, other-person turns, corrections, uncertainty, short
answers, ASR-like phrases, unseen goals. NEVER include these rows in any
training split (enforced by split_group prefix + overlap check).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from tools.voice_lab.build_semantic_dataset import GOALS

OUT = ROOT / "datasets" / "semantic_nlu" / "eval_relation_v1.jsonl"

# (question, goal_id, utterance, relevant, value)
PAIRS: list[tuple[str, str, str, bool, str | None]] = [
    # --- medications_taken ---
    ("Таблетки приняли?", "medications_taken", "Утром не забыла, всё приняла.", True, "yes"),
    ("Таблетки приняли?", "medications_taken", "Сегодня уже пила.", True, "yes"),
    ("Таблетки приняли?", "medications_taken", "Выпила после обеда.", True, "yes"),
    ("Таблетки приняли?", "medications_taken", "Ой, пропустила сегодня.", True, "no"),
    ("Таблетки приняли?", "medications_taken", "Лекарства на полке стоят.", False, None),
    ("Таблетки приняли?", "medications_taken", "Муж выпил свои.", False, None),
    ("Таблетки приняли?", "medications_taken", "Надо бы выпить.", False, None),
    # --- utilities_paid ---
    ("Коммунальные услуги оплачены?", "utilities_paid", "Счета висят.", True, "no"),
    ("Коммунальные услуги оплачены?", "utilities_paid", "За свет и воду заплатила.", True, "yes"),
    ("Коммунальные услуги оплачены?", "utilities_paid", "Бумаги дочь себе забрала.", False, None),
    ("Коммунальные услуги оплачены?", "utilities_paid", "Дочь разберётся с бумагами.", False, None),
    # --- daughter_visit ---
    ("Дочь сегодня будет?", "daughter_visit", "Сказала, придёт как освободится.", True, "yes"),
    ("Дочь сегодня будет?", "daughter_visit", "Ленка заедет вечером.", True, "yes"),
    ("Дочь сегодня будет?", "daughter_visit", "С утра был звонок от дочери.", False, None),
    ("Дочь сегодня будет?", "daughter_visit", "С дочкой всё хорошо.", False, None),
    # --- onset ---
    ("Когда началось?", "onset", "Ещё вчера вечером.", True, None),
    ("Когда началось?", "onset", "Дня три уже.", True, None),
    ("Когда началось?", "onset", "Самочувствие хорошее.", False, None),
    ("Когда началось?", "onset", "Давление померила.", False, None),
    # --- wellness ---
    ("Как вы себя чувствуете?", "wellness", "В целом ничего.", True, None),
    ("Как вы себя чувствуете?", "wellness", "Слабость какая-то.", True, None),
    ("Как вы себя чувствуете?", "wellness", "Вечером жду дочку.", False, None),
    ("Как вы себя чувствуете?", "wellness", "Лекарство приняла.", False, None),
    # --- mood / sleep / plans ---
    ("Как настроение?", "mood", "Грустно что-то.", True, None),
    ("Как настроение?", "mood", "Бодрое.", True, None),
    ("Как настроение?", "mood", "Голова разболелась.", False, None),
    ("Как спали?", "sleep", "Ворочалась полночи.", True, None),
    ("Как спали?", "sleep", "Часов пять поспала.", True, None),
    ("Как спали?", "sleep", "Норм.", False, None),
    ("Какие планы?", "plans", "В поликлинику схожу.", True, None),
    ("Какие планы?", "plans", "Никуда не пойду.", True, None),
    ("Какие планы?", "plans", "Выспался.", False, None),
    # --- blood_pressure ---
    ("Давление какое?", "blood_pressure", "Сто пятьдесят на сто.", True, None),
    ("Давление какое?", "blood_pressure", "Высокое с утра.", True, None),
    ("Давление какое?", "blood_pressure", "Тонометр не нашла.", True, "unknown"),
    ("Давление какое?", "blood_pressure", "Кружится голова.", False, None),
    # --- multi-goal turns ---
    ("Как вы себя чувствуете?", "wellness", "Плохо, и давление высокое.", True, None),
    ("Как вы себя чувствуете?", "blood_pressure", "Плохо, и давление высокое.", False, None),
    ("Как вы себя чувствуете?", "medications_taken", "Нормально, таблетки выпила.", True, "yes"),
    ("Как вы себя чувствуете?", "wellness", "Нормально, таблетки выпила.", True, None),
    # --- other-person ---
    ("Как вы себя чувствуете?", "wellness", "У мужа голова болит.", False, None),
    ("Таблетки приняли?", "medications_taken", "Муж свои выпил.", False, None),
    # --- corrections ---
    ("Как самочувствие?", "wellness", "Плохо… нет, уже лучше.", True, None),
    ("Что болит?", "wellness", "Живот… хотя нет, всё прошло.", True, None),
    # --- uncertainty ---
    ("Когда началось?", "onset", "То ли вчера, то ли позавчера.", True, None),
    ("Как вы себя чувствуете?", "wellness", "Вроде ничего.", True, None),
    # --- short answers ---
    ("Как вы себя чувствуете?", "wellness", "Норм.", True, None),
    ("Дочь сегодня будет?", "daughter_visit", "Ну да, приедет.", True, "yes"),
    ("Дочь сегодня будет?", "daughter_visit", "Не, не приедет.", True, "no"),
    ("Таблетки приняли?", "medications_taken", "Мгм, приняла.", True, "yes"),
    # --- ASR-like (fragmented, no punctuation) ---
    ("Когда началось?", "onset", "вчера вечером кажется", True, None),
    ("Как вы себя чувствуете?", "wellness", "ну так себе вообще", True, None),
    ("Таблетки приняли?", "medications_taken", "да утром да", True, "yes"),
]


def main() -> None:
    rows = []
    for question, goal_id, text, relevant, value in PAIRS:
        goal = dict(GOALS[goal_id])
        rows.append(
            {
                "question": question,
                "goal": goal,
                "utterance": text,
                "relevant": relevant,
                "value": value,
                "act": None,
                "subject": "speaker",
                "polarity": None,
                "correction": False,
                "certainty": None,
                "ood": False,
                "evidence_span": None,
                "split_group": "eval_v1",
                "source": "eval_handmade",
            }
        )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    pos = sum(1 for r in rows if r["relevant"])
    print(f"wrote {len(rows)} eval pairs ({pos} pos / {len(rows) - pos} neg)")


if __name__ == "__main__":
    main()
