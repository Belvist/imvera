"""Runtime goal catalog for relation shadow scoring (mirrors the training
goal descriptions verbatim — same strings the cross-encoder saw)."""

from __future__ import annotations

GOALS: list[dict] = [
    {
        "goal_id": "wellness",
        "description": "Как человек себя чувствует в целом прямо сейчас",
        "answer_type": "free_text",
        "allowed_values": [],
    },
    {
        "goal_id": "mood",
        "description": "Какое настроение у человека",
        "answer_type": "free_text",
        "allowed_values": [],
    },
    {
        "goal_id": "sleep",
        "description": "Как человек спал",
        "answer_type": "free_text",
        "allowed_values": [],
    },
    {
        "goal_id": "plans",
        "description": "Какие планы на день, где находится",
        "answer_type": "free_text",
        "allowed_values": [],
    },
    {
        "goal_id": "onset",
        "description": "Когда начался симптом",
        "answer_type": "free_text",
        "allowed_values": [],
    },
    {
        "goal_id": "medications_taken",
        "description": "Принял ли человек лекарства",
        "answer_type": "bool",
        "allowed_values": ["yes", "no", "unknown"],
    },
    {
        "goal_id": "blood_pressure",
        "description": "Какое давление у человека",
        "answer_type": "free_text",
        "allowed_values": [],
    },
    {
        "goal_id": "daughter_visit",
        "description": "Придёт ли дочь сегодня",
        "answer_type": "bool",
        "allowed_values": ["yes", "no", "unknown"],
    },
    {
        "goal_id": "utilities_paid",
        "description": "Оплачены ли коммунальные услуги",
        "answer_type": "bool",
        "allowed_values": ["yes", "no", "unknown"],
    },
]
