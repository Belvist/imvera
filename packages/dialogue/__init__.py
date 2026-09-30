"""Dialogue package.

Legacy planner path stays importable for flag-off configs and parity
tests, but nothing on the DialogueEngine path may load it: the engine
decides, the planner is flag-off-only (Cut 3b). Submodules are imported
directly (``packages.dialogue.session`` etc.); the planner/fsm names
below resolve lazily for backward compatibility only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from packages.dialogue.state import DialogueState
from packages.dialogue.validator import Validator

if TYPE_CHECKING:  # pragma: no cover
    from packages.dialogue import fsm as fsm
    from packages.dialogue import planner as planner
    from packages.dialogue.fsm import CallFsm
    from packages.dialogue.planner import Planner

__all__ = ["CallFsm", "DialogueState", "Planner", "Validator", "fsm", "planner"]


def __getattr__(name: str) -> Any:
    if name in ("planner", "Planner", "fsm", "CallFsm"):
        import importlib

        if name in ("planner", "fsm"):
            return importlib.import_module(f"packages.dialogue.{name}")
        module = importlib.import_module(
            f"packages.dialogue.{'planner' if name == 'Planner' else 'fsm'}"
        )
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
