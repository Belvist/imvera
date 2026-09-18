"""Scenario execution — acoustic turn-taking only (no server events)."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from tools.blackbox_caller.audio import load_wav_u8, play_u8_on_call
from tools.blackbox_caller.config import VOICE_MANIFEST, BlackboxConfig
from tools.blackbox_caller.scenarios.catalog import BlackboxScenario
from tools.blackbox_caller.sip_client import create_sip_client


@dataclass
class UplinkTurn:
    phrase_id: str
    wav_path: str
    started_at: float
    duration_s: float
    action: str


@dataclass
class ScenarioRunResult:
    scenario_id: str
    sip_connected: bool
    rtp_rx: bool
    rtp_tx: bool
    user_turns_sent: int
    uplink_turns: list[UplinkTurn] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    timestamps: dict[str, float] = field(default_factory=dict)


def load_manifest() -> dict[str, str]:
    if not VOICE_MANIFEST.is_file():
        raise FileNotFoundError(
            f"BLACKBOX_GATE=FAIL: voice manifest missing at {VOICE_MANIFEST}. "
            "Record human WAV assets first — see tests/assets/blackbox_voice/README.md"
        )
    data = json.loads(VOICE_MANIFEST.read_text(encoding="utf-8"))
    phrases = data.get("phrases") or {}
    root = VOICE_MANIFEST.parent
    resolved: dict[str, str] = {}
    missing: list[str] = []
    for phrase_id, rel in phrases.items():
        path = root / rel
        if path.is_file():
            resolved[phrase_id] = str(path)
        else:
            missing.append(phrase_id)
    if missing:
        raise FileNotFoundError(
            "BLACKBOX_GATE=FAIL: missing human WAV assets: "
            + ", ".join(missing[:8])
            + (f" (+{len(missing)-8} more)" if len(missing) > 8 else "")
        )
    return resolved


def run_scenario(
    scenario: BlackboxScenario,
    config: BlackboxConfig,
    *,
    manifest: dict[str, str] | None = None,
) -> tuple[ScenarioRunResult, object | None, float]:
    manifest = manifest or load_manifest()
    started = time.time()
    result = ScenarioRunResult(
        scenario_id=scenario.id,
        sip_connected=False,
        rtp_rx=False,
        rtp_tx=False,
        user_turns_sent=0,
        timestamps={"started_at": started},
    )
    client: object | None = None
    try:
        client = create_sip_client(config)
        info = client.connect()
        result.sip_connected = info.answered
        if not info.answered:
            result.errors.append("SIP call not answered")
            return result, client, started

        deadline = started + config.max_call_s
        for step in scenario.steps:
            if time.time() > deadline:
                result.errors.append("call timeout")
                break
            if step.action == "wait_bot_finish":
                client.wait_bot_finish(step.wait_s or 30.0)
                continue
            if step.action in {"play_wav", "barge_in"}:
                if step.phrase_id not in manifest:
                    result.errors.append(f"unknown phrase_id {step.phrase_id}")
                    continue
                wav_path = Path(manifest[step.phrase_id])
                clip = load_wav_u8(wav_path, target_rate=config.sample_rate)
                if step.action == "barge_in":
                    if not client.wait_bot_start(min(step.wait_s or 15.0, 15.0)):
                        result.errors.append("barge_in: bot speech not detected")
                    time.sleep(config.barge_in_delay_ms / 1000.0)
                turn_started = time.time()
                play_u8_on_call(
                    client.call,
                    clip.pcm_u8,
                    frame_bytes=config.frame_bytes,
                )
                result.user_turns_sent += 1
                result.rtp_tx = True
                result.uplink_turns.append(
                    UplinkTurn(
                        phrase_id=step.phrase_id,
                        wav_path=str(wav_path),
                        started_at=turn_started,
                        duration_s=len(clip.pcm_u8) / max(1, config.sample_rate),
                        action=step.action,
                    )
                )
                continue
            result.errors.append(f"unsupported step action: {step.action}")

        downlink = client.recorder.bytes()
        result.rtp_rx = len(downlink) > config.frame_bytes * 20
        result.timestamps["ended_at"] = time.time()
    except Exception as exc:
        result.errors.append(str(exc))
    return result, client, started


def uplink_manifest_payload(result: ScenarioRunResult) -> dict[str, Any]:
    return {
        "scenario_id": result.scenario_id,
        "user_turns_sent": result.user_turns_sent,
        "turns": [asdict(t) for t in result.uplink_turns],
    }
