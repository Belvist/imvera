"""Durable persist spool: outage writes land on disk, replay restores them."""

from __future__ import annotations

from packages.contracts.core import CallResultSnapshot
from packages.contracts.enums import FsmState
from packages.core import create_call_record_store
from packages.core.memory_store import InMemoryCallRecordStore, observation_from_fact
from packages.core.spill import SpillingCallRecordStore, replay_spool


class _DownStore(InMemoryCallRecordStore):
    def ensure_call(self, *_a, **_k):
        raise ConnectionError("pg down")

    def save_observation(self, *_a, **_k):
        raise ConnectionError("pg down")

    def append_event(self, *args, **kwargs):
        raise ConnectionError("pg down")

    def finalize_call(self, *_a, **_k):
        raise ConnectionError("pg down")


def _spilling(tmp_path, delegate=None):
    store = SpillingCallRecordStore(delegate or _DownStore(), tmp_path / "spool")
    return store


def test_outage_writes_spill_to_disk_not_to_void(tmp_path) -> None:
    store = _spilling(tmp_path)
    assert store.ensure_call("c1", "f1").ok is False
    obs = observation_from_fact("c1", 1, _fact(), 1)
    assert store.save_observation(obs, "f1").ok is False

    files = list((tmp_path / "spool").glob("spill-*.jsonl"))
    assert len(files) == 1
    rows = files[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 2
    assert "ensure_call" in rows[0] and "save_observation" in rows[1]


def _fact():
    from packages.dialogue.facts import FactRecord

    return FactRecord(field="wellness", value="ok", source_quote="хорошо", turn_id=1)


def test_replay_restores_and_double_replay_is_safe(tmp_path) -> None:
    spool_store = _spilling(tmp_path)
    spool_store.ensure_call("c1", "f1")
    obs = observation_from_fact("c1", 1, _fact(), 1)
    spool_store.save_observation(obs, "f1")

    live = InMemoryCallRecordStore()
    counts = replay_spool(tmp_path / "spool", live)
    assert counts["applied"] == 2
    assert live.get_call_result("c1", "f1") is not None

    counts2 = replay_spool(tmp_path / "spool", live)
    assert counts2["applied"] == 0  # file renamed to .done after first replay


def test_healthy_store_passes_through_without_spool(tmp_path) -> None:
    live = InMemoryCallRecordStore()
    store = SpillingCallRecordStore(live, tmp_path / "spool")
    assert store.ensure_call("c1", "f1").ok is True
    assert list((tmp_path / "spool").glob("spill-*.jsonl")) == []


def test_finalize_spills_and_replays(tmp_path) -> None:
    spool_store = _spilling(tmp_path)
    snap = CallResultSnapshot(
        call_id="c9", family_id="f9", fsm_state=FsmState.DAILY_CHECK
    )
    assert spool_store.finalize_call(snap).ok is False

    live = InMemoryCallRecordStore()
    live.ensure_call("c9", "f9")
    counts = replay_spool(tmp_path / "spool", live)
    assert counts["applied"] == 1


def test_spool_opt_in_via_env(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("IMVERA_PERSIST_SPOOL_DIR", raising=False)
    plain = create_call_record_store(dsn=None)
    assert not isinstance(plain, SpillingCallRecordStore)

    monkeypatch.setenv("IMVERA_PERSIST_SPOOL_DIR", str(tmp_path / "spool"))
    wrapped = create_call_record_store(dsn=None)
    assert isinstance(wrapped, SpillingCallRecordStore)
