"""Protocol table is the single source (P0b Step 1).

Fails if anyone forks a second copy of required/coverage lists.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.dialogue_engine


def test_yaml_loads_with_version() -> None:
    from packages.dialogue_engine.protocol import ACTS, MODES, PROTOCOL, STATUS_IMPACT

    assert PROTOCOL["version"] == 1
    assert set(MODES) >= {"short", "full", "complaint"}
    assert STATUS_IMPACT["missing_required_after_close"] == "YELLOW"
    assert set(ACTS) >= {"WELLNESS_OK", "DECLINE", "ISSUE_SITE"}


def test_short_mode_requires_no_bg() -> None:
    from packages.dialogue_engine.protocol import BACKGROUND_SLOTS, required_slots

    short = set(required_slots("short"))
    assert not (short & set(BACKGROUND_SLOTS))
    assert {"identity", "consent", "can_talk", "wellness"} <= short


def test_full_mode_requires_bg() -> None:
    from packages.dialogue_engine.protocol import BACKGROUND_SLOTS, required_slots

    full = set(required_slots("full"))
    assert set(BACKGROUND_SLOTS) <= full


def test_constants_match_yaml() -> None:
    from packages.contracts.mandatory import PILOT_MANDATORY_CHECKS
    from packages.dialogue_engine.coverage import FILLER_ORDER
    from packages.dialogue_engine.protocol import coverage_order, required_slots

    assert tuple(PILOT_MANDATORY_CHECKS) == tuple(required_slots("full"))
    assert tuple(FILLER_ORDER) == tuple(coverage_order("full"))
