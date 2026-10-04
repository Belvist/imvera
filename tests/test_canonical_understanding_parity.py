"""Real Actor admission and SDK use one grounded producer, without repeated inference.

ASR/proposal delivery is controlled; no model accuracy or heard-audio claim.
"""

from __future__ import annotations

import re
import struct
from types import SimpleNamespace

import pytest

from packages.contracts.enums import AsrQuality
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.dialogue_engine.semantic import SemanticAct, SemanticTurn
from packages.dialogue_engine.semantic_kernel.kernel import interpret
from packages.dialogue_engine.state import EngineState
from packages.dialogue_engine.turn_understanding import TurnUnderstandingV2
from packages.voice_perception.post_stt_gate import TurnAdmissionDecision, TurnAdmissionVerdict
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks

pytestmark = pytest.mark.dialogue_engine


async def noop(*args, **kwargs):
    return None


def canonical(value):
    """Only per-inference IDs and measured wall-clock duration differ."""
    if isinstance(value, dict):
        return {k: canonical(v) for k, v in value.items() if k != "kernel_elapsed_ms"}
    if isinstance(value, list):
        return [canonical(v) for v in value]
    if isinstance(value, str) and re.match(r"^(sp|im|obs)-", value):
        return value.split("-", 1)[0] + "-ID"
    return value


CASES = [
    ("Самочувствие хорошее, настроение спокойное, спала хорошо, сегодня пойду гулять.", None),
    ("Голова болит со вчера, сейчас сильная боль.", None),
    ("Ой, поел нормально? Вот у меня что-то голова болит и руки ноют.", None),
    ("Внучка приезжала, хорошо посидели.", None),
    ("Чай пили, разговаривали.", "Внучка приезжала, хорошо посидели."),
    ("А вы любите музыку?", None),
    ("и что дальше", None),
    ("и что дальше", "Внучка приезжала, хорошо посидели."),
    ("Что я говорила про внучку?", "Внучка приезжала, хорошо посидели."),
    ("Я часто слушаю старые песни.", None),
    ("Почему болит голова?", None),
    ("Почему у меня болит голова?", None),
    ("Почему болит голова? А у меня сейчас спина болит.", None),
    ("Что означает фраза «у меня болит голова»?", None),
    ("Что делать, если у меня болит голова?", None),
    ("Зачем вы звоните?", None),
    ("Не хочу отвечать на этот вопрос.", None),
    ("Не беспокойте меня больше.", None),
    ("Помогите, вызовите скорую.", None),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("text,seed", CASES)
@pytest.mark.parametrize("candidate_act", [None, SemanticAct.REPAIR_REQUEST])
async def test_actor_and_sdk_have_identical_grounded_turn_and_one_kernel(
    monkeypatch, text, seed, candidate_act,
):
    import packages.dialogue_engine.mission_understanding as mission_module
    import packages.dialogue_engine.semantic_kernel.kernel as kernel_module
    import packages.dialogue_engine.semantic_nlp.candidate as candidate_module

    session = CallSession(call_id="canonical-parity", family_id="f",
                          store=InMemoryCallRecordStore())
    opening = session.start()
    engine = session._engine
    assert engine is not None and opening.speak_effect is not None
    fx = opening.speak_effect
    engine.on_playout_completed(fx.generation, fx.question_id)
    if seed:
        rich = engine.build_rich_turn(seed, utterance_id="seed")
        engine.on_user_turn("seed", seed, rich_turn=rich)
        while (effect := engine.pop_speak_effect()) is not None:
            engine.on_playout_completed(effect.generation, effect.question_id)

    candidate = (SemanticTurn(act=candidate_act, source_quote=text, confidence=0.99)
                 if candidate_act is not None else None)
    counts = {"kernel": 0, "mission": 0, "act": 0}
    original_kernel = kernel_module.interpret
    original_mission = mission_module.understand_mission

    def count_kernel(*args, **kwargs):
        counts["kernel"] += 1
        return original_kernel(*args, **kwargs)

    def count_mission(*args, **kwargs):
        counts["mission"] += 1
        return original_mission(*args, **kwargs)

    def propose(*args, **kwargs):
        counts["act"] += 1
        return candidate, candidate is not None, {"nlp_act": str(candidate_act), "used": False}

    monkeypatch.setattr(kernel_module, "interpret", count_kernel)
    monkeypatch.setattr(mission_module, "understand_mission", count_mission)
    monkeypatch.setattr(candidate_module, "nlp_candidate_turn", propose)
    before = engine.state.model_dump(mode="json")
    expected = engine.build_rich_turn(
        text, utterance_id="u-1", act_candidate=candidate,
        candidate_confident=candidate is not None,
    )
    assert engine.state.model_dump(mode="json") == before
    assert counts == {"kernel": 1, "mission": 1, "act": 0}
    counts.update(kernel=0, mission=0)

    async def stt(*args, **kwargs):
        return SimpleNamespace(text=text, asr_quality=AsrQuality.GOOD)

    events = []

    async def emit(event):
        events.append(event)

    actor = CallActor(
        call_id=session.state.call_id, family_id="f", session=session,
        stt=SimpleNamespace(transcribe_final=stt), tts=SimpleNamespace(cancel=noop),
        llm=SimpleNamespace(), media=MediaCallbacks(noop, noop, noop, emit),
    )
    monkeypatch.setattr(actor, "_deliver_session_turn", noop)
    monkeypatch.setattr(actor, "_relation_shadow_task", noop)
    captured = []
    original_handle = session.handle_user_text

    def capture(*args, **kwargs):
        captured.append(kwargs.get("rich_turn"))
        return original_handle(*args, **kwargs)

    monkeypatch.setattr(session, "handle_user_text", capture)
    try:
        await actor._handle_utterance(struct.pack("<h", 1000) * 16000, 1)
        assert captured and captured[-1] is not None
        assert canonical(captured[-1].model_dump(mode="json")) == canonical(
            expected.model_dump(mode="json"),
        )
        assert counts == {"kernel": 1, "mission": 1, "act": 1}
        if expected.user_question and not expected.goal_facts and not expected.issue_mentions:
            assert expected.dialogue_act == "question"
            assert expected.answers_pending_question is False
        if candidate is not None:
            # Runtime reports actual application independently of raw confidence.
            usage = [event.payload for event in events if "proposed" in event.payload]
            assert usage and usage[-1]["proposed"] is True
            assert usage[-1]["used"] is (expected.dialogue_act == "repair")
            assert usage[-1]["resolution_reason"]
    finally:
        await actor._shutdown_runtime_tasks()


@pytest.mark.parametrize("different", ["text", "utterance_id"])
def test_reused_kernel_cannot_cross_utterance_boundary(different):
    state = EngineState(call_id="kernel-boundary")
    result = interpret("Хорошо.", utterance_id="u-a", engine_state=state)
    with pytest.raises(ValueError, match="does not belong"):
        TurnUnderstandingV2().resolve(
            "Плохо." if different == "text" else "Хорошо.",
            utterance_id="u-b" if different == "utterance_id" else "u-a",
            engine_state=state, precomputed_kernel_result=result,
        )


@pytest.mark.parametrize("text,act,control", [
    ("Ага?", "backchannel", "none"),
    ("Повтори?", "repair", "none"),
    ("Стоп?", "answer", "stop_call"),
])
def test_complete_question_recognition_preserves_deterministic_level_zero(text, act, control):
    prepared = TurnUnderstandingV2().prepare_kernel(text, utterance_id="protected")
    assert prepared.level == 0
    assert prepared.dialogue_act == act
    assert prepared.control == control
    assert prepared.user_question is None


@pytest.mark.parametrize("text,quote", [
    ("Потом гуляли в саду.", None),
    ("Сегодня гуляла в саду.", None),
    ("Внучка завтра пойдёт в магазин.", None),
    ("Вчера ходила в магазин, а завтра пойду гулять.", "завтра пойду гулять"),
    ("Внучка приезжала, а я завтра пойду в магазин.", "я завтра пойду в магазин"),
    ("Планирую погулять.", "Планирую погулять."),
])
def test_sdk_contextual_fallback_cannot_resurrect_or_broaden_plans(text, quote):
    from packages.dialogue_engine.engine import DialogueEngine

    engine = DialogueEngine(call_id="canonical-plan-evidence")
    turn = engine.build_rich_turn(text, utterance_id="plans-u1")
    plans = [fact for fact in turn.goal_facts if fact.field == "plans"]
    if quote is None:
        assert plans == []
    else:
        assert len(plans) == 1
        assert plans[0].value == quote and plans[0].evidence.quote == quote
        assert text[plans[0].evidence.start:plans[0].evidence.end] == quote


@pytest.mark.asyncio
@pytest.mark.parametrize("verdict", [TurnAdmissionVerdict.DROP_ECHO,
                                    TurnAdmissionVerdict.HOLD_FRAGMENT])
async def test_admission_rejection_precedes_final_understanding_and_models(monkeypatch, verdict):
    import packages.dialogue_engine.mission_understanding as mission_module
    import packages.dialogue_engine.semantic_nlp.candidate as candidate_module
    import packages.voice_runtime.call_actor as actor_module

    session = CallSession(call_id="drop-before-understand", family_id="f",
                          store=InMemoryCallRecordStore())
    session.start()
    before = session._engine.state.model_dump(mode="json")
    turn_id_before = session.turn_id
    text = "Голова болит."

    async def stt(*args, **kwargs):
        return SimpleNamespace(text=text, asr_quality=AsrQuality.GOOD)

    def forbidden(*args, **kwargs):
        raise AssertionError("rejected STT must not enter the final producer or act model")

    monkeypatch.setattr(actor_module, "evaluate_post_stt_turn", lambda ctx: TurnAdmissionDecision(
        verdict=verdict, reason="controlled_admission", confidence=1.0,
    ))
    monkeypatch.setattr(TurnUnderstandingV2, "resolve", forbidden)
    monkeypatch.setattr(mission_module, "understand_mission", forbidden)
    monkeypatch.setattr(candidate_module, "nlp_candidate_turn", forbidden)
    actor = CallActor(
        call_id=session.state.call_id, family_id="f", session=session,
        stt=SimpleNamespace(transcribe_final=stt), tts=SimpleNamespace(cancel=noop),
        llm=SimpleNamespace(), media=MediaCallbacks(noop, noop, noop, noop),
    )
    try:
        await actor._handle_utterance(struct.pack("<h", 1000) * 16000, 1)
        assert session._engine.state.model_dump(mode="json") == before
        assert session.turn_id == turn_id_before
    finally:
        await actor._shutdown_runtime_tasks()
