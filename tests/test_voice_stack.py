"""Voice stack unit tests — no MLX required."""

from __future__ import annotations

import json

import httpx

from packages.dialogue.context_builder import active_question_kind
from packages.dialogue.semantic_bridge import semantic_to_user_interpretation
from packages.dialogue.state import DialogueState
from packages.contracts.enums import FsmState
from packages.contracts.semantic import Evidence, SemanticPayload
from packages.telephony.asterisk import _json_or_empty
from packages.telephony.ws_protocol import flush_media_command, parse_media_start
from packages.voice_runtime.playback import PlaybackQueue, split_pcm_frames
from packages.voice_runtime.audio import AudioEnvelope, pcm16_frame_bytes


def test_json_or_empty_on_204():
    response = httpx.Response(204, request=httpx.Request("POST", "http://test"))
    assert _json_or_empty(response) == {}


def test_media_start_parse():
    fmt = parse_media_start(
        {
            "type": "MEDIA_START",
            "format": {"sample_rate": 16000, "encoding": "slin16"},
            "optimal_frame_size": 320,
        }
    )
    assert fmt.sample_rate == 16000
    assert fmt.frame_size_bytes == 320


def test_flush_media_command():
    cmd = json.loads(flush_media_command())
    assert cmd["type"] == "FLUSH_MEDIA"


def test_semantic_identity_yes():
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
    assert interp.sets_consent is None


def test_semantic_mood_not_consent():
    state = DialogueState(
        call_id="c1",
        family_id="f1",
        fsm_state=FsmState.DAILY_CHECK,
        pending_slot="mood",
    )
    from packages.contracts.semantic import FactCandidate

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


def test_tts_done_line_skipped():
    line = '{"done": true}'
    data = json.loads(line)
    assert data.get("done") is True
    assert "pcm_b64" not in data


def test_playback_splits_frames():
    frame = b"\x00\x01" * (pcm16_frame_bytes(16000, 20) // 2)
    big = frame * 3
    parts = split_pcm_frames(big, 16000, 20)
    assert len(parts) == 3
    assert all(len(p) == len(frame) for p in parts)


def test_playback_queue_consumer():
    q = PlaybackQueue("c1", buffer_limit_ms=800, sample_rate=16000)
    q.begin_phrase("g1", "p1", "hello")
    chunk = AudioEnvelope("c1", "g1", "p1", 0, 16000, b"\x00" * 640)
    assert q.enqueue(chunk)
    popped = q.pop()
    assert popped is not None
    assert q._ledger.sent_samples == 320
