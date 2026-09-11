"""RichUserTurn — canonical turn meaning for DialogueEngine."""

from __future__ import annotations

from pydantic import BaseModel

from packages.contracts.semantic import (
    Evidence,
    FactCandidate,
    IssueMention,
    RiskCandidate,
    SemanticPayload,
)
from packages.dialogue_engine.evidence_invariant import sanitize_issue_mention
from packages.dialogue_engine.issue_mention_extract import (
    detect_correction,
    detect_user_question,
    extract_goal_facts,
    extract_issue_mentions,
)
from packages.dialogue_engine.mission import GoalAnswerCandidate
from packages.dialogue_engine.semantic_kernel.types import (
    Observation,
    SemanticRelation,
    SemanticSpan,
)


class RichUserTurn(BaseModel):
    utterance_id: str
    raw_text: str

    dialogue_act: str
    control: str
    consent_answer: str = "not_applicable"

    answers_pending_question: bool
    needs_clarification: bool

    user_question: str | None = None

    goal_facts: tuple[FactCandidate, ...] = ()
    goal_answers: tuple[GoalAnswerCandidate, ...] = ()
    goal_dispositions: tuple = ()
    issue_mentions: tuple[IssueMention, ...] = ()
    risk_candidates: tuple[RiskCandidate, ...] = ()

    correction: bool = False

    semantic_spans: tuple[SemanticSpan, ...] = ()
    semantic_relations: tuple[SemanticRelation, ...] = ()
    observations: tuple[Observation, ...] = ()
    kernel_confidence: float = 1.0
    kernel_ambiguities: tuple[str, ...] = ()
    kernel_level: int = 1
    kernel_route: str = ""
    kernel_elapsed_ms: float = 0.0
    kernel_corrections: tuple = ()

    model_config = {"frozen": True}


def enrich_payload_issue_mentions(
    payload: SemanticPayload,
    raw_text: str,
) -> SemanticPayload:
    """Validate LLM mentions; emergency regex fallback only when field is empty."""
    if payload.issue_mentions:
        validated = tuple(
            m
            for m in (
                sanitize_issue_mention(mention, raw_text)
                for mention in payload.issue_mentions
            )
            if m is not None
        )
        return payload.model_copy(update={"issue_mentions": validated})
    extracted = extract_issue_mentions(raw_text)
    if not extracted:
        return payload
    return payload.model_copy(update={"issue_mentions": extracted})


def payload_to_rich_turn(
    payload: SemanticPayload,
    *,
    utterance_id: str,
    raw_text: str,
) -> RichUserTurn:
    enriched = enrich_payload_issue_mentions(payload, raw_text)
    goal_facts = tuple(enriched.facts) or extract_goal_facts(raw_text)
    correction = enriched.dialogue_act == "correction" or detect_correction(raw_text)
    user_q = enriched.user_question or detect_user_question(raw_text)
    return RichUserTurn(
        utterance_id=utterance_id,
        raw_text=raw_text,
        dialogue_act=enriched.dialogue_act,
        control=enriched.control,
        consent_answer=enriched.consent_answer,
        answers_pending_question=enriched.answers_pending_question,
        needs_clarification=enriched.needs_clarification,
        user_question=user_q,
        goal_facts=goal_facts,
        issue_mentions=tuple(enriched.issue_mentions),
        risk_candidates=tuple(enriched.risk_candidates),
        correction=correction,
    )


def build_rich_turn_from_payload(
    payload: SemanticPayload,
    *,
    utterance_id: str,
    raw_text: str,
) -> RichUserTurn:
    return payload_to_rich_turn(payload, utterance_id=utterance_id, raw_text=raw_text)


def attach_mission_understanding(
    turn: RichUserTurn,
    *,
    engine_state: object | None,
    provider: object | None = None,
) -> RichUserTurn:
    """Merge provider StructuredMissionResult into RichUserTurn. No EngineState writes."""
    if engine_state is None or not getattr(engine_state, "mission_catalog", None):
        return turn
    from packages.dialogue_engine.mission_context import build_mission_understanding_context
    from packages.dialogue_engine.mission_seed import mission_from_state
    from packages.dialogue_engine.mission_understanding import (
        MissionUnderstandingRequest,
        understand_mission,
    )
    from packages.dialogue_engine.state import QuestionPhase

    mission = mission_from_state(engine_state)  # type: ignore[arg-type]
    if not mission.goals:
        return turn
    ctx = build_mission_understanding_context(engine_state)  # type: ignore[arg-type]
    dq = getattr(engine_state, "delivered_question", None)
    delivered_goal = None
    delivered_text = None
    delivered_phase = None
    if dq is not None and getattr(dq, "phase", None) == QuestionPhase.DELIVERED:
        delivered_goal = dq.goal_id or dq.slot
        delivered_text = dq.text
        delivered_phase = dq.phase.value
    result = understand_mission(
        MissionUnderstandingRequest(
            text=turn.raw_text,
            utterance_id=turn.utterance_id,
            mission=mission,
            active_goal_id=delivered_goal,
            delivered_goal_id=delivered_goal,
            delivered_question_text=delivered_text,
            delivered_question_phase=delivered_phase,
            context=ctx,
        ),
        provider=provider,  # type: ignore[arg-type]
    )
    observations = tuple(turn.observations) + tuple(
        o
        for o in result.observations
        if o.observation_id not in {x.observation_id for x in turn.observations}
    )
    existing_labels = {m.label.lower() for m in turn.issue_mentions}
    extra_mentions = tuple(
        m for m in result.issue_mentions if m.label.lower() not in existing_labels
    )
    mentions = tuple(turn.issue_mentions) + extra_mentions
    updates: dict = {
        "goal_answers": result.goal_answers,
        "goal_dispositions": result.goal_dispositions,
        "observations": observations,
        "issue_mentions": mentions,
    }
    if result.user_question and not turn.user_question:
        updates["user_question"] = result.user_question
    if result.control and result.control != "none" and turn.control in {"", "none"}:
        updates["control"] = result.control
    return turn.model_copy(update=updates)


def build_rich_turn_from_text(
    text: str,
    *,
    utterance_id: str,
    engine_state: object | None = None,
    mission_provider: object | None = None,
) -> RichUserTurn:
    """Semantic Kernel → RichUserTurn (canonical NLU path)."""
    from packages.dialogue_engine.semantic_kernel.kernel import interpret, kernel_to_rich_turn

    result = interpret(text, utterance_id=utterance_id, engine_state=engine_state)
    answer_slot = None
    if engine_state is not None and hasattr(engine_state, "answer_context_slot"):
        answer_slot = engine_state.answer_context_slot()
    turn = kernel_to_rich_turn(
        result,
        answer_slot=answer_slot,
        engine_state=engine_state,
        mission_provider=mission_provider,
    )
    turn = attach_mission_understanding(
        turn, engine_state=engine_state, provider=mission_provider
    )
    if engine_state is not None and hasattr(engine_state, "answer_context_slot"):
        from packages.dialogue_engine.context import InterpretContext
        from packages.dialogue_engine.contextual_interpreter import contextual_interpret

        ctx = InterpretContext.from_engine_state(engine_state, turn_id=utterance_id)
        sem, confident = contextual_interpret(text.strip(), ctx)
        harvested = {
            f.field: f
            for f in extract_goal_facts(text.strip(), answer_slot=answer_slot)
        }
        for f in turn.goal_facts:
            harvested.setdefault(f.field, f)
        if confident and sem.slots:
            raw = text.strip()
            multi_slot = len(sem.slots) >= 2
            for slot_name, cand in sem.slots.items():
                if slot_name not in ("wellness", "mood", "sleep", "plans"):
                    continue
                if not multi_slot and answer_slot and slot_name != answer_slot:
                    continue
                if slot_name in harvested and harvested[slot_name].value in (
                    "positive",
                    "negative",
                    "uncertain",
                    "neutral",
                ):
                    continue
                value = cand.value or raw
                harvested[slot_name] = FactCandidate(
                    field=slot_name,
                    value=value,
                    subject="speaker",
                    temporal_scope="now",
                    negated=False,
                    evidence=Evidence(start=0, end=len(raw), quote=raw),
                )
        if harvested:
            turn = turn.model_copy(update={"goal_facts": tuple(harvested.values())})
            return attach_mission_understanding(
                turn, engine_state=engine_state, provider=mission_provider
            )
        return turn
    if turn.goal_facts or not answer_slot:
        return turn
    from packages.dialogue_engine.fast_interpreter import fast_interpret_semantic

    sem, confident = fast_interpret_semantic(text.strip(), answer_slot=answer_slot)
    if (
        not confident
        or not sem.target_slot
        or sem.target_slot not in ("wellness", "mood", "sleep", "plans")
    ):
        harvested = extract_goal_facts(text.strip(), answer_slot=answer_slot)
        if harvested:
            turn = turn.model_copy(update={"goal_facts": harvested})
        return attach_mission_understanding(
            turn, engine_state=engine_state, provider=mission_provider
        )
    value = sem.value or text.strip()
    fact = FactCandidate(
        field=sem.target_slot,
        value=value,
        subject="speaker",
        temporal_scope="now",
        negated=False,
        evidence=Evidence(start=0, end=len(text.strip()), quote=text.strip()),
    )
    harvested = {f.field: f for f in extract_goal_facts(text.strip(), answer_slot=answer_slot)}
    harvested.setdefault(fact.field, fact)
    turn = turn.model_copy(update={"goal_facts": tuple(harvested.values())})
    return attach_mission_understanding(
        turn, engine_state=engine_state, provider=mission_provider
    )


def build_rich_turn_from_text_legacy(text: str, *, utterance_id: str) -> RichUserTurn:
    """LEVEL0 compatibility helper — issue_mention_extract only."""
    raw = text.strip()
    dialogue_act = "answer"
    if detect_correction(raw):
        dialogue_act = "correction"
    elif detect_user_question(raw):
        dialogue_act = "question"
    elif raw.lower() in {"угу", "ага", "да", "нет"}:
        dialogue_act = "backchannel"
    payload = SemanticPayload(
        dialogue_act=dialogue_act,
        control="none",
        consent_answer="not_applicable",
        answers_pending_question=dialogue_act == "answer",
        needs_clarification=False,
        facts=extract_goal_facts(raw),
        issue_mentions=extract_issue_mentions(raw),
    )
    return payload_to_rich_turn(payload, utterance_id=utterance_id, raw_text=raw)


def rich_turn_has_episode_content(turn: RichUserTurn) -> bool:
    return bool(turn.issue_mentions) or turn.correction or turn.user_question
