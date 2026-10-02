"""Comparable canonical text replay; deliberately does not synthesize or score warmth."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from packages.dialogue_engine.engine import DialogueEngine

SCENARIOS = {
    "ordinary_good": ["Хорошо.", "Нет.", "До свидания."],
    "complaint": ["Голова болит.", "С утра.", "Терпимо.", "Нет.", "До свидания."],
    "personal_story": [
        "Внучка приезжала, хорошо посидели.", "Чай пили, разговаривали.",
        "Да, приятно было.", "Хорошо.", "Нет.", "До свидания.",
    ],
    "lonely": [
        "Мне одиноко, скучаю по дочери.", "Она далеко, редко звонит.",
        "Я просто поговорить хотела.", "Нормально.", "Нет.", "До свидания.",
    ],
}
SOURCES = (
    "packages/dialogue_engine/conversation_policy.py",
    "packages/dialogue_engine/discourse.py",
    "packages/dialogue_engine/questions.py",
    "packages/dialogue_engine/reducer.py",
    "packages/dialogue_engine/state.py",
    "packages/dialogue_engine/turn_understanding.py",
    "packages/dialogue_engine/deterministic_mission.py",
)


class ReplayTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 2, 10, 0, tzinfo=tz)


def replay() -> dict:
    outputs = {}
    for name, inputs in SCENARIOS.items():
        engine = DialogueEngine(
            call_id=f"heard-quality-{name}", elder_display_name="Тамара Юрьевна",
        )
        transcript = []
        engine.start()
        for number, text in enumerate([None, *inputs]):
            if text is not None:
                uid = f"replay-{number}"
                turn = engine.build_rich_turn(text, utterance_id=uid)
                transcript.append({
                    "speaker": "caller", "text": text,
                    "proposed_goal_answers": [a.model_dump() for a in turn.goal_answers],
                })
                engine.on_user_turn(uid, text, rich_turn=turn)
            while (effect := engine.pop_speak_effect()) is not None:
                engine.on_playout_completed(effect.generation, effect.question_id)
                transcript.append({
                    "speaker": "vera", "text": effect.text, "intent": effect.intent,
                    "marks_question": effect.marks_question,
                    "pending_intent": getattr(engine.state.delivered_question, "intent", None),
                    "wellness": str(engine.state.slots["wellness"]),
                    "wellness_quote": getattr(
                        engine.state.slot_records.get("wellness"), "source_text", None,
                    ),
                })
        outputs[name] = transcript
    return {
        "layer": "offline canonical DialogueEngine SDK text; no STT, TTS or phone",
        "clock": "2026-10-02 10:00; fixed copy rotation and call IDs",
        "human_warmth": "NOT_RUN", "heard_audio": "NOT_RUN",
        "inputs": SCENARIOS,
        "source_sha256": {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in SOURCES},
        "outputs": outputs,
    }


if __name__ == "__main__":
    with (
        patch("datetime.datetime", ReplayTime),
        patch(
            "packages.dialogue_engine.questions._speech_day",
            return_value=date(2026, 10, 2).toordinal(),
        ),
    ):
        print(json.dumps(replay(), ensure_ascii=False, indent=2))
