"""No memory mixing between подопечные (reviewer item 3).

Same family, different elders: the second call must NOT inherit the
first call's facts (follow_up_opening stays off, prior empty).
"""

from __future__ import annotations

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession


def _closed_session(store: InMemoryCallRecordStore, call_id: str, elder: str) -> None:
    s = CallSession(
        call_id=call_id, family_id="fam", store=store, elder_display_name=elder
    )
    s.start()
    s.state.facts["dummy"] = type("F", (), {"value": "x", "source_quote": "y"})()
    snap = s._snapshot()
    snap.call_ended = True
    store.save_dialogue_snapshot(snap, "fam")


def test_prior_scoped_to_elder_not_family() -> None:
    store = InMemoryCallRecordStore()
    _closed_session(store, "c1", "Анна")
    got_anna = store.get_latest_family_snapshot("fam", elder_display_name="Анна")
    assert got_anna is not None and got_anna.call_id == "c1"
    assert store.get_latest_family_snapshot("fam", elder_display_name="Пётр") is None


def test_second_elder_starts_clean(monkeypatch) -> None:
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    store = InMemoryCallRecordStore()
    _closed_session(store, "c1", "Анна")
    s2 = CallSession(
        call_id="c2", family_id="fam", store=store, elder_display_name="Пётр"
    )
    s2.start()
    assert s2._engine is not None
    assert s2._engine.state.prior_call_context == {}
    assert s2._engine.state.follow_up_opening is False
