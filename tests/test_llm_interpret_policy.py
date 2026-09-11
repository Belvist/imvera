"""LLM interpret hot-path policy — custom free speech may use /v1/interpret."""

from __future__ import annotations

import pytest

from packages.dialogue_engine.runtime import llm_interpret_enabled


@pytest.mark.dialogue_engine
def test_llm_interpret_enabled_with_dialogue_engine_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.delenv("IMVERA_LLM_INTERPRET", raising=False)
    monkeypatch.delenv("IMVERA_MISSION_LLM_INTERPRET", raising=False)
    assert llm_interpret_enabled()


def test_llm_interpret_kill_switches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.setenv("IMVERA_LLM_INTERPRET", "0")
    assert not llm_interpret_enabled()
    monkeypatch.setenv("IMVERA_LLM_INTERPRET", "1")
    monkeypatch.setenv("IMVERA_MISSION_LLM_INTERPRET", "0")
    assert not llm_interpret_enabled()


def test_llm_interpret_opt_in_for_legacy_planner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "0")
    monkeypatch.setenv("IMVERA_LLM_INTERPRET", "0")
    assert not llm_interpret_enabled()
    monkeypatch.setenv("IMVERA_LLM_INTERPRET", "1")
    assert llm_interpret_enabled()
