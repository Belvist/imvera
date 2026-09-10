# ADR-016: Live RichUserTurn path — semantic apply before decision

Date: 2026-09-10
Status: Accepted

## Context

`fs-1f6d3000` showed legacy `probe_phase` short-circuit consuming a turn before
`atomic_semantic_apply`, dropping a new headache IssueEpisode and jumping to
IMPORTANT_TO_SHARE. Topic/probe must not own live turns.

## Decision

For every accepted RichUserTurn:

1. `filter_rich_turn_mentions`
2. `atomic_semantic_apply` exactly once
3. Compatibility projections only (probe advance / clear)
4. `schedule_next_action` owns all speech

Legacy `probe_phase` / `active_topic` may observe state after apply.
They must not skip apply, emit next question directly, or discard semantic content.

## Consequences

- Vague negative wellness → `probe_concern`, not duration-by-word-count
- Explicit farewell → immediate `goodbye_final` (no confirm)
- ITS answers classified semantically; meta/unclear does not record or close
