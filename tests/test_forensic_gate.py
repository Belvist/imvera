"""Tests for voice lab forensic gate."""

from __future__ import annotations

import json
from pathlib import Path

from packages.voice_runtime.forensic import (
    classify_turn,
    is_text_echo_of_bot,
    text_echo_similarity,
)
from tools.voice_lab.forensic_gate import analyze_call


def test_text_echo_similarity_detects_vera_question_bleed() -> None:
    bot = "Как у вас настроение — хотя бы коротко?"
    stt = "Какое настроение, плохо себя чувствуешь?"
    score = text_echo_similarity(stt, bot)
    assert score >= 0.4
    assert is_text_echo_of_bot(stt, bot) is True


def test_is_text_echo_rejects_plans_question_repeat() -> None:
    bot = "Какие у вас планы на сегодня — в двух словах?"
    stt = "Каких планов на сегодня?"
    assert is_text_echo_of_bot(stt, bot) is True


def test_is_text_echo_keeps_real_mood_answer() -> None:
    bot = "А какое у вас сегодня настроение?"
    stt = "Плохое настроение. Говорю, самочувствие плохое."
    assert is_text_echo_of_bot(stt, bot) is False


def test_polarity_contradictory_wellness_is_negative() -> None:
    from packages.dialogue_engine.fast_interpreter import _detect_polarity
    from packages.dialogue_engine.questions import wellness_ack

    text = "Хорошо чувствую себя, но состояние не очень."
    assert _detect_polarity(text) == "negative"
    assert wellness_ack(value=text) == "Мне жаль это слышать."


def test_classify_stt_error_when_expected_differs(tmp_path: Path) -> None:
    verdict = classify_turn(
        echo_similarity=0.2,
        echo_score_max=0.55,
        interpret_path="llm",
        interpret_latency_ms=6000,
        stt_text="какое настроение плохо",
        expected_text="плохое настроение",
    )
    assert verdict == "STT_ERROR"


def test_classify_capture_echo_on_high_similarity() -> None:
    verdict = classify_turn(
        echo_similarity=0.8,
        echo_score_max=0.55,
        interpret_path="llm",
        interpret_latency_ms=100,
        stt_text="как у вас настроение",
        expected_text=None,
    )
    assert verdict == "CAPTURE_ECHO"


def test_forensic_gate_parses_legacy_trace(tmp_path: Path) -> None:
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()
    call_id = "fs-test"
    rows = [
        {
            "ts": "2026-09-08T18:00:00+00:00",
            "call_id": call_id,
            "type": "playback.completed",
            "payload": {},
        },
        {
            "ts": "2026-09-08T18:00:01+00:00",
            "call_id": call_id,
            "type": "stage.timing",
            "payload": {"stage": "listen.enabled"},
        },
        {
            "ts": "2026-09-08T18:00:02+00:00",
            "call_id": call_id,
            "type": "stage.timing",
            "payload": {"stage": "audio.speech_started"},
        },
        {
            "ts": "2026-09-08T18:00:03+00:00",
            "call_id": call_id,
            "type": "stage.timing",
            "payload": {"stage": "audio.speech_ended", "duration_ms": 1000},
        },
        {
            "ts": "2026-09-08T18:00:03+00:00",
            "call_id": call_id,
            "type": "renderer.phrase_ready",
            "payload": {"text": "Какое настроение?"},
        },
        {
            "ts": "2026-09-08T18:00:04+00:00",
            "call_id": call_id,
            "type": "stage.timing",
            "payload": {
                "stage": "stt.request",
                "utterance_id": "u-1",
                "pcm_rms": 300.0,
                "duration_ms": 1000,
                "pending_slot": "mood",
            },
        },
        {
            "ts": "2026-09-08T18:00:05+00:00",
            "call_id": call_id,
            "type": "stage.timing",
            "payload": {
                "stage": "stt.result",
                "utterance_id": "u-1",
                "text": "плохое настроение",
                "stt_elapsed_ms": 500,
            },
        },
        {
            "ts": "2026-09-08T18:00:05+00:00",
            "call_id": call_id,
            "type": "stage.timing",
            "payload": {
                "stage": "interpret.fast_path",
                "utterance_id": "u-1",
            },
        },
        {
            "ts": "2026-09-08T18:00:05+00:00",
            "call_id": call_id,
            "type": "stage.timing",
            "payload": {
                "stage": "interpret.ready",
                "utterance_id": "u-1",
                "elapsed_ms": 520,
            },
        },
    ]
    (trace_dir / f"{call_id}.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows),
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        json.dumps(
            {
                "call_id": call_id,
                "utterance_id": "u-1",
                "expected_text": "плохое настроение",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    import tools.voice_lab.forensic_gate as gate

    gate.TRACE_DIR = trace_dir
    report = analyze_call(call_id, manifest_path=manifest)
    assert report["turns"][0]["interpret_path"] == "fast_contextual"
    assert report["turns"][0]["verdict"] == "FAST_PATH"
