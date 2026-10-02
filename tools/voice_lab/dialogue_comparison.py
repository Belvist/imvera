"""Replay a frozen text suite or compare captured, attributable transcripts.

No competitor response is generated, inferred from marketing, or scored as MOS.
External captures require provider/version/channel/evidence and the exact inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import time
from collections import Counter
from datetime import UTC, datetime
from math import ceil, isfinite
from pathlib import Path

DEFAULT_SUITE = Path(__file__).parent / "fixtures/dialogue_comparison_v1.json"
FORMAT = "imvera.dialogue-comparison.v1"


def read_suite(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    suite = json.loads(raw)
    ids = [case["id"] for case in suite["cases"]]
    if len(ids) != len(set(ids)) or not ids:
        raise ValueError("Suite case IDs must be unique and non-empty")
    return suite, hashlib.sha256(raw).hexdigest()


def validate_capture(capture: dict, suite: dict, suite_sha: str) -> None:
    if capture.get("format") != FORMAT or capture.get("suite_sha256") != suite_sha:
        raise ValueError("Capture must identify the exact frozen suite")
    provider = capture.get("provider", {})
    for field in ("name", "version", "channel", "language", "captured_at", "evidence_ref"):
        if not isinstance(provider.get(field), str) or not provider[field].strip():
            raise ValueError(f"Capture requires attributable provider.{field}")
    if provider["language"] != suite["language"]:
        raise ValueError("Different language: use a separate suite; do not rank translated runs")
    cases = capture.get("cases", [])
    expected = {case["id"]: case for case in suite["cases"]}
    seen = set()
    for row in cases:
        case_id = row.get("id")
        if case_id not in expected or case_id in seen:
            raise ValueError("Unknown or duplicated capture case ID")
        seen.add(case_id)
        turns = row.get("turns", [])
        if not turns or turns[0].get("user") is not None:
            raise ValueError("Every case must include its real opening response")
        inputs = [turn.get("user") for turn in turns[1:]]
        if inputs != expected[case_id]["inputs"]:
            raise ValueError(f"Changed or missing inputs in {case_id}")
        for turn in turns:
            response = turn.get("assistant")
            if not isinstance(response, list) or any(
                not isinstance(text, str) for text in response
            ):
                raise ValueError("assistant must contain actual text strings; [] means no response")
    if not cases:
        raise ValueError("An empty capture is NOT_RUN, not a measured competitor")


def _decision_state(engine) -> dict:
    """Read-only projection; never invoke a scheduler/renderer to inspect state."""
    state = engine.state
    return {
        "revision": state.revision,
        "active_playout_generation": state.active_playout_generation,
        "slots": {key: str(value) for key, value in state.slots.items()},
        "slot_values": dict(state.slot_values),
        "active_episode_id": state.active_episode_id,
        "pending_episode_attribute": state.pending_episode_attribute,
        "episodes": {
            key: {
                "label": ep.primary_label,
                "known_attributes": dict(ep.known_attributes),
                "status": ep.status,
            }
            for key, ep in state.issue_episodes.items()
        },
        "planned_question": (
            state.planned_question.model_dump(mode="json") if state.planned_question else None
        ),
        "delivered_question": (
            state.delivered_question.model_dump(mode="json") if state.delivered_question else None
        ),
        "important_to_share_asked": state.important_to_share_asked,
        "important_to_share_resolved": state.important_to_share_resolved,
        "thread": {
            "label": state.current_thread_label,
            "hook": state.open_hook,
            "followup_count": state.thread_followup_count,
            "reply_finished": state.thread_reply_finished,
        },
        "router_stats": dict(state.action_policy_router_stats),
    }


def _source_fingerprints() -> dict[str, str]:
    root = Path(__file__).resolve().parents[2]
    paths = sorted((root / "packages/dialogue_engine").rglob("*.py"))
    paths.extend(root / name for name in (
        "packages/dialogue/session.py", "packages/voice_runtime/call_actor.py",
        "tools/voice_lab/dialogue_comparison.py",
    ))
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


def run_imvera(
    suite: dict, suite_sha: str, label: str, *, decision_metadata: bool = False,
) -> dict:
    from packages.dialogue_engine.engine import DialogueEngine
    from packages.dialogue_engine.mission import CallMission
    from packages.dialogue_engine.mission_result import build_call_outcomes, build_mission_result

    os.environ["IMVERA_SPEECH_DAY"] = suite["speech_day"]
    os.environ["IMVERA_SPEECH_HOUR"] = suite["speech_hour"]
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip())

    def drain(engine: DialogueEngine) -> tuple[list[str], list[str], list[dict]]:
        texts, intents, decisions = [], [], []
        while (effect := engine.pop_speak_effect()) is not None:
            texts.append(effect.text)
            intents.append(effect.intent)
            if decision_metadata:
                decision = {
                    "effect": effect.model_dump(mode="json"),
                    "before_delivery": _decision_state(engine),
                }
            engine.on_playout_completed(effect.generation, effect.question_id)
            if decision_metadata:
                decision["after_delivery"] = _decision_state(engine)
                decision["delivery"] = "SIMULATED_COMPLETED"
                decisions.append(decision)
        return texts, intents, decisions

    cases = []
    for case in suite["cases"]:
        mission_data = suite["missions"].get(case["mission"])
        mission = CallMission.model_validate(mission_data) if mission_data else None
        engine = DialogueEngine(
            call_id=f"compare-{case['id']}",
            mission=mission,
            elder_display_name=suite["elder_display_name"],
        )
        engine.state.mandatory_background_goals = case.get(
            "mandatory_background_goals", mission is None
        )
        replay_configuration = {
            "mandatory_background_goals": engine.state.mandatory_background_goals,
            "required_background_goals": sorted(engine.state.required_background_goals),
            "mission_preset": engine.state.mission_preset,
        }
        engine.start()
        texts, intents, decisions = drain(engine)
        turns = [{"user": None, "assistant": texts, "intents": intents}]
        if decision_metadata:
            turns[0].update(decisions=decisions, state_after=_decision_state(engine))
        for index, text in enumerate(case["inputs"]):
            uid = f"u{index + 1}"
            before = _decision_state(engine) if decision_metadata else None
            started = time.perf_counter()
            rich = engine.build_rich_turn(text, utterance_id=uid)
            engine.on_user_turn(uid, text, rich_turn=rich)
            elapsed = (time.perf_counter() - started) * 1000
            texts, intents, decisions = drain(engine)
            turns.append(
                {
                    "user": text,
                    "assistant": texts,
                    "intents": intents,
                    "text_processing_ms": round(elapsed, 3),
                }
            )
            if decision_metadata:
                turns[-1].update(
                    utterance_id=uid, state_before=before,
                    understanding={
                        key: value for key, value in rich.model_dump(mode="json").items()
                        if key in {
                            "dialogue_act", "answers_pending_question", "user_question",
                            "goal_facts", "goal_answers", "issue_mentions", "not_recalled",
                            "control", "kernel_route", "kernel_ambiguities",
                        }
                    },
                    decisions=decisions, state_after=_decision_state(engine),
                )
        cases.append(
            {
                "id": case["id"],
                "turns": turns,
                "mission_result": build_mission_result(engine.state).model_dump(mode="json"),
                "outcomes": build_call_outcomes(engine.state).model_dump(mode="json"),
                "episodes": [
                    ep.model_dump(mode="json") for ep in engine.state.issue_episodes.values()
                ],
                **({"replay_configuration": replay_configuration} if decision_metadata else {}),
            }
        )
    result = {
        "format": FORMAT,
        "suite_sha256": suite_sha,
        "suite_version": suite["version"],
        "provider": {
            "name": label,
            "version": sha,
            "channel": "text",
            "language": suite["language"],
            "captured_at": datetime.now(UTC).isoformat(),
            "evidence_ref": "canonical SDK replay",
        },
        "runtime": {
            "git_dirty": dirty,
            "python": platform.python_version(),
            "platform": platform.system(),
            "audio": "NOT_RUN",
            "live_act_inference": "NOT_RUN",
            "human_warmth_rating": "NOT_RUN",
        },
        "cases": cases,
    }
    if decision_metadata:
        from packages.dialogue_engine.action_policy_shadow_config import action_policy_runtime_truth
        from packages.dialogue_engine.runtime import coverage_ladder_enabled

        result["runtime"].update(
            understanding_path="SDK TurnUnderstandingV2.resolve; CallActor producer NOT_RUN",
            delivery="SIMULATED_COMPLETED; transport/audible delivery NOT_RUN",
            router=action_policy_runtime_truth(),
            coverage_ladder_enabled=coverage_ladder_enabled(),
            speech_day=os.environ.get("IMVERA_SPEECH_DAY"),
            speech_hour=os.environ.get("IMVERA_SPEECH_HOUR"),
            act_head_requested=os.environ.get("IMVERA_ACT_HEAD_VERSION", "v2"),
            source_sha256=_source_fingerprints(),
        )
        for row, case in zip(result["cases"], suite["cases"], strict=True):
            row["required_modalities"] = case.get("required_modalities", ["text"])
    validate_capture(result, suite, suite_sha)
    return result


def _percentiles(samples: list[float]) -> dict | str:
    if not samples:
        return "NOT_RUN"
    ordered = sorted(samples)
    return {
        "n": len(ordered),
        "p50": ordered[max(0, ceil(0.50 * len(ordered)) - 1)],
        "p95": ordered[max(0, ceil(0.95 * len(ordered)) - 1)],
    }


def measure_capture(capture: dict) -> dict:
    """Measure captured SDK presentations, not clinical correctness or heard warmth.

    Repeated presentations may be warranted repairs/unknown answers. Proxy counts
    are diagnostics, not automatic safety/quality verdicts. IDs distinguish real
    questions from text containing '?' and repeated delivery callbacks.
    """
    if capture.get("provider", {}).get("channel") != "text":
        raise ValueError("SDK metrics require a text capture, not a telephone-delivery claim")
    if not capture.get("runtime", {}).get("source_sha256"):
        raise ValueError("Metrics require source fingerprints and --decision-metadata")
    rows = []
    for case in capture["cases"]:
        counts: Counter = Counter()
        seen_ids: set[str] = set()
        needs: Counter = Counter()
        samples = []
        run = maximum_run = max_fills = 0
        for turn in case["turns"]:
            if "decisions" not in turn or "state_after" not in turn:
                raise ValueError("Metrics require actual captured decision/state metadata")
            effects = [d["effect"] for d in turn["decisions"]]
            if (
                turn.get("assistant") != [fx["text"] for fx in effects]
                or turn.get("intents") != [fx["intent"] for fx in effects]
            ):
                raise ValueError("Decision effects must match captured assistant/intents")
            if turn.get("user") is not None:
                counts["user_turns"] += 1
                if "text_processing_ms" in turn:
                    elapsed = turn["text_processing_ms"]
                    if (
                        isinstance(elapsed, bool) or not isinstance(elapsed, (int, float))
                        or not isfinite(elapsed) or elapsed < 0
                    ):
                        raise ValueError("Invalid SDK elapsed time; missing is NOT_RUN, not zero")
                    samples.append(elapsed)
                before = turn["state_before"]
                after = turn["state_after"]
                fills = sum(
                    value == "FILLED" and before["slots"].get(key) != "FILLED"
                    for key, value in after["slots"].items()
                )
                max_fills = max(max_fills, fills)
                if turn["understanding"].get("user_question"):
                    counts["user_question_turns"] += 1
                    if "answer_user_question" not in turn["intents"]:
                        counts["user_question_without_answer_intent_proxy"] += 1
                if (
                    before["thread"]["followup_count"] >= 2
                    and "resume_after_thread" in turn["intents"]
                ):
                    counts["budget_to_wellness_return_proxy"] += 1
            for decision in turn["decisions"]:
                if decision.get("delivery") != "SIMULATED_COMPLETED":
                    raise ValueError("SDK metrics do not establish real delivery")
                fx = decision["effect"]
                if type(fx.get("marks_question")) is not bool:
                    raise ValueError("Question marks_question must be a boolean")
                counts["speech_presentations"] += 1
                question = fx["marks_question"]
                run = run + 1 if question else 0
                maximum_run = max(maximum_run, run)
                if not question:
                    counts["nonquestion_speech_presentations"] += 1
                    continue
                qid = fx.get("question_id")
                if not qid:
                    raise ValueError("Question presentation requires an actual question ID")
                after_delivery = decision["after_delivery"]
                delivered = after_delivery["delivered_question"]
                if (
                    not delivered or delivered["question_id"] != qid
                    or delivered["phase"] != "DELIVERED"
                    or after_delivery["active_playout_generation"] != fx["generation"]
                ):
                    raise ValueError("Question identity/generation must match delivered state")
                if qid in seen_ids:
                    counts["same_question_identity_representations"] += 1
                    continue
                seen_ids.add(qid)
                counts["distinct_question_ids"] += 1
                state = decision["before_delivery"]
                if fx["intent"].startswith(("repair_", "clarify_")):
                    counts["repair_or_clarification_presentations"] += 1
                    continue
                key = (fx["intent"], fx.get("slot"), state["active_episode_id"],
                       state["pending_episode_attribute"])
                needs[key] += 1
                if needs[key] > 1:
                    counts["repeated_question_key_presentations_proxy"] += 1
                if (
                    state["active_episode_id"]
                    and fx["intent"].startswith(("episode_", "topic_"))
                    and not after_delivery["pending_episode_attribute"]
                ):
                    counts["clinical_question_without_pending_attribute_proxy"] += 1
        rows.append({
            "id": case["id"], "counts": dict(counts),
            "max_consecutive_vera_question_presentations": maximum_run,
            "max_newly_filled_slots_per_user_turn": max_fills,
            "sdk_text_processing_ms": _percentiles(samples),
            "final_state": case["turns"][-1]["state_after"],
            "required_modalities": case.get("required_modalities", ["text"]),
            "replay_configuration": case.get("replay_configuration"),
            "phone_acceptance": "NOT_RUN",
        })
    return {
        "format": "imvera.dialogue-measurements.v1",
        "provider": capture["provider"], "suite_sha256": capture["suite_sha256"],
        "runtime": capture["runtime"],
        "boundary": "SDK-only simulated presentations; not CallActor or heard delivery",
        "definitions": {
            "repeated_question_key_presentations_proxy":
                "same intent/slot/active episode/pending attribute, excluding repair IDs; "
                "not proof of unnecessary repetition",
            "clinical_question_without_pending_attribute_proxy":
                "episode/topic question with active episode but no delivered pending attribute; "
                "diagnostic requires obligation review",
            "budget_to_wellness_return_proxy":
                "resume_after_thread after followup_count>=2; not proof transition was appropriate",
            "user_question_without_answer_intent_proxy":
                "understanding has user_question but no answer_user_question intent; "
                "not semantic answer correctness",
            "sdk_text_processing_ms":
                "local understand+reduce elapsed; excludes STT/TTS/delivery/audio; not M5",
        },
        "not_measured": dict.fromkeys((
            "topic_jump_rate", "questions_per_minute", "grounded_fact_recall",
            "safety_error_rate", "human_questionnaire_feel", "listener_warmth",
            "end_of_speech_to_first_pcm_ms", "model_invocation_counts",
            "model_ram", "concurrent_call_capacity", "barge_in", "slow_speech",
        ), "NOT_RUN"),
        "cases": rows,
    }


def compare_captures(left: dict, right: dict, suite: dict, suite_sha: str) -> str:
    for capture in (left, right):
        validate_capture(capture, suite, suite_sha)
    if left["provider"]["channel"] != right["provider"]["channel"]:
        raise ValueError("Different channels: text and telephone audio are not a head-to-head")
    left_cases = {row["id"]: row for row in left["cases"]}
    right_cases = {row["id"]: row for row in right["cases"]}
    common = set(left_cases) & set(right_cases)
    total = len(suite["cases"])
    lines = [
        "# Dialogue comparison — captured text",
        "",
        f"Suite: `{suite['version']}` / `{suite_sha}`.",
        "",
        f"Comparable cases: **{len(common)}/{total}**. Missing cases remain NOT_RUN.",
        "",
        "This is a transcript comparison, not a measured superiority or warmth/MOS score.",
        "",
    ]
    for name, capture in (("A", left), ("B", right)):
        p = capture["provider"]
        lines.append(
            f"{name}: {p['name']} / `{p['version']}` / {p['channel']} / {p['captured_at']}."
        )
        lines.append(f"Evidence: {p['evidence_ref']}; runtime: `{capture.get('runtime', {})}`.")
    changed = 0
    for case in suite["cases"]:
        case_id = case["id"]
        lines.extend(["", f"## {case_id}", ""])
        if case_id not in common:
            lines.append("NOT_RUN: no matching capture from both providers.")
            continue
        a, b = left_cases[case_id], right_cases[case_id]
        if [t["assistant"] for t in a["turns"]] != [t["assistant"] for t in b["turns"]]:
            changed += 1
        for index, (ta, tb) in enumerate(zip(a["turns"], b["turns"], strict=True)):
            lines.append(f"Input {index}: {ta['user'] or '[opening]'}")
            lines.append(f"A: {' '.join(ta['assistant']) or '[no response]'}")
            lines.append(f"B: {' '.join(tb['assistant']) or '[no response]'}")
            lines.append("")
        for name, row in (("A", a), ("B", b)):
            if "outcomes" in row:
                lines.append(
                    f"{name} SDK observations: `{row['outcomes']}`; "
                    f"episodes: {len(row.get('episodes', []))}."
                )
    lines.extend(
        [
            "",
            f"Changed response sequences: {changed}/{len(common)} comparable cases.",
            "Human review of warmth, respect, accuracy and rhythm remains required.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--label", default="IMVERA")
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--decision-metadata", action="store_true")
    metrics = sub.add_parser("metrics")
    metrics.add_argument("--capture", type=Path, required=True)
    metrics.add_argument("--output", type=Path, required=True)
    load = sub.add_parser("import")
    load.add_argument("--capture", type=Path, required=True)
    load.add_argument("--output", type=Path, required=True)
    compare = sub.add_parser("compare")
    compare.add_argument("--left", type=Path, required=True)
    compare.add_argument("--right", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    suite, suite_sha = read_suite(args.suite)
    if args.command == "run":
        result = run_imvera(suite, suite_sha, args.label, decision_metadata=args.decision_metadata)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(
            f"Captured {len(result['cases'])} SDK cases; "
            f"audio/models/human warmth NOT_RUN: {args.output}"
        )
    elif args.command == "metrics":
        capture = json.loads(args.capture.read_text())
        validate_capture(capture, suite, suite_sha)
        result = measure_capture(capture)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(f"Captured decision metrics; phone/human/model acceptance NOT_RUN: {args.output}")
    elif args.command == "import":
        result = json.loads(args.capture.read_text())
        validate_capture(result, suite, suite_sha)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(
            "Validated capture inputs/metadata; "
            f"authenticity requires evidence review: {args.output}"
        )
    else:
        left, right = json.loads(args.left.read_text()), json.loads(args.right.read_text())
        args.output.write_text(compare_captures(left, right, suite, suite_sha))
        print(f"Transcript comparison written; no automated warmth ranking: {args.output}")


if __name__ == "__main__":
    main()
