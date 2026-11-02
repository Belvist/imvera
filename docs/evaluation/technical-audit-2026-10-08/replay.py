"""Source-bound synthetic audit captures; no phone/audio/model-quality claim."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.checkout.resolve()
    sys.path.insert(0, str(root))
    flags = {"IMVERA_DIALOGUE_ENGINE": "1", "IMVERA_ACTION_POLICY_MODE": "off",
             "IMVERA_COVERAGE_LADDER": "1", "IMVERA_LLM_INTERPRET": "0",
             "IMVERA_MISSION_LLM_INTERPRET": "0",
             "IMVERA_SPEECH_DAY": "102", "IMVERA_SPEECH_HOUR": "14"}
    os.environ.update(flags)
    from packages.dialogue_engine.engine import DialogueEngine
    from packages.dialogue_engine.events import CallStarted
    from packages.dialogue_engine.scenario_runner import ScenarioRunner
    from packages.safety.rules import match_deterministic_signals

    routine = ["Хорошо.", "Поела.", "Нет.", "Нормальное.", "Выспалась."]
    story = ["Вчера дочь приехала, мы смотрели фотографии.",
             "Долго сидели и вспоминали дачу.", "А потом пили чай и смеялись.",
             "Она рассказала про поездку к морю.",
             "Обсуждали фотографии с нашей прошлой поездки.",
             "Вспоминали, как гуляли по набережной вместе.",
             "Потом вспоминали нашу дачу и летние вечера.",
             "Рассматривали старые фотографии из поездки."]
    cases = {
        "breathing": ["Мне сейчас трудно дышать."],
        "foreign_breathing": ["Дочери сейчас трудно дышать."],
        "past_breathing": ["Вчера было трудно дышать."],
        "denied_breathing": ["Мне сейчас не тяжело дышать."],
        "volunteered_food_meds": ["Мне хорошо. Сегодня поела, таблетки уже приняла."],
        "eight_story_turns": routine + story + ["Нет, ничего."],
    }
    transcripts = {}
    for name, texts in cases.items():
        runner = ScenarioRunner(call_id="audit-" + name, elder_display_name="Тест")
        runner.run([CallStarted()])
        rows = []
        for text in texts:
            result = runner.run([text])
            rows.append({"user": text, "signals": match_deterministic_signals(text),
                         "speech": [{"intent": s.intent, "text": s.text,
                                     "marks_question": s.marks_question}
                                    for s in result.speak_effects],
                         "check_path": str(runner.state.check_path),
                         "closed": runner.state.call_closed,
                         "personal_ring_size": len(runner.state.thread_statements)})
        transcripts[name] = rows
    illustration = ("Да нормально я. Вчера дочь заходила. А сегодня голова болит, "
                    "но терпимо, таблетки уже выпила.")
    engine = DialogueEngine(call_id="audit-understanding", elder_display_name="Тест")
    for effect in engine.start():
        if getattr(effect, "kind", "") == "speak":
            engine.on_playout_started(effect.generation, effect.question_id)
            engine.on_playout_completed(effect.generation, effect.question_id)
    rich = engine.build_rich_turn(illustration, utterance_id="illustration")
    effects = engine.on_user_turn("illustration", illustration, rich_turn=rich)
    accepted = {"slots": {k: v.model_dump(mode="json")
                          for k, v in engine.state.slot_records.items()},
                "coverage": {k: v.model_dump(mode="json")
                             for k, v in engine.state.coverage_records.items()},
                "episodes": {k: v.model_dump(mode="json")
                             for k, v in engine.state.issue_episodes.items()},
                "personal_ring": [v.model_dump(mode="json")
                                  for v in engine.state.thread_statements],
                "speech": [{"intent": e.intent, "text": e.text}
                           for e in effects if getattr(e, "kind", "") == "speak"]}
    out = {"head": subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                           text=True).strip(),
           "source_hashes": {p: hashlib.sha256((root / p).read_bytes()).hexdigest()
                             for p in ["packages/safety/patterns.py", "packages/safety/rules.py",
                                       "packages/dialogue_engine/check_path.py",
                                       "services/tts/worker.py"]},
           "scope": "synthetic SDK text, simulated completed playback; no STT/TTS/SIP",
           "flags": flags, "transcripts": transcripts,
           "understanding_illustration": {"text": illustration,
                                          "actual_rich_turn": rich.model_dump(mode="json"),
                                          "accepted_state": accepted}}
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "cases": len(cases)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
