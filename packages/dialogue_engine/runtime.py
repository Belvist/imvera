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


def _flag_on(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes"}


def llm_interpret_enabled() -> bool:
    """Whether legacy CallActor may call HttpLLMProvider.interpret_turn.

    Product default: OFF. DialogueEngine product path never calls interpret
    regardless of these flags (need_llm is always False when engine is active).

    Opt-in (legacy planner / experiments only):
    - IMVERA_LLM_INTERPRET=1
    - and when engine is on, also IMVERA_MISSION_LLM_INTERPRET=1
    """
    if not _flag_on("IMVERA_LLM_INTERPRET", "0"):
        return False
    if engine_enabled() and not _flag_on("IMVERA_MISSION_LLM_INTERPRET", "0"):
        return False
    return True


def coverage_ladder_enabled() -> bool:
    """Adaptive 5-domain coverage + reluctance early close (ADR-014 exception).

    Default OFF (frozen short-call shapes). Explicit opt-in for pilot:
    IMVERA_COVERAGE_LADDER=1. Owner: user directive 2026-09-13; gates must
    pass identically with the flag OFF.
    """
    return _flag_on("IMVERA_COVERAGE_LADDER", "0")


@lru_cache(maxsize=1)
def git_sha_short() -> str:
    # Container images carry an explicit source revision and need not ship git
    # or a .git directory. This is the deployed revision, not a host checkout.
    configured = os.environ.get("IMVERA_GIT_SHA", "").strip()
    if configured:
        return configured
    root = Path(__file__).resolve().parents[2]
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            cwd=root,
        )
    except OSError:
        return "unknown"
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    return "unknown"


def direct_wellness_opening_enabled() -> bool:
    """Lab shortcut: skip identity/consent → wellness. Default ON for automated gates.

    Lives here (not in legacy planner) so the engine-active check never
    loads the planner module (Cut 3b). Legacy import path re-exports it.
    """
    return os.environ.get("IMVERA_VOICE_DIRECT_WELLNESS_OPENING", "1").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def dialogue_engine_active() -> bool:
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
        "IMVERA_MISSION_LLM_INTERPRET": os.environ.get(
            "IMVERA_MISSION_LLM_INTERPRET", "0"
        ),
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
