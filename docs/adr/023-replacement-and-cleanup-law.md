# ADR-023: Replacement and Cleanup Law

Date: 2026-09-28
Status: accepted
Supersedes: freeze clauses of [ADR-013](013-production-telephony-freeswitch.md) and [ADR-014](014-architecture-freeze-acceptance-gates.md) listed below.
Does not erase history: ADR-013 and ADR-014 remain readable historical records.

## Context

Layers accumulated faster than they were retired. The live path now carries
dead models, dead flags, dead services, duplicate interpreters, and parallel
schedulers. Tests can stay green while the live call uses none of the new
work, and stale docs/configs mislead the next change.

The old freeze correctly protected stability, but its blanket bans now block
needed replacement: better understanding, licensed voice, human speech,
hearing/barge-in, and status truth.

## Decision

Replace the blanket freeze with a replacement law.

### 1. One owner per concern, no parallel production owners

A replacement must name the exact old owner it displaces:

```text
module / config / service / flag / doc / test → new owner
```

Two dialogue brains, two schedulers, two verdict paths, or two speech paths
must not coexist in production.

### 2. Compare before deleting

Before removing the old implementation, run the same comparison:

```text
same real/live inputs and traces
old behavior vs new behavior
safety, truth, latency, stability: equal or better
no silent fallback
Core keeps verdict ownership
canonical text remains traceable to spoken text
consent and safety stay deterministic
```

If the new path does not pass, do not merge it. If the result is unknown,
mark it `NOT VERIFIED` and keep the old path.

### 3. Delete completely on pass

When the replacement passes:

- remove the old module, config, flag, service wiring, docs, and dead tests
  in the same stream;
- migrate only contract tests that prove the new behavior;
- never leave “temporary both”;
- rollback means `git revert`, not dual runtime.

### 4. No misleading leftovers

After replacement, the tree must not claim a removed capability:

- no env flags pointing at dead models;
- no stopped services presented as live;
- no docs/tests/comments describing deleted behavior;
- no raw STT text presented as verified fact;
- no GREEN/RED without the owning evidence path.

### 5. What stays non-negotiable

The following survive from ADR-013/ADR-014 and ADR-020/ADR-021:

- FreeSWITCH answers; directional PCM only.
- Transport never generates Vera speech.
- One dialogue brain; no second FSM in production.
- Core owns verdicts and incidents.
- No silent cloud fallback.
- Consent, control, RED, and safety paths stay deterministic.
- Observability tiers and measured capacity remain in force.

### 6. What the freeze no longer blocks

Gated vertical replacement slices are allowed for:

- understanding/NLP inside CDK Understand;
- licensed TTS/voice replacement;
- human speech surface through PhraseSelect discipline;
- hearing, turn-taking, and barge-in;
- status/report truth owned by StatusEngine.

Big-bang rewrites remain forbidden. Each slice needs:

```text
red test or red live-trace proof
green gates
behavioral delta enumerated
old owner deleted
live voice proof before acceptance
```

## Consequences

- ADR-014’s “100 consecutive calls before any model/voice change” is replaced
  by per-slice live comparison gates plus explicit pilot acceptance.
- `docs/adr/README.md` and `AGENTS.md` record this amendment.
- The next implementation slice must include: displaced owner, comparison
  inputs, gate commands, deletion diff, and live proof or `NOT VERIFIED`.

## Alternatives Considered

- Keep the blanket freeze: rejected — it preserves dead layers and blocks
  competitive voice quality.
- Big-bang rewrite: rejected — unreviewable, untestable, unsafe to deploy.
- Keep both old and new paths: rejected — dual ownership is how the current
  confusion was created.

## Interfaces

Every replacement record must contain:

```text
displaced owner:
comparison inputs/traces:
metrics before/after:
deletion checklist:
live proof or NOT VERIFIED:
```

## Verification status

| Claim | Status |
|-------|--------|
| ADR-023 decision documented | CHANGED |
| Old owners deleted | NOT VERIFIED — separate slices required |
| Live acceptance | NOT VERIFIED |
