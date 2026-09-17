"""Deterministic mission understanding — product path without Qwen."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from packages.contracts.enums import AsrQuality
from packages.core.memory_store import InMemoryCallRecordStore
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
                # Hints are authoritative for factual negation polarity.
                semantic_hints=(
                    "приходил",
                    "приходил мастер",
                    "мастер приходил",
                ),
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
                semantic_hints=(
                    "починить",
                    "починили",
                    "починить кран",
                    "починил кран",
                    "кран починили",
                ),
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
        assert result.goal_dispositions
        assert any(d.disposition == "unclear" for d in result.goal_dispositions)
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
            req = httpx.Request("GET", url)
            if ":9103" in url:
                return httpx.Response(503, json={"status": "down"}, request=req)
            return httpx.Response(200, json={"status": "ok"}, request=req)

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


def _groceries_mission(*, with_alias: bool) -> CallMission:
    aliases = (
        {"no": ("принесла", "принесли", "уже принесла", "дочь уже принесла")}
        if with_alias
        else {}
    )
    return CallMission(
        mission_id="groceries-det",
        goals=(
            GoalDefinition(
                goal_id="groceries_help",
                description="Узнать, нужна ли помощь с продуктами",
                prompt_hint="Нужна ли сегодня помощь с продуктами?",
                required=True,
                priority=10,
                answer_type="enum",
                allowed_values=("yes", "no", "unknown"),
                aliases=("продукты", "продукт"),
                semantic_hints=("помощь с продуктами",),
                answer_aliases=aliases,
            ),
        ),
    )


def test_a_groceries_topic_mention_without_alias_is_not_yes() -> None:
    """A: topic mention alone must not SATISFY as yes."""
    mission = _groceries_mission(with_alias=False)
    p = DeterministicMissionUnderstandingProvider()
    text = "продукты дочь уже принесла"
    result = p.understand(_req(text, mission, "groceries_help"))
    assert not any(a.value == "yes" for a in result.goal_answers)
    assert not any(a.goal_id == "groceries_help" for a in result.goal_answers)
    assert any(d.disposition == "unclear" for d in result.goal_dispositions)


def test_b_groceries_with_answer_alias_maps_value() -> None:
    """B: answer_aliases from GoalDefinition may bind value."""
    mission = _groceries_mission(with_alias=True)
    p = DeterministicMissionUnderstandingProvider()
    text = "продукты дочь уже принесла"
    result = p.understand(_req(text, mission, "groceries_help"))
    by_id = {a.goal_id: a for a in result.goal_answers}
    assert by_id["groceries_help"].value == "no"
    assert "принесла" in by_id["groceries_help"].evidence.casefold()


def test_c_refusal_is_declined_not_factual_no() -> None:
    """C: generic refusal → declined; bare нет stays factual no."""
    mission = _repair_mission()
    p = DeterministicMissionUnderstandingProvider()
    refused = p.understand(_req("Не хочу говорить", mission, "worker_visited"))
    assert refused.goal_answers == ()
    assert len(refused.goal_dispositions) == 1
    assert refused.goal_dispositions[0].goal_id == "worker_visited"
    assert refused.goal_dispositions[0].disposition == "declined"

    bare = p.understand(_req("нет", mission, "worker_visited"))
    assert bare.goal_answers[0].value == "no"

    control = p.understand(_req("не звоните больше", mission, "worker_visited"))
    assert control.goal_answers == ()
    assert control.control == "stop_call"


def test_d_correction_reopens_satisfied_goal() -> None:
    """D: correction marker may reopen SATISFIED; without marker must not."""
    mission = _repair_mission()
    p = DeterministicMissionUnderstandingProvider()
    life = {"worker_visited": "SATISFIED", "repair_completed": "ACTIVE"}
    ctx = _ctx(mission, delivered="repair_completed", lifecycles=life)
    # Without marker — do not reopen satisfied worker_visited.
    no_marker = p.understand(
        MissionUnderstandingRequest(
            text="мастер не приходил",
            utterance_id="u-corr-0",
            mission=mission,
            delivered_goal_id="repair_completed",
            delivered_question_phase=QuestionPhase.DELIVERED.value,
            context=ctx,
        )
    )
    assert not any(a.goal_id == "worker_visited" for a in no_marker.goal_answers)

    marked = p.understand(
        MissionUnderstandingRequest(
            text="На самом деле мастер не приходил",
            utterance_id="u-corr-1",
            mission=mission,
            delivered_goal_id="repair_completed",
            delivered_question_phase=QuestionPhase.DELIVERED.value,
            context=ctx,
        )
    )
    by_id = {a.goal_id: a for a in marked.goal_answers}
    assert "worker_visited" in by_id
    assert by_id["worker_visited"].value == "no"
    assert by_id["worker_visited"].is_correction is True


def test_e_free_text_rejects_user_question() -> None:
    """E: free_text must not eat user questions; names still ok; refusal → declined."""
    mission = CallMission(
        mission_id="name-check",
        goals=(
            GoalDefinition(
                goal_id="contact_name",
                prompt_hint="Как вас зовут?",
                answer_type="free_text",
                allowed_values=(),
                priority=10,
            ),
        ),
    )
    p = DeterministicMissionUnderstandingProvider()
    q = p.understand(_req("А зачем вы это спрашиваете?", mission, "contact_name"))
    assert q.goal_answers == ()
    assert q.user_question is not None
    assert "зачем" in q.user_question.casefold()

    name = p.understand(_req("Иван Петров", mission, "contact_name"))
    assert len(name.goal_answers) == 1
    assert name.goal_answers[0].value == "Иван Петров"

    declined = p.understand(_req("Не хочу говорить", mission, "contact_name"))
    assert declined.goal_answers == ()
    assert any(d.disposition == "declined" for d in declined.goal_dispositions)


def test_no_domain_dictionaries_in_deterministic_mission() -> None:
    src = Path("packages/dialogue_engine/deterministic_mission.py").read_text(
        encoding="utf-8"
    )
    for banned in (
        "оплатил",
        "приходил",
        "заплатил",
        "слома",
        "еле работает",
        "utilities_paid",
        "worker_visited",
        "groceries_help",
        "сантехник",
        "таблет",
    ):
        assert banned not in src, f"domain/mission token leaked: {banned}"


# ---------------------------------------------------------------------------
# P0 predicate-negation / question / uncertainty — mandatory A–I
# ---------------------------------------------------------------------------


def _answers_by_id(result):
    return {a.goal_id: a for a in result.goal_answers}


def test_p0_a_predicate_negation_master_did_not_come() -> None:
    """A: «мастер не приходил» → worker_visited=no (predicate grounded)."""
    mission = _repair_mission()
    p = DeterministicMissionUnderstandingProvider()
    result = p.understand(_req("мастер не приходил", mission, "worker_visited"))
    by_id = _answers_by_id(result)
    assert by_id["worker_visited"].value == "no"
    assert "не приходил" in by_id["worker_visited"].evidence.casefold()


def test_p0_b_tak_i_ne_prihodil_is_no() -> None:
    """B: «так и не приходил» → worker_visited=no."""
    mission = _repair_mission()
    p = DeterministicMissionUnderstandingProvider()
    result = p.understand(_req("так и не приходил", mission, "worker_visited"))
    by_id = _answers_by_id(result)
    assert by_id["worker_visited"].value == "no"


def test_p0_c_ne_skazal_must_not_be_worker_no() -> None:
    """C: «мастер не сказал, когда придёт» must NOT become worker_visited=no."""
    mission = _repair_mission()
    p = DeterministicMissionUnderstandingProvider()
    result = p.understand(
        _req("мастер не сказал, когда придёт", mission, "worker_visited")
    )
    assert not any(
        a.goal_id == "worker_visited" and a.value == "no" for a in result.goal_answers
    )
    assert not any(a.goal_id == "worker_visited" for a in result.goal_answers) or all(
        a.value != "no" for a in result.goal_answers if a.goal_id == "worker_visited"
    )


def test_p0_d_ne_zvonil_must_not_be_worker_no_or_hangup() -> None:
    """D: «мастер мне не звонил» must NOT be worker_visited=no or stop_call."""
    mission = _repair_mission()
    p = DeterministicMissionUnderstandingProvider()
    result = p.understand(_req("мастер мне не звонил", mission, "worker_visited"))
    assert result.control != "stop_call"
    assert not any(
        a.goal_id == "worker_visited" and a.value == "no" for a in result.goal_answers
    )


def test_p0_e_kran_ne_pochinili_is_no() -> None:
    """E: «кран не починили» → repair_completed=no."""
    mission = _repair_mission()
    p = DeterministicMissionUnderstandingProvider()
    result = p.understand(_req("кран не починили", mission, "worker_visited"))
    by_id = _answers_by_id(result)
    assert by_id["repair_completed"].value == "no"
    assert "не починил" in by_id["repair_completed"].evidence.casefold()


def test_p0_f_pro_kran_ne_skazali_must_not_be_repair_no() -> None:
    """F: «про кран мне ничего не сказали» must NOT become repair_completed=no."""
    mission = _repair_mission()
    p = DeterministicMissionUnderstandingProvider()
    result = p.understand(
        _req("про кран мне ничего не сказали", mission, "worker_visited")
    )
    assert not any(
        a.goal_id == "repair_completed" and a.value == "no"
        for a in result.goal_answers
    )


def test_p0_g_question_ne_skazal_is_user_question_not_fact() -> None:
    """G: «Мастер не сказал, когда придёт?» → user_question, no worker fact."""
    mission = _repair_mission()
    p = DeterministicMissionUnderstandingProvider()
    text = "Мастер не сказал, когда придёт?"
    result = p.understand(_req(text, mission, "worker_visited"))
    assert result.user_question is not None
    assert not any(a.goal_id == "worker_visited" for a in result.goal_answers)


def test_p0_h_question_ne_pochinil_not_repair_fact() -> None:
    """H: «Кран он не починил?» → user_question/unclear, no repair factual."""
    mission = _repair_mission()
    p = DeterministicMissionUnderstandingProvider()
    text = "Кран он не починил?"
    result = p.understand(_req(text, mission, "repair_completed"))
    assert result.user_question is not None
    assert not any(a.goal_id == "repair_completed" for a in result.goal_answers)
    assert any(
        d.goal_id == "repair_completed" and d.disposition == "unclear"
        for d in result.goal_dispositions
    )


def test_p0_i_mixed_answer_plus_question_and_uncertainty_unclear() -> None:
    """I: mixed fact+question binds; uncertainty+negation → UNCLEAR not hard no."""
    mission = _repair_mission()
    p = DeterministicMissionUnderstandingProvider()

    mixed = p.understand(
        _req("Да, мастер приходил, а кто вы?", mission, "worker_visited")
    )
    by_id = _answers_by_id(mixed)
    assert by_id["worker_visited"].value == "yes"
    assert mixed.user_question is not None

    uncertain = p.understand(
        _req("Кажется, кран не починили.", mission, "worker_visited")
    )
    assert not any(
        a.goal_id == "repair_completed" and a.value in {"yes", "no"}
        for a in uncertain.goal_answers
    )
    assert any(
        d.goal_id == "repair_completed" and d.disposition == "unclear"
        for d in uncertain.goal_dispositions
    )


def test_p0_near_miss_extra_false_facts_blocked() -> None:
    """Near-miss phrases of the same bug class must not write false facts."""
    mission = _repair_mission()
    p = DeterministicMissionUnderstandingProvider()

    # Topic + unrelated negation (wrote / called / explained).
    for text in (
        "мастер не написал адрес",
        "про мастера мне ничего не объяснили",
        "кран он не показал, где течёт",
    ):
        result = p.understand(_req(text, mission, "worker_visited"))
        assert not any(
            a.goal_id == "worker_visited" and a.value == "no"
            for a in result.goal_answers
        ), text
        assert not any(
            a.goal_id == "repair_completed" and a.value == "no"
            for a in result.goal_answers
        ), text

    # Uncertainty softens even clear-looking predicate negation.
    soft = p.understand(
        _req("Наверное, мастер не приходил", mission, "worker_visited")
    )
    assert not any(
        a.goal_id == "worker_visited" and a.value == "no" for a in soft.goal_answers
    )
    assert any(
        d.goal_id == "worker_visited" and d.disposition == "unclear"
        for d in soft.goal_dispositions
    )

    # Bare unknown still maps to unknown (not unclear / not hangup).
    unk = p.understand(_req("не знаю", mission, "worker_visited"))
    assert unk.goal_answers[0].value == "unknown"
    assert unk.control != "stop_call"


def test_p0_j_unable_to_find_out_is_not_worker_no() -> None:
    """«про мастера не удалось узнать» must NOT become worker_visited=no."""
    mission = _repair_mission()
    p = DeterministicMissionUnderstandingProvider()
    result = p.understand(
        _req("про мастера не удалось узнать", mission, "worker_visited")
    )
    assert not any(
        a.goal_id == "worker_visited" and a.value == "no" for a in result.goal_answers
    )


def test_p0_k_unable_to_contact_is_not_repair_no() -> None:
    """«по крану не удалось связаться с мастером» must NOT be repair_completed=no."""
    mission = _repair_mission()
    p = DeterministicMissionUnderstandingProvider()
    result = p.understand(
        _req("по крану не удалось связаться с мастером", mission, "worker_visited")
    )
    assert not any(
        a.goal_id == "repair_completed" and a.value == "no"
        for a in result.goal_answers
    )


def test_p0_l_hints_authoritative_direct_worker_and_repair_no() -> None:
    """Direct predicate negation still binds when semantic_hints cover the verb."""
    mission = _repair_mission()
    p = DeterministicMissionUnderstandingProvider()
    worker = p.understand(_req("мастер не приходил", mission, "worker_visited"))
    assert _answers_by_id(worker)["worker_visited"].value == "no"
    repair = p.understand(_req("кран не починили", mission, "worker_visited"))
    assert _answers_by_id(repair)["repair_completed"].value == "no"


def test_p0_m_uncertain_delivered_yes_is_unclear() -> None:
    """«Да, кажется мастер приходил.» → NOT hard worker_visited=yes → UNCLEAR."""
    mission = _repair_mission()
    p = DeterministicMissionUnderstandingProvider()
    result = p.understand(
        _req("Да, кажется мастер приходил.", mission, "worker_visited")
    )
    assert not any(
        a.goal_id == "worker_visited" and a.value in {"yes", "no"}
        for a in result.goal_answers
    )
    assert any(
        d.goal_id == "worker_visited" and d.disposition == "unclear"
        for d in result.goal_dispositions
    )


def test_p0_n_mixed_certain_plus_uncertain_clause_local() -> None:
    """Certain worker yes + uncertain repair clause → worker=yes, repair UNCLEAR."""
    mission = _repair_mission()
    p = DeterministicMissionUnderstandingProvider()
    result = p.understand(
        _req(
            "Да, мастер приходил, но кажется кран не починили.",
            mission,
            "worker_visited",
        )
    )
    by_id = _answers_by_id(result)
    assert by_id["worker_visited"].value == "yes"
    assert not any(
        a.goal_id == "repair_completed" and a.value in {"yes", "no"}
        for a in result.goal_answers
    )
    assert any(
        d.goal_id == "repair_completed" and d.disposition == "unclear"
        for d in result.goal_dispositions
    )


def test_p0_o_empty_semantic_hints_no_free_negation_guess() -> None:
    """Empty semantic_hints: free negative phrase must not invent factual no."""
    mission = CallMission(
        mission_id="no-hints",
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
                semantic_hints=(),
            ),
        ),
    )
    p = DeterministicMissionUnderstandingProvider()
    guessed = p.understand(_req("мастер не приходил", mission, "worker_visited"))
    assert not any(
        a.goal_id == "worker_visited" and a.value == "no" for a in guessed.goal_answers
    )
    bare = p.understand(_req("нет", mission, "worker_visited"))
    assert bare.goal_answers[0].value == "no"
