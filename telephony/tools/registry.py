"""Tool registry (Architecture plan, tools layer).

A central registry where the agent's tools are declared. Tools are plain
callables with a name + description; the registry lets the dialogue layer
enumerate and dispatch them without hardcoding a switch. Currently a minimal
scaffold used by future worker tool-calling; kept dependency-free.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Optional

_ToolFn = Callable[..., Any]


class ToolRegistry:
    """Thread-safe registry of named callables."""

    def __init__(self) -> None:
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def register(self, name: str, fn: _ToolFn,
                 description: str = "") -> _ToolFn:
        with self._lock:
            self._tools[name] = {"fn": fn, "description": description}
        return fn

    def get(self, name: str) -> Optional[_ToolFn]:
        with self._lock:
            entry = self._tools.get(name)
        return entry["fn"] if entry else None

    def describe(self, name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            entry = self._tools.get(name)
        return dict(entry) if entry else None

    def names(self) -> List[str]:
        with self._lock:
            return sorted(self._tools)

    def call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        fn = self.get(name)
        if fn is None:
            raise KeyError(f"unknown tool: {name}")
        return fn(*args, **kwargs)


# Process-wide default registry for the agent's tools.
registry = ToolRegistry()