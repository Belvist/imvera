---
name: implementation
description: Write production voiseup code following project invariants. Use for features, fixes, and new modules after architecture is clear.
---

# Implementation

## Preconditions

- [ ] `AGENTS.md` invariants understood
- [ ] Owner layer identified for every change
- [ ] ADR exists if new boundary or provider

## Rules

1. **Minimal diff** — solve the stated problem only
2. **No stubs in prod paths** — no `pass`, `TODO`, fake `return ok`
3. **Match conventions** — read surrounding code first
4. **Contracts first** — types/schemas before logic when adding boundaries
5. **Trace hooks** — latency events per `performance-realtime` skill
6. **Tests with behavior** — not trivial assert-true

## Layer Placement

| Code belongs in | Examples |
|-----------------|----------|
| `packages/telephony/` | SIP adapter, RTP bridge, DTMF |
| `packages/voice_runtime/` | CallSession, VAD, playback, barge-in |
| `packages/dialogue/` | Planner, State, Renderer, Validator |
| `packages/contracts/` | Event schemas shared with Core |
| `services/stt`, `services/tts` | Provider implementations |
| `tools/voice_lab/` | Offline eval only — not imported by prod |

## Before Marking Done

Run applicable checks and report:

```text
CHANGED: ...
VERIFIED: make test / specific command + result
NOT VERIFIED: ...
REMAINING RISKS: ...
NEXT GATE: ...
```

## Forbidden

- Second dialogue brain «just for fallback»
- Verdict logic in transport or runtime hot path
- String-concat SQL; secrets in source
