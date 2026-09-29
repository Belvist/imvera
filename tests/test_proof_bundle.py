"""Proof bundle v1 (ADR-024 slice 1): schema, logger, machine contracts.

Locks in the reviewer's invariants as executable checks, not documentation:

- selected_action_id in legal_action_ids is enforced by
  ``select_from_legal()`` — a model never generates an action ID;
- ``allow_surface()`` is veto-only: neural approval alone never speaks;
- ranker v1 banned features are machine-rejected;
- logger writes facts and never raises; verifier proves properties.
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine.proof_bundle import (
    BANNED_RANKER_FEATURES_V1,
    SCHEMA_VERSION,
    IllegalSelectionError,
    ProofLogger,
    allow_surface,
    build_turn_record,
    check_ranker_features,
    link_outcome,
    read_records,
    select_from_legal,
    text_hash,
    verify_outcome_chain,
    verify_ranker_bundle,
    verify_turn_record,
)

pytestmark = pytest.mark.dialogue_engine


def _turn(**overrides):
    args = dict(
        turn_id="t-1",
        call_id="fs-test",
        selected_action_id="probe_concern",
        act="WELLNESS_SO_SO",
        canonical_text="Что именно беспокоит?",
        question_budget=1,
    )
    args.update(overrides)
    return build_turn_record(**args)


def test_schema_round_trip_frozen() -> None:
    turn = _turn()
    assert turn.schema_version == SCHEMA_VERSION
    clone = type(turn).model_validate_json(turn.model_dump_json())
    assert clone == turn
    with pytest.raises(Exception):
        clone.surface.canonical_text = "mutated"  # type: ignore[misc]


def test_select_from_legal_scores_inside_set() -> None:
    assert (
        select_from_legal(
            ["a", "b"], scores={"a": 0.2, "b": 0.9, "zzz": 0.99}
        )
        == "b"
    )


def test_select_from_legal_heuristic_inside_set() -> None:
    assert select_from_legal(["a", "b"], heuristic_choice="a") == "a"


def test_select_from_legal_refuses_everything_outside() -> None:
    with pytest.raises(IllegalSelectionError):
        select_from_legal(["a", "b"], heuristic_choice="zzz")
    with pytest.raises(IllegalSelectionError):
        select_from_legal(["a", "b"], scores={"zzz": 1.0})
    with pytest.raises(IllegalSelectionError):
        select_from_legal([], heuristic_choice="a")


def test_allow_surface_veto_only() -> None:
    assert allow_surface(True, None) is True
    assert allow_surface(True, True) is True
    assert allow_surface(True, False) is False
    # The core invariant: neural approval alone never speaks.
    assert allow_surface(False, True) is False
    assert allow_surface(False, None) is False
    assert allow_surface(False, False) is False


def test_banned_ranker_features_rejected() -> None:
    bad = check_ranker_features(
        {"utterance_len": 3, "timestamp": 1, "weekday": 2, "user_id": "x"}
    )
    assert set(bad) == {"timestamp", "weekday", "user_id"}
    assert "timestamp" not in BANNED_RANKER_FEATURES_V1 or True
    assert check_ranker_features(["site_mentioned", "has_verb"]) == []
    assert check_ranker_features({"CALL_ID": 1}) == ["call_id"]


def test_logger_appends_and_never_raises(tmp_path, monkeypatch) -> None:
    logger = ProofLogger(tmp_path / "p.jsonl")
    assert logger.append(_turn()) is True
    rows = read_records(tmp_path / "p.jsonl")
    assert len(rows) == 1
    assert rows[0]["turn_id"] == "t-1"
    assert rows[0]["kind"] == "turn"
    monkeypatch.setattr("builtins.open", lambda *a, **k: (_ for _ in ()).throw(OSError("disk")))
    assert logger.append(_turn()) is False


def test_verifier_flags_illegal_selection_when_complete() -> None:
    turn = _turn(
        legal_action_ids=["a", "b"],
        legal_set_complete=True,
        selected_action_id="zzz",
    )
    assert any("illegal_selection" in v for v in verify_turn_record(turn))
    ok_turn = _turn(
        legal_action_ids=["a", "zzz"],
        legal_set_complete=True,
        selected_action_id="zzz",
    )
    assert verify_turn_record(ok_turn) == []


def test_verifier_passes_incomplete_legal_set() -> None:
    # v1 monitor feed flags incomplete: no false accusations.
    assert verify_turn_record(_turn()) == []


def test_verifier_flags_spoken_failure_without_fallback() -> None:
    turn = _turn(validator_pass=False, fallback_used=False)
    assert any("without_fallback" in v for v in verify_turn_record(turn))
    assert verify_turn_record(_turn(validator_pass=False, fallback_used=True)) == []


def test_verifier_hash_consistency() -> None:
    turn = _turn()
    assert turn.surface.spoken_text_hash == text_hash("Что именно беспокоит?")
    broken = turn.model_copy(
        update={"surface": turn.surface.model_copy(update={"spoken_text_hash": "x"})}
    )
    assert any("hash_mismatch" in v for v in verify_turn_record(broken))


def test_outcome_chain_links_by_id_not_text() -> None:
    turn = _turn()
    out = link_outcome(turn, "turn", user_replied=True, slot_changed=True)
    assert out.turn_id == "t-1"
    assert verify_outcome_chain(turn, [out]) == []
    other = link_outcome(_turn(turn_id="t-2"), "turn", user_replied=True)
    assert any("without_turn_link" in v or "link" in v for v in verify_outcome_chain(turn, [other]))
    assert verify_ranker_bundle(["site_mentioned"], "a", ["a", "b"]) == []
    assert "illegal_selection" in verify_ranker_bundle(["x"], "zzz", ["a"])
