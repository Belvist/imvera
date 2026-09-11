"""Production completion acceptance — PR #14 correction pass regressions."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from packages.contracts.enums import AsrQuality, FsmState
from packages.contracts.mission_result import MissionResultSnapshot
from packages.contracts.semantic import (
    GoalAnswerSemantic,
    MissionContextSnapshot,
    SemanticPayload,
    TurnContext,
)
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.mission import CallMission, GoalAnswerCandidate, GoalDefinition
from packages.dialogue_engine.mission_result import build_call_outcomes, build_mission_result
from packages.dialogue_engine.runtime import llm_interpret_enabled
from packages.dialogue_engine.semantic_kernel.observation_memory import (
    classify_target_presence,
)
from packages.dialogue_engine.semantic_kernel.types import Observation, SubjectKind
from packages.dialogue_engine.state import GoalLifecycle, OpeningState, Question, QuestionPhase
from packages.dialogue_engine.turn_understanding import RichUserTurn, payload_to_rich_turn
from packages.telephony.product_originate import (
    build_stream_start_command,
    media_bridge_ws_url,
    originate_product_call,
)
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks, build_call_actor
from packages.voice_runtime.call_registry import CallBinding, build_call_registry


def _unseen_mission() -> CallMission:
    return CallMission(
        mission_id="repair-check-381",
        goals=(
            GoalDefinition(
                goal_id="parcel_received_9182",
                prompt_hint="Посылка сегодня пришла?",
                required=True,
                priority=10,
                answer_type="enum",
                allowed_values=("yes", "no", "unknown"),
            ),
            GoalDefinition(
                goal_id="worker_visited",
                prompt_hint="Мастер сегодня приходил?",
                required=True,
                priority=20,
            ),
        ),
    )


def _repair_mission() -> CallMission:
    return CallMission(
        mission_id="repair-safety",
        goals=(
            GoalDefinition(
                goal_id="worker_visited",
                prompt_hint="Мастер сегодня приходил?",
                required=True,
                priority=10,
            ),
            GoalDefinition(
                goal_id="repair_completed",
                prompt_hint="Он починил кран?",
                required=True,
                priority=20,
            ),
        ),
    )


async def _noop(*_a, **_k):
    return None


# ---------------------------------------------------------------------------
# 1) Custom-mission LLM path
# ---------------------------------------------------------------------------


def test_llm_interpret_enabled_by_default_with_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.delenv("IMVERA_LLM_INTERPRET", raising=False)
    monkeypatch.delenv("IMVERA_MISSION_LLM_INTERPRET", raising=False)
    assert llm_interpret_enabled() is True
    monkeypatch.setenv("IMVERA_MISSION_LLM_INTERPRET", "0")
    assert llm_interpret_enabled() is False
    monkeypatch.setenv("IMVERA_MISSION_LLM_INTERPRET", "1")
    monkeypatch.setenv("IMVERA_LLM_INTERPRET", "0")
    assert llm_interpret_enabled() is False


def test_call_actor_custom_free_speech_calls_interpret_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.setenv("IMVERA_VOICE_DIRECT_WELLNESS_OPENING", "1")
    monkeypatch.delenv("IMVERA_LLM_INTERPRET", raising=False)
    monkeypatch.delenv("IMVERA_MISSION_LLM_INTERPRET", raising=False)

    mission = _repair_mission()
    store = InMemoryCallRecordStore()
    interpret = AsyncMock(
        return_value=SimpleNamespace(
            payload=SemanticPayload(
                dialogue_act="answer",
                control="none",
                consent_answer="not_applicable",
                answers_pending_question=True,
                needs_clarification=False,
                goal_answers=(
                    GoalAnswerSemantic(
                        goal_id="worker_visited",
                        value="yes",
                        confidence=0.9,
                        evidence="мастер утром был",
                    ),
                ),
            )
        )
    )

    async def stt_free(_pcm, *_a, **_k):
        return SimpleNamespace(
            text="Да, мастер утром был, кран так и не сделал",
            asr_quality=AsrQuality.GOOD,
        )

    actor = build_call_actor(
        call_id="llm-free-1",
        family_id="fam-pc",
        elder_name="Анне Петровне",
        stt_url="http://127.0.0.1:9101",
        tts_url="http://127.0.0.1:9102",
        llm_url="http://127.0.0.1:9103",
        media=MediaCallbacks(send_pcm=_noop, flush=_noop, hangup=_noop, emit=_noop),
        store=store,
        mission=mission,
    )
    actor.llm = SimpleNamespace(interpret_turn=interpret)
    actor.stt = SimpleNamespace(transcribe_final=stt_free)
    actor._speak_phrase = _noop  # type: ignore[method-assign]

    eng = actor.session._engine
    assert eng is not None
    actor.session.start()
    speak = eng.pop_speak_effect()
    if speak is None and eng.state.active_playout is not None:
        q = eng.state.active_playout
        eng.on_playout_completed(eng.state.active_playout_generation, q.question_id)
    else:
        assert speak is not None
        eng.on_playout_completed(speak.generation, speak.question_id)

    asyncio.run(actor._handle_utterance(b"pcm-free", 1))
    assert interpret.await_count == 1


def test_call_actor_custom_bare_yes_skips_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.setenv("IMVERA_VOICE_DIRECT_WELLNESS_OPENING", "1")
    monkeypatch.delenv("IMVERA_LLM_INTERPRET", raising=False)

    interpret = AsyncMock(side_effect=AssertionError("LLM must not run for bare да"))

    async def stt_yes(_pcm, *_a, **_k):
        return SimpleNamespace(text="да", asr_quality=AsrQuality.GOOD)

    actor = build_call_actor(
        call_id="llm-bare-1",
        family_id="fam-pc",
        elder_name="Анне Петровне",
        stt_url="http://127.0.0.1:9101",
        tts_url="http://127.0.0.1:9102",
        llm_url="http://127.0.0.1:9103",
        media=MediaCallbacks(send_pcm=_noop, flush=_noop, hangup=_noop, emit=_noop),
        store=InMemoryCallRecordStore(),
        mission=_repair_mission(),
    )
    actor.llm = SimpleNamespace(interpret_turn=interpret)
    actor.stt = SimpleNamespace(transcribe_final=stt_yes)
    actor._speak_phrase = _noop  # type: ignore[method-assign]

    eng = actor.session._engine
    assert eng is not None
    actor.session.start()
    speak = eng.pop_speak_effect()
    if speak is None and eng.state.active_playout is not None:
        q = eng.state.active_playout
        eng.on_playout_completed(eng.state.active_playout_generation, q.question_id)
    else:
        assert speak is not None
        eng.on_playout_completed(speak.generation, speak.question_id)

    asyncio.run(actor._handle_utterance(b"pcm-yes", 1))
    assert interpret.await_count == 0


# ---------------------------------------------------------------------------
# 2) RED safety continuation
# ---------------------------------------------------------------------------


def test_red_safety_continuation_closes_without_mission_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.setenv("IMVERA_VOICE_DIRECT_WELLNESS_OPENING", "1")
    store = InMemoryCallRecordStore()
    session = CallSession(
        call_id="safe-session-1",
        family_id="fam-safe",
        store=store,
        mission=_repair_mission(),
        elder_display_name="Анне Петровне",
    )
    eng = session._engine
    assert eng is not None
    start = session.start()
    gen = getattr(start.proposal, "generation_id", None) or (
        eng.state.active_playout_generation if eng.state.active_playout else None
    )
    if gen:
        session.mark_spoken_action(gen)
    else:
        speak = eng.pop_speak_effect()
        if speak:
            eng.on_playout_completed(speak.generation, speak.question_id)
    assert eng.state.delivered_question is not None
    assert eng.state.delivered_question.goal_id == "worker_visited"

    r1 = session.handle_user_text("Я упала и не могу встать.")
    assert eng.state.safety_mode == "red"
    assert eng.state.risk_handling
    speech1 = (r1.validated.speech if r1.validated else "") or ""
    assert "кран" not in speech1.lower()
    assert "мастер" not in speech1.lower()
    session.mark_spoken_action(r1.proposal.generation_id)

    r2 = session.handle_user_text("Возле кровати упала.")
    speech2 = (r2.validated.speech if r2.validated else "") or ""
    low2 = speech2.lower()
    assert "кран" not in low2
    assert "мастер" not in low2
    assert "почин" not in low2
    assert speech2.strip(), "must not go silent after RED answer"
    assert eng.state.call_closed or (r2.proposal.intent or "") == "safety_close"
    mr = build_mission_result(eng.state)
    outcomes = build_call_outcomes(eng.state, mission_result=mr)
    assert outcomes.family_status == "RED"
    assert outcomes.mission_status == "PARTIAL"
    assert eng.state.goals["worker_visited"].lifecycle != GoalLifecycle.SATISFIED


# ---------------------------------------------------------------------------
# 3) Mission result semantics
# ---------------------------------------------------------------------------


def _goal_state(eng: DialogueEngine, gid: str, life: GoalLifecycle, *, attempts: int = 1):
    g = eng.state.goals[gid]
    g.lifecycle = life
    g.delivered_attempts = attempts
    if life == GoalLifecycle.SATISFIED:
        g.answer = "yes"
        obs_id = f"obs-goal-{gid}-t"
        eng.state.observations[obs_id] = Observation(
            observation_id=obs_id,
            attribute=gid,
            value="yes",
            normalized_value="yes",
            goal_id=gid,
            subject=SubjectKind.SPEAKER,
            confidence=0.95,
            evidence="приходил",
            status="confirmed",
        )
        g.evidence_ids = [f"ev-synthetic-{gid}", obs_id]


def test_mission_status_rules_and_grounded_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.setenv("IMVERA_VOICE_DIRECT_WELLNESS_OPENING", "1")
    mission = CallMission(
        mission_id="status-rules",
        goals=(
            GoalDefinition(goal_id="g1", prompt_hint="A?", required=True, priority=1),
            GoalDefinition(goal_id="g2", prompt_hint="B?", required=True, priority=2),
        ),
    )
    eng = DialogueEngine(call_id="st-1", mission=mission)
    eng.start()

    # nothing attempted
    mr = build_mission_result(eng.state)
    assert mr.status == "NOT_RUN"

    # SKIPPED must not yield COMPLETED
    _goal_state(eng, "g1", GoalLifecycle.SKIPPED)
    _goal_state(eng, "g2", GoalLifecycle.SKIPPED)
    mr = build_mission_result(eng.state)
    assert mr.status == "PARTIAL"

    # all SATISFIED → COMPLETED + grounded quotes (no ev-...)
    _goal_state(eng, "g1", GoalLifecycle.SATISFIED)
    _goal_state(eng, "g2", GoalLifecycle.SATISFIED)
    mr = build_mission_result(eng.state)
    assert mr.status == "COMPLETED"
    for g in mr.goals:
        assert g.evidence
        assert all(not e.startswith("ev-") for e in g.evidence)
        assert "приходил" in g.evidence

    # mix SATISFIED + DECLINED → PARTIAL
    _goal_state(eng, "g2", GoalLifecycle.DECLINED)
    mr = build_mission_result(eng.state)
    assert mr.status == "PARTIAL"

    # all DECLINED → DECLINED
    _goal_state(eng, "g1", GoalLifecycle.DECLINED)
    mr = build_mission_result(eng.state)
    assert mr.status == "DECLINED"

    # SATISFIED + NOT_APPLICABLE → COMPLETED
    _goal_state(eng, "g1", GoalLifecycle.SATISFIED)
    _goal_state(eng, "g2", GoalLifecycle.NOT_APPLICABLE)
    mr = build_mission_result(eng.state)
    assert mr.status == "COMPLETED"


# ---------------------------------------------------------------------------
# 4) Third-party target presence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("сейчас", None),
        ("я сейчас", None),
        ("подождите", None),
        ("секундочку", None),
        ("минутку", None),
        ("сейчас её нет", "unavailable"),
        ("её сейчас нет", "unavailable"),
        ("сейчас она спит", "unavailable"),
        ("она не может подойти", "unavailable"),
        ("сейчас передам", "confirmed"),
        ("передаю трубку", "confirmed"),
        ("сейчас дам трубку", "confirmed"),
        ("минутку, сейчас позову", "confirmed"),
        ("минутку, передам", "confirmed"),
        ("минутку, позову", None),
        ("сейчас её нет, но сейчас передам", "unavailable"),
    ],
)
def test_classify_target_presence(text: str, expected: str | None) -> None:
    assert classify_target_presence(text) == expected


def test_third_party_unknown_preserves_obligation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown wait phrases must keep third_party and re-ask target person — no mission goal."""
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.setenv("IMVERA_VOICE_DIRECT_WELLNESS_OPENING", "1")
    eng = DialogueEngine(call_id="tp-unknown", mission=_unseen_mission())
    eng.state.target_presence = "third_party"
    eng.state.elder_display_name = "Анне Петровне"
    eng.state.target_display_name = "Анне Петровне"
    eng.state.delivered_question = Question(
        question_id="q-tp",
        slot="target_presence",
        text="Могу я поговорить с Анне Петровне?",
        phase=QuestionPhase.DELIVERED,
        intent="ask_target_person",
    )
    eng.state.opening_state = OpeningState.DELIVERED
    eng.state.first_user_turn_received = True
    effects = eng.on_user_turn(
        "u-wait",
        "подождите",
        rich_turn=RichUserTurn(
            utterance_id="u-wait",
            raw_text="подождите",
            dialogue_act="other",
            control="none",
            answers_pending_question=False,
            needs_clarification=False,
        ),
    )
    assert eng.state.target_presence == "third_party"
    speak = next((e for e in effects if getattr(e, "kind", None) == "speak"), None)
    assert speak is not None
    assert speak.intent == "ask_target_person"
    assert speak.slot == "target_presence"
    # Mission goal must not be asked while still in target-presence obligation.
    assert "parcel" not in (speak.text or "").lower()
    assert "посыл" not in (speak.text or "").lower()
    assert all(
        g.lifecycle
        in (
            GoalLifecycle.UNSEEN,
            GoalLifecycle.AVAILABLE,
            GoalLifecycle.ACTIVE,
        )
        for g in eng.state.goals.values()
    )


def test_third_party_unavailable_outcomes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.setenv("IMVERA_VOICE_DIRECT_WELLNESS_OPENING", "1")
    eng = DialogueEngine(call_id="tp-1", mission=_unseen_mission())
    eng.state.target_presence = "unavailable"
    outcomes = build_call_outcomes(eng.state)
    assert outcomes.call_outcome == "NO_ANSWER"
    assert outcomes.mission_status == "NOT_RUN"
    assert outcomes.family_status == "UNSET"


# ---------------------------------------------------------------------------
# 5) Generic model observations
# ---------------------------------------------------------------------------


def test_observation_notes_not_persisted_as_speaker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    note = "Дочь вечером принесёт продукты."
    payload = SemanticPayload(
        dialogue_act="answer",
        control="none",
        consent_answer="not_applicable",
        answers_pending_question=False,
        needs_clarification=False,
        observation_notes=(note,),
    )
    rich = payload_to_rich_turn(payload, utterance_id="u-obs", raw_text=note)
    assert rich.observations == ()
    eng = DialogueEngine(call_id="obs-1", mission=_unseen_mission())
    eng.start()
    speak = eng.pop_speak_effect()
    if speak:
        eng.on_playout_completed(speak.generation, speak.question_id)
    eng.on_user_turn("u-obs", note, rich_turn=rich)
    for obs in eng.state.observations.values():
        if obs.subject == SubjectKind.SPEAKER:
            assert note not in (obs.value or "")
            assert note not in (obs.evidence or "")


# ---------------------------------------------------------------------------
# 6) Result family lookup
# ---------------------------------------------------------------------------


def test_result_lookup_after_session_pop_uses_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.setenv("IMVERA_VOICE_DIRECT_WELLNESS_OPENING", "1")
    from services.voice_service import main as vs

    store = InMemoryCallRecordStore()
    registry = build_call_registry(store)
    monkeypatch.setattr(vs, "_store", store)
    monkeypatch.setattr(vs, "_call_registry", registry)
    monkeypatch.setattr(vs, "_sessions", {})

    call_id = "call-result-fam"
    family_id = "fam-non-default"
    mission = _repair_mission()
    registry.register(
        CallBinding(
            call_id=call_id,
            family_id=family_id,
            person_id="p1",
            mission=mission.model_dump(mode="json"),
            mission_id=mission.mission_id,
        )
    )
    session = CallSession(
        call_id=call_id,
        family_id=family_id,
        store=store,
        mission=mission,
    )
    eng = session._engine
    assert eng is not None
    session.start()
    speak = eng.pop_speak_effect()
    if speak is None and eng.state.active_playout is not None:
        q = eng.state.active_playout
        eng.on_playout_completed(eng.state.active_playout_generation, q.question_id)
    else:
        assert speak is not None
        eng.on_playout_completed(speak.generation, speak.question_id)
    eng.on_user_turn(
        "u1",
        "Да, приходил.",
        rich_turn=RichUserTurn(
            utterance_id="u1",
            raw_text="Да, приходил.",
            dialogue_act="answer",
            control="none",
            answers_pending_question=True,
            needs_clarification=False,
            goal_answers=(
                GoalAnswerCandidate(
                    goal_id="worker_visited",
                    value="yes",
                    confidence=0.96,
                    evidence="приходил",
                ),
            ),
        ),
    )
    eng.state.fsm_state = FsmState.GOODBYE
    eng.state.call_closed = True
    session.state.final_action_done = True
    session.state.call_finalized = False
    ok, err = session._finalize_call_if_needed()
    assert ok, err
    # Simulate stop_call popping live session — only shared store binding remains.
    assert call_id not in vs._sessions

    client = TestClient(vs.app)
    resp = client.get(f"/v1/calls/{call_id}/result")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["family_id"] == family_id
    assert body["mission_result"]["mission_id"] == "repair-safety"


def test_call_binding_separate_store_instances_share_persistence() -> None:
    """Simulate voice_service vs media_bridge: two store instances, no Python globals."""
    shared: dict = {}
    store_a = InMemoryCallRecordStore(shared=shared)
    store_b = InMemoryCallRecordStore(shared=shared)
    assert store_a is not store_b
    assert store_a._results is store_b._results

    mission = _unseen_mission()
    reg_a = build_call_registry(store_a)
    reg_b = build_call_registry(store_b)
    assert reg_a is not reg_b

    call_id = "call-cross-proc"
    reg_a.register(
        CallBinding(
            call_id=call_id,
            family_id="fam-shared",
            person_id="p1",
            elder_name="Анне Петровне",
            transport="freeswitch",
            mission=mission.model_dump(mode="json"),
            mission_id=mission.mission_id,
        )
    )
    # Resolve via the OTHER process's registry/store instance.
    resolved = reg_b.resolve(call_id=call_id)
    assert resolved is not None
    assert resolved.family_id == "fam-shared"
    assert resolved.mission_id == "repair-check-381"
    assert resolved.mission is not None
    goals = resolved.mission.get("goals") or []
    goal_ids = {g.get("goal_id") for g in goals if isinstance(g, dict)}
    assert "parcel_received_9182" in goal_ids
    assert "worker_visited" in goal_ids


# ---------------------------------------------------------------------------
# 7) Product API → FreeSWITCH handoff
# ---------------------------------------------------------------------------


def test_product_api_freeswitch_handoff_same_mission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.setenv("IMVERA_VOICE_DIRECT_WELLNESS_OPENING", "1")
    from services.imvera_media_bridge import callactor as ca
    from services.voice_service import main as vs

    shared: dict = {}
    store = InMemoryCallRecordStore(shared=shared)
    registry = build_call_registry(store)
    monkeypatch.setattr(vs, "_call_registry", registry)
    monkeypatch.setattr(vs, "_sessions", {})
    monkeypatch.setattr(vs, "_store", store)
    monkeypatch.setattr(vs, "_telephony_shared_store_ready", lambda: (True, ""))
    monkeypatch.setattr(ca, "create_call_record_store", lambda: InMemoryCallRecordStore(shared=shared))

    async def fake_originate(*, call_id: str, **_k):
        return {
            "ok": True,
            "call_id": call_id,
            "fs_uuid": "fs-uuid-test",
            "ws_url": media_bridge_ws_url(call_id, fs_uuid="fs-uuid-test"),
            "destination": "user/zoiper",
            "dial_string": f"{{imvera_call_id={call_id}}}user/zoiper &park()",
            "commands": [
                f"originate {{imvera_call_id={call_id}}}user/zoiper &park()",
                "uuid_setvar fs-uuid-test STREAM_PLAYBACK 1",
                build_stream_start_command("fs-uuid-test", call_id),
            ],
            "stream_started": True,
        }

    monkeypatch.setattr(
        "packages.telephony.product_originate.originate_product_call",
        fake_originate,
    )

    client = TestClient(vs.app)
    mission = _unseen_mission()
    resp = client.post(
        "/v1/calls",
        json={
            "person_id": "p1",
            "family_id": "fam-fs",
            "elder_name": "Анне Петровне",
            "transport": "freeswitch",
            "mission": mission.model_dump(mode="json"),
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["mission_id"] == "repair-check-381"
    assert data["owner"] == "media_bridge_callactor"
    assert data["telephony"]["ok"] is True
    call_id = data["call_id"]
    # No second conversation owner in voice_service for FS transport.
    assert call_id not in vs._sessions

    class _QP(dict):
        def get(self, key, default=None):
            return super().get(key, default)

    ws = SimpleNamespace(query_params=_QP({"call_id": call_id}))
    resolved_call, family, elder, mission_obj = ca._resolve_product_mission(ws, "fs-uuid-test")
    assert resolved_call == call_id
    assert family == "fam-fs"
    assert mission_obj is not None
    assert mission_obj.mission_id == "repair-check-381"
    cmd = build_stream_start_command("fs-uuid-test", call_id)
    assert f"call_id={call_id}" in cmd


def test_telephony_without_pg_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /v1/calls transport=freeswitch must not originate on process-local InMemory."""
    monkeypatch.delenv("IMVERA_PG_URL", raising=False)
    from services.voice_service import main as vs

    store = InMemoryCallRecordStore()
    registry = build_call_registry(store)
    monkeypatch.setattr(vs, "_call_registry", registry)
    monkeypatch.setattr(vs, "_sessions", {})
    monkeypatch.setattr(vs, "_store", store)

    originated = {"n": 0}

    async def boom(*, call_id: str, **_k):
        originated["n"] += 1
        raise AssertionError("must not originate without shared PG")

    monkeypatch.setattr(
        "packages.telephony.product_originate.originate_product_call",
        boom,
    )

    client = TestClient(vs.app)
    resp = client.post(
        "/v1/calls",
        json={
            "person_id": "p1",
            "family_id": "fam-no-pg",
            "elder_name": "Анне Петровне",
            "transport": "freeswitch",
            "mission": _unseen_mission().model_dump(mode="json"),
        },
    )
    assert resp.status_code == 503, resp.text
    detail = resp.json()["detail"]
    assert "IMVERA_PG_URL" in detail or "Postgres" in detail or "shared" in detail.lower()
    assert originated["n"] == 0
    assert registry.resolve(call_id="unused") is None


def test_product_call_id_missing_binding_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """?call_id= product path with missing CallBinding: no actor, no daily mission fallback."""
    from services.imvera_media_bridge import callactor as ca

    monkeypatch.setattr(ca, "create_call_record_store", lambda: InMemoryCallRecordStore())
    built = {"actor": 0}

    def _forbid_actor(*_a, **_k):
        built["actor"] += 1
        raise AssertionError("CallActor must not be constructed without CallBinding")

    monkeypatch.setattr(ca, "build_call_actor", _forbid_actor)

    class _QP(dict):
        def get(self, key, default=None):
            return super().get(key, default)

    ws = SimpleNamespace(query_params=_QP({"call_id": "call-missing-binding"}))
    with pytest.raises(ca.ProductBindingMissing) as ei:
        ca._resolve_product_mission(ws, "fs-uuid-missing")
    assert ei.value.call_id == "call-missing-binding"
    assert ei.value.fs_uuid == "fs-uuid-missing"

    closed: dict[str, object] = {}

    class _WS:
        query_params = _QP({"call_id": "call-missing-binding"})

        async def close(self, code: int = 1000, reason: str = "") -> None:
            closed["code"] = code
            closed["reason"] = reason

    async def _no_blockers() -> list[str]:
        return []

    monkeypatch.setattr(ca, "inference_blockers", _no_blockers)

    asyncio.run(ca.handle_callactor_ws(_WS(), "fs-uuid-missing"))  # type: ignore[arg-type]
    assert built["actor"] == 0
    assert closed.get("code") == 1008
    assert "CallBinding" in str(closed.get("reason", ""))


def test_originate_attaches_audio_stream_with_product_call_id() -> None:
    """Integration-level mocked ESL: originate → answer → uuid_audio_stream with same call_id."""
    call_id = "call-esl-stream-1"
    commands: list[str] = []

    async def fake_esl(command: str, *, timeout_s: float = 3.0) -> str:
        commands.append(command)
        if command.startswith("originate "):
            return "+OK 11111111-2222-3333-4444-555555555555\n"
        if command.startswith("uuid_setvar "):
            return "+OK\n"
        if command.startswith("uuid_audio_stream "):
            return "+OK\n"
        return "-ERR unexpected\n"

    result = asyncio.run(originate_product_call(call_id=call_id, api=fake_esl, timeout_s=2.0))
    assert result["ok"] is True
    assert result["stream_started"] is True
    assert result["call_id"] == call_id
    assert len(commands) >= 3
    assert commands[0].startswith("originate ")
    assert "&park()" in commands[0]
    assert "imvera_call_id=" + call_id in commands[0]
    assert any(c.startswith("uuid_setvar ") and "STREAM_PLAYBACK" in c for c in commands)
    stream_cmds = [c for c in commands if c.startswith("uuid_audio_stream ")]
    assert len(stream_cmds) == 1
    stream = stream_cmds[0]
    assert " start " in stream
    assert f"call_id={call_id}" in stream
    assert result["fs_uuid"] in stream
    # Order: originate before stream attach
    assert commands.index(stream_cmds[0]) > commands.index(
        next(c for c in commands if c.startswith("originate "))
    )


def test_create_call_api_accepts_mission(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.setenv("IMVERA_VOICE_DIRECT_WELLNESS_OPENING", "1")
    from services.voice_service import main as vs

    store = InMemoryCallRecordStore()
    registry = build_call_registry(store)
    monkeypatch.setattr(vs, "_call_registry", registry)
    monkeypatch.setattr(vs, "_sessions", {})
    monkeypatch.setattr(vs, "_store", store)
    monkeypatch.setattr(vs, "_max_sessions", 10)

    client = TestClient(vs.app)
    body = {
        "person_id": "p1",
        "family_id": "fam-pc",
        "elder_name": "Анне Петровне",
        "transport": "browser",
        "mission": _unseen_mission().model_dump(mode="json"),
    }
    resp = client.post("/v1/calls", json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["mission_id"] == "repair-check-381"
    call_id = data["call_id"]
    assert call_id in vs._sessions
    eng = vs._sessions[call_id].actor.session._engine
    assert eng is not None
    assert eng.state.mission_id == "repair-check-381"
    assert "parcel_received_9182" in eng.state.goals


def test_build_call_actor_accepts_unseen_mission(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.setenv("IMVERA_VOICE_DIRECT_WELLNESS_OPENING", "1")
    mission = _unseen_mission()
    actor = build_call_actor(
        call_id="pc-1",
        family_id="fam-pc",
        elder_name="Анне Петровне",
        stt_url="http://127.0.0.1:9101",
        tts_url="http://127.0.0.1:9102",
        llm_url="http://127.0.0.1:9103",
        media=MediaCallbacks(send_pcm=_noop, flush=_noop, hangup=_noop, emit=_noop),
        store=InMemoryCallRecordStore(),
        mission=mission,
    )
    eng = actor.session._engine
    assert eng is not None
    assert eng.state.mission_id == "repair-check-381"
    assert "parcel_received_9182" in eng.state.goals
    # No goal-id branching in CallActor source.
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "packages/voice_runtime/call_actor.py"
    assert "parcel_received_9182" not in src.read_text(encoding="utf-8")


def test_payload_to_rich_turn_maps_goal_answers() -> None:
    payload = SemanticPayload(
        dialogue_act="answer",
        control="none",
        consent_answer="not_applicable",
        answers_pending_question=True,
        needs_clarification=False,
        goal_answers=(
            GoalAnswerSemantic(
                goal_id="worker_visited",
                value="yes",
                confidence=0.95,
                evidence="мастер приходил",
            ),
        ),
    )
    rich = payload_to_rich_turn(payload, utterance_id="u1", raw_text="Да, мастер приходил.")
    assert len(rich.goal_answers) == 1
    assert rich.goal_answers[0].goal_id == "worker_visited"


def test_mission_result_persists_in_memory_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.setenv("IMVERA_VOICE_DIRECT_WELLNESS_OPENING", "1")
    store = InMemoryCallRecordStore()
    mission = CallMission(
        mission_id="repair-check-381",
        goals=(
            GoalDefinition(
                goal_id="worker_visited",
                prompt_hint="Мастер сегодня приходил?",
                answer_type="enum",
                allowed_values=("yes", "no", "unknown"),
            ),
        ),
    )
    session = CallSession(
        call_id="persist-1",
        family_id="fam-pc",
        store=store,
        mission=mission,
    )
    eng = session._engine
    assert eng is not None
    result = session.start()
    speak = eng.pop_speak_effect()
    if speak is None and result is not None and getattr(result, "speak_effect", None):
        speak = result.speak_effect
    if speak is None and eng.state.active_playout is not None:
        q = eng.state.active_playout
        eng.on_playout_completed(eng.state.active_playout_generation, q.question_id)
    else:
        assert speak is not None
        eng.on_playout_completed(speak.generation, speak.question_id)
    eng.on_user_turn(
        "u1",
        "Да, приходил.",
        rich_turn=RichUserTurn(
            utterance_id="u1",
            raw_text="Да, приходил.",
            dialogue_act="answer",
            control="none",
            answers_pending_question=True,
            needs_clarification=False,
            goal_answers=(
                GoalAnswerCandidate(
                    goal_id="worker_visited",
                    value="yes",
                    confidence=0.96,
                    evidence="приходил",
                ),
            ),
        ),
    )
    eng.state.call_closed = True
    eng.state.fsm_state = FsmState.GOODBYE
    session.state.final_action_done = True
    session.state.call_finalized = False
    ok, err = session._finalize_call_if_needed()
    assert ok, err
    snap = store.get_call_result("persist-1", "fam-pc")
    assert snap is not None
    assert snap.mission_result is not None
    assert snap.mission_result.mission_id == "repair-check-381"
    goals = {g.goal_id: g for g in snap.mission_result.goals}
    assert goals["worker_visited"].lifecycle == GoalLifecycle.SATISFIED.value
    assert goals["worker_visited"].value == "yes"
    assert snap.outcomes is not None
    assert snap.outcomes.family_status == "UNSET"
    assert snap.outcomes.mission_status in {"COMPLETED", "PARTIAL"}


def test_mission_context_for_llm_is_read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.setenv("IMVERA_VOICE_DIRECT_WELLNESS_OPENING", "1")
    from packages.dialogue_engine.mission_result import mission_context_for_llm

    eng = DialogueEngine(call_id="ctx-1", mission=_unseen_mission())
    eng.start()
    speak = eng.pop_speak_effect()
    eng.on_playout_completed(speak.generation, speak.question_id)
    ctx = mission_context_for_llm(eng.state)
    assert isinstance(ctx, MissionContextSnapshot)
    assert ctx.mission_id == "repair-check-381"
    assert ctx.delivered_goal_id == "parcel_received_9182"


def test_cancelled_final_open_does_not_commit_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.setenv("IMVERA_VOICE_DIRECT_WELLNESS_OPENING", "1")
    eng = DialogueEngine(
        call_id="fo-1",
        mission=CallMission(
            mission_id="done",
            goals=(
                GoalDefinition(
                    goal_id="g1",
                    prompt_hint="Ок?",
                ),
            ),
        ),
    )
    eng.state.goals["g1"].lifecycle = GoalLifecycle.SATISFIED
    eng.state.goals["g1"].answer = "yes"
    from packages.dialogue_engine.conversation_policy import TurnContext, schedule_next_action

    plan = schedule_next_action(
        eng.state,
        TurnContext(
            turn=RichUserTurn(
                utterance_id="x",
                raw_text="да",
                dialogue_act="answer",
                control="none",
                answers_pending_question=True,
                needs_clarification=False,
            ),
            user_text="да",
        ),
    )
    assert plan.intent == "mission_final_open"
    assert eng.state.important_to_share_planned is True
    assert eng.state.important_to_share_asked is False
    from packages.dialogue_engine.reducer import _emit_from_plan

    eng.state, effects = _emit_from_plan(eng.state, plan)
    speak = effects[0]
    eng.on_playout_cancelled(speak.generation, speak.question_id)
    assert eng.state.important_to_share_asked is False
    assert eng.state.important_to_share_planned is False


def test_two_postgres_stores_share_call_binding() -> None:
    """Two PostgresCallRecordStore instances must share CallBinding across processes."""
    import os
    import uuid

    pg_url = os.environ.get("IMVERA_PG_URL")
    if not pg_url:
        pytest.skip("IMVERA_PG_URL not set")
    try:
        import psycopg

        with psycopg.connect(pg_url, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    except Exception as exc:
        pytest.skip(f"PostgreSQL not available: {exc}")

    from packages.core.pg_store import PostgresCallRecordStore

    call_id = f"pg-bind-{uuid.uuid4().hex[:12]}"
    family_id = "fam-pg-bind"
    mission = _unseen_mission()
    mission_payload = mission.model_dump(mode="json")
    goals = mission_payload.get("goals") or []

    store_a = PostgresCallRecordStore(pg_url)
    store_b = PostgresCallRecordStore(pg_url)
    assert store_a is not store_b

    ensure = store_a.ensure_call(call_id, family_id)
    assert ensure.ok, ensure.error
    put = store_a.put_call_binding(
        {
            "call_id": call_id,
            "family_id": family_id,
            "person_id": "p-pg",
            "elder_name": "Анне Петровне",
            "transport": "freeswitch",
            "mission": mission_payload,
            "mission_id": mission.mission_id,
            "metadata": {},
        }
    )
    assert put.ok, put.error

    got = store_b.get_call_binding(call_id)
    assert got is not None
    assert got["call_id"] == call_id
    assert got["family_id"] == family_id
    assert got["mission_id"] == mission.mission_id
    got_goals = got.get("mission", {}).get("goals") or []
    assert {g.get("goal_id") for g in goals if isinstance(g, dict)} == {
        g.get("goal_id") for g in got_goals if isinstance(g, dict)
    }

    fs_uuid = f"fs-{uuid.uuid4().hex[:12]}"
    reg_a = build_call_registry(store_a)
    bound = reg_a.bind_fs_uuid(call_id, fs_uuid)
    assert bound is not None
    assert bound.metadata.get("fs_uuid") == fs_uuid

    via_b = store_b.get_call_binding_by_fs_uuid(fs_uuid)
    assert via_b is not None
    assert via_b["call_id"] == call_id
    assert via_b["family_id"] == family_id
    assert via_b["mission_id"] == mission.mission_id
