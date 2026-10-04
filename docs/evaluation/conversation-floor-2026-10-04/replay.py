"""Source-bound text SDK replay. NOT STT/TTS/SIP or a human-quality benchmark."""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

CASES = {
    "reported_live_vague": ["Нормально вроде бы.", "Нормально говорю.", "Да.",
                            "Правильно, говорю, всё.", "И что дальше?"],
    "story_feedback_handoff": ["Вчера дочь приезжала, мы смотрели старые фотографии.",
                               "Да.", "Потом вспоминали деревню и соседей.",
                               "Я вас слушаю.", "Я всё сказала."],
    "story_navigation": ["Вчера дочь приезжала, мы смотрели старые фотографии.",
                         "И что дальше?"],
    "story_navigation_unpunctuated": [
        "Вчера дочь приезжала, мы смотрели старые фотографии.", "и что дальше",
    ],
    "substantive_continuation": ["Вчера дочь приезжала, мы смотрели старые фотографии.",
                                 "Всё нормально, вчера дочь приезжала.",
                                 "Я всё рассказала дочери, потом мы гуляли.",
                                 "А дальше мы пошли гулять в саду."],
    "external_question": ["Вчера дочь приезжала, мы смотрели старые фотографии.",
                          "Что будет дальше с моей дочерью?"],
    "safety": ["Вчера дочь приезжала, мы смотрели старые фотографии.", "Не могу дышать."],
    "stop": ["Вчера дочь приезжала, мы смотрели старые фотографии.", "До свидания."],
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--checkout", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--cases", type=Path)
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text()) if args.cases else CASES
    root = args.checkout.resolve()
    sys.path.insert(0, str(root))
    flags = {
        "IMVERA_DIALOGUE_ENGINE": "1", "IMVERA_COVERAGE_LADDER": "1",
        "IMVERA_ACTION_POLICY_MODE": "off", "IMVERA_LLM_INTERPRET": "0",
        "IMVERA_MISSION_LLM_INTERPRET": "0", "IMVERA_SPEECH_DAY": "102",
        "IMVERA_SPEECH_HOUR": "14",
    }
    os.environ.update(flags)
    from packages.dialogue_engine.events import CallStarted
    from packages.dialogue_engine.scenario_runner import ScenarioRunner

    timings = []
    transcripts = {}
    for repetition in range(args.repeats):
        for name, turns in cases.items():
            runner = ScenarioRunner(call_id="floor-" + name, elder_display_name="Тамара Юрьевна")
            runner.run([CallStarted()])
            rows = []
            for text in turns:
                started = time.perf_counter()
                result = runner.run([text])
                elapsed = (time.perf_counter() - started) * 1000
                timings.append(elapsed)
                speech = result.speak_effects[-1]
                rows.append({
                    "user": text, "vera": speech.text, "intent": speech.intent,
                    "slot": speech.slot, "marks_question": speech.marks_question,
                    "wellness": str(runner.state.slots["wellness"]),
                    "facts": dict(runner.state.slot_values),
                    "thread_statement": runner.state.thread_last_statement,
                    "thread_finished": runner.state.thread_reply_finished,
                    "closed": runner.state.call_closed,
                    "personal_context": [item.model_dump(mode="json") for item in
                                         getattr(runner.state, "thread_statements", ())],
                })
            if repetition == 0:
                transcripts[name] = rows
    out = {
        "checkout": str(root),
        "head": subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True,
        ).strip(),
        "dirty": bool(subprocess.check_output(
            ["git", "-C", str(root), "status", "--porcelain"], text=True,
        )),
        "flags": flags, "scope": "synthetic canonical SDK; simulated audible completion",
        "repeats": args.repeats, "text_turns": len(timings),
        "sdk_turn_ms_p50": statistics.median(timings),
        "sdk_turn_ms_p95": sorted(timings)[int(0.95 * (len(timings) - 1))],
        "end_of_speech_to_PCM": "NOT_RUN", "provider_model_invocations": "NOT_MEASURED",
        "transcripts": transcripts,
    }
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "transcripts"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
