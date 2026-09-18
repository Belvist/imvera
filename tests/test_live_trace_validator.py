"""Unit tests for live trace validator (offline — no SIP)."""

from __future__ import annotations

from tools.voice_lab.live_trace_validator import validate_full_daily_check_trace


def _row(ts: str, stage: str, **payload: object) -> dict:
    return {
        "ts": ts,
        "call_id": "fs-test",
        "type": "stage.timing",
        "payload": {"stage": stage, **payload},
    }


def _full_passing_trace() -> list[dict]:
    intents = [
        "opening_wellness",
        "check_mood",
        "check_sleep",
        "check_plans",
        "summary",
        "goodbye_confirm",
        "goodbye_final",
    ]
    rows: list[dict] = []
    for i, intent in enumerate(intents):
        rows.append(_row(f"2026-09-08T18:00:{i:02d}Z", "dialogue.engine_decision", intent=intent))
        rows.append(_row(f"2026-09-08T18:00:{i:02d}Z", "tts.start"))
    rows.append(_row("2026-09-08T18:00:10Z", "stt.final", text="хорошо"))
    rows.append(_row("2026-09-08T18:00:20Z", "end_call.started"))
    rows.append(_row("2026-09-08T18:00:21Z", "call.cleanup_ok"))
    return rows


def test_full_daily_check_trace_passes() -> None:
    result = validate_full_daily_check_trace(
        _full_passing_trace(),
        downlink_bytes=120_000,
        user_turns_sent=6,
        require_full_goodbye=True,
    )
    assert result.passed, result.errors


def test_missing_goodbye_fails() -> None:
    rows = _full_passing_trace()
    rows = [r for r in rows if r["payload"].get("intent") != "goodbye_final"]
    result = validate_full_daily_check_trace(
        rows, downlink_bytes=120_000, require_full_goodbye=True
    )
    assert not result.passed
    assert any("goodbye_final" in e for e in result.errors)


def test_planner_legacy_fails() -> None:
    rows = _full_passing_trace()
    rows.insert(
        1,
        _row(
            "2026-09-08T18:00:00Z",
            "dialogue.planner_decision",
            intent="check_wellness",
            skip_planner=False,
        ),
    )
    result = validate_full_daily_check_trace(
        rows, downlink_bytes=120_000, require_full_goodbye=True
    )
    assert not result.passed
    assert any("planner_legacy" in e for e in result.errors)
