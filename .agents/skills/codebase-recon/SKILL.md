---
name: codebase-recon
description: Map an unfamiliar area of voiseup before changing it. Use when entering a new package, service, or debugging unknown behavior.
---

# Codebase Recon

## When

- First task in repo or unfamiliar module
- Before any refactor spanning multiple packages
- Before claiming «how it works» in a review

## Steps

1. **Scope** — what question must be answered? (one sentence)
2. **Entry points** — `main`, HTTP handlers, CLI, dialplan hooks, `__init__.py` exports
3. **Ownership** — which module owns State? Planner? Transport? (per AGENTS.md)
4. **Data flow** — draw audio/text/event path for one turn
5. **Contracts** — find schemas, protos, typed events, OpenAPI
6. **Tests** — what exists; what gate they claim
7. **Deploy path** — Dockerfile, compose, env vars, feature flags
8. **Gaps** — what is NOT VERIFIED

## Output Template

```text
SCOPE: ...
ENTRY POINTS: ...
OWNERS: Planner=... State=... Renderer=... Validator=... Realtime=... Transport=...
TURN FLOW: ...
CONTRACTS: ...
TESTS: ... (VERIFIED / NOT RUN)
DEPLOY: ...
GAPS: ...
RECOMMENDED NEXT: ...
```

## Rules

- Do not guess file paths — use search and read
- If two modules both mutate dialogue state → flag as **architecture violation**
- Recon is read-only unless user asked for changes
