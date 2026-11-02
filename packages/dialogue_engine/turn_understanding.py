"""RichUserTurn — canonical turn meaning for DialogueEngine."""

from __future__ import annotations

import re
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
    requires_scoped_goal_evidence,
)
from packages.dialogue_engine.mission import GoalAnswerCandidate
from packages.dialogue_engine.semantic import SemanticTurn
from packages.dialogue_engine.semantic_kernel.types import (
    Observation,
    SemanticKernelResult,
    SemanticRelation,
    SemanticSpan,
    SpanType,
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


def _asserted_question_ranges(text: str) -> tuple[tuple[int, int], ...]:
    """Literal assertion ranges, excluding generic questions/conditionals/quotes.

    Declarative symptoms can imply the speaker; an interrogative clause needs
    explicit speaker evidence to make the same assertion. This is grammar and
    subject ownership, independent of any symptom or question phrase catalog.
    """
    from packages.dialogue_engine.semantic_kernel.clauses import clause_bounds
    from packages.dialogue_engine.semantic_kernel.morphology import normalize_text
    from packages.dialogue_engine.semantic_kernel.subject_resolver import _subject_for_clause
    from packages.dialogue_engine.semantic_kernel.types import SubjectKind

    quotes = [(match.start(), match.end()) for match in re.finditer(
        r'«[^»]*»|“[^”]*”|"[^"]*"', text,
    )]
    interrogatives = {"почему", "зачем", "как", "когда", "какой", "что", "кто",
                     "сколько", "где", "куда", "откуда"}
    ranges = []
    conditional = False
    previous_end = 0
    clauses = clause_bounds(text)
    for index, (start, end, _) in enumerate(clauses):
        if any(mark in text[previous_end:start] for mark in ".!?…"):
            conditional = False
        previous_end = end
        visible = list(text[start:end])
        for left, right in quotes:
            for pos in range(max(left, start), min(right, end)):
                visible[pos - start] = " "
        visible_text = "".join(visible)
        words = normalize_text(visible_text).split()
        if not words:
            continue
        conditional = conditional or "если" in words or "бы" in words
        head = next((word for word in words if word not in {"а", "но", "ну", "ой"}), "")
        following = clauses[index + 1][0] if index + 1 < len(clauses) else len(text)
        question_clause = head in interrogatives or "?" in text[end:following]
        explicit_speaker = _subject_for_clause(visible_text, has_issue=False) == SubjectKind.SPEAKER
        if conditional or (question_clause and not explicit_speaker):
            continue
        # Keep exact offsets: quoted speaker words cannot make the surrounding
        # clause a personal report, and quoted symptom words are never facts.
        cursor = start
        for left, right in quotes:
            if right <= cursor or left >= end:
                continue
            if cursor < left:
                ranges.append((cursor, left))
            cursor = max(cursor, right)
        if cursor < end:
            ranges.append((cursor, end))
    return tuple(ranges)


def _ground_question_assertions(turn: RichUserTurn, *, answer_slot: str | None) -> RichUserTurn:
    """Adjudicate all harvesters once; models/candidate spans never assert a question."""
    from packages.dialogue_engine.deterministic_mission import _is_user_question

    if turn.risk_candidates or not (turn.user_question or _is_user_question(turn.raw_text)):
        return turn
    ranges = _asserted_question_ranges(turn.raw_text)

    def accepted(quote: str) -> bool:
        return bool(quote.strip()) and any(
            quote.strip() in turn.raw_text[start:end] for start, end in ranges
        )

    def accepted_span(span) -> bool:
        return any(start <= span.start and span.end <= end for start, end in ranges)

    asserted_issues = [span for span in turn.semantic_spans
                       if span.type == SpanType.ISSUE and accepted_span(span)]
    asserted_sites = {span.normalized for span in turn.semantic_spans
                      if span.type == SpanType.BODY_SITE and accepted_span(span)}
    all_sites = {span.normalized for span in turn.semantic_spans if span.type == SpanType.BODY_SITE}
    asserted_issue_keys = {span.normalized for span in asserted_issues}

    facts = {}
    proposed_fields = {fact.field for fact in turn.goal_facts}
    proposed_values = {fact.field: fact.value for fact in turn.goal_facts}
    for start, end in ranges:
        clause = turn.raw_text[start:end]
        for fact in extract_goal_facts(clause, answer_slot=answer_slot):
            if fact.field not in proposed_fields:
                continue
            if fact.value in {"positive", "negative", "neutral", "uncertain"} and (
                fact.value != proposed_values[fact.field]
            ):
                continue
            evidence = fact.evidence
            if evidence is not None:
                fact = fact.model_copy(update={"evidence": evidence.model_copy(update={
                    "start": start + evidence.start, "end": start + evidence.end,
                })})
            facts.setdefault(fact.field, fact)
    # Grounded custom/model facts outside the classic harvester also survive.
    for fact in turn.goal_facts:
        if fact.evidence is not None and accepted(fact.evidence.quote):
            facts.setdefault(fact.field, fact)
    mentions = []
    for mention in turn.issue_mentions:
        evidence = mention.evidence
        if evidence is None or not accepted(evidence.quote):
            continue
        if mention.body_site in all_sites and mention.body_site not in asserted_sites:
            continue
        if not any(start <= evidence.start and evidence.end <= end for start, end in ranges):
            # Old mention conversion used the first global occurrence of the
            # predicate. Rebind only to an existing asserted literal span in
            # the same clause as this mention's body anchor.
            body_spans = [span for span in turn.semantic_spans
                          if span.type == SpanType.BODY_SITE
                          and span.normalized == mention.body_site and accepted_span(span)]
            matching = [span for span in asserted_issues if span.text == evidence.quote
                        and any(start <= span.start < end and any(
                            start <= body.start < end for body in body_spans
                        ) for start, end in ranges)]
            if len(matching) != 1:
                continue
            evidence = evidence.model_copy(update={
                "start": matching[0].start, "end": matching[0].end,
            })
            mention = mention.model_copy(update={"evidence": evidence})
        mentions.append(mention)
    observations = tuple(observation for observation in turn.observations
                         if accepted(observation.evidence)
                         and (not observation.body_site or observation.body_site in asserted_sites)
                         and (not observation.issue_normalized
                              or observation.issue_normalized in asserted_issue_keys))
    answers = tuple(answer for answer in turn.goal_answers if accepted(answer.evidence))
    dispositions = tuple(disposition for disposition in turn.goal_dispositions
                         if accepted(getattr(disposition, "evidence", "")))
    return turn.model_copy(update={
        "goal_facts": tuple(facts.values()), "issue_mentions": tuple(mentions),
        "observations": observations, "goal_answers": answers,
        "goal_dispositions": dispositions,
        "episode_attributes": turn.episode_attributes if mentions else (),
        "needs_clarification": turn.needs_clarification if mentions else False,
    })


class TurnUnderstandingV2:
    """Single resolution facade: grounded producers and bounded act votes."""

    def prepare_kernel(
        self,
        text: str,
        *,
        utterance_id: str,
        engine_state: object | None = None,
        answer_slot: str | None = None,
    ) -> SemanticKernelResult:
        """Read-only meaning for admission; final mission attachment comes later.

        Reuse the existing mission question recognizer before the fragment
        gate. Otherwise a complete open question beginning with ``А`` can be
        held as a fragment before the final producer has a chance to see it.
        Deterministic repairs and controls retain their kernel precedence.
        """
        from packages.dialogue_engine.deterministic_mission import _is_user_question
        from packages.dialogue_engine.mission_flow import is_conversation_navigation
        from packages.dialogue_engine.semantic_kernel.kernel import interpret

        if engine_state is not None and hasattr(engine_state, "answer_context_slot"):
            answer_slot = engine_state.answer_context_slot()
        result = interpret(
            text, utterance_id=utterance_id, engine_state=engine_state,
            answer_slot=answer_slot,
        )
        if (
            result.level != 0 and not result.user_question and result.control in ("", "none")
            and result.dialogue_act != "repair"
            and (_is_user_question(text) or is_conversation_navigation(text))
        ):
            updates = {"user_question": result.raw_text}
            asserted = _asserted_question_ranges(result.raw_text)
            if not any(
                span.type == SpanType.ISSUE
                and any(start <= span.start < end for start, end in asserted)
                for span in result.spans
            ) and not any(
                observation.evidence.strip()
                and any(observation.evidence.strip() in result.raw_text[start:end]
                        for start, end in asserted)
                for observation in result.observations
            ):
                updates["dialogue_act"] = "question"
            # A reported symptom remains a report even if a neighbouring
            # question contains '?'. Its grounded clinical need must preempt
            # the side question and release interrupted background ownership.
            result = result.model_copy(update=updates)
        return result

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
        precomputed_kernel_result: SemanticKernelResult | None = None,
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
            precomputed_kernel_result=precomputed_kernel_result,
        )
        votes.append(
            StrategyVote(
                strategy="build_rich_turn_from_text",
                elapsed_ms=round((time.monotonic() - step) * 1000.0, 2),
                confident=True,
                detail=("admitted kernel reused" if precomputed_kernel_result is not None
                        else "canonical kernel and grounded harvesters"),
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
    from packages.dialogue_engine.semantic_kernel.observation_memory import resolve_mention_subjects

    if payload.issue_mentions:
        validated = tuple(
            m
            for m in (
                sanitize_issue_mention(mention, raw_text)
                for mention in payload.issue_mentions
            )
            if m is not None
        )
        return payload.model_copy(update={
            "issue_mentions": resolve_mention_subjects(validated, raw_text),
        })
    extracted = extract_issue_mentions(raw_text)
    if not extracted:
        return payload
    return payload.model_copy(update={
        "issue_mentions": resolve_mention_subjects(extracted, raw_text),
    })


def payload_to_rich_turn(
    payload: SemanticPayload,
    *,
    utterance_id: str,
    raw_text: str,
) -> RichUserTurn:
    from packages.dialogue_engine.mission import GoalAnswerCandidate, GoalDispositionCandidate

    enriched = enrich_payload_issue_mentions(payload, raw_text)
    goal_facts = (extract_goal_facts(raw_text) if requires_scoped_goal_evidence(raw_text)
                  else tuple(enriched.facts) or extract_goal_facts(raw_text))
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
    precomputed_kernel_result: SemanticKernelResult | None = None,
) -> RichUserTurn:
    """Adjudicate all harvesters into one canonical, context-owned turn."""
    from packages.dialogue_engine.deterministic_mission import (
        _unowned_positive_wellness_evaluation,
    )

    turn = _build_rich_turn_from_text(
        text, utterance_id=utterance_id,
        engine_state=engine_state, mission_provider=mission_provider,
        precomputed_kernel_result=precomputed_kernel_result,
    )
    answer_slot = (engine_state.answer_context_slot()
                   if engine_state is not None and hasattr(engine_state, "answer_context_slot")
                   else None)
    turn = _ground_question_assertions(turn, answer_slot=answer_slot)
    if any(f.field == "wellness" for f in turn.goal_facts) and (
        _unowned_positive_wellness_evaluation(text, positive_proposed=any(
            f.field == "wellness" and f.value == "positive" for f in turn.goal_facts
        ))
    ):
        turn = turn.model_copy(update={
            "goal_facts": tuple(f for f in turn.goal_facts if f.field != "wellness"),
        })
    if (
        turn.user_question and turn.control in ("", "none")
        and not turn.goal_answers and not turn.goal_facts and not turn.issue_mentions
        and not turn.risk_candidates and not turn.correction
    ):
        # Mission understanding may recognize an open question beyond the
        # kernel's controls/identity grammar. Recognizing that question does
        # not answer the delivered medical question. Mixed grounded answers
        # retain their evidence and binding instead of being discarded.
        turn = turn.model_copy(update={
            "dialogue_act": "question", "answers_pending_question": False,
        })
    return turn


def _build_rich_turn_from_text(
    text: str,
    *,
    utterance_id: str,
    engine_state: object | None = None,
    mission_provider: object | None = None,
    precomputed_kernel_result: SemanticKernelResult | None = None,
) -> RichUserTurn:
    """Semantic Kernel → RichUserTurn (canonical NLU path)."""
    from packages.dialogue_engine.semantic_kernel.kernel import kernel_to_rich_turn

    answer_slot = None
    if engine_state is not None and hasattr(engine_state, "answer_context_slot"):
        answer_slot = engine_state.answer_context_slot()
    if precomputed_kernel_result is None:
        result = TurnUnderstandingV2().prepare_kernel(
            text, utterance_id=utterance_id, engine_state=engine_state,
            answer_slot=answer_slot,
        )
    else:
        result = precomputed_kernel_result
        if result.raw_text != text.strip() or result.utterance_id != utterance_id:
            raise ValueError("precomputed kernel result does not belong to this utterance")
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
        # Bare valence evaluates the heard story. It has no predicate
        # proving a health fact, even if an earlier question supplied context.
        standard = {"wellness", "mood", "sleep", "plans"}
        return turn.model_copy(update={
            "goal_facts": tuple(f for f in turn.goal_facts if f.field not in standard),
            "goal_answers": tuple(a for a in turn.goal_answers if a.goal_id not in standard),
            "goal_dispositions": tuple(
                d for d in turn.goal_dispositions if d.goal_id not in standard
            ),
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
        scoped = requires_scoped_goal_evidence(text)
        if not scoped:
            for f in turn.goal_facts:
                harvested.setdefault(f.field, f)
        if confident and sem.slots:
            raw = text.strip()
            multi_slot = len(sem.slots) >= 2
            for slot_name, cand in sem.slots.items():
                if slot_name not in ("wellness", "mood", "sleep", "plans"):
                    continue
                if slot_name == "plans" or scoped:
                    # Plans and mixed subjects require the fact owner's
                    # scoped evidence. Context must not resurrect rejected
                    # foreign facts or broaden a quote to the whole story.
                    continue
                if not multi_slot and answer_slot and slot_name != answer_slot:
                    continue
                if slot_name in harvested and harvested[slot_name].value in (
                    "positive", "negative", "uncertain", "neutral",
                ):
                    continue
                value = cand.value or raw
                if (slot_name == "sleep" and (owned := harvested.get(slot_name)) is not None
                        and owned.temporal_scope not in ("now", "today")):
                    # Context cannot redress explicitly historical sleep as
                    # today's answer merely because a check-in is pending.
                    continue
                if len(value) > 500:
                    # Canonical clause harvesting already owns bounded facts.
                    # A whole-turn contextual proposal cannot replace them or
                    # exceed the typed value limit for a long spoken narrative.
                    continue
                harvested[slot_name] = FactCandidate(
                    field=slot_name,
                    value=value,
                    subject="speaker",
                    temporal_scope="now",
                    negated=False,
                    evidence=Evidence(start=0, end=len(raw), quote=raw),
                )
        if harvested or scoped:
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
    harvested = {f.field: f for f in extract_goal_facts(text.strip(), answer_slot=answer_slot)}
    if sem.target_slot == "plans":
        if harvested:
            turn = turn.model_copy(update={"goal_facts": tuple(harvested.values())})
        return turn
    value = sem.value or text.strip()
    if len(value) > 500:
        return turn.model_copy(update={"goal_facts": tuple(harvested.values())})
    fact = FactCandidate(
        field=sem.target_slot,
        value=value,
        subject="speaker",
        temporal_scope="now",
        negated=False,
        evidence=Evidence(start=0, end=len(text.strip()), quote=text.strip()),
    )
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
