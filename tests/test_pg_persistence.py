"""PostgreSQL persistence — skipped when IMVERA_PG_URL is unset or DB unreachable."""

import os
import uuid

import pytest

from packages.contracts.core import DeliveryStage, TerminationReason
from packages.contracts.enums import FsmState
from packages.core import create_call_record_store
from packages.dialogue.session import CallSession

PG_URL = os.environ.get("IMVERA_PG_URL")


def _pg_available() -> bool:
    if not PG_URL:
        return False
    try:
        import psycopg

        with psycopg.connect(PG_URL, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _pg_available(), reason="PostgreSQL not available")


@pytest.fixture
def pg_store():
    store = create_call_record_store(PG_URL)
    return store


def test_pg_consent_decline_survives_restart(pg_store) -> None:
    call_id = f"pg-{uuid.uuid4().hex[:12]}"
    family_id = "fam-pg-test"
    session = CallSession(call_id=call_id, family_id=family_id, store=pg_store)
    session.start()
    session.handle_user_text("да")
    session.handle_user_text("нет, не согласен")

    result = pg_store.get_call_result(call_id, family_id)
    assert result is not None
    assert result.family_id == family_id
    assert result.call_ended is True
    assert result.delivery_stage == DeliveryStage.PERSISTED
    assert result.termination_reason == TerminationReason.CONSENT_DECLINED
    assert result.fsm_state == FsmState.FINAL_CLASSIFICATION

    assert pg_store.get_call_result(call_id, "wrong-family") is None

    events = pg_store.get_events(call_id, family_id)
    ended = [e for e in events if e.event_type == "CALL_ENDED"]
    assert len(ended) == 1


def test_pg_idempotent_finalize(pg_store) -> None:
    call_id = f"pg-idem-{uuid.uuid4().hex[:12]}"
    family_id = "fam-pg-idem"
    session = CallSession(call_id=call_id, family_id=family_id, store=pg_store)
    session.start()
    session.handle_user_text("да")
    session.handle_user_text("нет, не согласен")
    session.handle_user_text("алло")
    session.handle_user_text("ещё раз")

    events = pg_store.get_events(call_id, family_id)
    ended = [e for e in events if e.event_type == "CALL_ENDED"]
    assert len(ended) == 1
