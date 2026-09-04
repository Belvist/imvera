"""JSONL trace writer for Golden Path sessions."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from golden_path.analyzer import Analysis
from golden_path.planner import Plan
from golden_path.validator import ValidatorResult


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_trace_dir() -> Path:
    env = os.environ.get("GOLDEN_PATH_TRACE_DIR", "").strip()
    if env:
        return Path(env)
    return _repo_root() / "golden_path" / "traces"


class TraceWriter:
    """Append-only JSONL per session."""

    def __init__(self, session_id: str, trace_dir: Path | None = None) -> None:
        self.session_id = session_id
        self.trace_dir = trace_dir or default_trace_dir()
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.trace_dir / f"{session_id}.jsonl"

    def write_turn(
        self,
        *,
        turn_no: int,
        user_text: str,
        state_before: dict[str, Any],
        state_after_user: dict[str, Any],
        analysis: Analysis,
        planner_action: Plan,
        required_slot: str | None,
        exact_llm_prompt: str,
        raw_llm_output: str | None,
        validator_result: ValidatorResult,
        final_assistant_text: str,
        state_after: dict[str, Any],
        content_plan: dict[str, Any] | None = None,
        regen_used: bool = False,
        fallback_used: bool = False,
        deterministic: bool = False,
    ) -> None:
        validator = validator_result.to_dict()
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            "turn_no": turn_no,
            "user_text": user_text,
            "state_before": state_before,
            "state_after_user": state_after_user,
            "analysis": analysis.to_dict(),
            "planner_action": planner_action.to_dict(),
            "content_plan": content_plan,
            "required_slot": required_slot,
            "exact_llm_prompt": exact_llm_prompt,
            "prompt": exact_llm_prompt,
            "raw_llm_output": raw_llm_output,
            "validator_result": validator,
            "validator": validator,
            "regen_used": regen_used,
            "fallback_used": fallback_used,
            "deterministic": deterministic,
            "final_assistant_text": final_assistant_text,
            "final_text": final_assistant_text,
            "state_after": state_after,
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def write_event(self, event: str, payload: dict[str, Any]) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            "event": event,
            "payload": payload,
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    @property
    def location(self) -> str:
        return str(self.path)
