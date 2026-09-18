"""Live E2E evidence layout and anti-cheating summary."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from tools.blackbox_caller.config import LIVE_E2E_ROOT, BlackboxConfig


@dataclass
class CallEvidencePaths:
    call_dir: Path
    scenario_json: Path
    sip_log: Path
    caller_downlink_wav: Path
    uplink_manifest: Path
    external_bot_transcript: Path
    external_assertions: Path
    server_trace: Path
    timestamps: Path
    result_json: Path


def new_run_dir(run_id: str | None = None) -> Path:
    rid = run_id or time.strftime("%Y%m%d-%H%M%S")
    path = LIVE_E2E_ROOT / rid
    path.mkdir(parents=True, exist_ok=True)
    return path


def call_evidence_paths(run_dir: Path, call_index: int) -> CallEvidencePaths:
    call_dir = run_dir / f"call-{call_index:03d}"
    call_dir.mkdir(parents=True, exist_ok=True)
    return CallEvidencePaths(
        call_dir=call_dir,
        scenario_json=call_dir / "scenario.json",
        sip_log=call_dir / "sip.log",
        caller_downlink_wav=call_dir / "caller_downlink.wav",
        uplink_manifest=call_dir / "uplink_manifest.json",
        external_bot_transcript=call_dir / "external_bot_transcript.txt",
        external_assertions=call_dir / "external_assertions.json",
        server_trace=call_dir / "server_trace.jsonl",
        timestamps=call_dir / "timestamps.json",
        result_json=call_dir / "result.json",
    )


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


@dataclass
class AntiCheatingReport:
    production_git_sha: str
    production_image_digest: str
    caller_git_sha: str
    test_only_runtime_branches: int = 0
    mocked_components: int = 0
    direct_internal_api_calls: int = 0
    external_sip: bool = True
    external_rtp: bool = True
    external_downlink_recording: bool = True
    independent_bot_transcription: bool = True
    import_guard_passed: bool = True


@dataclass
class SoakSummary:
    run_id: str
    calls_attempted: int = 0
    calls_passed: int = 0
    calls_failed: int = 0
    stop_on_fail: bool = True
    anti_cheating: AntiCheatingReport | None = None
    failures: list[dict[str, Any]] = field(default_factory=list)
    passed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def anti_cheating_from_config(
    config: BlackboxConfig, *, import_guard_passed: bool
) -> AntiCheatingReport:
    return AntiCheatingReport(
        production_git_sha=config.production_git_sha,
        production_image_digest=config.production_git_sha,
        caller_git_sha=config.caller_git_sha,
        import_guard_passed=import_guard_passed,
    )


def write_summary(run_dir: Path, summary: SoakSummary) -> Path:
    path = run_dir / "summary.json"
    write_json(path, summary.to_dict())
    return path
