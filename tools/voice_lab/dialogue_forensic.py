"""Dialogue topic-policy checks on live call traces (Phase 1 live gate)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_POOR_SLEEP = re.compile(r"плохо\s+спал", re.I)
_MIXED_ABDOMINAL = re.compile(r"живот", re.I)
_IMPROVING_ABDOMINAL = re.compile(r"почти\s+не\s+бол", re.I)
_OFF_TOPIC = re.compile(r"кто\s+вы|кто\s+ты|кто\s+вообще", re.I)


@dataclass(frozen=True)
class DialoguePolicyViolation:
    rule: str
    detail: str


@dataclass(frozen=True)
class TimelineEvent:
    kind: str  # user | intent
    ts: str
    value: str


def _payload(row: dict) -> dict:
    return row.get("payload") or {}


def build_timeline(rows: list[dict]) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []
    for row in rows:
        ts = str(row.get("ts") or "")
        payload = _payload(row)
        if row.get("type") == "stage.timing":
            stage = payload.get("stage")
            if stage in ("dialogue.engine_decision", "dialogue.planner_decision"):
                intent = str(payload.get("intent") or "").strip()
                if intent:
                    events.append(TimelineEvent("intent", ts, intent))
            elif stage == "stt.result":
                text = str(payload.get("text") or "").strip()
                if text:
                    events.append(TimelineEvent("user", ts, text))
            elif stage == "forensic.turn":
                text = str(payload.get("stt_text") or "").strip()
                if text:
                    events.append(TimelineEvent("user", ts, text))
    return events


def extract_intent_sequence(rows: list[dict]) -> list[str]:
    return [ev.value for ev in build_timeline(rows) if ev.kind == "intent"]


def check_topic_dialogue_policy(rows: list[dict]) -> list[DialoguePolicyViolation]:
    """Rules from ADR-015 / fs-592 live gate."""
    violations: list[DialoguePolicyViolation] = []
    timeline = build_timeline(rows)
    intents_seen: list[str] = []
    pending_after_poor_sleep = False
    saw_mixed_abdominal = False
    block_onset_after_improving = False

    for event in timeline:
        if event.kind == "intent":
            intents_seen.append(event.value)
            if pending_after_poor_sleep and event.value == "probe_concern":
                violations.append(
                    DialoguePolicyViolation(
                        rule="no_probe_after_poor_sleep",
                        detail=(
                            "probe_concern after «плохо спал»; "
                            f"expected topic_sleep_* (got {event.value})"
                        ),
                    )
                )
                pending_after_poor_sleep = False
            if block_onset_after_improving and event.value == "topic_abdominal_pain_onset":
                violations.append(
                    DialoguePolicyViolation(
                        rule="no_onset_after_improving_abdominal",
                        detail="topic_abdominal_pain_onset after improving abdominal context",
                    )
                )
            continue

        text = event.value
        norm = text.lower().replace("ё", "е")
        if _POOR_SLEEP.search(norm):
            pending_after_poor_sleep = True
        if _MIXED_ABDOMINAL.search(norm) and re.search(
            r"проснул|в\s+\d+|в\s+четыре|не\s+мог\s+заснуть", norm
        ):
            saw_mixed_abdominal = True
        if saw_mixed_abdominal and _IMPROVING_ABDOMINAL.search(norm) and _MIXED_ABDOMINAL.search(
            norm
        ):
            block_onset_after_improving = True
        if pending_after_poor_sleep and _OFF_TOPIC.search(norm):
            # Off-topic at pattern question must not close pattern via blind fallback.
            # We cannot read engine state from trace; flag if Vera skips to daytime
            # without ever asking pattern again after off-topic.
            pass

    if pending_after_poor_sleep and not any(
        i.startswith("topic_sleep_") for i in intents_seen
    ):
        violations.append(
            DialoguePolicyViolation(
                rule="sleep_topic_started",
                detail="«плохо спал» seen but no topic_sleep_* intent in trace",
            )
        )

    return violations


def load_trace_rows(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def check_trace_file(trace_path: Path) -> list[DialoguePolicyViolation]:
    return check_topic_dialogue_policy(load_trace_rows(trace_path))
