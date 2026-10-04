"""A mood move asks one semantic need; SDK replay binds to its checkout."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from packages.dialogue_engine.coverage import domain_question


@pytest.mark.parametrize("day", range(102, 108))
@pytest.mark.parametrize("variant", [0, 1])
def test_mood_move_does_not_also_ask_about_health_or_anxiety(monkeypatch, day, variant):
    monkeypatch.setenv("IMVERA_SPEECH_DAY", str(day))
    text, intent, slot = domain_question("mood", variant=variant)
    assert intent == "background_mood" and slot == "mood"
    assert text.count("?") == 1, "one move cannot deliver two independent questions"
    assert "беспокоит" not in text and "тревожит" not in text, (
        "a mood description and a negated anxiety screen have different answer semantics"
    )


def test_replay_uses_own_checkout_even_when_another_sdk_is_installed(tmp_path):
    root = Path(__file__).resolve().parents[1]
    script = root / "docs/evaluation/conversational-grounding-2026-10-03/replay.py"
    foreign = tmp_path / "packages"
    foreign.mkdir()
    (foreign / "__init__.py").write_text("raise RuntimeError('foreign SDK imported')\n")
    output = tmp_path / "replay.json"
    env = dict(os.environ, PYTHONPATH=str(tmp_path), OMP_NUM_THREADS="2")
    result = subprocess.run(
        [sys.executable, str(script), str(output)], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    cases = json.loads(output.read_text())
    story = cases["food_story"]
    assert story[1]["intent"] == "thread_invite"
    assert all(row["intent"] == "thread_listening_ack" for row in story[2:4])
    assert not any(row["question"] for row in story[1:4])
    assert story[-1]["intent"] == "background_nutrition"
    assert cases["stop"][-1]["closed"]
