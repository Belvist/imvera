"""Export all persisted lab dialogues to docs/live-calls.md for owner review.

Sources: Postgres (results/observations/events) + .run/traces/<call_id>.jsonl
(turn-by-turn: renderer.phrase_ready = Vera text, stt.final = user text).
Q0.2: full conversation transcript, not just persistence summary.
"""

from __future__ import annotations

import datetime
import json
from datetime import UTC
from pathlib import Path

import psycopg

TRACE_DIR = Path(".run/traces")


def _fmt(value: object, limit: int = 160) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + "..."


def _trace_dialogue(call_id: str) -> list[str]:
    """Turn-by-turn transcript from the forensic trace, if present."""
    path = TRACE_DIR / f"{call_id}.jsonl"
    if not path.is_file():
        return []
    turns: list[str] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_type = row.get("type", "")
            payload = row.get("payload", {})
            if not isinstance(payload, dict):
                continue
            if event_type == "renderer.phrase_ready" and payload.get("text"):
                turns.append(f"Vera: {payload['text']}")
            elif event_type == "stt.final" and payload.get("text"):
                uid = payload.get("utterance_id", "?")
                turns.append(f"User[{uid}]: {payload['text']}")
    except OSError:
        return []
    return turns


def main() -> None:
    conn = psycopg.connect(
        "postgresql://imvera:imvera_dev_change_me@127.0.0.1:5432/imvera"
    )
    calls = conn.execute(
        "SELECT call_id, family_id, fsm_state, facts, fact_quotes,"
        " termination_reason, call_ended, updated_at"
        " FROM call_results ORDER BY updated_at"
    ).fetchall()
    with_trace = 0
    lines: list[str] = [
        "# Live call log (lab, auto-exported from Postgres + traces)",
        "",
        f"Exported: {datetime.datetime.now(UTC).isoformat()}",
        f"Total calls: {len(calls)}",
        "",
    ]
    for call_id, family_id, fsm, facts, quotes, term, ended, updated in calls:
        lines.append(f"## {call_id} — {updated} (fsm={fsm}, termination={term})")
        lines.append("")
        lines.append(f"family={family_id} ended={ended}")
        lines.append(f"facts={_fmt(facts)}")
        turns = _trace_dialogue(str(call_id))
        if turns:
            with_trace += 1
            lines.append("dialogue:")
            lines.extend(f"- {t[:200]}" for t in turns)
        obs = conn.execute(
            "SELECT turn_id, field, value, source_quote, created_at"
            " FROM call_observations WHERE call_id=%s ORDER BY created_at",
            (call_id,),
        ).fetchall()
        lines.append(f"observations: {len(obs)}")
        for turn_id, field, value, quote, created in obs:
            lines.append(
                f"- t{turn_id} [{field}] {str(value)[:120]}"
                f" | quote: {str(quote or '')[:120]}"
            )
        events = conn.execute(
            "SELECT event_type, sequence_no, occurred_at, payload"
            " FROM call_events WHERE call_id=%s ORDER BY sequence_no",
            (call_id,),
        ).fetchall()
        skipped = ("CALL_STARTED", "ENGINE_DECISION", "ACTION_POLICY_SHADOW_HEALTH")
        interesting = [
            (event_type, seq, occurred, payload)
            for event_type, seq, occurred, payload in events
            if event_type not in skipped
        ]
        lines.append(f"key events: {len(interesting)}")
        for event_type, seq, occurred, payload in interesting[:40]:
            lines.append(f"- #{seq} {event_type} {occurred} {_fmt(payload)}")
        lines.append("")
    lines.append(f"calls with trace transcript: {with_trace}")
    Path("docs/live-calls.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {len(calls)} calls ({with_trace} with trace)")


if __name__ == "__main__":
    main()
