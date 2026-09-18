"""Outbox dispatch failure matrix — spec §15 four terminal paths."""

from packages.contracts.enums import FsmState
from packages.contracts.outbox import ActionOutboxStatus, apply_transition, may_auto_replay
from packages.contracts.turn import TurnProposal
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.planner import Planner
from packages.dialogue.session import CallSession


def _session_with_wellness_question() -> tuple[CallSession, TurnProposal]:
    session = CallSession(
        call_id="outbox-matrix",
        family_id="family-1",
        store=InMemoryCallRecordStore(),
    )
    session.start()
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    session.state.fsm_state = FsmState.DAILY_CHECK
    proposal = Planner.plan_vera_turn(session.state, session.turn_id + 1, "g-wellness")
    session.transitions.commit_transition(session.state, proposal)
    return session, proposal


def _outbox_status(session: CallSession, action_id: str) -> ActionOutboxStatus:
    record = session.transitions.get_outbox_record(session.state.call_id, action_id)
    assert record is not None
    return record.status


def test_failure_point_1_cancel_before_dispatch() -> None:
    """PCM never started — PENDING → CANCELLED; pending action cleared on replay."""
    session, proposal = _session_with_wellness_question()
    assert _outbox_status(session, proposal.generation_id) == ActionOutboxStatus.PENDING

    result = session.transitions.mark_outbox_cancelled(session.state, proposal.generation_id)
    assert result.ok
    assert _outbox_status(session, proposal.generation_id) == ActionOutboxStatus.CANCELLED
    assert session.transitions.replay_pending_action(session.state.call_id) is None


def test_failure_point_2_transport_complete() -> None:
    """Full phrase delivered — PENDING → DISPATCHING → TRANSPORT_COMPLETE."""
    session, proposal = _session_with_wellness_question()
    action_id = proposal.generation_id

    dispatch = session.transitions.mark_outbox_dispatching(session.state, action_id)
    assert dispatch.ok
    assert _outbox_status(session, action_id) == ActionOutboxStatus.DISPATCHING

    complete = session.transitions.mark_outbox_transport_complete(
        session.state, action_id, sent_samples=8000
    )
    assert complete.ok
    assert _outbox_status(session, action_id) == ActionOutboxStatus.TRANSPORT_COMPLETE
    record = session.transitions.get_outbox_record(session.state.call_id, action_id)
    assert record is not None
    assert record.sent_samples == 8000
    assert session.transitions.replay_pending_action(session.state.call_id) is None


def test_failure_point_3_delivery_unknown_after_partial_pcm() -> None:
    """Barge-in after partial send — DISPATCHING → DELIVERY_UNKNOWN; no auto replay."""
    session, proposal = _session_with_wellness_question()
    action_id = proposal.generation_id
    session.transitions.mark_outbox_dispatching(session.state, action_id)

    unknown = session.transitions.mark_outbox_delivery_unknown(
        session.state, action_id, sent_samples=1200
    )
    assert unknown.ok
    assert _outbox_status(session, action_id) == ActionOutboxStatus.DELIVERY_UNKNOWN
    assert may_auto_replay(ActionOutboxStatus.DELIVERY_UNKNOWN) is False
    assert session.transitions.replay_pending_action(session.state.call_id) is None


def test_failure_point_4_illegal_transitions_rejected() -> None:
    """Terminal states and skipped DISPATCHING cannot be forged."""
    session, proposal = _session_with_wellness_question()
    action_id = proposal.generation_id
    record = session.transitions.get_outbox_record(session.state.call_id, action_id)
    assert record is not None

    assert apply_transition(record, ActionOutboxStatus.TRANSPORT_COMPLETE) is None
    assert session.transitions.mark_outbox_transport_complete(session.state, action_id).ok is False

    session.transitions.mark_outbox_dispatching(session.state, action_id)
    session.transitions.mark_outbox_transport_complete(session.state, action_id, sent_samples=1)
    assert _outbox_status(session, action_id) == ActionOutboxStatus.TRANSPORT_COMPLETE
    assert session.transitions.mark_outbox_cancelled(session.state, action_id).ok is False


def test_mark_action_delivered_moves_pending_to_dispatching() -> None:
    """Question delivery marks DISPATCHING and clears pending_action metadata."""
    session, proposal = _session_with_wellness_question()
    assert session.transitions.replay_pending_action(session.state.call_id) is not None

    ok = session.mark_spoken_action(proposal.generation_id)
    assert ok
    assert _outbox_status(session, proposal.generation_id) == ActionOutboxStatus.DISPATCHING
    trans = session.transitions.load(session.state.call_id)
    assert trans is not None
    assert trans.pending_action is None
