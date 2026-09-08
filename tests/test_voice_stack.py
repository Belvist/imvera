"""Voice stack unit tests — no MLX required."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from packages.contracts.enums import FsmState
from packages.contracts.semantic import Evidence, FactCandidate, SemanticPayload
from packages.dialogue.context_builder import active_question_kind
from packages.dialogue.semantic_bridge import semantic_to_user_interpretation
from packages.dialogue.state import DialogueState
from packages.telephony.ws_protocol import flush_media_command, is_media_start, parse_media_start
from packages.voice_runtime.audio import AudioEnvelope, pcm16_frame_bytes
from packages.voice_runtime.playback import PlaybackQueue, PlaybackState, split_pcm_frames


def test_media_start_parse_string_format():
    msg = {
        "event": "MEDIA_START",
        "format": "slin16",
        "optimal_frame_size": 640,
        "ptime": 20,
    }
    assert is_media_start(msg)
    fmt = parse_media_start(msg)
    assert fmt.sample_rate == 16000
    assert fmt.frame_size_bytes == 640
    assert fmt.ptime_ms == 20


def test_plain_text_media_start_parse():
    from packages.telephony.ws_protocol import parse_control_message

    raw = (
        "MEDIA_START connection_id:abc channel:WebSocket/imvera_inject "
        "format:ulaw optimal_frame_size:160 ptime:20"
    )
    msg = parse_control_message(raw)
    assert msg is not None
    assert is_media_start(msg)
    fmt = parse_media_start(msg)
    assert fmt.encoding == "ulaw"
    assert fmt.sample_rate == 8000
    assert fmt.frame_size_bytes == 160


def test_flush_media_command():
    cmd = json.loads(flush_media_command())
    assert cmd["command"] == "FLUSH_MEDIA"


def test_semantic_identity_yes_requires_evidence():
    state = DialogueState(call_id="c1", family_id="f1", fsm_state=FsmState.IDENTIFY_PERSON)
    payload = SemanticPayload(
        dialogue_act="answer",
        control="none",
        consent_answer="yes",
        consent_evidence=Evidence(start=0, end=2, quote="да"),
        answers_pending_question=True,
        needs_clarification=False,
    )
    interp = semantic_to_user_interpretation(
        "да", payload, active_question_kind=active_question_kind(state)
    )
    assert interp.confirms_identity is True


def test_semantic_identity_no_not_confirm():
    state = DialogueState(call_id="c1", family_id="f1", fsm_state=FsmState.IDENTIFY_PERSON)
    payload = SemanticPayload(
        dialogue_act="answer",
        control="none",
        consent_answer="no",
        consent_evidence=Evidence(start=0, end=3, quote="нет"),
        answers_pending_question=True,
        needs_clarification=False,
    )
    interp = semantic_to_user_interpretation(
        "нет", payload, active_question_kind=active_question_kind(state)
    )
    assert interp.declines is True
    assert interp.confirms_identity is False


def test_semantic_can_talk_with_pending_answer():
    state = DialogueState(call_id="c1", family_id="f1", fsm_state=FsmState.CHECK_CAN_TALK)
    payload = SemanticPayload(
        dialogue_act="answer",
        control="none",
        consent_answer="not_applicable",
        consent_evidence=Evidence(start=0, end=2, quote="да"),
        answers_pending_question=True,
        needs_clarification=False,
    )
    interp = semantic_to_user_interpretation(
        "да", payload, active_question_kind=active_question_kind(state)
    )
    assert interp.confirms_can_talk is True


def test_semantic_mood_not_consent():
    state = DialogueState(
        call_id="c1",
        family_id="f1",
        fsm_state=FsmState.DAILY_CHECK,
        pending_slot="mood",
    )
    payload = SemanticPayload(
        dialogue_act="answer",
        control="none",
        consent_answer="not_applicable",
        facts=(
            FactCandidate(
                field="mood",
                value="хорошо",
                subject="speaker",
                temporal_scope="today",
                negated=False,
                evidence=Evidence(start=0, end=6, quote="хорошо"),
            ),
        ),
        answers_pending_question=True,
        needs_clarification=False,
    )
    interp = semantic_to_user_interpretation(
        "хорошо", payload, active_question_kind=active_question_kind(state)
    )
    assert interp.fact_candidates
    assert interp.confirms_identity is False


@pytest.mark.asyncio
async def test_playback_queue_no_loss():
    q = PlaybackQueue("c1", buffer_limit_ms=200, sample_rate=16000, frame_ms=20)
    q.begin_phrase("g1", "p1", "hello")
    data = b"\x01\x00" * 4000
    chunk = AudioEnvelope("c1", "g1", "p1", 0, 16000, data)
    total_out = 0

    async def consumer() -> None:
        nonlocal total_out
        while total_out < len(data):
            item = q.pop_nowait()
            if item:
                total_out += len(item.pcm_s16le)
            await asyncio.sleep(0)

    task = asyncio.create_task(consumer())
    assert await q.enqueue_wait(chunk)
    assert await q.flush_carried_frames(chunk)
    q.mark_generation_done("success")
    await task
    frame_bytes = pcm16_frame_bytes(16000, 20)
    assert total_out >= len(data)
    assert total_out - len(data) < frame_bytes


@pytest.mark.asyncio
async def test_playback_zero_sent_not_completed():
    q = PlaybackQueue("c1", buffer_limit_ms=200, sample_rate=16000, frame_ms=20)
    q.begin_phrase("g1", "p1", "hello")
    q.mark_generation_done("failed")
    assert not q.playback_complete()
    q.mark_completed()
    assert q._ledger is not None
    assert q._ledger.state != PlaybackState.COMPLETED


@pytest.mark.asyncio
async def test_playback_flush_carried_frame_once() -> None:
    q = PlaybackQueue("c1", buffer_limit_ms=200, sample_rate=16000, frame_ms=20)
    q.begin_phrase("g1", "p1", "hello")
    frame = pcm16_frame_bytes(16000, 20)
    partial = b"\x01\x00" * (frame // 4)
    chunk = AudioEnvelope("c1", "g1", "p1", 0, 16000, partial)
    assert await q.enqueue_wait(chunk)
    assert q.pop_nowait() is None
    assert await q.flush_carried_frames(chunk)
    flushed = q.pop_nowait()
    assert flushed is not None
    assert len(flushed.pcm_s16le) == frame
    assert q.pop_nowait() is None


def test_playback_splits_frames() -> None:
    frame = b"\x00\x01" * (pcm16_frame_bytes(16000, 20) // 2)
    big = frame * 3
    parts = split_pcm_frames(big, 16000, 20)
    assert len(parts) == 3
    assert all(len(p) == len(frame) for p in parts)


def test_media_start_parse_slin48():
    msg = {
        "event": "MEDIA_START",
        "format": "slin48",
        "optimal_frame_size": 1920,
        "ptime": 20,
    }
    fmt = parse_media_start(msg)
    assert fmt.sample_rate == 48000
    assert fmt.frame_size_bytes == 1920
    assert fmt.encoding == "slin48"

