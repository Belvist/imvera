"""Real SDK/state capture; delivered speech is simulated, no phone or audio."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

CASES = {
    "correction": [
        "Самочувствие хорошее, спала хорошо.",
        "Нет, я перепутала, спала плохо.",
        "Часто просыпалась.",
    ],
    "late_summary": ["Самочувствие хорошее, спала хорошо.", "Нет, ничего.", "Часто просыпалась."],
    "foreign": ["Самочувствие хорошее, спала хорошо.", "Дочь спала плохо."],
    "historical": ["Самочувствие хорошее, спала хорошо.", "Я перепутала, раньше спала плохо."],
    "conditional": ["Самочувствие хорошее, спала хорошо.", "Если я спала плохо, то буду усталой."],
    "foreign_pattern": [
        "Самочувствие хорошее, спала хорошо.",
        "Нет, я перепутала, спала плохо.",
        "Дочь проснулась в четыре.",
    ],
    "different_complaint": [
        "Самочувствие хорошее, спала хорошо.",
        "Нет, я перепутала, спала плохо.",
        "Голова болит пять часов.",
    ],
    "safety": ["Самочувствие хорошее, спала хорошо.", "Мне сейчас трудно дышать."],
    "stop": ["Самочувствие хорошее, спала хорошо.", "Не звоните больше."],
    "unknown_onset": ["Голова болит.", "Не помню."],
    "declined_onset": ["Голова болит.", "Не хочу отвечать."],
    "open_historical_sleep": ["Самочувствие хорошее, год назад спала плохо."],
    "long_sleep": ["Спала плохо. " + "Вчера мы вспоминали фотографии и сад. " * 20],
    "functional_answer": [
        "Голова болит со вчера, сейчас ещё болит, терпимо.",
        "Могу делать обычные дела.",
    ],
    "multi_complaint": ["Голова болит со вчера, живот болит с утра.", "Не помню."],
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--checkout", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--mode", choices=("legacy", "shadow", "policy"), default="legacy")
    parser.add_argument("--warm-models", action="store_true")
    args = parser.parse_args()
    root = args.checkout.resolve()
    sys.path.insert(0, str(root))
    flags = {
        "IMVERA_DIALOGUE_ENGINE": "1",
        "IMVERA_COVERAGE_LADDER": "0",
        "IMVERA_ACTION_POLICY_MODE": args.mode,
        "IMVERA_LLM_INTERPRET": "0",
        "IMVERA_ACTION_POLICY_CUTOVER_ENABLED": "1" if args.mode == "policy" else "0",
        "IMVERA_MISSION_LLM_INTERPRET": "0",
        "IMVERA_SPEECH_DAY": "102",
        "IMVERA_SPEECH_HOUR": "14",
    }
    os.environ.update(flags)
    from packages.dialogue_engine.engine import DialogueEngine

    model_calls, warm_report = {}, []
    if args.warm_models:
        from packages.dialogue_engine.semantic_nlp.model import SemanticNLP
        from packages.dialogue_engine.semantic_nlp.polarity import PolarityModel
        from packages.dialogue_engine.semantic_nlp.relation import RelationScorer
        from packages.dialogue_engine.semantic_nlp.warmup import warmup_all

        report = warmup_all()
        if not report.all_hot:
            raise RuntimeError("real semantic models not all hot; capture refused")
        warm_report = [{"name": m.name, "ok": m.ok, "device": m.device} for m in report.models]

        def counted(name, fn):
            def invoke(*a, **kw):
                model_calls[name] = model_calls.get(name, 0) + 1
                return fn(*a, **kw)
            return invoke

        for name, model, method in (("act", SemanticNLP.get(), "predict"),
                                    ("polarity", PolarityModel.get(), "predict"),
                                    ("relation_cpu", RelationScorer.get_cpu(), "score_all")):
            model_calls[name] = 0
            setattr(model, method, counted(name, getattr(model, method)))

    def deliver(engine):
        speaks = []
        while (speech := engine.pop_speak_effect()) is not None:
            speaks.append({"text": speech.text, "intent": speech.intent})
            engine.on_playout_completed(speech.generation, speech.question_id)
        return speaks

    timings, transcripts = [], {}
    for name, texts in CASES.items():
        engine = DialogueEngine(call_id="revision-" + name)
        engine.start()
        deliver(engine)
        rows = []
        for index, text in enumerate(texts):
            start = time.perf_counter()
            calls_before = dict(model_calls)
            uid = f"u-{index + 1}"
            try:
                turn = engine.build_rich_turn(text, utterance_id=uid)
                engine.on_user_turn(uid, text, rich_turn=turn)
            except Exception as exc:
                rows.append({"user": text, "error_type": type(exc).__name__})
                break
            speaks = deliver(engine)
            timings.append((time.perf_counter() - start) * 1000)
            row = {
                "user": text,
                "speaks": speaks,
                "slots": {
                    k: v.model_dump(mode="json") for k, v in engine.state.slot_records.items()
                },
                "topic_dimensions": engine.state.topic_dimensions,
                "episodes": {k: v.model_dump(mode="json")
                             for k, v in engine.state.issue_episodes.items()},
                "pending_episode_attribute": engine.state.pending_episode_attribute,
                "closed": engine.state.call_closed,
                "sdk_ms": timings[-1],
                "semantic_method_calls": {
                    k: value - calls_before.get(k, 0) for k, value in model_calls.items()
                },
            }
            rows.append(json.loads(json.dumps(row, ensure_ascii=False)))
        transcripts[name] = rows
    files = (
        "reducer.py",
        "state.py",
        "turn_understanding.py",
        "fast_interpreter.py",
        "issue_mention_extract.py",
        "mission_grounding.py",
        "questions.py",
        "deterministic_mission.py",
        "conversation_policy.py",
        "topic_tracker.py",
        "issue_memory.py",
        "semantic_kernel/clauses.py",
        "semantic_kernel/kernel.py",
        "semantic_kernel/relation_parser.py",
        "semantic_kernel/observation_memory.py",
        "action_policy/snapshot.py",
        "action_policy/needs.py",
        "action_policy/need_value.py",
        "action_policy/constraints.py",
        "action_policy/scorer.py",
        "product/spoken.py",
    )
    result = {
        "head": subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
        ).strip(),
        "source_hashes": {
            p: hashlib.sha256((root / "packages/dialogue_engine" / p).read_bytes()).hexdigest()
            for p in files
        },
        "flags": flags,
        "offline_environment": {k: os.environ.get(k)
                                for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")},
        "git_state": "dirty" if subprocess.check_output(
            ["git", "-C", str(root), "status", "--porcelain"], text=True
        ).strip() else "clean",
        "scope": "DialogueEngine SDK; simulated delivery; no audio",
        "environment": {"platform": platform.platform(), "logical_cpus": os.cpu_count(),
                        "cpu_max": Path("/sys/fs/cgroup/cpu.max").read_text().strip()
                        if Path("/sys/fs/cgroup/cpu.max").exists() else None},
        "turns": len(timings),
        "failed_turns": sum("error_type" in row for rows in transcripts.values() for row in rows),
        "sdk_ms_p50": statistics.median(timings),
        "sdk_ms_p95": sorted(timings)[int(0.95 * (len(timings) - 1))],
        "model_invocations": "NOT_MEASURED; generative path explicitly disabled",
        "counted_semantic_methods": model_calls,
        "warm_report": warm_report,
        "first_audible_pcm": "NOT_RUN",
        "transcripts": transcripts,
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
