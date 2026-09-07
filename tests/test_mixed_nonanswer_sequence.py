"""Mixed non-answer sequence — budget must not reset (spec §21.1)."""

from packages.contracts.enums import FsmState, GoalStatus
from packages.contracts.semantic import SemanticPayload
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.context_builder import active_question_kind
from packages.dialogue.planner import Planner
from packages.dialogue.question_ledger import MAX_AUTOMATIC_ATTEMPTS
from packages.dialogue.semantic_adapter import adapt_semantic_turn
from packages.dialogue.session import CallSession


def _payload(dialogue_act: str, **kw) -> SemanticPayload:
    base = {
        "dialogue_act": dialogue_act,
        "control": "none",
        "consent_answer": "not_applicable",
        "answers_pending_question": False,
        "needs_clarification": False,
    }
    base.update(kw)
    return SemanticPayload(**base)


def _daily() -> CallSession:
    session = CallSession(call_id="mixed-nonanswer", family_id="audit-family",
                          store=InMemoryCallRecordStore())
    session.start()
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    session.state.fsm_state = FsmState.DAILY_CHECK
    open_prop = Planner.plan_vera_turn(session.state, 1, "g1")
    session.transitions.commit_transition(session.state, open_prop)
    session.mark_spoken_action("g1")
    return session


def _turn(session: CallSession, text: str, payload: SemanticPayload) -> str:
    interp, _ = adapt_semantic_turn(
        text,
        payload,
        state=session.state,
        active_question_kind=active_question_kind(session.state),
    )
    result = session.handle_user_text(text, interp=interp)
    return result.proposal.intent


def test_mixed_nonanswer_sequence_limited_attempts() -> None:
    session = _daily()
    goal = session.state.ensure_goal("wellness")
    assert goal.automatic_attempts_used == 1

    sequence = [
        ("ага", _payload("backchannel")),
        ("не знаю", _payload("unclear", needs_clarification=True)),
        ("кто вы", _payload("question", user_question="кто вы")),
        ("алло", _payload("backchannel")),
    ]
    intents: list[str] = []
    for text, meaning in sequence:
        intents.append(_turn(session, text, meaning))

    assert intents[0] == "wait_for_continuation"
    assert intents[2] == "explain_vera_resume"
    assert len(session.state.facts) == 0

    clarify = session.handle_wait_expired()
    if clarify.proposal.intent.startswith(("check_", "clarify_")):
        session.mark_spoken_action(clarify.proposal.generation_id)

    _turn(session, "ага", _payload("backchannel"))
    close = session.handle_wait_expired()

    goal = session.state.get_goal("wellness")
    assert goal is not None
    assert goal.automatic_attempts_used <= MAX_AUTOMATIC_ATTEMPTS
    assert goal.status in (GoalStatus.UNRESOLVED, GoalStatus.OPEN)
    assert "не получилось" in close.proposal.speech or goal.status == GoalStatus.UNRESOLVED
