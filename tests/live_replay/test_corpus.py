"""Live call corpus — all known broken calls must pass together."""

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

FIXTURE_PATHS = sorted(FIXTURES_DIR.glob("*.json"))


@pytest.mark.parametrize("fixture_path", FIXTURE_PATHS, ids=lambda p: p.stem)
def test_live_replay_fixture(fixture_path: Path) -> None:
    fixture = ReplayFixture.load(fixture_path)
    result = replay_fixture(fixture)
    assert_fixture_invariants(fixture, result)
    assert all(v in {"ACCEPT", "HOLD_FRAGMENT", "DROP_ECHO"} for v in result.admissions)
    for turn in fixture.turns:
        if turn.expected_admission == "ACCEPT" and turn.stt_final.strip():
            assert result.admissions, "accepted turn must produce admission verdict"
