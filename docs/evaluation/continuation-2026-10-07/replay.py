"""Paired SDK captures. Simulated delivery; no STT/TTS/provider/human acceptance."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROUTINE = ["Хорошо.", "Поела.", "Нет.", "Нормальное.", "Выспалась."]
STORY = ["Вчера дочь приехала, мы смотрели фотографии.",
         "Долго сидели и вспоминали дачу.", "А потом пили чай и смеялись.",
         "Она рассказала про поездку к морю.",
         "Обсуждали фотографии с нашей прошлой поездки.",
         "Вспоминали, как гуляли по набережной вместе."]
CASES = {
    "heard_invitation_story": (1, ROUTINE + STORY + ["На этом всё.", "До свидания."]),
    "heard_summary_story": (1, ROUTINE + ["Нет, ничего."] + STORY + ["На этом всё."]),
    "late_plans_then_story": (1, ROUTINE + ["Нет, ничего.", "Сегодня буду гулять."] + STORY),
    "late_food_short": (0, ["Хорошо.", "Нет, ничего.", "Сегодня поела."]),
    "late_medication_short": (0, ["Хорошо.", "Нет, ничего.", "Сегодня таблетки приняла."]),
    "user_question": (1, ROUTINE + ["Нет, ничего.", "А ты кто?"]),
    "safety_in_story": (1, ROUTINE + STORY[:2] + ["Не могу дышать."]),
    "clinical_in_story": (1, ROUTINE + STORY[:2] + ["А потом у меня голова заболела."]),
    "explicit_goodbye": (1, ROUTINE + STORY[:2] + ["До свидания."]),
    "polite_finished": (1, ROUTINE + STORY[:2] + ["Ну всё, спасибо.", "До свидания."]),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=10)
    args = parser.parse_args()
    root = args.checkout.resolve()
    sys.path.insert(0, str(root))
    flags = {"IMVERA_DIALOGUE_ENGINE": "1", "IMVERA_ACTION_POLICY_MODE": "off",
             "IMVERA_LLM_INTERPRET": "0", "IMVERA_MISSION_LLM_INTERPRET": "0",
             "IMVERA_SPEECH_DAY": "102", "IMVERA_SPEECH_HOUR": "14"}
    os.environ.update(flags)
    from packages.dialogue_engine.events import CallStarted
    from packages.dialogue_engine.scenario_runner import ScenarioRunner
    timings, transcripts = [], {}
    for repetition in range(args.repeats):
        for name, (ladder, turns) in CASES.items():
            os.environ["IMVERA_COVERAGE_LADDER"] = str(ladder)
            runner = ScenarioRunner(call_id="continuation-" + name,
                                    elder_display_name="Тамара Юрьевна")
            runner.run([CallStarted()])
            rows = []
            for text in turns:
                start = time.perf_counter()
                result = runner.run([text])
                timings.append((time.perf_counter() - start) * 1000)
                state = runner.state
                rows.append({"user": text, "speech": [
                    {"text": s.text, "intent": s.intent, "marks_question": s.marks_question}
                    for s in result.speak_effects],
                    "closed": state.call_closed, "fsm": str(state.fsm_state),
                    "important_invitation_resolved": state.important_to_share_resolved,
                    "summary_delivered": state.summary_delivered,
                    "thread": state.current_thread_label,
                    "records": {key: value.model_dump(mode="json")
                                for key, value in state.slot_records.items()},
                    "coverage_records": {key: value.model_dump(mode="json")
                                         for key, value in state.coverage_records.items()}})
            if repetition == 0:
                transcripts[name] = {"coverage_ladder": ladder, "turns": rows}
    output = {
        "head": subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                         text=True).strip(),
        "dirty": bool(subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"],
                                              text=True)),
        "source_hashes": {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in (
            "packages/dialogue_engine/reducer.py", "packages/dialogue_engine/discourse.py",
            "packages/dialogue_engine/state.py")},
        "flags": flags, "scope": "synthetic SDK text; simulated audible completion",
        "cases": len(CASES), "repeats": args.repeats, "turns": len(timings),
        "sdk_ms_p50": statistics.median(timings),
        "sdk_ms_p95": sorted(timings)[int(.95 * (len(timings) - 1))],
        "end_of_speech_to_PCM": "NOT_RUN", "model_invocations": "NOT_MEASURED",
        "added_model_stages": 0, "transcripts": transcripts,
    }
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in output.items()
                      if key != "transcripts"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
