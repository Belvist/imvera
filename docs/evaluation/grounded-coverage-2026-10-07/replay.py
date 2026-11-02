"""Source-bound full SDK exchanges; delivery is simulated, no audio providers."""
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

CASES = {
    "volunteered_three": ["Мне хорошо. Сегодня поела, таблетки уже приняла.",
                          "Нет, больше ничего."],
    "negative_three": ["Мне хорошо. Сегодня не ела. Таблетки не принимаю.", "Не помню."],
    "family_sleep": ["Я чувствую себя хорошо. Дочь приехала. Плохо спала.", "Нет, я про дочь."],
    "clinical_sugar": ["Мне хорошо. Сахар сегодня высокий."],
    "family_food": ["Мне хорошо. Дочь приехала. Поела."],
    "own_food_return": ["Мне хорошо. Дочь приехала. Я сегодня поела."],
    "uncertain_meds": ["Мне хорошо. Может быть, таблетки уже приняла."],
    "heard_answers": ["Мне хорошо.", "Да.", "Таблетки не принимаю."],
    "medication_habit": ["Мне хорошо. Сегодня поела. Таблетки каждый день принимаю."],
    "story": ["Мне хорошо. Сегодня поела, таблетки уже приняла.",
              "Вчера дочь приехала, мы смотрели фотографии.",
              "Долго сидели и вспоминали дачу.", "А потом пили чай и смеялись."],
    "local_refusal": ["Мне хорошо.", "Не хочу отвечать."],
    "unknown": ["Мне хорошо.", "Не помню."],
    "urgent": ["Мне хорошо. Сегодня поела, таблетки уже приняла.", "Не могу дышать."],
    "goodbye": ["Мне хорошо. Сегодня поела, таблетки уже приняла.", "До свидания."],
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--checkout", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--repeats", type=int, default=10)
    args = parser.parse_args()
    root = args.checkout.resolve()
    sys.path.insert(0, str(root))
    flags = {
        "IMVERA_DIALOGUE_ENGINE": "1", "IMVERA_COVERAGE_LADDER": "1",
        "IMVERA_ACTION_POLICY_MODE": "off", "IMVERA_LLM_INTERPRET": "0",
        "IMVERA_MISSION_LLM_INTERPRET": "0", "IMVERA_SPEECH_DAY": "102",
        "IMVERA_SPEECH_HOUR": "14",
    }
    os.environ.update(flags)
    from packages.dialogue_engine.coverage import content_exchanges, covered_domains
    from packages.dialogue_engine.events import CallStarted
    from packages.dialogue_engine.scenario_runner import ScenarioRunner

    timings, transcripts = [], {}
    for repetition in range(args.repeats):
        for name, turns in CASES.items():
            runner = ScenarioRunner(call_id="coverage-" + name, elder_display_name="Тамара Юрьевна")
            runner.run([CallStarted()])
            rows = []
            for text in turns:
                started = time.perf_counter()
                result = runner.run([text])
                timings.append((time.perf_counter() - started) * 1000)
                rows.append({
                    "user": text,
                    "speaks": [{"text": s.text, "intent": s.intent,
                                "marks_question": s.marks_question} for s in result.speak_effects],
                    "covered": sorted(covered_domains(runner.state)),
                    "content_items": content_exchanges(runner.state),
                    "records": {key: value.model_dump(mode="json") for key, value
                                in runner.state.coverage_records.items()},
                    "pending": runner.state.pending_coverage_domain,
                    "closed": runner.state.call_closed,
                })
            if repetition == 0:
                transcripts[name] = rows
    out = {
        "head": subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                        text=True).strip(),
        "dirty": bool(subprocess.check_output(
            ["git", "-C", str(root), "status", "--porcelain"], text=True,
        )),
        "source_hashes": {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in (
            "packages/dialogue_engine/coverage.py",
            "packages/dialogue_engine/conversation_policy.py",
            "packages/dialogue_engine/deterministic_mission.py",
        )},
        "flags": flags, "scope": "synthetic SDK; simulated audible completion",
        "repeats": args.repeats, "turns": len(timings),
        "sdk_ms_p50": statistics.median(timings),
        "sdk_ms_p95": sorted(timings)[int(.95 * (len(timings) - 1))],
        "end_of_speech_to_PCM": "NOT_RUN", "model_invocations": "NOT_MEASURED",
        "transcripts": transcripts,
    }
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "transcripts"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
