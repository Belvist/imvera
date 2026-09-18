"""Live LLM interpret gate — runs when MLX LLM worker is up (product smoke)."""

import os

import httpx
import pytest

from packages.contracts.enums import FsmState
from packages.dialogue.context_builder import build_turn_context
from packages.dialogue.semantic_adapter import adapt_semantic_turn
from packages.dialogue.state import DialogueState
from services.llm.http_provider import HttpLLMProvider

LLM_URL = os.environ.get("IMVERA_LLM_URL", "http://127.0.0.1:9103").rstrip("/")


def _llm_reachable() -> bool:
    try:
        response = httpx.get(f"{LLM_URL}/health/ready", timeout=2.0)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


@pytest.mark.skipif(not _llm_reachable(), reason=f"LLM not reachable at {LLM_URL}")
@pytest.mark.asyncio
async def test_live_llm_complaint_wellness_fact() -> None:
    """Product gate: real interpret for elderly complaint utterance."""
    state = DialogueState(call_id="live-complaint", family_id="audit-family")
    state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    state.greeted = True
    state.fsm_state = FsmState.DAILY_CHECK
    state.pending_slot = "wellness"
    state.pending_question = "Расскажите, как вы себя чувствуете сейчас?"
    state.pending_question_delivered = True

    text = "Голова болит с утра"
    ctx = build_turn_context(
        state,
        turn_id=3,
        utterance_id="u-live",
        raw_text=text,
    )
    provider = HttpLLMProvider(LLM_URL, timeout_s=30.0)
    import time

    deadline = time.monotonic() + 30.0
    semantic = await provider.interpret_turn(ctx, deadline=deadline)
    interp, validated = adapt_semantic_turn(
        text,
        semantic.payload,
        state=state,
        active_question_kind="slot",
        pending_slot="wellness",
    )
    assert semantic.payload.dialogue_act in ("answer", "report", "complaint", "unclear")
    assert len(validated.payload.facts) >= 1 or interp.fact_candidates
    if validated.payload.facts:
        field = validated.payload.facts[0].field
        assert field in ("wellness", "mood", "pain")


@pytest.mark.skipif(not _llm_reachable(), reason=f"LLM not reachable at {LLM_URL}")
@pytest.mark.asyncio
async def test_live_llm_backchannel_not_consent() -> None:
    state = DialogueState(call_id="live-bc", family_id="audit-family")
    state.fsm_state = FsmState.CHECK_CONSENT
    state.pending_question = "Вы согласны получать регулярные звонки?"
    state.pending_question_delivered = True

    text = "ага"
    ctx = build_turn_context(state, turn_id=2, utterance_id="u-bc", raw_text=text)
    provider = HttpLLMProvider(LLM_URL, timeout_s=20.0)
    import time

    semantic = await provider.interpret_turn(ctx, deadline=time.monotonic() + 20.0)
    interp, _ = adapt_semantic_turn(
        text,
        semantic.payload,
        state=state,
        active_question_kind="consent",
        pending_slot=None,
    )
    assert semantic.payload.consent_answer != "yes"
    assert not interp.fills_pending_slot
