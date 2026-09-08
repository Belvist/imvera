"""Shared pytest fixtures — planner path by default; engine tests opt in."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def disable_dialogue_engine_by_default(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    """Legacy planner tests stay on planner unless marked ``@pytest.mark.dialogue_engine``."""
    if request.node.get_closest_marker("dialogue_engine"):
        monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
        return
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "0")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "dialogue_engine: run with DialogueEngine enabled")
