"""Strict server-trace validation for live daily-check — primary E2E oracle."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_OPENING_INTENTS = frozenset({"opening", "opening_wellness"})
_SLOT_INTENTS = ("wellness", "mood", "sleep", "plans")
_CHECK_INTENTS = ("check_mood", "check_sleep", "check_plans")
_CLOSING_INTENTS = ("summary", "goodbye_confirm", "goodbye_final")
_LIFECYCLE_OK = frozenset({"end_call.started", "call.cleanup_ok"})


@dataclass
class TraceTimelineEvent:
    ts: str
    kind: str
    detail: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceValidationResult:
    passed: bool
    call_id: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    engine_intents: list[str] = field(default_factory=list)
    stages: list[str] = field(default_factory=list)
    stt_texts: list[str] = field(default_factory=list)
    timeline: list[TraceTimelineEvent] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "call_id": self.call_id,
            "errors": self.errors,
            "warnings": self.warnings,
            "engine_intents": self.engine_intents,
            "stages": self.stages,
            "stt_texts": self.stt_texts,
            "timeline": [
                {"ts": e.ts, "kind": e.kind, "detail": e.detail, "payload": e.payload}
                for e in self.timeline
            ],
            "metrics": self.metrics,
        }


def load_trace_rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("payload") or {}


def extract_engine_intents(rows: list[dict[str, Any]]) -> list[str]:
    intents: list[str] = []
    for row in rows:
        if row.get("type") != "stage.timing":
            continue
        payload = _payload(row)
        if payload.get("stage") != "dialogue.engine_decision":
            continue
        intent = str(payload.get("intent") or "")
        if intent:
            intents.append(intent)
    return intents


def extract_stages(rows: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for row in rows:
        if row.get("type") != "stage.timing":
            continue
        stage = str(_payload(row).get("stage") or "")
        if stage:
            out.append(stage)
    return out


def build_timeline(rows: list[dict[str, Any]]) -> list[TraceTimelineEvent]:
    events: list[TraceTimelineEvent] = []
    for row in rows:
        ts = str(row.get("ts") or "")
        typ = str(row.get("type") or "")
        payload = _payload(row)
        if typ == "stage.timing":
            stage = str(payload.get("stage") or "")
            if not stage:
                continue
            detail = stage
            if stage == "dialogue.engine_decision":
                detail = f"engine:{payload.get('intent')}"
            elif stage == "stt.final":
                detail = f"stt:{payload.get('text', '')[:48]}"
            events.append(TraceTimelineEvent(ts=ts, kind="stage", detail=detail, payload=payload))
        elif typ == "stt.final":
            events.append(
                TraceTimelineEvent(
                    ts=ts,
                    kind="stt",
                    detail=str(payload.get("text") or "")[:80],
                    payload=payload,
                )
            )
        elif typ in {"playback.completed", "CALL_ENDED"}:
            events.append(TraceTimelineEvent(ts=ts, kind=typ, detail=typ, payload=payload))
    return events


def scenario_requires_full_goodbye(steps: list[Any]) -> bool:
    goodbye_phrases = 0
    for step in steps:
        action = getattr(step, "action", None) or (
            step.get("action") if isinstance(step, dict) else None
        )
        phrase = getattr(step, "phrase_id", None) or (
            step.get("phrase_id") if isinstance(step, dict) else None
        )
        if action == "play_wav" and phrase in {"goodbye_01", "goodbye_confirm_01"}:
            goodbye_phrases += 1
    return goodbye_phrases >= 1


def validate_full_daily_check_trace(
    rows: list[dict[str, Any]],
    *,
    call_id: str = "",
    downlink_bytes: int = 0,
    user_turns_sent: int = 0,
    require_full_goodbye: bool = True,
    min_downlink_bytes: int = 80_000,
    family: str = "",
) -> TraceValidationResult:
    """Validate server trace for greeting → slots → summary → goodbye → cleanup."""
    result = TraceValidationResult(
        passed=True,
        call_id=call_id or str(rows[0].get("call_id") if rows else ""),
    )
    if not rows:
        result.passed = False
        result.errors.append("empty server trace")
        return result

    intents = extract_engine_intents(rows)
    stages = extract_stages(rows)
    stt_texts = [
        str(_payload(row).get("text") or "")
        for row in rows
        if row.get("type") == "stage.timing" and _payload(row).get("stage") == "stt.final"
    ]
    if not stt_texts:
        stt_texts = [
            str(_payload(row).get("text") or "") for row in rows if row.get("type") == "stt.final"
        ]

    result.engine_intents = intents
    result.stages = stages
    result.stt_texts = [t for t in stt_texts if t.strip()]
    result.timeline = build_timeline(rows)

    opening_count = sum(1 for i in intents if i in _OPENING_INTENTS)
    planner_legacy = sum(
        1
        for row in rows
        if row.get("type") == "stage.timing"
        and _payload(row).get("stage") == "dialogue.planner_decision"
        and not _payload(row).get("skip_planner", True)
    )

    result.metrics = {
        "opening_count": opening_count,
        "planner_legacy_events": planner_legacy,
        "stt_final_count": len(result.stt_texts),
        "tts_start_count": sum(1 for s in stages if s == "tts.start"),
        "user_turns_sent": user_turns_sent,
        "downlink_bytes": downlink_bytes,
        "family": family,
    }

    if planner_legacy > 0:
        result.errors.append(
            f"planner_legacy_events={planner_legacy} (expected DialogueEngine only)"
        )

    if opening_count != 1:
        result.errors.append(f"opening_count={opening_count} expected 1")

    if downlink_bytes < min_downlink_bytes:
        result.errors.append(
            f"downlink too small ({downlink_bytes} bytes < {min_downlink_bytes})"
            " — caller likely heard silence"
        )

    if user_turns_sent > 0 and len(result.stt_texts) < max(1, user_turns_sent // 2):
        result.warnings.append(
            f"stt_final_count={len(result.stt_texts)} low vs user_turns_sent={user_turns_sent}"
        )

    if require_full_goodbye:
        if not any(i in _OPENING_INTENTS for i in intents):
            result.errors.append("missing opening/opening_wellness engine intent")

        ladder = family in {"clean_short", "decline"} or "coverage_ladder" in family
        if family == "decline":
            # Layer B decline: opening + close, no pain-site probe in engine path.
            if any("pain" in i or i == "probe_concern" for i in intents):
                result.errors.append(f"decline path hit probe intent: {intents}")
            if "goodbye_final" not in intents and "end_call" not in intents:
                result.errors.append("decline path missing goodbye_final/end_call")
        elif ladder:
            for check in (
                "background_nutrition",
                "background_medication",
                "background_mood",
                "background_sleep",
            ):
                if check not in intents:
                    result.warnings.append(f"ladder missing engine intent {check}")
            if "goodbye_final" not in intents and "end_call" not in intents:
                result.errors.append("missing goodbye_final or end_call")
        else:
            for check in _CHECK_INTENTS:
                if check not in intents and family != "multi_slot":
                    result.errors.append(f"missing engine intent {check}")

            if "summary" not in intents:
                result.errors.append("missing engine intent summary")

            if "goodbye_confirm" not in intents and "goodbye_final" not in intents:
                result.errors.append("missing goodbye_confirm or goodbye_final")

            if "goodbye_final" not in intents:
                result.errors.append("missing engine intent goodbye_final")

            summary_idx = next((i for i, x in enumerate(intents) if x == "summary"), -1)
            goodbye_idx = next((i for i, x in enumerate(intents) if x == "goodbye_final"), -1)
            if summary_idx >= 0 and goodbye_idx >= 0 and goodbye_idx < summary_idx:
                result.errors.append("goodbye_final before summary in engine decisions")

        for required_stage in ("end_call.started", "call.cleanup_ok"):
            if required_stage not in stages and family != "decline":
                result.errors.append(f"missing lifecycle stage {required_stage}")

        tts_count = sum(1 for s in stages if s == "tts.start")
        min_tts = 2 if family == "decline" else 4
        if tts_count < min_tts:
            result.errors.append(f"expected multiple tts.start, got {tts_count}")

    if "CALL_CLEANUP_FAILURE" in stages:
        result.errors.append("CALL_CLEANUP_FAILURE in trace")

    result.passed = not result.errors
    return result


def validate_trace_file(
    path: Path,
    *,
    downlink_bytes: int = 0,
    user_turns_sent: int = 0,
    require_full_goodbye: bool = True,
    family: str = "",
) -> TraceValidationResult:
    rows = load_trace_rows(path)
    call_id = path.stem
    for row in rows:
        if row.get("call_id"):
            call_id = str(row["call_id"])
            break
    return validate_full_daily_check_trace(
        rows,
        call_id=call_id,
        downlink_bytes=downlink_bytes,
        user_turns_sent=user_turns_sent,
        require_full_goodbye=require_full_goodbye,
        family=family,
    )
