"""Product invariants for live call fs-1f6d3000 — must fail until live path is unified."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.live_replay.harness import (
    FIXTURES_DIR,
    ReplayFixture,
    assert_fixture_invariants,
    replay_fixture,
)

pytestmark = pytest.mark.dialogue_engine

_FIXTURE = FIXTURES_DIR / "fs-1f6d3000.json"


def test_fs_1f6d3000_live_replay_product_invariants() -> None:
    assert _FIXTURE.is_file(), "trace-derived fixture missing"
    fixture = ReplayFixture.load(_FIXTURE)
    result = replay_fixture(fixture)
    assert_fixture_invariants(fixture, result)

    # U1 vague negative → concern clarify, never duration-first
    assert result.turn_intents[0]
    assert any(i.startswith("probe_concern") for i in result.turn_intents[0])
    assert "probe_duration" not in result.turn_intents[0]

    # U2 headache + temporal must create IssueEpisode before ITS
    headaches = [
        ep
        for ep in result.state.issue_episodes.values()
        if "голов" in (ep.primary_label or "").lower() or ep.kind == "symptom"
    ]
    assert headaches, "headache IssueEpisode must survive probe context"
    ep = headaches[0]
    temporal = (
        ep.known_attributes.get("onset")
        or ep.known_attributes.get("duration")
        or ""
    )
    assert temporal, "temporal evidence must attach to headache episode"
    assert "там" not in temporal.lower()
    assert any(
        tok in temporal.lower() for tok in ("вчера", "дня", "со вчера")
    ), temporal

    # Must not jump to ITS on the headache turn itself
    assert "important_to_share" not in result.turn_intents[1]

    # U3 meta must not resolve as recorded share + summary
    assert "summary" not in result.turn_intents[2]
    assert result.state.observations.get("important_to_share") in (None, "")

    # U4 explicit farewell → one goodbye_final, no confirm
    assert "goodbye_final" in result.turn_intents[3]
    assert "goodbye_confirm" not in result.turn_intents[3]
    assert result.state.call_closed is True


def test_architecture_no_probe_short_circuit_before_semantic_apply() -> None:
    """Static guard: live rich path must not consume turns via probe before apply."""
    reducer = Path("packages/dialogue_engine/reducer.py").read_text(encoding="utf-8")
    # Forbidden pattern: probe answer branch that returns advance WITHOUT apply first
    needle = "return _advance_probe_after_answer(state, user_text)"
    # Allow the helper definition and non-rich/legacy only if commented as compatibility.
    # Live rich path must not contain the early return sequence.
    rich_fn_start = reducer.find("def _apply_rich_turn(")
    next_def = reducer.find("\ndef _", rich_fn_start + 1)
    rich_body = reducer[rich_fn_start:next_def]
    assert "return _advance_probe_after_answer(state, user_text)" not in rich_body, (
        "legacy probe short-circuit still owns RichUserTurn before atomic_semantic_apply"
    )
    assert "atomic_semantic_apply(state, turn)" in rich_body
