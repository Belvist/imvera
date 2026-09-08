"""Runtime truth for DialogueEngine deployment verification."""

from packages.dialogue_engine.runtime import (
    dialogue_engine_active,
    dialogue_engine_mode,
    git_sha_short,
    log_runtime_truth,
    runtime_truth,
)

__all__ = [
    "dialogue_engine_active",
    "dialogue_engine_mode",
    "git_sha_short",
    "log_runtime_truth",
    "runtime_truth",
]
