"""Live SIP daily-check debug runner — real calls, strict trace validation, forensic bundle."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from tools.blackbox_caller.config import load_config
from tools.blackbox_caller.evidence import anti_cheating_from_config, write_json
from tools.blackbox_caller.import_guard import assert_blackbox_clean
from tools.blackbox_caller.scenario_driver import (
    load_manifest,
    run_scenario,
    uplink_manifest_payload,
)
from tools.blackbox_caller.scenarios.catalog import BlackboxScenario, generate_catalog
from tools.blackbox_caller.trace_correlation import copy_server_trace, wait_for_trace
from tools.voice_lab.live_trace_validator import (
    scenario_requires_full_goodbye,
    validate_full_daily_check_trace,
)

ROOT = Path(__file__).resolve().parents[2]
DEBUG_ROOT = ROOT / ".run" / "live_debug"


@dataclass
class LiveDebugCallResult:
    call_index: int
    scenario_id: str
    passed: bool
    call_id: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    trace_path: str = ""
    evidence_dir: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_index": self.call_index,
            "scenario_id": self.scenario_id,
            "passed": self.passed,
            "call_id": self.call_id,
            "errors": self.errors,
            "warnings": self.warnings,
            "trace_path": self.trace_path,
            "evidence_dir": self.evidence_dir,
        }


@dataclass
class LiveDebugSummary:
    run_id: str
    calls_attempted: int = 0
    calls_passed: int = 0
    calls_failed: int = 0
    stop_on_fail: bool = True
    passed: bool = False
    failures: list[dict[str, Any]] = field(default_factory=list)
    git_sha: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "calls_attempted": self.calls_attempted,
            "calls_passed": self.calls_passed,
            "calls_failed": self.calls_failed,
            "stop_on_fail": self.stop_on_fail,
            "passed": self.passed,
            "failures": self.failures,
            "git_sha": self.git_sha,
            "layer": "live_sip_full_daily_check",
            "note": "Primary pass/fail = server trace validator (not external ASR alone)",
        }


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, OSError):
        return "unknown"


def _require_freeswitch() -> None:
    import os

    if os.environ.get("IMVERA_INTERNAL_DOCKER_SMOKE", "").strip().lower() in {"1", "true", "yes"}:
        return
    proc = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", "imvera-freeswitch"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.stdout.strip() != "true":
        raise RuntimeError(
            "LIVE_DEBUG=FAIL: imvera-freeswitch not running.\n"
            "  make freeswitch-zoiper-voice-up\n"
            "  make freeswitch-zoiper-info   # LAN IP for RTP"
        )


def _select_scenarios(
    count: int,
    *,
    profile: str,
    scenario_id: str | None,
) -> list[BlackboxScenario]:
    catalog = generate_catalog()
    if scenario_id:
        for sc in catalog:
            if sc.id == scenario_id:
                return [sc]
        raise ValueError(f"unknown scenario_id: {scenario_id}")

    if profile == "full":
        # Families that play through goodbye (exclude backchannel-only partial paths).
        allowed = {
            "clean_short",
            "clean_long",
            "colloquial",
            "paraphrase",
            "repair_allo",
            "delayed_answer",
            "silence_once",
            "unclear_once",
            "self_correction",
            "full_mixed",
        }
        filtered = [s for s in catalog if s.family in allowed]
        return filtered[:count]

    if count >= len(catalog):
        return catalog
    return catalog[:count]


def _write_debug_report(
    path: Path,
    *,
    scenario: BlackboxScenario,
    validation: dict[str, Any],
    forensic: dict[str, Any] | None,
    sip_result: dict[str, Any],
) -> None:
    lines = [
        f"# Live debug report — {scenario.id}",
        "",
        "## Verdict",
        f"- **passed:** {validation.get('passed')}",
        "",
        "## Errors",
    ]
    for err in validation.get("errors") or []:
        lines.append(f"- {err}")
    if validation.get("warnings"):
        lines.extend(["", "## Warnings"])
        for warn in validation["warnings"]:
            lines.append(f"- {warn}")

    lines.extend(["", "## Engine intents (order)"])
    for intent in validation.get("engine_intents") or []:
        lines.append(f"- `{intent}`")

    lines.extend(["", "## STT finals (server)"])
    for text in validation.get("stt_texts") or []:
        lines.append(f"- {text!r}")

    if forensic:
        lines.extend(["", "## Forensic turns"])
        for turn in forensic.get("turns") or []:
            lines.append(
                f"- `{turn.get('utterance_id')}` "
                f"verdict={turn.get('verdict')} "
                f"path={turn.get('interpret_path')} "
                f"stt={turn.get('stt_text')!r}"
            )

    lines.extend(["", "## SIP uplink"])
    lines.append(f"- user_turns_sent: {sip_result.get('user_turns_sent')}")
    lines.append(f"- rtp_rx: {sip_result.get('rtp_rx')}")
    lines.append(f"- rtp_tx: {sip_result.get('rtp_tx')}")

    lines.extend(["", "## Timeline (server)"])
    for ev in (validation.get("timeline") or [])[-40:]:
        lines.append(f"- `{ev.get('ts')}` {ev.get('detail')}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_live_debug(
    *,
    call_count: int = 1,
    run_id: str | None = None,
    profile: str = "full",
    scenario_id: str | None = None,
    stop_on_fail: bool = True,
) -> LiveDebugSummary:
    """Real SIP calls with strict server-trace validation and per-call debug bundle."""
    assert_blackbox_clean(context="live_debug_runner")
    config = load_config()
    _require_freeswitch()
    manifest = load_manifest()

    rid = run_id or time.strftime("%Y%m%d-%H%M%S")
    run_dir = DEBUG_ROOT / rid
    run_dir.mkdir(parents=True, exist_ok=True)

    summary = LiveDebugSummary(
        run_id=rid,
        stop_on_fail=stop_on_fail,
        git_sha=_git_sha(),
    )
    scenarios = _select_scenarios(call_count, profile=profile, scenario_id=scenario_id)

    write_json(
        run_dir / "run_config.json",
        {
            "call_count": call_count,
            "profile": profile,
            "scenario_id": scenario_id,
            "stop_on_fail": stop_on_fail,
            "git_sha": summary.git_sha,
            "anti_cheating": asdict(anti_cheating_from_config(config, import_guard_passed=True)),
        },
    )

    for idx, scenario in enumerate(scenarios, start=1):
        call_dir = run_dir / f"call-{idx:03d}"
        call_dir.mkdir(parents=True, exist_ok=True)
        write_json(call_dir / "scenario.json", scenario.to_dict())

        call_result = LiveDebugCallResult(
            call_index=idx,
            scenario_id=scenario.id,
            passed=False,
            evidence_dir=str(call_dir),
        )

        call_config = replace(
            config,
            local_sip_port=config.local_sip_port + (idx - 1) * 2,
            rtp_port_low=config.rtp_port_low + (idx - 1) * 20,
            rtp_port_high=config.rtp_port_high + (idx - 1) * 20,
        )

        run_result, client, started = run_scenario(scenario, call_config, manifest=manifest)
        summary.calls_attempted += 1
        downlink = b""

        try:
            if client is not None:
                downlink = client.close()
                if downlink:
                    from tools.blackbox_caller.audio import save_pcm_u8_wav

                    save_pcm_u8_wav(
                        downlink,
                        call_dir / "caller_downlink.wav",
                        sample_rate=config.sample_rate,
                    )
        except Exception as exc:
            call_result.errors.append(f"close: {exc}")

        write_json(call_dir / "uplink_manifest.json", uplink_manifest_payload(run_result))
        write_json(
            call_dir / "sip_result.json",
            {
                "scenario_id": run_result.scenario_id,
                "sip_connected": run_result.sip_connected,
                "rtp_rx": run_result.rtp_rx,
                "rtp_tx": run_result.rtp_tx,
                "user_turns_sent": run_result.user_turns_sent,
                "errors": run_result.errors,
            },
        )

        if not run_result.sip_connected:
            call_result.errors.append("SIP not answered")
        if not run_result.rtp_tx:
            call_result.errors.append("no RTP uplink")
        if not run_result.rtp_rx and downlink:
            call_result.errors.append("no RTP downlink recorded")

        trace = wait_for_trace(since_ts=started, timeout_s=60.0)
        validation_dict: dict[str, Any] = {"passed": False, "errors": ["no server trace"]}
        forensic_dict: dict[str, Any] | None = None

        if trace is None:
            call_result.errors.append("no server trace within 60s")
        else:
            copy_server_trace(trace, call_dir / "server_trace.jsonl")
            call_result.trace_path = str(trace)
            rows = [
                json.loads(line)
                for line in trace.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            for row in rows:
                if row.get("call_id"):
                    call_result.call_id = str(row["call_id"])
                    break

            require_goodbye = scenario_requires_full_goodbye(scenario.steps)
            validation = validate_full_daily_check_trace(
                rows,
                call_id=call_result.call_id,
                downlink_bytes=len(downlink),
                user_turns_sent=run_result.user_turns_sent,
                require_full_goodbye=require_goodbye,
                family=scenario.family,
            )
            validation_dict = validation.to_dict()
            call_result.errors.extend(validation.errors)
            call_result.warnings.extend(validation.warnings)

            try:
                from tools.voice_lab.forensic_gate import _load_manifest, _parse_trace

                manifest_path = (
                    ROOT / "tools" / "voice_lab" / "fixtures" / "stt_phone" / "manifest.jsonl"
                )
                manifest_map = _load_manifest(manifest_path)
                turns = _parse_trace(trace, manifest_map)
                forensic_dict = {
                    "call_id": call_result.call_id,
                    "trace": str(trace),
                    "turns": [t.__dict__ for t in turns],
                }
                write_json(call_dir / "forensic.json", forensic_dict)
                for turn in turns:
                    if turn.verdict in {"CAPTURE_ECHO", "STT_ERROR", "INTERPRETER_SLOW_PATH"}:
                        call_result.errors.append(f"forensic {turn.utterance_id}: {turn.verdict}")
            except Exception as exc:
                call_result.warnings.append(f"forensic skipped: {exc}")

        write_json(call_dir / "trace_validation.json", validation_dict)

        sip_payload = {
            "sip_connected": run_result.sip_connected,
            "rtp_rx": run_result.rtp_rx or len(downlink) > 0,
            "rtp_tx": run_result.rtp_tx,
            "user_turns_sent": run_result.user_turns_sent,
            "errors": run_result.errors,
        }
        _write_debug_report(
            call_dir / "DEBUG_REPORT.md",
            scenario=scenario,
            validation=validation_dict,
            forensic=forensic_dict,
            sip_result=sip_payload,
        )

        call_result.passed = not call_result.errors
        write_json(call_dir / "result.json", call_result.to_dict())

        if call_result.passed:
            summary.calls_passed += 1
        else:
            summary.calls_failed += 1
            summary.failures.append(call_result.to_dict())
            if stop_on_fail:
                break

        time.sleep(3.0)

    summary.passed = summary.calls_failed == 0 and summary.calls_passed == summary.calls_attempted
    write_json(run_dir / "summary.json", summary.to_dict())
    return summary
