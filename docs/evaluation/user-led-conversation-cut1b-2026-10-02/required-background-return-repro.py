"""Text-only SDK reproduction with simulated delivery, not an audio call."""

# ruff: noqa: E402
import json
import os

os.environ["IMVERA_ACTION_POLICY_MODE"] = "off"
os.environ["IMVERA_COVERAGE_LADDER"] = "0"
from packages.dialogue_engine.action_policy.snapshot import build_policy_snapshot
from packages.dialogue_engine.engine import DialogueEngine

engine = DialogueEngine(call_id="mandatory-story-resume")
engine.state.mandatory_background_goals = True
rows = []


def capture(text):
    effects = []
    while (fx := engine.pop_speak_effect()) is not None:
        effects.append(
            {
                "text": fx.text,
                "intent": fx.intent,
                "slot": fx.slot,
                "marks_question": fx.marks_question,
            }
        )
        engine.on_playout_completed(fx.generation, fx.question_id)
    snap = build_policy_snapshot(engine.state)
    rows.append(
        {
            "input": text,
            "speech": effects,
            "slots": {k: str(v) for k, v in engine.state.slots.items()},
            "background": {k: str(v) for k, v in engine.state.background_goal_status.items()},
            "snapshot_background": dict(snap.background_goal_status),
            "snapshot_resume": snap.thread_resume_slot,
            "goals": {
                k: {"status": str(v.status), "lifecycle": str(v.lifecycle)}
                for k, v in engine.state.goals.items()
                if v.slot in ("wellness", "mood", "sleep", "plans")
            },
        }
    )


engine.start()
capture("START")
for i, text in enumerate(
    ("Хорошо, дочь сегодня приезжала.", "Мы пили чай и разговаривали.", "Больше нечего добавить.")
):
    turn = engine.build_rich_turn(text, utterance_id=f"coverage-u{i}")
    engine.on_user_turn(f"coverage-u{i}", text, rich_turn=turn)
    capture(text)
print(json.dumps(rows, ensure_ascii=False, indent=2))
