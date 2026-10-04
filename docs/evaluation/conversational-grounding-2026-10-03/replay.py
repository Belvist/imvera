"""Synthetic canonical SDK replay; no STT, TTS or phone acceptance."""

import json
import os
import sys
from pathlib import Path

# Direct-script execution can otherwise import an editable SDK installed from
# another checkout. Evidence must exercise the code beside this replay file.
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def main():
    for name, value in {
        "IMVERA_DIALOGUE_ENGINE": "1",
        "IMVERA_COVERAGE_LADDER": "1",
        "IMVERA_LLM_INTERPRET": "0",
        "IMVERA_MISSION_LLM_INTERPRET": "0",
        "IMVERA_ACTION_POLICY_MODE": "off",
        "IMVERA_SPEECH_DAY": "102",
        "IMVERA_SPEECH_HOUR": "14",
    }.items():
        os.environ[name] = value

    from packages.core.memory_store import InMemoryCallRecordStore
    from packages.dialogue.session import CallSession

    CASES = {
        "food_no": ["Чувствую себя хорошо.", "Не поел."],
        "food_bare_no": ["Чувствую себя хорошо.", "Нет."],
        "food_yes": ["Чувствую себя хорошо.", "Да, поел."],
        "food_unknown": ["Чувствую себя хорошо.", "Не помню."],
        "food_future": ["Чувствую себя хорошо.", "Потом поем."],
        "volunteered_negative_food": ["Чувствую себя хорошо, но сегодня ещё не поел."],
        "volunteered_other_food": ["Чувствую себя хорошо, дочь уже поела."],
        "sleep_mixed": ["Чувствую себя хорошо, спала всего два часа."],
        "food_story": [
            "Чувствую себя хорошо.",
            "Вчера дочь приезжала, смотрели старые фотографии.",
            "Вспоминали, как вместе жили в деревне.",
            "А потом ещё посидели и поговорили.",
            "Больше нечего добавить.",
        ],
        "food_reactive_story": [
            "Чувствую себя хорошо.",
            "Да, поела. А вчера дочь приезжала, мы смотрели старые фотографии.",
            "Потом вспоминали нашу деревню и соседей.",
            "Больше нечего добавить.",
        ],
        "meds_unknown": ["Чувствую себя хорошо.", "Да, поела.", "Не помню."],
        "meds_no": ["Чувствую себя хорошо.", "Да, поела.", "Нет, не принимаю."],
        "question": ["Чувствую себя хорошо.", "А какая погода сегодня?"],
        "clinical": ["Голова тяжёлая со вчера, сейчас сильно болит."],
        "local_refusal": [
            "Чувствую себя хорошо.",
            "Не хочу отвечать про еду, но хочу поговорить.",
            "Дочь приезжала, мы гуляли вместе.",
        ],
        "stop": ["Чувствую себя хорошо.", "Спасибо, не хочу больше разговаривать."],
    }
    out = {}
    for cid, texts in CASES.items():
        s = CallSession(
            call_id="reaction-" + cid,
            family_id="f",
            elder_display_name="Тамара Юрьевна",
            store=InMemoryCallRecordStore(),
        )
        s.start()
        s.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
        s.state.greeted = True
        rows = []
        for i, text in enumerate(texts):
            e = s._engine
            uid = f"{cid}-{i}"
            rich = e.build_rich_turn(text, utterance_id=uid)
            result = s.handle_user_text(text, rich_turn=rich, utterance_id=uid)
            s.mark_spoken_action(result.proposal.generation_id)
            st = s._engine.state
            rows.append(
                {
                    "user": text,
                    "vera": result.proposal.speech,
                    "intent": getattr(result.speak_effect, "intent", None),
                    "question": getattr(result.speak_effect, "marks_question", None),
                    "coverage": {
                        k: v for k, v in st.observations.items() if k.startswith("coverage_")
                    },
                    "pending": st.pending_coverage_domain,
                    "closed": st.call_closed,
                    "thread_origin": dict(st.action_policy_router_stats),
                    "slots": {k: v.model_dump() for k, v in st.slot_records.items()},
                }
            )
            rows[-1]["coverage_records"] = {
                k: v.model_dump() for k, v in getattr(st, "coverage_records", {}).items()
            }
            rows[-1]["thread_statement"] = st.thread_last_statement
        out[cid] = rows
    with open(sys.argv[1], "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    for cid, rows in out.items():
        print(cid)
        for row in rows:
            print(" ", row["user"], "=>", row["vera"])


if __name__ == "__main__":
    main()
