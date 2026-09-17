"""Single-writer reducer — synchronous, deterministic, no I/O."""

from __future__ import annotations

import re
import uuid

from packages.contracts.enums import FsmState, SlotStatus
from packages.dialogue_engine import questions
from packages.dialogue_engine.check_path import (
    advance_probe_phase,
    apply_wellness_branch,
    classify_wellness_path,
    is_urgent_action,
    is_urgent_concern,
    is_urgent_state,
)
from packages.dialogue_engine.conversation_policy import (
    TurnContext,
    decide_conversation_policy,
    schedule_next_action,
)
from packages.dialogue_engine.effects import (
    Effect,
    EndCallEffect,
    InterpretEffect,
    SpeakEffect,
    TimerEffect,
)
from packages.dialogue_engine.events import (
    CallStarted,
    DeliveryDeferred,
    DialogueEvent,
    EffectFailed,
    InterpretationCompleted,
    PlayoutCancelled,
    PlayoutCompleted,
    PlayoutStarted,
    SafetyInterrupt,
    SpeakEffectStale,
    TimerExpired,
    UserTurnReceived,
)
from packages.dialogue_engine.policy import (
    apply_slot_answer,
    can_ask_slot,
    fill_from_semantic,
    mark_question_delivered,
    may_close_partial,
    release_reservation,
    reserve_question,
)
from packages.dialogue_engine.response_plan import (
    build_response_plan,
    composed_text,
    render_response_plan,
)
from packages.dialogue_engine.semantic import SemanticAct
from packages.dialogue_engine.semantic_kernel.observation_memory import atomic_semantic_apply
from packages.dialogue_engine.state import (
    BackgroundGoalCoverage,
    CheckPath,
    EngineState,
    GoalLifecycle,
    OpeningState,
    Question,
    QuestionPhase,
)
from packages.dialogue_engine.topic_tracker import (
    TopicPrompt,
    _topic_complete,
    is_topic_slot,
    observe_topic_answer,
    prime_topics,
    should_start_topic_flow,
    topic_ack_for_family,
    topic_slot,
)
from packages.dialogue_engine.turn_understanding import RichUserTurn

_STANDARD_CHECK_SLOTS = frozenset({"wellness", "mood", "sleep", "plans"})

_CONTROL_HANGUP_INTENTS = frozenset(
    {
        "goodbye_final",
        "partial_unresolved_close",
        "urgent_close",
        "wrong_person_final",
        "defer_final",
        "revoke_consent_final",
    }
)

_STALE = "STALE_EFFECT_IGNORED"


def reduce(
    state: EngineState,
    event: DialogueEvent,
) -> tuple[EngineState, list[Effect]]:
    if isinstance(event, CallStarted):
        return _on_call_started(state)
    if isinstance(event, UserTurnReceived):
        return _on_user_turn(state, event)
    if isinstance(event, InterpretationCompleted):
        return _on_interpretation_completed(state, event)
    if isinstance(event, PlayoutStarted):
        return _on_playout_started(state, event)
    if isinstance(event, PlayoutCompleted):
        return _on_playout_completed(state, event)
    if isinstance(event, PlayoutCancelled):
        return _on_playout_cancelled(state, event)
    if isinstance(event, TimerExpired):
        return _on_timer_expired(state, event)
    if isinstance(event, DeliveryDeferred):
        return _on_delivery_deferred(state, event)
    if isinstance(event, SpeakEffectStale):
        return _on_speak_effect_stale(state, event)
    if isinstance(event, EffectFailed):
        return _on_effect_failed(state, event)
    if isinstance(event, SafetyInterrupt):
        return _on_safety_interrupt(state, event)
    return state, []


_SAFETY_RED_PROMPT = (
    "Расскажите, что произошло? Правильно ли я понимаю ситуацию?"
)
_SAFETY_CLOSE = (
    "Поняла. Завершаю звонок. "
)


def _safety_close_after_clarify(state: EngineState) -> tuple[EngineState, list[Effect]]:
    """RED clarify already delivered; substantive answer → close (no mission resume)."""
    state.call_closed = True
    state.closing_reason = "safety_red"
    state.suspended_obligation = None
    state.pending_resume_goal_id = None
    state.processing_turn_id = None
    state.processing_effect_id = None
    return _emit_speak(
        state,
        text=_SAFETY_CLOSE.strip(),
        intent="safety_close",
        slot=None,
        marks_question=False,
    )


def _maybe_handle_safety_continuation(
    state: EngineState,
    *,
    user_text: str,
) -> tuple[EngineState, list[Effect]] | None:
    if not (state.safety_mode == "red" or state.risk_handling):
        return None
    if state.safety_clarify_count >= 2 or (
        state.safety_clarify_count >= 1 and (user_text or "").strip()
    ):
        return _safety_close_after_clarify(state)
    return None


def _on_safety_interrupt(
    state: EngineState,
    event: SafetyInterrupt,
) -> tuple[EngineState, list[Effect]]:
    from packages.dialogue_engine.mission_flow import capture_mission_suspend

    suspend = capture_mission_suspend(state)
    if suspend:
        state.suspended_obligation = suspend
    state.safety_mode = "red" if event.level == "RED" else "yellow"
    state.risk_handling = True
    state.risk_episode_id = event.episode_id
    state.fsm_state = FsmState.RED_SIGNAL
    state.processing_turn_id = None
    state.processing_effect_id = None
    state.bump_revision()
    if state.safety_clarify_count >= 2:
        return _safety_close_after_clarify(state)
    state.safety_clarify_count += 1
    return _emit_speak(
        state,
        text=_SAFETY_RED_PROMPT,
        intent="safety_clarify",
        slot="safety",
        marks_question=True,
    )


def _tag_effects(effects: list[Effect], state: EngineState) -> list[Effect]:
    tagged: list[Effect] = []
    for eff in effects:
        if hasattr(eff, "model_copy"):
            tagged.append(
                eff.model_copy(
                    update={
                        "revision": state.revision,
                        "effect_id": eff.effect_id or _new_effect_id(),
                    }
                )
            )
        else:
            tagged.append(eff)
    return tagged


def _new_effect_id() -> str:
    return f"fx-{uuid.uuid4().hex[:8]}"


def _stale(state: EngineState, event_revision: int) -> bool:
    return event_revision > 0 and event_revision != state.revision


def _on_call_started(state: EngineState) -> tuple[EngineState, list[Effect]]:
    if state.opening_state != OpeningState.NOT_STARTED:
        return state, []
    if state.first_user_turn_received:
        return state, []
    from packages.dialogue_engine.mission_flow import (
        is_custom_mission,
        next_askable_goal,
        opening_custom_greeting,
    )

    if is_custom_mission(state):
        gdef = next_askable_goal(state)
        greeting = opening_custom_greeting(state.elder_display_name)
        if gdef is None:
            state.fsm_state = FsmState.DAILY_CHECK
            state.opening_state = OpeningState.PLAYING
            state.opening_play_count += 1
            return _emit_speak(
                state,
                text=greeting,
                intent="opening_mission",
                slot=None,
                marks_question=False,
            )
        runtime = state.ensure_goal(gdef.goal_id)
        runtime.lifecycle = GoalLifecycle.ACTIVE
        text = f"{greeting} {gdef.prompt_hint}".strip()
        state.fsm_state = FsmState.DAILY_CHECK
        state.opening_state = OpeningState.PLAYING
        state.opening_play_count += 1
        return _emit_speak(
            state,
            text=text,
            intent="ask_mission_goal",
            slot=gdef.goal_id,
            marks_question=True,
            goal_id=gdef.goal_id,
        )

    state.fsm_state = FsmState.DAILY_CHECK
    state.opening_state = OpeningState.PLAYING
    state.opening_play_count += 1
    return _emit_speak(
        state,
        text=questions.opening_speech(
            state.elder_display_name,
            state.prior_call_context or None,
        ),
        intent="opening_wellness",
        slot="wellness",
        marks_question=True,
    )


def _note_temporal_emit(state: EngineState, slot: str | None, intent: str) -> bool:
    """Count a spoken temporal probe; True when the loop must break.

    Shared by _emit_speak and _speak_repair (the only two SpeakEffect
    builders): the same onset/duration question must never go out 3x in a
    row. On the 3rd repeat temporal pending is dropped (no fabrication),
    ask-caps are marked honestly, and the caller must _schedule_advance.
    """
    blob = f"{slot or ''} {intent or ''}".lower()
    tkey: str | None = None
    if "duration" in blob:
        tkey = "temporal_duration"
    elif "onset" in blob:
        tkey = "temporal_onset"
    if tkey is None:
        state.last_temporal_probe = None
        state.slot_unclear_counts.pop("emit_temporal_onset_run", None)
        state.slot_unclear_counts.pop("emit_temporal_duration_run", None)
        return False
    last = state.last_temporal_probe
    if last == tkey:
        run = state.slot_unclear_counts.get(f"emit_{tkey}_run", 0) + 1
    else:
        other = "temporal_duration" if tkey == "temporal_onset" else "temporal_onset"
        state.slot_unclear_counts.pop(f"emit_{other}_run", None)
        run = 1
    state.last_temporal_probe = tkey
    state.slot_unclear_counts[f"emit_{tkey}_run"] = run
    if run < 3:
        return False
    state.slot_unclear_counts.pop(f"emit_{tkey}_run", None)
    state.last_temporal_probe = None
    dropped = (
        state.pending_episode_attribute
        if state.pending_episode_attribute in ("onset", "duration")
        else None
    )
    if dropped:
        state.pending_episode_attribute = None
    if state.probe_phase in ("duration", "concern"):
        state.probe_phase = None
    # Persist the skip honestly: 3 spoken asks with no grounded answer.
    # Mark temporal steps asked + bump pack caps (honest ask telemetry).
    # No attribute values fabricated. Caller decides the next speech:
    # _speak_repair → bare repair (pending kept elsewhere), _emit_speak →
    # advance when the episode completes without onset, else honest
    # exhaustion via _close_partial (urgent guard inside escalates red).
    try:
        from packages.dialogue_engine.issue_memory import get_active_episode
        from packages.dialogue_engine.product import (
            bump_product_ask,
            classify_episode_family,
        )

        _ep = get_active_episode(state)
        if _ep is not None:
            _fam = classify_episode_family(_ep)
            for _attr in ("onset", "duration"):
                _mark = f"_product_asked:{_attr}"
                if _mark not in _ep.known_attributes:
                    _ep.known_attributes[_mark] = "1"
                    bump_product_ask(state, _fam)
            _ep.known_attributes["_temporal_skipped"] = "1"
    except Exception:  # noqa: BLE001 — guard must never break speech
        pass
    return True


def _emit_speak(
    state: EngineState,
    *,
    text: str,
    intent: str,
    slot: str | None,
    marks_question: bool,
    goal_id: str | None = None,
) -> tuple[EngineState, list[Effect]]:
    # Anti-loop: same onset/duration probe must never go out 3x in a row
    # (fuzz I3; live question_back/vague/garbage while temporal pending).
    if _note_temporal_emit(state, slot, intent):
        # 3rd repeat: honest exhaustion (frozen semantics). An episode that
        # completes without onset advances; otherwise partial close —
        # _close_partial escalates to urgent when red evidence exists.
        from packages.dialogue_engine.issue_memory import (
            activate_next_pending_episode as _activate_next,
        )
        from packages.dialogue_engine.issue_memory import (
            episode_complete as _ep_complete,
        )
        from packages.dialogue_engine.issue_memory import (
            finalize_episode_if_complete as _finalize,
        )
        from packages.dialogue_engine.issue_memory import (
            get_active_episode as _get_ep,
        )

        _ep2 = _get_ep(state)
        if _ep2 is not None:
            _finalize(_ep2)
        state.waiting_on_slot = None
        if _ep2 is not None and _ep_complete(_ep2):
            _activate_next(state)
            return _schedule_advance(state)
        return _close_partial(state)
    # Asked-history for «а что ты спрашивал?» (cap 20, questions only).
    if marks_question and text.strip():
        state.asked_history.append(text.strip())
        del state.asked_history[:-20]
    gen_id = state.next_generation_id()
    gen = state.active_playout_generation + 1
    state.active_playout_generation = gen
    if marks_question and slot and not reserve_question(state, slot, gen_id):
        # Safety probes are not quizzes: attempt caps must never silence
        # «Что именно беспокоит?» (live: cap eaten by opening+clarify closed
        # the call on fresh «плохо»). Bounded by concern_probe_count instead.
        if intent not in ("probe_concern", "probe_concern_options"):
            # Exhausted episode probes fall back to the frozen partial-close path.
            # Never fabricate attribute values: "unknown" is not an answer and
            # must not be written into known_attributes (noise != answer).
            if slot.startswith("episode_"):
                from packages.dialogue_engine.issue_memory import (
                    activate_next_pending_episode,
                    episode_complete,
                    finalize_episode_if_complete,
                    get_active_episode,
                )

                ep = get_active_episode(state)
                if ep is not None:
                    finalize_episode_if_complete(ep)
                state.pending_episode_attribute = None
                state.waiting_on_slot = None
                if ep is not None and episode_complete(ep):
                    activate_next_pending_episode(state)
                    return _schedule_advance(state)
            return _close_partial(state)
    resolved_goal = goal_id or (slot if intent == "ask_mission_goal" else None)
    q = Question(
        question_id=gen_id,
        slot=slot or "",
        text=text,
        phase=QuestionPhase.PLANNED,
        intent=intent,
        goal_id=resolved_goal,
    )
    state.planned_question = q if marks_question else None
    state.playing_question = q if marks_question else None
    state.active_playout = q
    if intent == "summary":
        state.summary_delivered = False
    state.bump_revision()
    effect = SpeakEffect(
        effect_id=_new_effect_id(),
        revision=state.revision,
        generation_id=gen_id,
        generation=gen,
        text=text,
        intent=intent,
        question_id=gen_id if marks_question else "",
        slot=slot,
        marks_question=marks_question,
    )
    return state, [effect]


def _on_playout_started(
    state: EngineState,
    event: PlayoutStarted,
) -> tuple[EngineState, list[Effect]]:
    if _stale(state, event.revision):
        return state, []
    if event.generation != state.active_playout_generation:
        return state, []
    if state.playing_question and state.playing_question.question_id == event.question_id:
        state.playing_question = state.playing_question.model_copy(
            update={"phase": QuestionPhase.PLAYING}
        )
    state.bump_revision()
    return state, []


def _on_playout_completed(
    state: EngineState,
    event: PlayoutCompleted,
) -> tuple[EngineState, list[Effect]]:
    if _stale(state, event.revision):
        return state, []
    if event.generation != state.active_playout_generation:
        return state, []
    q = state.playing_question
    if q is not None:
        if event.question_id and q.question_id != event.question_id:
            return state, []
        delivered = q.model_copy(update={"phase": QuestionPhase.DELIVERED})
        state.delivered_question = delivered
        state.playing_question = None
        state.planned_question = None
        state.active_playout = None
        if q.intent == "opening_wellness":
            state.opening_state = OpeningState.DELIVERED
        if q.intent == "mission_final_open" or q.slot == "mission_final_open":
            state.important_to_share_asked = True
            state.important_to_share_planned = False
        if q.intent in {"ask_mission_goal", "resume_mission_goal"} and state.pending_resume_goal_id:
            if (q.goal_id or q.slot) == state.pending_resume_goal_id:
                state.pending_resume_goal_id = None
                state.suspended_obligation = None
        if q.intent == "episode_needs_help" or (
            state.pending_episode_attribute_planned == "needs_help"
        ):
            state.pending_episode_attribute = "needs_help"
            state.pending_episode_attribute_planned = None
        if q.slot:
            mark_question_delivered(state, q.slot, q.question_id)
        state.bump_revision()
        if (
            q.slot
            and state.fsm_state == FsmState.DAILY_CHECK
            and not state.call_closed
        ):
            state.waiting_on_slot = q.slot
            return state, [
                TimerEffect(
                    effect_id=_new_effect_id(),
                    revision=state.revision,
                    timer_id=f"wait-{q.slot}",
                    wait_ms=questions._ANSWER_WAIT_MS,
                    reason="answer_wait",
                )
            ]
        return state, []

    ap = state.active_playout
    if ap is None:
        return state, []
    if event.question_id and ap.question_id and ap.question_id != event.question_id:
        return state, []
    state.active_playout = None
    if ap.intent == "summary":
        state.summary_delivered = True
    state.bump_revision()
    if ap.intent in _CONTROL_HANGUP_INTENTS:
        return state, [
            EndCallEffect(
                effect_id=_new_effect_id(),
                revision=state.revision,
                reason=state.closing_reason or ap.intent,
            )
        ]
    return state, []


def _on_playout_cancelled(
    state: EngineState,
    event: PlayoutCancelled,
) -> tuple[EngineState, list[Effect]]:
    if _stale(state, event.revision):
        return state, []
    if event.generation != state.active_playout_generation:
        return state, []
    if state.playing_question:
        q = state.playing_question
        release_reservation(state, q.slot)
        # Cancel before delivery: roll back planned-only mutations.
        if q.intent == "mission_final_open" or q.slot == "mission_final_open":
            state.important_to_share_planned = False
        if q.intent == "episode_needs_help":
            state.pending_episode_attribute_planned = None
        if state.pending_resume_goal_id and (q.goal_id or q.slot) == state.pending_resume_goal_id:
            state.pending_resume_goal_id = None
            # keep suspended_obligation so resume can retry
        state.playing_question = q.model_copy(update={"phase": QuestionPhase.CANCELLED})
        state.playing_question = None
        state.planned_question = None
    if state.active_playout:
        state.active_playout = None
    state.bump_revision()
    return state, []


def _on_user_turn(
    state: EngineState,
    event: UserTurnReceived,
) -> tuple[EngineState, list[Effect]]:
    # Post-close emergency (trailing audio after a close): re-open as urgent
    # instead of swallowing — a choking caller must escalate even if the
    # call was already closed (stress: emergency after partial close).
    if state.call_closed:
        _raw = ""
        if event.rich_turn is not None:
            _raw = event.rich_turn.raw_text
        elif event.text:
            _raw = event.text
        if _raw and is_urgent_action(_raw):
            state.call_closed = False
            state.closing_reason = None
            return _emit_urgent_close(state, user_text=_raw)
        return state, []
    if _stale(state, event.revision):
        return state, []
    state.first_user_turn_received = True
    state.turn_seq += 1
    if event.effect_id and event.semantic is None and event.rich_turn is None:
        state.processing_turn_id = event.turn_id
        state.processing_effect_id = event.effect_id
        state.bump_revision()
        return state, [
            InterpretEffect(
                effect_id=event.effect_id,
                revision=state.revision,
                turn_id=event.turn_id,
                text=event.text,
            )
        ]
    if event.rich_turn is not None:
        state.processing_turn_id = event.turn_id
        state.processing_effect_id = event.effect_id or None
        # Safety first: emergency verbs hijack any dialogue state — never
        # probe or partially close a possible emergency (live fs-41e2a57b).
        if is_urgent_action(event.rich_turn.raw_text):
            return _emit_urgent_close(state, user_text=event.rich_turn.raw_text)
        if is_urgent_state(event.rich_turn.raw_text):
            # Red state: escalate at once only when we know WHAT hurts;
            # otherwise record the negative fact and clarify first (asked,
            # never assumed) — the probe ladder below asks WHAT.
            if _concern_established(state, event.rich_turn.raw_text):
                return _emit_urgent_close(state, user_text=event.rich_turn.raw_text)
            _record_negative_wellness(
                state, event.rich_turn.raw_text, record_concern=False
            )
            state.red_state_pending = True
            state.check_path = CheckPath.URGENT
        return _apply_rich_turn(state, event.rich_turn)
    if event.semantic is None:
        return state, []
    # Same safety hijack for the semantic (non-rich) path.
    if is_urgent_action(event.text):
        state.processing_turn_id = event.turn_id
        state.processing_effect_id = event.effect_id or None
        return _emit_urgent_close(state, user_text=event.text)
    if is_urgent_state(event.text):
        if _concern_established(state, event.text):
            state.processing_turn_id = event.turn_id
            state.processing_effect_id = event.effect_id or None
            return _emit_urgent_close(state, user_text=event.text)
        state.processing_turn_id = event.turn_id
        state.processing_effect_id = event.effect_id or None
        _record_negative_wellness(state, event.text, record_concern=False)
        state.red_state_pending = True
        state.check_path = CheckPath.URGENT
    state.processing_turn_id = event.turn_id
    state.processing_effect_id = event.effect_id or None
    return _apply_semantic(state, event.semantic)


def _on_interpretation_completed(
    state: EngineState,
    event: InterpretationCompleted,
) -> tuple[EngineState, list[Effect]]:
    if state.call_closed:
        return state, []
    if event.turn_id != state.processing_turn_id:
        return state, []
    if state.processing_effect_id and event.effect_id != state.processing_effect_id:
        return state, []
    if _stale(state, event.revision):
        return state, []
    return _apply_semantic(state, event.semantic)


_VALENCE_ORDER = {"positive": 2, "uncertain": 1, "negative": 0}


def _wellness_contradicts(state: EngineState, fact, turn: RichUserTurn) -> bool:
    """Fresh deterioration or grounded current self-assessment over a filled slot.

    Someone else's complaint never contradicts the speaker's record
    («у мужа плохо» after speaker «хорошо» changes nothing).
    """
    if fact.value not in _VALENCE_ORDER:
        return False
    rec = state.slot_records.get("wellness")
    if rec is None:
        return False
    if rec.polarity == fact.value:
        return False
    try:
        from packages.dialogue_engine.policy import _is_other_person_only

        if _is_other_person_only(turn.raw_text):
            return False
    except Exception:  # noqa: BLE001 — fail open to contradiction
        pass
    if fact.value == "positive":
        from packages.dialogue_engine.fast_interpreter import _WELLNESS_POSITIVE

        # The harvester currently labels even historical facts as "now".
        # Require a complete present-tense self-assessment, not a positive
        # fragment inside a historical, conditional or mixed statement.
        quote = fact.evidence.quote if fact.evidence else ""
        assessment = re.sub(r"^(?:нет\s*[,—-]?\s*)?(?:я\s+)?", "", quote.strip(), flags=re.I)
        return bool(
            fact.subject == "speaker"
            and fact.temporal_scope == "now"
            and not fact.negated
            and quote
            and quote in turn.raw_text
            and turn.control in ("none", "")
            and not turn.user_question
            and _WELLNESS_POSITIVE.fullmatch(assessment.rstrip(".!…"))
        )
    rec_order = _VALENCE_ORDER.get(rec.polarity, 2)  # unknown ≈ positive-like
    return _VALENCE_ORDER[fact.value] < rec_order


def _is_bare_valence_for_wellness(text: str, turn: RichUserTurn) -> bool:
    """Whole utterance is just a valence assessment («Так себе.»).

    Such turns carry no slot-specific content, so harvesters scoped to the
    delivered slot yield nothing and the ladder would march on in silence.
    A bare negative/uncertain self-assessment is always health-relevant —
    never a reason to advance past it quietly.
    """
    raw = (text or "").strip()
    if not raw or len(raw) > 60:
        return False
    if turn.control not in ("none", ""):
        return False
    if turn.dialogue_act != "answer":
        return False
    if turn.user_question:
        return False
    try:
        from packages.dialogue_engine.fast_interpreter import (
            _detect_polarity as _bare_polarity,
        )
        from packages.dialogue_engine.policy import (
            _is_other_person_only as _bare_other_only,
        )

        if _bare_polarity(raw) not in ("negative", "uncertain"):
            return False
        if _bare_other_only(raw):
            return False
    except Exception:  # noqa: BLE001 — fail closed (no synthesis)
        return False
    return True


def _apply_goal_facts(state: EngineState, turn: RichUserTurn) -> list[str]:
    filled: list[str] = []
    for fact in turn.goal_facts:
        if state.slots.get(fact.field) != SlotStatus.OPEN:
            # Deterioration after a fill must never be silently dropped.
            # Live holes: «Плохо мне.» after positive wellness slid to food;
            # «мне плохо» at summary got a polite goodbye. A strictly worse
            # valence overwrites the record (probe follows via safety net);
            # the ladder is never advanced here — hence no `filled` append.
            if fact.field == "wellness" and _wellness_contradicts(state, fact, turn):
                quote = fact.evidence.quote if fact.evidence else turn.raw_text
                prev = state.slot_records.get("wellness")
                state.slot_corrections.append(
                    {
                        "slot": "wellness",
                        "old": prev.value if prev is not None else "",
                        "new": fact.value,
                        "source_turn": turn.utterance_id,
                    }
                )
                apply_slot_answer(
                    state,
                    "wellness",
                    fact.value,
                    turn_id=turn.utterance_id,
                    source_text=quote,
                    polarity=fact.value,
                    confidence=0.9,
                    correction=True,
                )
            continue
        if fact.field in ("wellness", "mood", "sleep"):
            from packages.dialogue_engine.policy import _is_other_person_only

            if _is_other_person_only(turn.raw_text):
                # Someone else's complaint is not the speaker's fact.
                continue
        quote = fact.evidence.quote if fact.evidence else turn.raw_text
        polarity = None
        if fact.field in ("wellness", "mood"):
            from packages.dialogue_engine.fast_interpreter import _detect_polarity

            polarity = _detect_polarity(quote)
        apply_slot_answer(
            state,
            fact.field,
            fact.value,
            turn_id=turn.utterance_id,
            source_text=quote,
            polarity=polarity,
            confidence=0.9,
            correction=turn.correction,
        )
        state.set_background_goal_coverage(fact.field, BackgroundGoalCoverage.COVERED_FROM_SPEECH)
        filled.append(fact.field)
    return filled


def _emit_from_plan(
    state: EngineState,
    plan,
) -> tuple[EngineState, list[Effect]]:
    if plan.action == "none":
        return state, []
    if plan.action == "close_urgent":
        return _emit_urgent_close(state)
    if plan.action == "close_summary":
        return _emit_summary(state, acknowledge=getattr(plan, "acknowledge", "") or "")
    if plan.action == "close_partial":
        return _close_partial(state)
    if plan.action == "control":
        return state, []
    rendered = render_response_plan(plan, state)
    text = composed_text(rendered)
    if not text.strip():
        return state, []
    goal_id = None
    if rendered.marks_question and rendered.slot:
        if rendered.intent in {"ask_mission_goal", "resume_mission_goal"} or (
            rendered.slot in (state.mission_goal_ids or ())
        ):
            goal_id = rendered.slot
    return _emit_speak(
        state,
        text=text,
        intent=rendered.intent or "rich_policy",
        slot=rendered.slot,
        marks_question=rendered.marks_question,
        goal_id=goal_id,
    )


def _schedule_advance(
    state: EngineState,
    *,
    newly_filled: list[str] | None = None,
    turn: RichUserTurn | None = None,
    user_text: str = "",
    answer_slot: str | None = None,
    clarify: bool = False,
) -> tuple[EngineState, list[Effect]]:
    """Canonical post-mutation advance — scheduler only, not slot ladder."""
    state.delivered_question = None
    state.planned_question = None
    ctx = TurnContext(
        turn=turn,
        newly_filled_slots=tuple(newly_filled or ()),
        user_text=user_text,
        answer_slot=answer_slot,
        clarify=clarify,
    )
    plan = schedule_next_action(state, ctx)
    return _emit_from_plan(state, plan)


def _apply_rich_turn(
    state: EngineState,
    turn: RichUserTurn,
) -> tuple[EngineState, list[Effect]]:
    user_text = turn.raw_text
    answer_slot = state.answer_context_slot()

    safety_done = _maybe_handle_safety_continuation(state, user_text=user_text)
    if safety_done is not None:
        return safety_done

    if turn.answers_pending_question and state.pending_episode_attribute:
        state.delivered_question = None
        state.planned_question = None

    if state.fsm_state in (FsmState.SUMMARY, FsmState.GOODBYE) or state.awaiting_goodbye_confirm:
        semantic_bridge = _rich_to_semantic(turn)
        closing = _handle_closing_turn(state, semantic_bridge)
        if closing is not None:
            state.processing_turn_id = None
            state.processing_effect_id = None
            return closing

    control_outcome = _apply_rich_control(state, turn)
    if control_outcome is not None:
        return control_outcome

    if turn.dialogue_act == "repair" or _is_repair_text(user_text):
        state.processing_turn_id = None
        state.processing_effect_id = None
        from packages.dialogue_engine.mission_flow import is_custom_mission

        if is_custom_mission(state):
            return _schedule_advance(state, turn=turn, user_text=user_text, answer_slot=answer_slot)
        return _speak_repair(state, answer_slot or "wellness")

    if turn.dialogue_act == "backchannel":
        state.processing_turn_id = None
        state.processing_effect_id = None
        state.bump_revision()
        if (
            state.fsm_state in (FsmState.SUMMARY, FsmState.GOODBYE)
            and not state.awaiting_goodbye_confirm
        ):
            return state, []
        if answer_slot:
            state.waiting_on_slot = answer_slot
            return state, [
                TimerEffect(
                    effect_id=_new_effect_id(),
                    revision=state.revision,
                    timer_id=f"wait-{answer_slot}",
                    wait_ms=7000,
                    reason="backchannel",
                )
            ]
        if _is_meaningful_turn(user_text):
            return _speak_never_silent(state, answer_slot or "wellness", user_text)
        return state, []

    if is_topic_slot(answer_slot):
        from packages.dialogue_engine.topic_tracker import (
            observe_topic_answer,
            sync_topic_hints_from_answer,
        )

        sync_topic_hints_from_answer(state, user_text, answer_slot=answer_slot)
        atomic_semantic_apply(state, turn)
        if turn.user_question and not turn.answers_pending_question:
            decision = decide_conversation_policy(state, turn)
            if decision is not None and decision.text:
                if decision.suspend is not None:
                    state.suspended_obligation = decision.suspend
                state.processing_turn_id = None
                state.processing_effect_id = None
                state.bump_revision()
                return _emit_speak(
                    state,
                    text=decision.text,
                    intent=decision.intent or "rich_policy",
                    slot=decision.slot or answer_slot or "wellness",
                    marks_question=decision.marks_question,
                )
        if turn.correction:
            decision = decide_conversation_policy(state, turn)
            if decision is not None and decision.text:
                state.processing_turn_id = None
                state.processing_effect_id = None
                state.bump_revision()
                return _emit_speak(
                    state,
                    text=decision.text,
                    intent=decision.intent or "rich_policy",
                    slot=decision.slot or answer_slot or "wellness",
                    marks_question=decision.marks_question,
                )
        newly_filled = _apply_goal_facts(state, turn)
        state.processing_turn_id = None
        state.processing_effect_id = None
        state.waiting_on_slot = None
        state.bump_revision()
        observe_topic_answer(state, user_text)
        return _advance_after_topic(state, user_text, newly_filled=newly_filled)

    # Legacy probe/topic may observe semantic state after apply, but must NOT
    # own a RichUserTurn (ADR live-path simplification). Always apply first.
    from packages.dialogue_engine.issue_memory import filter_rich_turn_mentions

    turn = filter_rich_turn_mentions(state, turn)
    atomic_semantic_apply(state, turn)
    # Background mood/sleep/plans may fill as projection — never before apply,
    # and never as exclusive owner of the turn.
    _harvest_off_context_background_slots(state, turn, answer_slot=answer_slot)

    # Explicit issue cancels generic probe ownership (compat projection only).
    if turn.issue_mentions and state.probe_phase:
        if not state.wellness_concern:
            state.wellness_concern = (
                turn.issue_mentions[0].label.strip() or user_text.strip()
            )
        state.probe_phase = None
    elif (
        state.probe_phase
        and turn.dialogue_act == "answer"
        and not turn.issue_mentions
    ):
        # Compatibility projection only — scheduler still owns next speech.
        advance_probe_phase(state, user_text)

    if turn.user_question and not turn.answers_pending_question:
        decision = decide_conversation_policy(state, turn)
        if decision is not None and decision.text:
            if decision.suspend is not None:
                state.suspended_obligation = decision.suspend
            state.processing_turn_id = None
            state.processing_effect_id = None
            state.bump_revision()
            goal_id = None
            if decision.intent in {"ask_mission_goal", "resume_mission_goal"} or (
                decision.slot and decision.slot in (state.mission_goal_ids or ())
            ):
                goal_id = decision.slot
            return _emit_speak(
                state,
                text=decision.text,
                intent=decision.intent or "rich_policy",
                slot=decision.slot or answer_slot or "wellness",
                marks_question=decision.marks_question,
                goal_id=goal_id,
            )

    if turn.needs_clarification:
        from packages.dialogue_engine.semantic_kernel.kernel import clarify_text
        from packages.dialogue_engine.semantic_kernel.types import SemanticKernelResult

        stub = SemanticKernelResult(
            raw_text=user_text,
            utterance_id=turn.utterance_id,
            ambiguity=turn.kernel_ambiguities,
            level=turn.kernel_level,
        )
        state.processing_turn_id = None
        state.processing_effect_id = None
        state.bump_revision()
        return _emit_speak(
            state,
            text=clarify_text(stub),
            intent="semantic_clarify",
            slot=answer_slot or "wellness",
            marks_question=True,
        )

    if turn.correction:
        decision = decide_conversation_policy(state, turn)
        if decision is not None and decision.text:
            state.processing_turn_id = None
            state.processing_effect_id = None
            state.bump_revision()
            return _emit_speak(
                state,
                text=decision.text,
                intent=decision.intent or "rich_policy",
                slot=decision.slot or answer_slot or "wellness",
                marks_question=decision.marks_question,
            )

    if turn.issue_mentions and answer_slot in ("wellness", "mood", "sleep", "plans"):
        if answer_slot == "wellness" and not state.wellness_concern:
            state.wellness_concern = user_text
            rec = state.slot_records.get("wellness")
            if rec is None or rec.value in ("", "negative", "positive", "neutral"):
                from packages.dialogue_engine.fast_interpreter import _detect_polarity

                apply_slot_answer(
                    state,
                    "wellness",
                    user_text,
                    turn_id=turn.utterance_id,
                    source_text=user_text,
                    polarity=_detect_polarity(user_text),
                )
        slot_filled = _apply_goal_facts(state, turn)
        if slot_filled and turn.answers_pending_question:
            state.processing_turn_id = None
            state.processing_effect_id = None
            state.waiting_on_slot = None
            state.bump_revision()
            return _advance_after_fills(
                state, slot_filled, user_text=user_text, turn=turn
            )
        decision = decide_conversation_policy(state, turn)
        if decision is not None and decision.text:
            state.processing_turn_id = None
            state.processing_effect_id = None
            state.bump_revision()
            spoken = _emit_speak(
                state,
                text=decision.text,
                intent=decision.intent or "rich_policy",
                slot=decision.slot or answer_slot,
                marks_question=decision.marks_question,
            )
            if spoken[1]:
                return spoken
        if slot_filled:
            state.processing_turn_id = None
            state.processing_effect_id = None
            state.waiting_on_slot = None
            state.bump_revision()
            return _advance_after_fills(
                state, slot_filled, user_text=user_text, turn=turn
            )

    if not turn.goal_facts and not answer_slot:
        from packages.dialogue_engine.issue_mention_extract import extract_goal_facts

        for slot in ("wellness", "mood", "sleep", "plans"):
            if state.slots.get(slot) != SlotStatus.OPEN:
                continue
            facts = extract_goal_facts(user_text, answer_slot=slot)
            if facts and facts[0].field == slot:
                turn = turn.model_copy(update={"goal_facts": facts})
                break

    if (
        not turn.goal_answers
        and not turn.goal_facts
        and _is_bare_valence_for_wellness(user_text, turn)
    ):
        from packages.dialogue_engine.issue_mention_extract import (
            extract_goal_facts as _bare_goal_facts,
        )

        _bare = [
            f
            for f in _bare_goal_facts(user_text, answer_slot="wellness")
            if f.field == "wellness" and f.value in ("negative", "uncertain")
        ]
        if _bare:
            turn = turn.model_copy(update={"goal_facts": tuple(_bare)})

    newly_filled = _apply_goal_facts(state, turn)
    if newly_filled:
        state.processing_turn_id = None
        state.processing_effect_id = None
        state.waiting_on_slot = None
        state.bump_revision()
        return _advance_after_fills(
            state, newly_filled, user_text=user_text, turn=turn
        )

    plan = schedule_next_action(
        state,
        TurnContext(turn=turn, user_text=user_text, answer_slot=answer_slot),
    )
    if plan.action == "control" and plan.control:
        control_outcome = _apply_rich_control(state, turn)
        if control_outcome is not None:
            return control_outcome
    if plan.suspend is not None:
        state.suspended_obligation = plan.suspend
    state.processing_turn_id = None
    state.processing_effect_id = None
    state.bump_revision()
    outcome = _emit_from_plan(state, plan)
    if outcome[1] or plan.action != "none":
        return outcome

    if any(m.kind == "sleep_problem" for m in turn.issue_mentions):
        if should_start_topic_flow(state, user_text, answer_slot=answer_slot):
            state.processing_turn_id = None
            state.processing_effect_id = None
            state.waiting_on_slot = None
            state.probe_phase = None
            prime_topics(state, user_text)
            return _advance_after_topic(state, user_text, newly_filled=[])

    state.processing_turn_id = None
    state.processing_effect_id = None
    state.bump_revision()
    episode_outcome = _advance_after_episode_answer(state, turn, answer_slot)
    if episode_outcome is not None:
        return episode_outcome

    if state.active_episode_id or state.pending_episode_ids:
        resumed = decide_conversation_policy(state, turn)
        if resumed and resumed.text:
            return _emit_speak(
                state,
                text=resumed.text,
                intent=resumed.intent,
                slot=resumed.slot or "wellness",
                marks_question=resumed.marks_question,
            )
    if state.summary_spoken and state.fsm_state in (FsmState.SUMMARY, FsmState.GOODBYE):
        state.processing_turn_id = None
        state.processing_effect_id = None
        return state, []
    if _is_meaningful_turn(user_text) and answer_slot:
        return _speak_never_silent(state, answer_slot, user_text)
    return state, []


def _rich_to_semantic(turn: RichUserTurn):
    from packages.dialogue_engine.semantic import SemanticAct, SemanticTurn

    if turn.control == "stop_call":
        return SemanticTurn(
            act=SemanticAct.GOODBYE_REQUEST,
            source_quote=turn.raw_text,
            confidence=0.95,
        )
    if turn.dialogue_act == "backchannel":
        return SemanticTurn(act=SemanticAct.BACKCHANNEL, source_quote=turn.raw_text)
    if turn.dialogue_act == "correction":
        return SemanticTurn(
            act=SemanticAct.ANSWER,
            correction=True,
            source_quote=turn.raw_text,
            value=turn.raw_text,
        )
    return SemanticTurn(
        act=SemanticAct.ANSWER,
        source_quote=turn.raw_text,
        value=turn.raw_text,
        confidence=0.85,
    )


def _apply_rich_control(
    state: EngineState,
    turn: RichUserTurn,
) -> tuple[EngineState, list[Effect]] | None:
    control = turn.control
    if control in ("none", ""):
        return None

    state.processing_turn_id = None
    state.processing_effect_id = None
    state.bump_revision()

    if control == "stop_call":
        return _emit_goodbye_final(state)

    if control == "wrong_person":
        state.call_closed = True
        state.closing_reason = "wrong_person"
        state.fsm_state = FsmState.FINAL_CLASSIFICATION
        return _emit_speak(
            state,
            text=questions._WRONG_PERSON_FINAL,
            intent="wrong_person_final",
            slot=None,
            marks_question=False,
        )

    if control in ("defer", "revoke_consent"):
        state.call_closed = True
        state.closing_reason = control
        state.fsm_state = FsmState.FINAL_CLASSIFICATION
        text = (
            questions._REVOKE_FINAL
            if control == "revoke_consent"
            else questions._DEFER_FINAL
        )
        intent = "revoke_consent_final" if control == "revoke_consent" else "defer_final"
        return _emit_speak(
            state,
            text=text,
            intent=intent,
            slot=None,
            marks_question=False,
        )

    if control == "pause":
        slot = state.answer_context_slot() or "wellness"
        state.waiting_on_slot = slot
        state, effects = _emit_speak(
            state,
            text=questions._PAUSE_ACK,
            intent="pause_ack",
            slot=slot,
            marks_question=False,
        )
        effects.append(
            TimerEffect(
                effect_id=_new_effect_id(),
                revision=state.revision,
                timer_id=f"wait-{slot}",
                wait_ms=7000,
                reason="pause",
            )
        )
        return state, effects

    return None


def _apply_semantic(
    state: EngineState,
    semantic,
) -> tuple[EngineState, list[Effect]]:
    if state.fsm_state in (FsmState.SUMMARY, FsmState.GOODBYE) or state.awaiting_goodbye_confirm:
        closing = _handle_closing_turn(state, semantic)
        if closing is not None:
            state.processing_turn_id = None
            state.processing_effect_id = None
            return closing

    answer_slot = state.answer_context_slot()

    user_text = semantic.source_quote or semantic.value or ""

    safety_done = _maybe_handle_safety_continuation(state, user_text=user_text)
    if safety_done is not None:
        return safety_done

    # Explicit farewell closes immediately from any non-terminal state.
    if semantic.act == SemanticAct.GOODBYE_REQUEST or _is_explicit_farewell(user_text):
        state.processing_turn_id = None
        state.processing_effect_id = None
        return _emit_goodbye_final(state)

    if semantic.act == SemanticAct.REPAIR_REQUEST:
        if state.delivered_question is None:
            state.processing_turn_id = None
            state.processing_effect_id = None
            state.bump_revision()
            if answer_slot:
                return state, [
                    TimerEffect(
                        effect_id=_new_effect_id(),
                        revision=state.revision,
                        timer_id=f"wait-{answer_slot}",
                        wait_ms=7000,
                        reason="backchannel",
                    )
                ]
            if _is_meaningful_turn(user_text):
                return _speak_never_silent(state, answer_slot or "wellness", user_text)
            return state, []
        state.processing_turn_id = None
        state.processing_effect_id = None
        return _speak_repair(state, answer_slot or semantic.target_slot or "wellness")

    if semantic.act == SemanticAct.BACKCHANNEL:
        state.processing_turn_id = None
        state.processing_effect_id = None
        state.bump_revision()
        if (
            state.fsm_state in (FsmState.SUMMARY, FsmState.GOODBYE)
            and not state.awaiting_goodbye_confirm
        ):
            return state, []
        if answer_slot:
            state.waiting_on_slot = answer_slot
            return state, [
                TimerEffect(
                    effect_id=_new_effect_id(),
                    revision=state.revision,
                    timer_id=f"wait-{answer_slot}",
                    wait_ms=7000,
                    reason="backchannel",
                )
            ]
        if _is_meaningful_turn(user_text):
            return _speak_never_silent(state, answer_slot or "wellness", user_text)
        return state, []

    if semantic.act == SemanticAct.UNCLEAR and answer_slot:
        if is_topic_slot(answer_slot) and _is_meaningful_turn(user_text):
            state.processing_turn_id = None
            state.processing_effect_id = None
            state.waiting_on_slot = None
            observe_topic_answer(state, user_text)
            return _advance_after_topic(state, user_text)
        if state.probe_phase:
            count = state.slot_unclear_counts.get(f"probe_{state.probe_phase}", 0) + 1
            state.slot_unclear_counts[f"probe_{state.probe_phase}"] = count
            state.processing_turn_id = None
            state.processing_effect_id = None
            if count >= 2:
                return _advance_probe_after_answer(state, user_text)
            return _speak_probe(state, state.probe_phase, clarification=True)
        count = state.slot_unclear_counts.get(answer_slot, 0) + 1
        state.slot_unclear_counts[answer_slot] = count
        state.processing_turn_id = None
        state.processing_effect_id = None
        if may_close_partial(state, answer_slot):
            return _close_partial(state)
        if can_ask_slot(state, answer_slot):
            return _speak_slot_question(state, answer_slot, clarification=True)
        if _is_meaningful_turn(user_text):
            return _speak_never_silent(state, answer_slot, user_text)
        return state, []

    if state.probe_phase and semantic.act == SemanticAct.ANSWER:
        # Compatibility only: project probe advance after content is known.
        # Rich path owns live calls; this branch must not skip issue creation.
        text = semantic.value or semantic.source_quote
        state.processing_turn_id = None
        state.processing_effect_id = None
        state.waiting_on_slot = None
        if should_start_topic_flow(
            state, text, answer_slot=f"probe_{state.probe_phase}"
        ):
            state.probe_phase = None
            prime_topics(state, text)
            return _advance_after_topic(state, text, newly_filled=[])
        advance_probe_phase(state, text)
        return _schedule_advance(state, user_text=text)

    if (
        semantic.act in (SemanticAct.ANSWER, SemanticAct.UNCLEAR)
        and not state.probe_phase
        and state.delivered_question is not None
        and state.delivered_question.intent in ("probe_concern", "probe_concern_options")
        and state.concern_probe_count >= 1
        and state.wellness_concern == ""
        and "concern_declined" not in state.observations
    ):
        # Delivered concern probe is an open obligation (mirrors the rich
        # path: complaint grounds via the shared check_path contract with a
        # duration follow-up; anything else goes to the scheduler safety net
        # — options after the first probe, decline/escalation after options).
        # Without this, grounded complaint evidence is dropped and unclear
        # answers strand in the slot-unclear logic instead of the net.
        from packages.dialogue_engine.check_path import (
            _looks_like_complaint,
            apply_concern_answer,
        )

        text = semantic.value or semantic.source_quote or ""
        if semantic.act == SemanticAct.ANSWER and _looks_like_complaint(text):
            state.processing_turn_id = None
            state.processing_effect_id = None
            state.waiting_on_slot = None
            state.delivered_question = None
            state.planned_question = None
            outcome = apply_concern_answer(state, text)
            if outcome == "urgent":
                return _emit_urgent_close(state, user_text=text)
            return _schedule_advance(state, user_text=text)
        if semantic.act == SemanticAct.UNCLEAR:
            state.processing_turn_id = None
            state.processing_effect_id = None
            state.waiting_on_slot = None
            state.delivered_question = None
            state.planned_question = None
            state.bump_revision()
            return _schedule_advance(state, user_text=text)
    if is_topic_slot(answer_slot) and semantic.act == SemanticAct.ANSWER:
        state.processing_turn_id = None
        state.processing_effect_id = None
        state.waiting_on_slot = None
        observe_topic_answer(state, user_text)
        return _advance_after_topic(state, user_text)

    if (
        semantic.act == SemanticAct.ANSWER
        and semantic.slots
        and len(_STANDARD_CHECK_SLOTS.intersection(semantic.slots)) >= 2
    ):
        filled = fill_from_semantic(
            state, semantic, turn_id=state.processing_turn_id or ""
        )
        if filled:
            state.processing_turn_id = None
            state.processing_effect_id = None
            state.waiting_on_slot = None
            return _advance_after_fills(state, filled, user_text=user_text)

    if should_start_topic_flow(state, user_text, answer_slot=answer_slot):
        if semantic.act in (SemanticAct.ANSWER, SemanticAct.UNCLEAR):
            state.processing_turn_id = None
            state.processing_effect_id = None
            state.waiting_on_slot = None
            state.probe_phase = None
            prime_topics(state, user_text)
            return _advance_after_topic(state, user_text, newly_filled=[])

    filled = fill_from_semantic(
        state, semantic, turn_id=state.processing_turn_id or ""
    )
    if filled:
        state.processing_turn_id = None
        state.processing_effect_id = None
        state.waiting_on_slot = None
        return _advance_after_fills(state, filled, user_text=user_text)

    state.processing_turn_id = None
    state.processing_effect_id = None
    state.bump_revision()
    if _is_meaningful_turn(user_text) and answer_slot:
        return _speak_never_silent(state, answer_slot, user_text)
    return state, []


def _is_meaningful_turn(text: str) -> bool:
    core = text.strip()
    if len(core) < 2:
        return False
    if core.lower() in {"да", "нет", "ага", "угу"}:
        return True
    return len(core.split()) >= 1


def _speak_never_silent(
    state: EngineState,
    answer_slot: str,
    user_text: str,
) -> tuple[EngineState, list[Effect]]:
    """No substantive user turn may end with zero Vera response."""
    if is_topic_slot(answer_slot):
        observe_topic_answer(state, user_text)
        advanced = _advance_after_topic(state, user_text)
        if advanced[1]:
            return advanced
    if state.probe_phase:
        return _speak_probe(state, state.probe_phase, clarification=True)
    if may_close_partial(state, answer_slot):
        return _close_partial(state)
    outcome = _schedule_advance(
        state,
        user_text=user_text,
        answer_slot=answer_slot,
        clarify=True,
    )
    if outcome[1]:
        return outcome
    if can_ask_slot(state, answer_slot):
        ack = "Понимаю."
        question = questions.slot_question(answer_slot, clarification=True, state=state)
        return _emit_speak(
            state,
            text=f"{ack} {question}".strip(),
            intent=f"clarify_{answer_slot}",
            slot=answer_slot,
            marks_question=True,
        )
    return _speak_repair(state, answer_slot)


def _advance_after_fills(
    state: EngineState,
    filled_slots: list[str],
    *,
    user_text: str = "",
    turn: RichUserTurn | None = None,
) -> tuple[EngineState, list[Effect]]:
    if not user_text and turn is not None:
        user_text = turn.raw_text or ""
    if not user_text:
        for slot in filled_slots:
            rec = state.slot_records.get(slot)
            if rec and rec.source_text:
                user_text = rec.source_text
                break
            val = state.slot_values.get(slot, "")
            if val:
                user_text = val
                break
    if "wellness" in filled_slots:
        if not user_text:
            rec = state.slot_records.get("wellness")
            user_text = (
                (rec.source_text if rec else "") or state.slot_values.get("wellness", "")
            )
        state.set_background_goal_coverage("wellness", BackgroundGoalCoverage.ANSWERED)
        if should_start_topic_flow(state, user_text, answer_slot="wellness"):
            state.probe_phase = None
            prime_topics(state, user_text)
        else:
            _apply_wellness_branch_state(state, user_text)
        for slot in filled_slots:
            if slot != "wellness":
                state.set_background_goal_coverage(slot, BackgroundGoalCoverage.ANSWERED)

    state.processing_turn_id = None
    state.processing_effect_id = None
    state.bump_revision()
    return _schedule_advance(
        state,
        newly_filled=filled_slots,
        user_text=user_text,
        turn=turn,
    )


def _resolve_sleep_problem_episodes_after_topic(state: EngineState) -> None:
    """Sleep topic flow satisfies sleep_problem episodes — do not re-ask onset."""
    from packages.dialogue_engine.topic_tracker import TopicFamily

    if TopicFamily.SLEEP not in state.topic_evidence:
        return
    for ep in state.issue_episodes.values():
        if ep.kind == "sleep_problem":
            ep.status = "resolved"
    state.pending_episode_ids = [
        eid
        for eid in state.pending_episode_ids
        if state.issue_episodes.get(eid, None) is None
        or state.issue_episodes[eid].kind != "sleep_problem"
    ]
    if state.active_episode_id:
        active = state.issue_episodes.get(state.active_episode_id)
        if active and active.kind == "sleep_problem":
            state.active_episode_id = None
            state.pending_episode_attribute = None


def _topics_need_attention(state: EngineState) -> bool:
    if state.active_topic and not _topic_complete(state, state.active_topic):
        return True
    return any(not _topic_complete(state, family) for family in state.pending_topics)


def _has_open_episodes(state: EngineState) -> bool:
    if state.active_episode_id:
        ep = state.issue_episodes.get(state.active_episode_id)
        if ep and ep.status != "resolved":
            return True
    for eid in state.pending_episode_ids:
        ep = state.issue_episodes.get(eid)
        if ep and ep.status != "resolved":
            return True
    return False


def _advance_after_topic(
    state: EngineState,
    user_text: str,
    *,
    newly_filled: list[str] | None = None,
) -> tuple[EngineState, list[Effect]]:
    state.delivered_question = None
    state.planned_question = None
    if not _topics_need_attention(state):
        state.active_topic = None
        state.topic_asked_dimension = None
    _resolve_sleep_problem_episodes_after_topic(state)
    state.processing_turn_id = None
    state.processing_effect_id = None
    state.bump_revision()
    return _schedule_advance(
        state,
        newly_filled=newly_filled or [],
        user_text=user_text,
    )


def _emit_topic_prompt(
    state: EngineState,
    prompt: TopicPrompt,
    *,
    newly_filled: list[str],
) -> tuple[EngineState, list[Effect]]:
    ack_parts: list[str] = []
    if newly_filled:
        ack_parts.append(
            build_response_plan(
                state,
                newly_filled=newly_filled,
                next_slot=state.next_open_slot() or "mood",
            ).acknowledge
        )
    ack_parts.append(topic_ack_for_family(prompt.family))
    question = questions.topic_question(prompt.intent)
    text = " ".join(p for p in ack_parts if p).strip()
    if text and question:
        text = f"{text} {question}"
    elif question:
        text = question
    slot = topic_slot(prompt.family)
    return _emit_speak(
        state,
        text=text,
        intent=prompt.intent,
        slot=slot,
        marks_question=True,
    )


def _apply_wellness_branch_state(state: EngineState, wellness_text: str) -> None:
    """Mutate probe/check_path from wellness classification — scheduler speaks."""
    if not state.wellness_probes_enabled:
        return
    rec = state.slot_records.get("wellness")
    text = wellness_text or (rec.source_text if rec else "")
    text = text or state.slot_values.get("wellness", "")
    polarity = rec.polarity if rec else None
    if polarity is None and text:
        from packages.dialogue_engine.fast_interpreter import _detect_polarity

        polarity = _detect_polarity(text)
    branch = classify_wellness_path(wellness_text=text, polarity=polarity)
    if branch.path == CheckPath.STANDARD:
        return
    apply_wellness_branch(state, branch)


def _advance_probe_after_answer(
    state: EngineState,
    text: str,
) -> tuple[EngineState, list[Effect]]:
    advance_probe_phase(state, text)
    state.processing_turn_id = None
    state.processing_effect_id = None
    state.bump_revision()
    return _schedule_advance(state, user_text=text)


def _speak_probe(
    state: EngineState,
    phase: str,
    *,
    clarification: bool = False,
) -> tuple[EngineState, list[Effect]]:
    state.probe_phase = phase
    state.processing_turn_id = None
    state.processing_effect_id = None
    state.bump_revision()
    return _schedule_advance(state, clarify=clarification)


def _emit_summary(state: EngineState, *, acknowledge: str = "") -> tuple[EngineState, list[Effect]]:
    """Close summary — NOT terminal by itself (frozen contract).

    Summary delivery must leave the call open so the elder's farewell turn
    reaches goodbye_final (corpus: summary → user goodbye → goodbye_final).
    Only goodbye_final / partial / urgent intents hang up.
    Anti-stall: a second summary with nothing new closes via goodbye_final
    instead of repeating «На сегодня всё» forever (stress: 25-turn chats
    re-summarizing debris). New symptoms never reach here (episode plans
    take priority in the scheduler).
    """
    if state.call_closed and state.summary_spoken:
        return state, []
    if state.summary_delivered:
        return _emit_goodbye_final(state)
    state.fsm_state = FsmState.SUMMARY
    state.summary_spoken = True
    state.bump_revision()
    return _emit_speak(
        state,
        text=questions.summary_close_speech(state, acknowledge=acknowledge),
        intent="summary",
        slot=None,
        marks_question=False,
    )


def _record_negative_wellness(
    state: EngineState, user_text: str, *, record_concern: bool = True
) -> bool:
    """Grounded negative wellness evidence (never a fabrication).

    Returns True when recorded. Shared by urgent close and the red-state
    clarify path: «мне плохо, я умираю» is a negative fact even before we
    know WHAT hurts. record_concern=False keeps wellness_concern empty so
    the probe ladder still asks WHAT (the raw red cry is not a complaint).
    """
    if not user_text or state.slots.get("wellness") != SlotStatus.OPEN:
        return False
    from packages.dialogue_engine.check_path import is_urgent_state
    from packages.dialogue_engine.fast_interpreter import _detect_polarity
    from packages.dialogue_engine.fast_interpreter import (
        is_nonhealth_evaluation as _film_eval,
    )

    # «Мне плохо от фильма» is not a health fact on any path.
    if _film_eval(user_text):
        return False

    # Red-state cries («умираю») are negative facts even though no polarity
    # list contains them.
    if _detect_polarity(user_text) != "negative" and not is_urgent_state(user_text):
        return False
    apply_slot_answer(
        state,
        "wellness",
        user_text.strip(),
        turn_id=state.processing_turn_id or "",
        source_text=user_text.strip(),
        polarity="negative",
        confidence=0.9,
    )
    if record_concern and not state.wellness_concern:
        state.wellness_concern = user_text.strip()
    return True


def _concern_established(state: EngineState, raw_text: str = "") -> bool:
    """Do we know WHAT hurts (site/symptom on record or in this turn)?"""
    if state.wellness_concern and state.wellness_concern.strip():
        return True
    if state.observations.get("important_to_share"):
        return True
    if any(ep.status != "resolved" for ep in state.issue_episodes.values()):
        return True
    if raw_text:
        from packages.dialogue_engine.check_path import _PAIN

        if _PAIN.search(raw_text):
            return True
    return False


def _emit_urgent_close(
    state: EngineState, *, user_text: str | None = None
) -> tuple[EngineState, list[Effect]]:
    # Urgent close owns the URGENT check path (frozen gate: emergency never
    # probes, never partially closes). Record the path explicitly so
    # check_path reflects reality even when the hijack fires before the
    # wellness branch runs (live fs-41e2a57b).
    state.check_path = CheckPath.URGENT
    # Preserve genuine evidence: an explicit "мне плохо" alongside the
    # emergency is a grounded negative wellness fact, not a fabrication.
    # Record it so the family summary keeps what Vera actually heard.
    if user_text:
        _record_negative_wellness(state, user_text)
    state.fsm_state = FsmState.SUMMARY
    state.summary_spoken = True
    state.call_closed = True
    state.closing_reason = "urgent"
    state.bump_revision()
    return _emit_speak(
        state,
        text=questions._URGENT_CLOSE,
        intent="urgent_close",
        slot=None,
        marks_question=False,
    )


def _advance_after_fill(
    state: EngineState,
    filled_slot: str,
) -> tuple[EngineState, list[Effect]]:
    return _advance_after_fills(state, [filled_slot])


def _speak_slot_question(
    state: EngineState,
    slot: str,
    *,
    clarification: bool = False,
) -> tuple[EngineState, list[Effect]]:
    if not can_ask_slot(state, slot):
        return _close_partial(state)
    text = questions.slot_question(slot, clarification=clarification, state=state)
    intent = f"clarify_{slot}" if clarification else f"check_{slot}"
    return _emit_speak(
        state,
        text=text,
        intent=intent,
        slot=slot,
        marks_question=True,
    )


def _harvest_off_context_background_slots(
    state: EngineState,
    turn,
    *,
    answer_slot: str | None = None,
) -> list[str]:
    """Fill open background slots from free speech after semantic apply.

    Must not own the RichUserTurn or skip IssueEpisode creation.
    """
    if not turn.raw_text.strip():
        return []
    slot_ctx = answer_slot or state.answer_context_slot()
    if not slot_ctx or not slot_ctx.startswith("episode_"):
        return []
    from packages.dialogue_engine.issue_mention_extract import extract_goal_facts

    harvested = extract_goal_facts(turn.raw_text)
    filled: list[str] = []
    for slot in ("plans", "mood", "sleep"):
        if state.slots.get(slot) != SlotStatus.OPEN:
            continue
        fact = next((f for f in harvested if f.field == slot), None)
        if fact is None:
            continue
        quote = fact.evidence.quote if fact.evidence else turn.raw_text
        apply_slot_answer(
            state,
            slot,
            fact.value if fact.value not in ("positive", "negative", "neutral") else quote,
            turn_id=turn.utterance_id,
            source_text=quote,
        )
        filled.append(slot)
    return filled


def _apply_off_context_slot_answer(
    state: EngineState,
    turn,
    *,
    answer_slot: str | None = None,
) -> tuple[EngineState, list[Effect]] | None:
    """Deprecated early-owner path — prefer _harvest_off_context_background_slots."""
    filled = _harvest_off_context_background_slots(
        state, turn, answer_slot=answer_slot
    )
    if not filled:
        return None
    state.processing_turn_id = None
    state.processing_effect_id = None
    state.pending_episode_attribute = None
    state.planned_question = None
    state.playing_question = None
    state.active_playout = None
    state.bump_revision()
    return _advance_after_fills(
        state, filled, user_text=turn.raw_text, turn=turn
    )
    return None


def _is_repair_text(text: str) -> bool:
    from packages.dialogue_engine.semantic_kernel.controls import match_repair

    return match_repair(text) is not None


def _advance_after_episode_answer(
    state: EngineState,
    turn,
    answer_slot: str | None,
) -> tuple[EngineState, list[Effect]] | None:
    from packages.dialogue_engine.issue_memory import get_active_episode
    from packages.dialogue_engine.question_context import (
        attribute_need_satisfied,
        episode_is_resolved,
    )

    if not turn.answers_pending_question:
        return None
    if not (
        (answer_slot and answer_slot.startswith("episode_"))
        or state.pending_episode_attribute
    ):
        return None
    pending = state.pending_episode_attribute
    if pending:
        ep = get_active_episode(state)
        if ep is not None:
            if episode_is_resolved(ep):
                state.pending_episode_attribute = None
                state.active_episode_id = None
            elif attribute_need_satisfied(ep, pending):
                state.pending_episode_attribute = None
                from packages.dialogue_engine.issue_memory import finalize_episode_if_complete

                finalize_episode_if_complete(ep)
    state.processing_turn_id = None
    state.processing_effect_id = None
    state.waiting_on_slot = None
    state.bump_revision()
    if state.pending_episode_attribute and state.active_episode_id:
        outcome = _schedule_advance(state, turn=turn)
        if outcome[1]:
            return outcome
        return state, []
    return _advance_after_fills(
        state, [], user_text=turn.raw_text, turn=turn
    )


def _speak_repair(
    state: EngineState,
    slot: str,
) -> tuple[EngineState, list[Effect]]:
    from packages.dialogue_engine.question_context import question_context_from_state

    delivered = state.delivered_question
    ctx = question_context_from_state(state)
    from packages.dialogue_engine.question_context import repair_question_text

    question_text = delivered.text if delivered else repair_question_text(state, slot)
    text = questions.repair_response(question_text)
    repair_slot = ctx.slot if ctx and ctx.slot else slot
    # Repair re-speaks the pending probe out loud — it counts toward the
    # temporal anti-loop like any other emission (fuzz I3). On the 3rd
    # repeat do NOT re-ask the probe: short bare repair, pending kept.
    if _note_temporal_emit(state, repair_slot, "repair_repeat"):
        return _emit_speak(
            state,
            text="Да, слышу. Повторите, пожалуйста.",
            intent="repair_repeat_bare",
            slot=None,
            marks_question=False,
        )
    state.bump_revision()
    gen_id = state.next_generation_id()
    gen = state.active_playout_generation + 1
    state.active_playout_generation = gen
    q = Question(
        question_id=delivered.question_id if delivered else gen_id,
        slot=repair_slot,
        text=text,
        phase=QuestionPhase.PLANNED,
        intent="repair_repeat",
        goal_id=delivered.goal_id if delivered else None,
    )
    state.active_playout = q
    return state, [
        SpeakEffect(
            effect_id=_new_effect_id(),
            revision=state.revision,
            generation_id=gen_id,
            generation=gen,
            text=text,
            intent="repair_repeat",
            question_id=delivered.question_id if delivered else gen_id,
            slot=repair_slot,
            marks_question=False,
        )
    ]


def _has_urgent_evidence(state: EngineState) -> bool:
    """True when any recorded concern already carries emergency lexicon.

    Guards _close_partial: emergency must never be abandoned via partial
    (live fs-41e2a57b, fuzz I4). A defused red-state (movie/news context,
    investigated) is NOT evidence — never escalate on it.
    """
    if str(state.observations.get("concern_status") or "").startswith("defused"):
        return False
    bits: list[str] = []
    if state.wellness_concern:
        bits.append(state.wellness_concern)
    if state.wellness_duration:
        bits.append(state.wellness_duration)
    for key in ("important_to_share", "wellness_concern"):
        val = state.observations.get(key)
        if val:
            bits.append(str(val))
    for slot in ("wellness", "mood"):
        val = state.slot_values.get(slot)
        if val:
            bits.append(str(val))
    for ep in state.issue_episodes.values():
        if ep.primary_label:
            bits.append(ep.primary_label)
        for attr in ("onset", "duration", "severity", "current"):
            val = ep.known_attributes.get(attr)
            if val:
                bits.append(str(val))
    return any(is_urgent_concern(b) for b in bits if b)


def _close_partial(state: EngineState) -> tuple[EngineState, list[Effect]]:
    if state.playing_question or state.planned_question:
        return state, []
    # While clarifying WHAT is red, the probe ladder owns the turn — never
    # cut it off with a close (partial text is wrong on red, and the urgent
    # verdict belongs to the ladder's third step, honestly marked).
    if state.red_state_pending:
        return _schedule_advance(state)
    # Emergency evidence must never be abandoned via partial — escalate.
    if _has_urgent_evidence(state):
        return _emit_urgent_close(state)
    state.call_closed = True
    state.closing_reason = "partial_unresolved"
    state.fsm_state = FsmState.FINAL_CLASSIFICATION
    state.bump_revision()
    return _emit_speak(
        state,
        text=questions._PARTIAL_CLOSE,
        intent="partial_unresolved_close",
        slot=None,
        marks_question=False,
    )


def _on_delivery_deferred(
    state: EngineState,
    event: DeliveryDeferred,
) -> tuple[EngineState, list[Effect]]:
    if state.deferred_speak and state.deferred_speak.effect_id == event.effect_id:
        return state, []
    return state, []


def _on_effect_failed(
    state: EngineState,
    event: EffectFailed,
) -> tuple[EngineState, list[Effect]]:
    state.bump_revision()
    return state, []


def _on_speak_effect_stale(
    state: EngineState,
    event: SpeakEffectStale,
) -> tuple[EngineState, list[Effect]]:
    if state.deferred_speak and state.deferred_speak.effect_id == event.effect_id:
        state.deferred_speak = None
    intent = event.intent
    if (
        intent == "summary"
        and state.summary_spoken
        and state.fsm_state == FsmState.SUMMARY
        and not state.call_closed
    ):
        return _emit_speak(
            state,
            text=questions.summary_close_speech(state),
            intent="summary",
            slot=None,
            marks_question=False,
        )
    if intent == "goodbye_final" and state.call_closed:
        return _emit_speak(
            state,
            text=questions.goodbye_final_speech(state),
            intent="goodbye_final",
            slot=None,
            marks_question=False,
        )
    if intent == "goodbye_confirm" and state.awaiting_goodbye_confirm:
        return _emit_speak(
            state,
            text=questions._GOODBYE_CONFIRM,
            intent="goodbye_confirm",
            slot=None,
            marks_question=False,
        )
    if intent.startswith(("check_", "clarify_")):
        slot = intent.split("_", 1)[1]
        if slot and can_ask_slot(state, slot):
            return _speak_slot_question(
                state,
                slot,
                clarification=intent.startswith("clarify_"),
            )
    return state, []


def _on_timer_expired(state: EngineState, event: TimerExpired) -> tuple[EngineState, list[Effect]]:
    if _stale(state, event.revision):
        return state, []
    slot = state.waiting_on_slot
    if event.timer_id.startswith("wait-") and not slot:
        slot = event.timer_id.removeprefix("wait-")
    state.waiting_on_slot = None
    state.bump_revision()
    if not slot or state.fsm_state != FsmState.DAILY_CHECK:
        return state, []
    if slot.startswith("probe_"):
        phase = slot.removeprefix("probe_")
        return _speak_probe(state, phase, clarification=True)
    if not can_ask_slot(state, slot):
        return _close_partial(state)
    return _speak_slot_question(state, slot, clarification=True)


def _handle_closing_turn(
    state: EngineState,
    semantic,
) -> tuple[EngineState, list[Effect]] | None:
    if semantic.act == SemanticAct.REPAIR_REQUEST:
        return None
    if (
        semantic.act == SemanticAct.BACKCHANNEL
        and state.summary_spoken
        and state.fsm_state == FsmState.SUMMARY
        and not state.call_closed
    ):
        if state.summary_delivered:
            return _emit_goodbye_final(state)
        if state.active_playout is None and state.deferred_speak is None:
            return _emit_summary(state)
        return state, []
    if semantic.act == SemanticAct.BACKCHANNEL and not state.awaiting_goodbye_confirm:
        return None
    if semantic.act == SemanticAct.UNCLEAR and not state.awaiting_goodbye_confirm:
        return None
    text = semantic.source_quote.lower().strip()
    if semantic.act == SemanticAct.GOODBYE_CONFIRM or (
        state.awaiting_goodbye_confirm and _confirms_goodbye(text)
    ):
        return _emit_goodbye_final(state)
    if semantic.act == SemanticAct.GOODBYE_REQUEST or _is_explicit_farewell(text):
        # Explicit farewell is enough — no double confirm.
        return _emit_goodbye_final(state)
    if _is_ambiguous_end_hint(text):
        state.awaiting_goodbye_confirm = True
        state.fsm_state = FsmState.GOODBYE
        state.bump_revision()
        return _emit_speak(
            state,
            text=questions._GOODBYE_CONFIRM,
            intent="goodbye_confirm",
            slot=None,
            marks_question=False,
        )
    return None


def _emit_goodbye_final(state: EngineState) -> tuple[EngineState, list[Effect]]:
    state.goodbye_confirmed = True
    state.awaiting_goodbye_confirm = False
    state.fsm_state = FsmState.FINAL_CLASSIFICATION
    state.call_closed = True
    state.closing_reason = "goodbye"
    state.goodbye_count = max(state.goodbye_count, 1)
    state.bump_revision()
    return _emit_speak(
        state,
        text=questions.goodbye_final_speech(state),
        intent="goodbye_final",
        slot=None,
        marks_question=False,
    )


def _is_explicit_farewell(text: str) -> bool:
    low = text.lower().strip().rstrip(".!?")
    if not low:
        return False
    if any(marker in low for marker in questions._GOODBYE_MARKERS):
        return True
    if low in {
        "пока",
        "заканчиваем",
        "закончили",
        "закончим",
        "давайте закончим",
        "закончим разговор",
        "хватит разговор",
        "хватит",
        "стоп",
    }:
        return True
    return bool(re.search(r"\b(закончим|закончить|заканчива\w*|хватит)\b", low))


def _is_ambiguous_end_hint(text: str) -> bool:
    """Only truly ambiguous end hints may ask goodbye_confirm."""
    low = text.lower().strip().rstrip(".!?")
    return low in {"всё", "все", "ладно всё", "ладно все", "ну всё", "ну все"}


def _confirms_goodbye(text: str) -> bool:
    return text in {"да", "ага", "угу", "конечно", "давайте", "ладно", "yes"}
