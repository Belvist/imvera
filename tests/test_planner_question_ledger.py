"""QuestionLedger regressions — 20× backchannel loop (spec §21.1, §23)."""

from collections import Counter

from packages.contracts.core import TerminationReason
from packages.contracts.enums import AnswerJudgement, FsmState, GoalStatus, SlotStatus
from packages.contracts.semantic import SemanticPayload
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.context_builder import active_question_kind
from packages.dialogue.planner import Planner
from packages.dialogue.question_ledger import MAX_AUTOMATIC_ATTEMPTS
from packages.dialogue.semantic_bridge import semantic_to_user_interpretation
from packages.dialogue.session import CallSession
from packages.dialogue.transition_store import DialogueTransitionStore


def _daily_session() -> CallSession:
    session = CallSession(
        call_id="audit-aha",
        family_id="audit-family",
        store=InMemoryCallRecordStore(),
    )
    session.start()
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    session.state.fsm_state = FsmState.DAILY_CHECK
    open_prop = Planner.plan_vera_turn(session.state, session.turn_id + 1, "g-open")
    session.transitions.commit_transition(session.state, open_prop)
    session.mark_spoken_action("g-open")
    return session


def _backchannel_payload() -> SemanticPayload:
    return SemanticPayload(
        dialogue_act="backchannel",
        control="none",
        consent_answer="not_applicable",
        answers_pending_question=False,
        needs_clarification=False,
    )


def _apply_backchannel(session: CallSession, text: str = "ага") -> None:
    meaning = _backchannel_payload()
    interp = semantic_to_user_interpretation(
        text,
        meaning,
        active_question_kind=active_question_kind(session.state),
        pending_slot=session.state.pending_slot,
    )
    result = session.handle_user_text(text, interp=interp)
    assert result.proposal.intent == "wait_for_continuation"


def _drive_wait_cycle(session: CallSession):
    return session.handle_wait_expired()


def test_twenty_backchannels_no_invented_facts_and_limited_attempts() -> None:
    """Reproduces §23: not 21 identical wellness questions; honest terminal outcome."""
    session = _daily_session()
    spoken: list[str] = []

    open_goal = session.state.ensure_goal("wellness")
    assert open_goal.automatic_attempts_used == 1

    for _ in range(20):
        if session.state.final_action_done:
            break
        _apply_backchannel(session)

    assert not session.state.final_action_done
    expired = _drive_wait_cycle(session)
    if expired.proposal.speech:
        spoken.append(expired.proposal.speech)
    if expired.proposal.intent.startswith(("check_", "clarify_")):
        session.mark_spoken_action(expired.proposal.generation_id)

    for _ in range(5):
        if session.state.final_action_done:
            break
        _apply_backchannel(session)
        expired = _drive_wait_cycle(session)
        if expired.proposal.speech:
            spoken.append(expired.proposal.speech)
        if session.state.final_action_done:
            break

    goal = session.state.get_goal("wellness")
    assert goal is not None
    assert goal.status == GoalStatus.UNRESOLVED
    assert goal.automatic_attempts_used <= MAX_AUTOMATIC_ATTEMPTS
    assert len(session.state.facts) == 0
    assert session.state.slots["wellness"] == SlotStatus.UNRESOLVED
    assert session.state.termination_reason == TerminationReason.PARTIAL
    assert session.state.final_action_done

    counts = Counter(spoken)
    assert len(counts) >= 2
    assert counts[_SLOT_WELLNESS_OPEN] <= 1
    assert "Сейчас не получилось узнать" in spoken[-1]


_SLOT_WELLNESS_OPEN = "Расскажите, как вы себя чувствуете сейчас?"


def test_backchannel_wait_then_clarify_then_unresolved() -> None:
    session = _daily_session()
    _apply_backchannel(session)
    clarify = _drive_wait_cycle(session)
    assert "двух словах" in clarify.proposal.speech
    session.mark_spoken_action(clarify.proposal.generation_id)

    _apply_backchannel(session)
    close = _drive_wait_cycle(session)
    assert "не получилось узнать" in close.proposal.speech
    assert session.state.slots["wellness"] == SlotStatus.UNRESOLVED


def test_restart_preserves_unresolved_goal() -> None:
    session = _daily_session()
    _apply_backchannel(session)
    clarify = _drive_wait_cycle(session)
    session.mark_spoken_action(clarify.proposal.generation_id)
    _apply_backchannel(session)
    _drive_wait_cycle(session)

    store = session.store
    family_id = session.state.family_id
    call_id = session.state.call_id
    reloaded = DialogueTransitionStore(store, family_id).load(call_id)
    assert reloaded is not None
    assert reloaded.state.slots["wellness"] == SlotStatus.UNRESOLVED
    goal = reloaded.state.get_goal("wellness")
    assert goal is not None
    assert goal.status == GoalStatus.UNRESOLVED
    assert goal.automatic_attempts_used == MAX_AUTOMATIC_ATTEMPTS


def test_planner_direct_twenty_backchannels_spec_script() -> None:
    """§23 script shape — must not emit 21 identical wellness prompts."""
    from packages.dialogue.state import DialogueState

    state = DialogueState(
        call_id="audit-aha",
        fsm_state=FsmState.DAILY_CHECK,
        greeted=True,
    )
    state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    open_prop = Planner.plan_vera_turn(state, 1, "g1")
    Planner.mark_question_delivered(state, "g1")
    spoken = [open_prop.speech]
    meaning = _backchannel_payload()

    for n in range(20):
        interp = semantic_to_user_interpretation(
            "ага",
            meaning,
            active_question_kind=active_question_kind(state),
            pending_slot=state.pending_slot,
        )
        wait = Planner.plan_after_user(state, "ага", f"g{n + 2}", n + 2, interp=interp)
        assert wait.intent == "wait_for_continuation"
        if state.final_action_done:
            break

    follow = Planner.plan_wait_expired(state, 22, "g22b")
    if follow.speech:
        spoken.append(follow.speech)
    if follow.intent.startswith(("check_", "clarify_")):
        Planner.mark_question_delivered(state, follow.generation_id)

    for n in range(5):
        interp = semantic_to_user_interpretation(
            "ага",
            meaning,
            active_question_kind=active_question_kind(state),
            pending_slot=state.pending_slot,
        )
        Planner.plan_after_user(state, "ага", f"g{n + 30}", n + 30, interp=interp)
        follow = Planner.plan_wait_expired(state, n + 31, f"g{n + 31}b")
        if follow.speech:
            spoken.append(follow.speech)
        if state.final_action_done:
            break

    assert Counter(spoken)[_SLOT_WELLNESS_OPEN] == 1
    assert len(state.facts) == 0
    assert state.get_goal("wellness").status == GoalStatus.UNRESOLVED
