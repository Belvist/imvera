#!/usr/bin/env python3
"""Live gate Call A + Call B on LIVE_GATE_SHA — pyVoIP black-box, no package edits."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# RTP must use LAN IP — Docker FS cannot reach wrong interface / public IP in SDP.
os.environ.setdefault("IMVERA_LIVE_CLIENT_IP", "192.168.1.26")
os.environ.setdefault("IMVERA_LIVE_SIP_HOST", "192.168.1.26")
os.environ.setdefault("IMVERA_LIVE_MAX_CALL_S", "240")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.blackbox_caller.audio import load_wav_u8, play_u8_on_call, save_pcm_u8_wav
from tools.blackbox_caller.config import load_config
from tools.blackbox_caller.import_guard import assert_blackbox_clean
from tools.blackbox_caller.scenario_driver import load_manifest
from tools.blackbox_caller.scenarios.catalog import BlackboxScenario, ScenarioStep, generate_catalog
from tools.blackbox_caller.sip_client import PyVoIPSipClient
from tools.blackbox_caller.trace_correlation import (
    copy_server_trace,
    wait_for_trace,
)

LIVE_GATE_SHA = "82dc1334faf375e8e15857183141cda09b2afb17"
OUT_ROOT = ROOT / ".run" / "live_gate_ab"
TRACE_DIR = ROOT / ".run" / "traces"


@dataclass
class GateResult:
    gate: str
    passed: bool
    call_id: str = ""
    trace_path: str = ""
    errors: list[str] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, OSError):
        return "unknown"


def _load_trace_rows(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _engine_intents(rows: list[dict]) -> list[str]:
    out: list[str] = []
    for row in rows:
        if row.get("type") != "stage.timing":
            continue
        payload = row.get("payload") or {}
        if payload.get("stage") != "dialogue.engine_decision":
            continue
        intent = str(payload.get("intent") or "")
        if intent:
            out.append(intent)
    return out


def _stages(rows: list[dict]) -> list[str]:
    return [
        str((row.get("payload") or {}).get("stage") or "")
        for row in rows
        if row.get("type") == "stage.timing"
    ]


def _call_id_from_trace(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        cid = row.get("call_id")
        if cid:
            return str(cid)
    return path.stem


def _run_steps(
    client: PyVoIPSipClient,
    steps: list[ScenarioStep],
    manifest: dict[str, str],
    *,
    started: float,
    max_call_s: float,
) -> list[str]:
    errors: list[str] = []
    config = client.config
    deadline = started + max_call_s
    for step in steps:
        if time.time() > deadline:
            errors.append("call timeout")
            break
        if step.action == "wait_bot_finish":
            client.wait_bot_finish(step.wait_s or 30.0)
            continue
        if step.action == "wait_silence":
            silence_s = step.wait_s or 9.0
            frame = bytes([128]) * config.frame_bytes
            end = time.time() + silence_s
            while time.time() < end:
                try:
                    client.call.write_audio(frame)
                except Exception:
                    break
                time.sleep(0.02)
            continue
        if step.action in {"play_wav", "barge_in"}:
            if step.phrase_id not in manifest:
                errors.append(f"unknown phrase_id {step.phrase_id}")
                continue
            wav_path = Path(manifest[step.phrase_id])
            clip = load_wav_u8(wav_path, target_rate=config.sample_rate)
            play_u8_on_call(client.call, clip.pcm_u8, frame_bytes=config.frame_bytes)
            continue
        errors.append(f"unsupported action {step.action}")
    return errors


def _scenario_call_a() -> BlackboxScenario:
    catalog = generate_catalog()
    for scenario in catalog:
        if scenario.id == "good-clean_short-00":
            return scenario
    return catalog[0]


def _scenario_call_b() -> BlackboxScenario:
    steps = [
        ScenarioStep(action="wait_bot_finish", wait_s=45.0),
        ScenarioStep(action="play_wav", phrase_id="wellness_good_01"),
        ScenarioStep(action="wait_bot_finish", wait_s=30.0),
        ScenarioStep(action="play_wav", phrase_id="mood_neutral_01"),
        ScenarioStep(action="wait_bot_finish", wait_s=30.0),
        ScenarioStep(action="play_wav", phrase_id="sleep_short_01"),
        ScenarioStep(action="wait_bot_finish", wait_s=35.0),
        ScenarioStep(action="wait_silence", wait_s=9.0),
        ScenarioStep(action="wait_bot_finish", wait_s=35.0),
    ]
    return BlackboxScenario(
        id="live_gate_b_plans_timer_silence",
        wellness_category="good",
        family="live_gate",
        variant=0,
        tags=["live_gate", "timer"],
        steps=steps,
        expected_intents=["opening", "check_plans", "clarify_plans"],
    )


def _validate_call_a(rows: list[dict], downlink_bytes: int) -> list[str]:
    errors: list[str] = []
    intents = _engine_intents(rows)
    stages = _stages(rows)
    for required in ("summary", "goodbye_final"):
        if required not in intents:
            errors.append(f"missing engine intent {required}")
    if "end_call.started" not in stages:
        errors.append("missing stage end_call.started")
    if "call.cleanup_ok" not in stages:
        errors.append("missing stage call.cleanup_ok")
    if downlink_bytes < 80000:
        errors.append(f"downlink too small ({downlink_bytes} bytes) — caller likely heard silence")
    summary_idx = next((i for i, x in enumerate(intents) if x == "summary"), -1)
    goodbye_idx = next((i for i, x in enumerate(intents) if x == "goodbye_final"), -1)
    if summary_idx >= 0 and goodbye_idx >= 0 and goodbye_idx <= summary_idx:
        errors.append("goodbye_final before summary in engine decisions")
    tts_count = sum(1 for s in stages if s == "tts.start")
    if tts_count < 4:
        errors.append(f"expected multiple tts.start, got {tts_count}")
    return errors


def _validate_call_b(rows: list[dict], downlink_bytes: int) -> list[str]:
    errors: list[str] = []
    intents = _engine_intents(rows)
    if "check_plans" not in intents and "opening" not in intents:
        errors.append("never reached plans context")
    clarify = [i for i in intents if i.startswith("clarify_")]
    if not clarify:
        errors.append("no clarify_* engine intent after timer silence")
    if downlink_bytes < 40000:
        errors.append(f"downlink too small ({downlink_bytes} bytes)")
    post_plans_tts = False
    seen_plans = False
    for row in rows:
        if row.get("type") != "stage.timing":
            continue
        payload = row.get("payload") or {}
        stage = payload.get("stage")
        if stage == "dialogue.engine_decision":
            intent = str(payload.get("intent") or "")
            if intent == "check_plans":
                seen_plans = True
            if seen_plans and intent.startswith("clarify_"):
                post_plans_tts = True
        if seen_plans and stage == "tts.start" and post_plans_tts:
            break
    if seen_plans and not post_plans_tts:
        errors.append("clarify decision not observed after plans")
    return errors


def _run_one(
    gate: str,
    scenario: BlackboxScenario,
    manifest: dict[str, str],
    *,
    local_sip_port: int,
) -> GateResult:
    import os

    os.environ["IMVERA_LIVE_LOCAL_SIP_PORT"] = str(local_sip_port)
    config = load_config()
    result = GateResult(gate=gate, passed=False)
    started = time.time()
    out_dir = OUT_ROOT / gate
    out_dir.mkdir(parents=True, exist_ok=True)
    client: PyVoIPSipClient | None = None
    downlink = b""
    try:
        client = PyVoIPSipClient(config)
        info = client.connect()
        if not info.answered:
            result.errors.append("SIP not answered")
            return result
        step_errors = _run_steps(
            client,
            scenario.steps,
            manifest,
            started=started,
            max_call_s=config.max_call_s,
        )
        result.errors.extend(step_errors)
        downlink = client.close()
    except Exception as exc:
        result.errors.append(str(exc))
        if client is not None:
            try:
                downlink = client.close()
            except Exception:
                pass

    if downlink:
        save_pcm_u8_wav(
            downlink,
            out_dir / "caller_downlink.wav",
            sample_rate=config.sample_rate,
        )

    trace = wait_for_trace(since_ts=started, timeout_s=45.0)
    if trace is None:
        result.errors.append("no server trace found")
        return result
    copy_server_trace(trace, out_dir / "server_trace.jsonl")
    result.trace_path = str(trace)
    rows = _load_trace_rows(trace)
    result.call_id = _call_id_from_trace(trace)
    result.evidence = {
        "engine_intents": _engine_intents(rows),
        "lifecycle_stages": [s for s in _stages(rows) if s in {
            "end_call.started",
            "call.cleanup_ok",
            "CALL_CLEANUP_FAILURE",
            "tts.start",
            "dialogue.engine_decision",
        }],
        "downlink_bytes": len(downlink),
        "git_sha": _git_sha(),
    }
    (out_dir / "evidence.json").write_text(
        json.dumps(result.evidence, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if gate == "call_a":
        result.errors.extend(_validate_call_a(rows, len(downlink)))
    else:
        result.errors.extend(_validate_call_b(rows, len(downlink)))

    result.passed = not result.errors
    (out_dir / "result.json").write_text(
        json.dumps(
            {
                "gate": gate,
                "passed": result.passed,
                "call_id": result.call_id,
                "errors": result.errors,
                "evidence": result.evidence,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return result


def main() -> int:
    assert_blackbox_clean(context="live_gate_ab")
    sha = _git_sha()
    if sha != LIVE_GATE_SHA:
        print(f"LIVE_GATE_AB=FAIL: HEAD {sha} != {LIVE_GATE_SHA}", file=sys.stderr)
        return 1

    proc = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", "imvera-freeswitch"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.stdout.strip() != "true":
        print("LIVE_GATE_AB=FAIL: imvera-freeswitch not running", file=sys.stderr)
        return 1

    manifest = load_manifest()
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    print(f"LIVE_GATE_AB sha={sha}", flush=True)
    call_a = _run_one("call_a", _scenario_call_a(), manifest, local_sip_port=5088)
    print(f"Call A: {'PASS' if call_a.passed else 'FAIL'} call_id={call_a.call_id}", flush=True)
    if call_a.errors:
        for err in call_a.errors:
            print(f"  A: {err}")

    time.sleep(4.0)

    call_b = _run_one("call_b", _scenario_call_b(), manifest, local_sip_port=5089)
    print(f"Call B: {'PASS' if call_b.passed else 'FAIL'} call_id={call_b.call_id}", flush=True)
    if call_b.errors:
        for err in call_b.errors:
            print(f"  B: {err}")

    overall = call_a.passed and call_b.passed
    summary = {
        "live_gate_sha": sha,
        "call_a": {"passed": call_a.passed, "call_id": call_a.call_id, "errors": call_a.errors},
        "call_b": {"passed": call_b.passed, "call_id": call_b.call_id, "errors": call_b.errors},
        "overall": "PASS" if overall else "FAIL",
    }
    (OUT_ROOT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"LIVE_GATE_AB overall={'PASS' if overall else 'FAIL'}", flush=True)
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
