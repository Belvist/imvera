"""RichUserTurn — canonical turn meaning for DialogueEngine."""

from __future__ import annotations

from dataclasses import dataclass

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
from packages.dialogue_engine.semantic import SemanticTurn
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
    episode_attributes: tuple = ()

    correction: bool = False
    not_recalled: bool = False

    semantic_spans: tuple[SemanticSpan, ...] = ()
    semantic_relations: tuple[SemanticRelation, ...] = ()
    observations: tuple[Observation, ...] = ()
    kernel_confidence: float = 1.0
    kernel_ambiguities: tuple[str, ...] = ()
    kernel_level: int = 1
    kernel_route: str = ""
    kernel_elapsed_ms: float = 0.0
    kernel_corrections: tuple = ()
    # Cut A: retired from the live path (always None now). Field kept for
    # trace/contract compatibility (reluctance.py reads it defensively).
    tiny_route: str | None = None

    model_config = {"frozen": True}


@dataclass(frozen=True)
class StrategyVote:
    """One producer's proposal inside a single resolution (trace only)."""

    strategy: str
    elapsed_ms: float
    confident: bool
    detail: str = ""


@dataclass(frozen=True)
class ResolvedTurn:
    """Canonical turn plus producer/adjudication trace.

    With no act candidate, preserves the text builder's behavior. An
    explicit non-generative candidate is fused before the reducer sees it.
    """

    turn: RichUserTurn
    trace: tuple[StrategyVote, ...]
    interpret_path: str
    total_elapsed_ms: float


class TurnUnderstandingV2:
    """Single resolution facade: grounded producers and bounded act votes."""

    def apply_act_candidate(
        self,
        turn: RichUserTurn,
        candidate: SemanticTurn | None,
        *,
        confident: bool,
        engine_state: object | None = None,
    ) -> tuple[RichUserTurn, bool, str]:
        """Fuse a non-generative act vote into the turn the reducer consumes.

        A dialogue act is not an answer/value extractor. Grounded facts,
        deterministic controls, risk and questions retain precedence. Return
        the applied flag and reason so trace never calls an ignored vote used.
        """
        from packages.dialogue_engine.mission_grounding import evidence_grounded_in_utterance
        from packages.dialogue_engine.semantic import SemanticAct
        from packages.dialogue_engine.semantic_nlp.model import CONFIDENCE_THRESHOLD

        if not confident or candidate is None:
            return turn, False, "abstained"
        if getattr(candidate, "confidence", 0.0) < CONFIDENCE_THRESHOLD:
            return turn, False, "below_confidence_threshold"
        if not evidence_grounded_in_utterance(
            getattr(candidate, "source_quote", ""), turn.raw_text
        ):
            return turn, False, "candidate_evidence_not_grounded"
        if turn.dialogue_act == "repair" and turn.kernel_route == "kernel_l0":
            return turn, False, "deterministic_repair_wins"
        if (
            turn.control not in {"", "none"} or turn.risk_candidates or turn.user_question
            or turn.consent_answer != "not_applicable"
        ):
            return turn, False, "protected_control_risk_or_question"
        if (
            turn.issue_mentions or turn.goal_facts or turn.observations
            or turn.correction or turn.goal_dispositions
        ):
            return turn, False, "grounded_meaning_wins"
        if engine_state is not None and turn.goal_answers:
            from packages.dialogue_engine.mission_grounding import filter_grounded_goal_answers
            from packages.dialogue_engine.mission_seed import mission_from_state

            mission = mission_from_state(engine_state)
            typed_goals = {
                goal.goal_id for goal in mission.goals if goal.answer_type != "free_text"
            }
            grounded = filter_grounded_goal_answers(
                turn.goal_answers, mission=mission, utterance=turn.raw_text,
            )
            if any(answer.goal_id in typed_goals for answer in grounded):
                return turn, False, "grounded_meaning_wins"
        act = getattr(candidate, "act", None)
        if act == SemanticAct.BACKCHANNEL and engine_state is not None:
            from packages.dialogue_engine.reducer import (
                _AFFIRM_ONLY,
                _DENY_ONLY,
                _is_yes_no_question,
            )

            question = getattr(engine_state, "delivered_question", None)
            word = turn.raw_text.strip().lower().rstrip(".!?…")
            if (
                question and _is_yes_no_question(question.text)
                and word in (_AFFIRM_ONLY | _DENY_ONLY)
            ):
                return turn, False, "delivered_yes_no_answer_wins"
        mapping = {
            SemanticAct.BACKCHANNEL: "backchannel",
            SemanticAct.REPAIR_REQUEST: "repair",
            SemanticAct.ANSWER: "answer",
        }
        if act not in mapping:
            # Goodbye, stop and safety remain deterministic, even if a model
            # proposes one of them with high confidence.
            return turn, False, "act_requires_deterministic_control"
        not_recalled = bool(getattr(candidate, "not_recalled", False))
        updates = {
            "dialogue_act": mapping[act],
            # Recognizing an answer act does not prove its relation to the
            # delivered question. Preserve Understand's answer binding.
            "answers_pending_question": act == SemanticAct.ANSWER and turn.answers_pending_question,
            "not_recalled": not_recalled,
        }
        if act != SemanticAct.ANSWER or not_recalled:
            # Context binding alone may have guessed a free-text answer.
            # A repair/backchannel/not-recalled vote cannot become that fact.
            updates["goal_answers"] = ()
        return turn.model_copy(update=updates), True, "applied_to_canonical_turn"

    def resolve(
        self,
        text: str,
        *,
        utterance_id: str,
        engine_state: object | None = None,
        mission_provider: object | None = None,
        act_candidate: SemanticTurn | None = None,
        candidate_confident: bool = False,
    ) -> ResolvedTurn:
        import time

        started = time.monotonic()
        votes: list[StrategyVote] = []
        step = time.monotonic()
        turn = build_rich_turn_from_text(
            text,
            utterance_id=utterance_id,
            engine_state=engine_state,
            mission_provider=mission_provider,
        )
        votes.append(
            StrategyVote(
                strategy="build_rich_turn_from_text",
                elapsed_ms=round((time.monotonic() - step) * 1000.0, 2),
                confident=True,
                detail="legacy canonical path, delegated verbatim",
            )
        )
        if act_candidate is not None:
            step = time.monotonic()
            turn, applied, reason = self.apply_act_candidate(
                turn, act_candidate, confident=candidate_confident, engine_state=engine_state
            )
            votes.append(StrategyVote(
                strategy="act_candidate_resolution",
                elapsed_ms=round((time.monotonic() - step) * 1000.0, 2),
                confident=applied,
                detail=reason,
            ))
        return ResolvedTurn(
            turn=turn,
            trace=tuple(votes),
            interpret_path="v2_resolve",
            total_elapsed_ms=round((time.monotonic() - started) * 1000.0, 2),
        )

    def adjudicate_final(
        self,
        *,
        use_rich_deterministic: bool,
        rich_turn: RichUserTurn | None,
        fast_confident: bool,
        kernel_has_meaning: bool,
        sem: object,
        incoming_path: str,
        legacy_state: object,
        text: str,
        fsm_override: object = None,
    ) -> tuple[object, str]:
        """Single-resolver final choice, verbatim precedence of the CallActor
        inline branches (P2 Cut 2). Returns (interp, interpret_path).
        No producer moved here — only the choice."""
        from packages.dialogue.interpretation import interpret_user_turn
        from packages.dialogue_engine.semantic import semantic_to_interpretation

        if use_rich_deterministic and rich_turn is not None:
            if (
                fast_confident
                and not rich_turn.issue_mentions
                and not kernel_has_meaning
            ):
                return semantic_to_interpretation(sem), incoming_path
            return (
                interpret_user_turn(
                    legacy_state, text, fsm_override=fsm_override
                ),
                incoming_path,
            )
        if not fast_confident:
            return (
                interpret_user_turn(
                    legacy_state, text, fsm_override=fsm_override
                ),
                "rules_fallback",
            )
        return semantic_to_interpretation(sem), incoming_path


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
    from packages.dialogue_engine.mission import GoalAnswerCandidate, GoalDispositionCandidate

    enriched = enrich_payload_issue_mentions(payload, raw_text)
    goal_facts = tuple(enriched.facts) or extract_goal_facts(raw_text)
    correction = enriched.dialogue_act == "correction" or detect_correction(raw_text)
    user_q = enriched.user_question or detect_user_question(raw_text)
    goal_answers = tuple(
        GoalAnswerCandidate(
            goal_id=a.goal_id,
            value=a.value,
            confidence=a.confidence,
            evidence=a.evidence,
            is_correction=a.is_correction,
        )
        for a in getattr(enriched, "goal_answers", ()) or ()
    )
    goal_dispositions = tuple(
        GoalDispositionCandidate(
            goal_id=d.goal_id,
            disposition=d.disposition,
            confidence=d.confidence,
            evidence=d.evidence,
        )
        for d in getattr(enriched, "goal_dispositions", ()) or ()
    )
    # Do not persist raw observation_notes as SPEAKER facts. A typed
    # ObservationSemantic contract (subject + evidence ∈ utterance) is required
    # before atomic apply; until then notes stay ephemeral on the payload only.
    observations: list = []
    episode_attrs = getattr(enriched, "episode_attributes", ()) or ()
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
        goal_answers=goal_answers,
        goal_dispositions=goal_dispositions,
        issue_mentions=tuple(enriched.issue_mentions),
        risk_candidates=tuple(enriched.risk_candidates),
        correction=correction,
        observations=tuple(observations),
        episode_attributes=tuple(episode_attrs),
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
    """Adjudicate all harvesters into one canonical, context-owned turn."""
    from packages.dialogue_engine.deterministic_mission import (
        _unowned_positive_wellness_evaluation,
    )

    turn = _build_rich_turn_from_text(
        text, utterance_id=utterance_id,
        engine_state=engine_state, mission_provider=mission_provider,
    )
    if any(f.field == "wellness" for f in turn.goal_facts) and (
        _unowned_positive_wellness_evaluation(text, positive_proposed=any(
            f.field == "wellness" and f.value == "positive" for f in turn.goal_facts
        ))
    ):
        return turn.model_copy(update={
            "goal_facts": tuple(f for f in turn.goal_facts if f.field != "wellness"),
        })
    return turn


def _build_rich_turn_from_text(
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
        attach_mission=False,
    )
    turn = attach_mission_understanding(
        turn, engine_state=engine_state, provider=mission_provider
    )
    from packages.dialogue_engine.discourse import is_listening_evaluation

    if is_listening_evaluation(engine_state, text):
        # A response to the actual listening question is an evaluation of
        # the story, not an answer to an unasked medical question.
        return turn.model_copy(update={
            "goal_facts": tuple(f for f in turn.goal_facts if f.field != "wellness"),
        })
    if engine_state is not None and hasattr(engine_state, "answer_context_slot"):
        from packages.dialogue_engine.context import InterpretContext
        from packages.dialogue_engine.contextual_interpreter import contextual_interpret

        ctx = InterpretContext.from_engine_state(engine_state, turn_id=utterance_id)
        sem, confident = contextual_interpret(text.strip(), ctx)
        try:
            from packages.dialogue_engine.policy import (
                _is_other_person_only as _turn_other_only,
            )

            if _turn_other_only(text.strip()):
                # Other person's complaint alone: no speaker facts from any
                # harvester (mission path already filters; legacy must agree).
                sem = sem.model_copy(update={"slots": {}}) if hasattr(sem, "model_copy") else sem
                harvested = {}
            else:
                harvested = {
                    f.field: f
                    for f in extract_goal_facts(text.strip(), answer_slot=answer_slot)
                }
        except Exception:  # noqa: BLE001
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
            # Single attach (P2 Cut 3): the attach above already ran with
            # identical inputs; re-attaching only recomputes the same result.
            return turn
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
        return turn
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
    return turn


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
