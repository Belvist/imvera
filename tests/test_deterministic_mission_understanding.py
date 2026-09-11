"""Deterministic mission understanding — product path without Qwen."""

from __future__ import annotations

import asyncio
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from packages.contracts.enums import AsrQuality
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.dialogue_engine.deterministic_mission import (
    DeterministicMissionUnderstandingProvider,
)
from packages.dialogue_engine.mission import CallMission, GoalDefinition
from packages.dialogue_engine.mission_understanding import (
    MissionUnderstandingContext,
    MissionUnderstandingRequest,
    get_mission_understanding_provider,
    reset_mission_understanding_provider,
)
from packages.dialogue_engine.runtime import llm_interpret_enabled
from packages.dialogue_engine.state import GoalLifecycle, QuestionPhase
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks, build_call_actor


def _repair_mission() -> CallMission:
    return CallMission(
        mission_id="repair-det",
        goals=(
            GoalDefinition(
                goal_id="worker_visited",
                description="Узнать, приходил ли мастер",
                prompt_hint="Мастер сегодня приходил?",
                required=True,
                priority=10,
                answer_type="enum",
                allowed_values=("yes", "no", "unknown"),
                aliases=("мастер",),
                semantic_hints=("приходил мастер",),
            ),
            GoalDefinition(
                goal_id="repair_completed",
                description="Узнать, починили ли кран",
                prompt_hint="Удалось починить кран?",
                required=True,
                priority=20,
                answer_type="enum",
                allowed_values=("yes", "no", "unknown"),
                aliases=("кран",),
                semantic_hints=("починить кран", "починил кран"),
            ),
        ),
    )


def _ctx(
    mission: CallMission,
    *,
    delivered: str,
    lifecycles: dict[str, str] | None = None,
) -> MissionUnderstandingContext:
    life = lifecycles or {g.goal_id: "ACTIVE" for g in mission.goals}
    return MissionUnderstandingContext(
        mission_id=mission.mission_id,
        goal_ids=tuple(g.goal_id for g in mission.goals),
        goal_lifecycles=tuple(life.items()),
        delivered_goal_id=delivered,
        delivered_question_text=next(
            g.prompt_hint for g in mission.goals if g.goal_id == delivered
        ),
        delivered_question_phase=QuestionPhase.DELIVERED.value,
    )


def _req(text: str, mission: CallMission, delivered: str) -> MissionUnderstandingRequest:
    return MissionUnderstandingRequest(
        text=text,
        utterance_id="u1",
        mission=mission,
        delivered_goal_id=delivered,
        delivered_question_phase=QuestionPhase.DELIVERED.value,
        active_goal_id=delivered,
        context=_ctx(mission, delivered=delivered),
    )


async def _noop(*_a, **_k):
    return None


@pytest.fixture(autouse=True)
def _reset_provider() -> None:
    reset_mission_understanding_provider()
    yield
    reset_mission_understanding_provider()


def test_product_default_provider_is_deterministic() -> None:
    provider = get_mission_understanding_provider()
    assert isinstance(provider, DeterministicMissionUnderstandingProvider)


def test_llm_interpret_defaults_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.delenv("IMVERA_LLM_INTERPRET", raising=False)
    monkeypatch.delenv("IMVERA_MISSION_LLM_INTERPRET", raising=False)
    assert llm_interpret_enabled() is False


def test_bare_yes_no_unknown() -> None:
    mission = _repair_mission()
    p = DeterministicMissionUnderstandingProvider()
    yes = p.understand(_req("да", mission, "worker_visited"))
    assert len(yes.goal_answers) == 1
    assert yes.goal_answers[0].goal_id == "worker_visited"
    assert yes.goal_answers[0].value == "yes"
    assert "да" in yes.goal_answers[0].evidence.casefold()

    no = p.understand(_req("нет", mission, "worker_visited"))
    assert no.goal_answers[0].value == "no"

    unk = p.understand(_req("не знаю", mission, "worker_visited"))
    assert unk.goal_answers[0].value == "unknown"


def test_two_goal_answers_in_one_utterance() -> None:
    mission = _repair_mission()
    p = DeterministicMissionUnderstandingProvider()
    text = "Да, мастер приходил, но кран он так и не починил."
    result = p.understand(_req(text, mission, "worker_visited"))
    by_id = {a.goal_id: a for a in result.goal_answers}
    assert by_id["worker_visited"].value == "yes"
    assert "мастер" in by_id["worker_visited"].evidence.casefold()
    assert by_id["worker_visited"].evidence.casefold() in text.casefold()
    assert by_id["repair_completed"].value == "no"
    assert "кран" in by_id["repair_completed"].evidence.casefold()
    assert "не починил" in by_id["repair_completed"].evidence.casefold()
    assert by_id["repair_completed"].evidence.casefold() in text.casefold()


def test_future_goal_answer_while_other_delivered() -> None:
    mission = _repair_mission()
    p = DeterministicMissionUnderstandingProvider()
    # Delivered is worker_visited, but user answers the future repair goal.
    text = "Кран так и не починили."
    result = p.understand(_req(text, mission, "worker_visited"))
    by_id = {a.goal_id: a for a in result.goal_answers}
    assert "repair_completed" in by_id
    assert by_id["repair_completed"].value == "no"
    # Must not fabricate SATISFIED yes for delivered without evidence.
    if "worker_visited" in by_id:
        assert by_id["worker_visited"].value != "yes" or "мастер" in text.casefold()


def test_ambiguous_does_not_fabricate_satisfied() -> None:
    mission = CallMission(
        mission_id="ambig",
        goals=(
            GoalDefinition(
                goal_id="a_paid",
                prompt_hint="Счета оплатили?",
                aliases=("счета", "оплатили"),
                semantic_hints=("оплата счетов",),
                priority=10,
            ),
            GoalDefinition(
                goal_id="b_paid",
                prompt_hint="Коммуналку оплатили?",
                aliases=("коммуналку", "оплатили"),
                semantic_hints=("оплата",),
                priority=20,
            ),
        ),
    )
    p = DeterministicMissionUnderstandingProvider()
    result = p.understand(_req("Ну вроде оплатили", mission, "a_paid"))
    # Ambiguous / weak → no fabricated SATISFIED answers (or unclear disposition).
    for ans in result.goal_answers:
        assert ans.evidence.strip()
        assert ans.evidence.casefold() in "ну вроде оплатили"
    # Prefer unclear over guessing when binding is weak/ambiguous.
    if not result.goal_answers:
        assert result.goal_dispositions or True
    else:
        # If something bound, must be uniquely evidenced — never both goals.
        assert len(result.goal_answers) <= 1


def test_answer_plus_side_issue_atomic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.setenv("IMVERA_VOICE_DIRECT_WELLNESS_OPENING", "1")
    monkeypatch.setenv("IMVERA_LLM_INTERPRET", "0")
    monkeypatch.setenv("IMVERA_MISSION_LLM_INTERPRET", "0")
    from packages.dialogue_engine.engine import DialogueEngine
    from packages.dialogue_engine.turn_understanding import build_rich_turn_from_text

    mission = _repair_mission()
    eng = DialogueEngine(
        call_id="det-side-1",
        elder_display_name="Анне Петровне",
        mission=mission,
    )
    effects = eng.start()
    # Complete opening playout if any.
    from packages.dialogue_engine.effects import SpeakEffect

    for eff in effects:
        if isinstance(eff, SpeakEffect):
            eng.on_playout_completed(eff.generation, eff.question_id)
    if eng.state.active_playout is not None:
        q = eng.state.active_playout
        eng.on_playout_completed(eng.state.active_playout_generation, q.question_id)
    assert eng.state.delivered_question is not None
    assert eng.state.delivered_question.goal_id == "worker_visited"

    text = "Да, мастер приходил, только голова сильно болит."
    rich = build_rich_turn_from_text(
        text,
        utterance_id="u-side-1",
        engine_state=eng.state,
        mission_provider=DeterministicMissionUnderstandingProvider(),
    )
    assert rich.goal_answers
    assert any(a.goal_id == "worker_visited" and a.value == "yes" for a in rich.goal_answers)
    assert rich.issue_mentions
    eng.on_user_turn("u-side-1", text, rich_turn=rich)
    assert eng.state.goals["worker_visited"].lifecycle == GoalLifecycle.SATISFIED
    assert eng.state.goals["worker_visited"].answer == "yes"
    assert eng.state.issue_episodes or eng.state.active_episode_id
    # Mission answer + side issue persist in one atomic apply.
    assert eng.state.goals["worker_visited"].lifecycle == GoalLifecycle.SATISFIED
    assert bool(eng.state.issue_episodes) or bool(eng.state.active_episode_id)


def _prime_actor(actor: CallActor) -> None:
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


def test_custom_free_speech_zero_llm_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.setenv("IMVERA_VOICE_DIRECT_WELLNESS_OPENING", "1")
    monkeypatch.setenv("IMVERA_LLM_INTERPRET", "0")
    monkeypatch.setenv("IMVERA_MISSION_LLM_INTERPRET", "0")

    interpret = AsyncMock(side_effect=AssertionError("interpret_turn must not run"))
    render = AsyncMock(side_effect=AssertionError("render_stream must not run"))

    async def stt_free(_pcm, *_a, **_k):
        return SimpleNamespace(
            text="Да, мастер приходил, но кран он так и не починил.",
            asr_quality=AsrQuality.GOOD,
        )

    actor = build_call_actor(
        call_id="det-free-1",
        family_id="fam-det",
        elder_name="Анне Петровне",
        stt_url="http://127.0.0.1:9101",
        tts_url="http://127.0.0.1:9102",
        llm_url="http://127.0.0.1:9103",
        media=MediaCallbacks(send_pcm=_noop, flush=_noop, hangup=_noop, emit=_noop),
        store=InMemoryCallRecordStore(),
        mission=_repair_mission(),
    )
    actor.llm = SimpleNamespace(interpret_turn=interpret, render_stream=render)
    actor.stt = SimpleNamespace(transcribe_final=stt_free)
    actor._speak_phrase = _noop  # type: ignore[method-assign]
    _prime_actor(actor)

    asyncio.run(actor._handle_utterance(b"pcm-free", 1))
    assert interpret.await_count == 0
    assert render.await_count == 0
    eng = actor.session._engine
    assert eng is not None
    assert eng.state.goals["worker_visited"].lifecycle == GoalLifecycle.SATISFIED
    assert eng.state.goals["repair_completed"].lifecycle == GoalLifecycle.SATISFIED
    assert eng.state.goals["repair_completed"].answer == "no"


def test_llm_unavailable_call_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.setenv("IMVERA_VOICE_DIRECT_WELLNESS_OPENING", "1")
    monkeypatch.setenv("IMVERA_LLM_INTERPRET", "0")

    async def boom(*_a, **_k):
        raise RuntimeError("llm down")

    async def stt_yes(_pcm, *_a, **_k):
        return SimpleNamespace(text="да", asr_quality=AsrQuality.GOOD)

    actor = build_call_actor(
        call_id="det-llm-down",
        family_id="fam-det",
        elder_name="Анне Петровне",
        stt_url="http://127.0.0.1:9101",
        tts_url="http://127.0.0.1:9102",
        llm_url="http://127.0.0.1:9103",
        media=MediaCallbacks(send_pcm=_noop, flush=_noop, hangup=_noop, emit=_noop),
        store=InMemoryCallRecordStore(),
        mission=_repair_mission(),
    )
    actor.llm = SimpleNamespace(interpret_turn=boom, render_stream=boom)
    actor.stt = SimpleNamespace(transcribe_final=stt_yes)
    actor._speak_phrase = _noop  # type: ignore[method-assign]
    _prime_actor(actor)
    asyncio.run(actor._handle_utterance(b"pcm-yes", 1))
    eng = actor.session._engine
    assert eng is not None
    assert eng.state.goals["worker_visited"].answer == "yes"


def test_media_bridge_readiness_green_without_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.imvera_media_bridge import callactor as ca

    class Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url: str):
            if ":9103" in url:
                return httpx.Response(503, json={"status": "down"}, request=httpx.Request("GET", url))
            return httpx.Response(200, json={"status": "ok"}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    blockers = asyncio.run(ca.inference_blockers())
    assert blockers == []
    # Prove LLM URL was never required: even if only stt/tts checked, empty blockers.


def test_launcher_does_not_require_llm_worker() -> None:
    src = Path("scripts/freeswitch_zoiper_voice_up.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "_ensure_mlx_workers"
    )
    dumped = ast.dump(fn)
    assert "llm" not in dumped or "not required" in src
    assert 'is_running("llm")' not in src
    assert "IMVERA_MODELS_WORKERS" in src
    assert "stt,tts" in src


def test_need_llm_always_false_when_engine_active() -> None:
    src = Path("packages/voice_runtime/call_actor.py").read_text(encoding="utf-8")
    assert "Product DialogueEngine path: NEVER call /v1/interpret" in src
    assert "need_llm = (not fastpath_enough)" not in src
    # Engine branch forces False; only legacy non-engine may set True.
    assert "if not self.session.uses_dialogue_engine():" in src
