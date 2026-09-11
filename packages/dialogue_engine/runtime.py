"""DialogueEngine runtime truth — env flags, mode, deploy SHA for live verification."""

from __future__ import annotations

import logging
import os
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

_LOG = logging.getLogger("dialogue.engine")


def engine_enabled() -> bool:
    return os.environ.get("IMVERA_DIALOGUE_ENGINE", "1").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def llm_interpret_enabled() -> bool:
    """Hot-path /v1/interpret. Disabled for DialogueEngine — deterministic NLU only."""
    if engine_enabled():
        return False
    return os.environ.get("IMVERA_LLM_INTERPRET", "0").strip().lower() in {
        "1",
        "true",
        "yes",
    }


@lru_cache(maxsize=1)
def git_sha_short() -> str:
    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        cwd=root,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    return os.environ.get("IMVERA_GIT_SHA", "unknown")


def dialogue_engine_active() -> bool:
    from packages.dialogue.planner import direct_wellness_opening_enabled

    return direct_wellness_opening_enabled() and engine_enabled()


def dialogue_engine_mode() -> str:
    return "single_writer" if dialogue_engine_active() else "planner_legacy"


def runtime_truth() -> dict[str, Any]:
    from packages.dialogue_engine.action_policy_shadow_config import (
        action_policy_runtime_truth,
    )

    truth = {
        "dialogue.engine.enabled": dialogue_engine_active(),
        "dialogue.engine.mode": dialogue_engine_mode(),
        "dialogue.engine.version": git_sha_short(),
        "IMVERA_DIALOGUE_ENGINE": os.environ.get("IMVERA_DIALOGUE_ENGINE", "1"),
        "IMVERA_VOICE_DIRECT_WELLNESS_OPENING": os.environ.get(
            "IMVERA_VOICE_DIRECT_WELLNESS_OPENING", "1"
        ),
        "IMVERA_LLM_INTERPRET": os.environ.get("IMVERA_LLM_INTERPRET", "0"),
        "dialogue.llm_interpret.enabled": llm_interpret_enabled(),
    }
    truth.update(action_policy_runtime_truth())
    return truth


def log_runtime_truth(logger: logging.Logger | None = None) -> dict[str, Any]:
    """Emit mandatory startup lines for ops / forensic grep."""
    truth = runtime_truth()
    out = logger or _LOG
    out.info(
        "dialogue.engine.enabled=%s dialogue.engine.mode=%s dialogue.engine.version=%s "
        "IMVERA_DIALOGUE_ENGINE=%s IMVERA_VOICE_DIRECT_WELLNESS_OPENING=%s "
        "dialogue.llm_interpret.enabled=%s action_policy.mode=%s "
        "action_policy.policy_version=%s action_policy.frozen_policy_sha=%s",
        truth["dialogue.engine.enabled"],
        truth["dialogue.engine.mode"],
        truth["dialogue.engine.version"],
        truth["IMVERA_DIALOGUE_ENGINE"],
        truth["IMVERA_VOICE_DIRECT_WELLNESS_OPENING"],
        truth["dialogue.llm_interpret.enabled"],
        truth["action_policy.mode"],
        truth["action_policy.policy_version"],
        truth["action_policy.frozen_policy_sha"],
    )
    return truth
