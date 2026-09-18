# ADR-019: Engine-native persistence projection (A.5.3 target)

Date: 2026-09-18
Status: accepted with owner constraint (b) — verbatim parity for A.5.3

Owner decision 2026-09-18: (b). A.5.3 is zero-behavior-change cleanup, so the
projection preserves the legacy-compatible surface (`facts`, `fact_quotes` /
`source_quote` verbatim) exactly. True engine evidence (`SlotValue.source_text`,
polarity, observations/evidence, `mission_result.evidence`, issue episodes)
is retained alongside in the engine-native projection — never dropped, never
substituted into the legacy surface. Migrating Core to richer quotes is a
separate contract change after A.5, not part of cleanup.

## Context

On the DialogueEngine path, `CallSession` persists via the legacy mirror:
`EngineState → sync_to_legacy() → DialogueState → TransitionStore/snapshot →
CallResultSnapshot`. The store interface (`CallRecordStore`) is already
state-agnostic (snapshots/observations only), and `_snapshot()` already merges
engine-native blobs (`build_call_metadata`, `build_mission_result`,
`build_call_outcomes`). The remaining legacy coupling is the envelope
(call_id/fsm/facts/quotes/finalized/termination), `_state_to_metadata` dump,
outbox lifecycle, and observation projection from synced facts.

Target end state (reviewer-confirmed):

```text
EngineState → read-only PersistenceProjection → CallResultSnapshot/events/DB
```

No permanent `sync_to_legacy → DialogueState → persistence` chain.

## Decision

Target is option B (engine-native projection). Migration via temporary
parity harness, not permanent dual-write:

1. Build `project_call_result(engine.state, ...)` producing a
   `CallResultSnapshot` byte-identical in contract to today's `_snapshot()`
   on the 500-scenario corpus + live-replay fixtures (field diff harness,
   offline).
2. Per owner decision (b): the projection emits legacy-compatible
   `facts`/`fact_quotes` verbatim. Rich engine evidence travels alongside
   (existing `mission_result.evidence`, observations, metadata) untouched.
3. Outbox lifecycle (`PendingAction`/`OutboxRecord`, optimistic
   `state_version`) is already keyed by engine `generation_id`; keep its
   mechanics, re-source the state dump from the projection.
4. Cut only when: corpus 500/500 byte-identical (modulo approved quote
   change), full suite green, differential/challenge green, remote CI green.
5. `CallActor` runtime reads (`pending_question/slot`, finalization flags)
   migrate on a parallel track to engine-native accessors; not this ADR's
   cut, but no new legacy reads may be added meanwhile.

## Consequences

- `sync_to_legacy` shrinks to CallActor-compat reads, then dies with the
  last reader; `DialogueState` becomes legacy-path-only, then orphaned.
- Observation idempotency keys must be re-derived from engine record
  revisions (engine `slot_records` revision semantics to be verified).
- No scheduling, dialogue, corpus, or ActionPolicy semantic change.

## Alternatives Considered

- Permanent dual-write: rejected (two truths, comparison debt forever).
- Direct cut without parity harness: rejected (silent contract drift risk
  for Core readers).
- Keep `sync_to_legacy` forever: rejected (the dual-state bug farm A.5
  exists to remove).

## Next gate

Parity-harness design + field map sign-off → implementation only after
remote CI green on the design step. Scheduler consolidation
(`_schedule_next_action_legacy`) stays out of scope until production
shadow evidence + cutover.
