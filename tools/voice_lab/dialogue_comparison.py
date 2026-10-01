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
from datetime import UTC, datetime
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


def run_imvera(suite: dict, suite_sha: str, label: str) -> dict:
    from packages.dialogue_engine.engine import DialogueEngine
    from packages.dialogue_engine.mission import CallMission
    from packages.dialogue_engine.mission_result import build_call_outcomes, build_mission_result

    os.environ["IMVERA_SPEECH_DAY"] = suite["speech_day"]
    os.environ["IMVERA_SPEECH_HOUR"] = suite["speech_hour"]
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip())

    def drain(engine: DialogueEngine) -> tuple[list[str], list[str]]:
        texts, intents = [], []
        while (effect := engine.pop_speak_effect()) is not None:
            texts.append(effect.text)
            intents.append(effect.intent)
            engine.on_playout_completed(effect.generation, effect.question_id)
        return texts, intents

    cases = []
    for case in suite["cases"]:
        mission_data = suite["missions"].get(case["mission"])
        mission = CallMission.model_validate(mission_data) if mission_data else None
        engine = DialogueEngine(
            call_id=f"compare-{case['id']}",
            mission=mission,
            elder_display_name=suite["elder_display_name"],
        )
        engine.state.mandatory_background_goals = mission is None
        engine.start()
        texts, intents = drain(engine)
        turns = [{"user": None, "assistant": texts, "intents": intents}]
        for index, text in enumerate(case["inputs"]):
            uid = f"u{index + 1}"
            started = time.perf_counter()
            rich = engine.build_rich_turn(text, utterance_id=uid)
            engine.on_user_turn(uid, text, rich_turn=rich)
            elapsed = (time.perf_counter() - started) * 1000
            texts, intents = drain(engine)
            turns.append(
                {
                    "user": text,
                    "assistant": texts,
                    "intents": intents,
                    "text_processing_ms": round(elapsed, 3),
                }
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
    validate_capture(result, suite, suite_sha)
    return result


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
        result = run_imvera(suite, suite_sha, args.label)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(
            f"Captured {len(result['cases'])} SDK cases; "
            f"audio/models/human warmth NOT_RUN: {args.output}"
        )
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
