"""Reproducible text demo: every assistant line comes from DialogueEngine.

No audio, live model-quality or capacity claim. Inputs are synthetic; no
expected replies are scripted. Run from repository root with --json for
machine-readable evidence and turn-computation timings.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import time

from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.mission import CallMission, GoalDefinition
from packages.dialogue_engine.mission_result import build_call_outcomes, build_mission_result


def drain(engine: DialogueEngine) -> list[dict]:
    lines = []
    while (effect := engine.pop_speak_effect()) is not None:
        lines.append({"text": effect.text, "intent": effect.intent})
        # A text simulation explicitly acknowledges delivery. An actual
        # integration must use the transport's completed playout event.
        engine.on_playout_completed(effect.generation, effect.question_id)
    return lines


def scenarios() -> tuple[tuple[str, CallMission | None, tuple[str, ...]], ...]:
    shopping = CallMission(mission_id="shopping", goals=(GoalDefinition(
        goal_id="items", prompt_hint="Какие продукты вам купить?",
        answer_type="free_text", allowed_values=(),
    ),))
    return (
        ("volunteered_facts", None, (
            "Чувствую себя хорошо. Настроение хорошее. Спал хорошо. Сегодня буду дома.",
            "Нет, больше ничего.", "До свидания.",
        )),
        ("unknown_onset", None, (
            "Голова болит.", "Не помню.", "Терпимая.",
            "Нет, больше ничего.", "До свидания.",
        )),
        ("polite_refusal", None, (
            "Здравствуйте.", "Всё, пока, не беспокой меня, мне сейчас некогда.", "Пока.",
        )),
        ("shopping_interrupted", shopping, (
            "Голова болит.", "Сегодня.", "Терпимая.", "Молока и хлеба.",
            "Нет, больше ничего.", "До свидания.",
        )),
        ("mixed_answer", shopping, ("Молока и хлеба. Сегодня сильно болит голова.",)),
    )


def run() -> dict:
    rows = []
    timings = []
    for name, mission, inputs in scenarios():
        engine = DialogueEngine(
            call_id=f"demo-{name}", mission=mission, elder_display_name="Тамара Юрьевна",
        )
        engine.start()
        turns = [{"speaker": "vera", **line} for line in drain(engine)]
        for index, text in enumerate(inputs):
            uid = f"u{index}"
            started = time.perf_counter()
            turn = engine.build_rich_turn(text, utterance_id=uid)
            engine.on_user_turn(uid, text, rich_turn=turn)
            timings.append((time.perf_counter() - started) * 1000)
            turns.append({"speaker": "caller", "text": text})
            turns.extend({"speaker": "vera", **line} for line in drain(engine))
        rows.append({
            "scenario": name, "turns": turns,
            "mission_result": build_mission_result(engine.state).model_dump(mode="json"),
            "outcomes": build_call_outcomes(engine.state).model_dump(mode="json"),
            "episodes": [episode.model_dump(mode="json")
                         for episode in engine.state.issue_episodes.values()],
        })
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip())
    ordered = sorted(timings)
    return {
        "layer": "text_simulation", "git_sha": sha, "dirty": dirty,
        "model_act_inference": "not_exercised", "audio": "not_exercised",
        "latency_ms": {
            "samples": len(timings), "p50": round(statistics.median(timings), 3),
            "p95": round(ordered[max(0, int(len(ordered) * 0.95 + 0.999) - 1)], 3),
        },
        "scenarios": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(f"# Dialogue SDK text demo\n\nSHA: {result['git_sha']}; dirty: {result['dirty']}")
    print("\nТекстовая симуляция. Аудио и качество живых моделей не проверены.")
    for row in result["scenarios"]:
        print(f"\n## {row['scenario']}\n")
        for turn in row["turns"]:
            speaker = "Вера" if turn["speaker"] == "vera" else "Человек"
            print(f"**{speaker}:** {turn['text']}\n")
        print(f"Результат: `{row['outcomes']}`")
    print(f"\nВычисление текстового хода, мс: {result['latency_ms']}")


if __name__ == "__main__":
    main()
