"""Shared pytest fixtures — planner path by default; engine tests opt in."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def disable_dialogue_engine_by_default(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    """Legacy planner tests stay on planner unless marked ``@pytest.mark.dialogue_engine``."""
    if request.node.get_closest_marker("dialogue_engine"):
        monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
        return
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "0")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "dialogue_engine: run with DialogueEngine enabled")


@pytest.fixture(scope="session", autouse=True)
def _ensure_slot_answer_model() -> None:
    """Pilot judge model is a built artifact (gitignored) — bake it if absent.

    Without this, CI (clean checkout, no models/*.pkl) silently disables the
    judge (fail-open → None) and every pilot-gated boundary test goes red
    for an environment reason, not a product reason. Training is seeded and
    takes seconds; a present file is never rebuilt.
    """
    model = Path(__file__).resolve().parent.parent / "models" / "slot_answer_clf.pkl"
    if model.exists():
        return
    from tools.voice_lab.train_slot_answer_clf import train

    train(model)
