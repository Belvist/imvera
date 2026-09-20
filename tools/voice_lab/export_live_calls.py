"""Export all persisted lab dialogues to docs/live-calls.md for owner review."""

from __future__ import annotations

import datetime
import json

import psycopg


def _fmt(value: object, limit: int = 160) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + "..."


def main() -> None:
    conn = psycopg.connect(
        "postgresql://imvera:imvera_dev_change_me@127.0.0.1:5432/imvera"
    )
    calls = conn.execute(
        "SELECT call_id, family_id, fsm_state, facts, fact_quotes,"
        " termination_reason, call_ended, updated_at"
        " FROM call_results ORDER BY updated_at"
    ).fetchall()
    lines: list[str] = [
        "# Live call log (lab, auto-exported from Postgres)",
        "",
        f"Exported: {datetime.datetime.now(datetime.timezone.utc).isoformat()}",
        f"Total calls: {len(calls)}",
        "",
    ]
    for call_id, family_id, fsm, facts, quotes, term, ended, updated in calls:
        lines.append(f"## {call_id} — {updated} (fsm={fsm}, termination={term})")
        lines.append("")
        lines.append(f"family={family_id} ended={ended}")
        lines.append(f"facts={_fmt(facts)}")
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
        interesting = [
            (sq, et, oc, pl)
            for sq, et, oc, pl in events
            if et not in ("CALL_STARTED", "ENGINE_DECISION", "ACTION_POLICY_SHADOW_HEALTH")
        ]
        lines.append(f"key events: {len(interesting)}")
        for sq, et, oc, pl in interesting[:40]:
            lines.append(f"- #{sq} {et} {oc} {_fmt(pl)}")
        lines.append("")
    Path = __import__("pathlib").Path
    Path("docs/live-calls.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {len(calls)} calls")


if __name__ == "__main__":
    main()
