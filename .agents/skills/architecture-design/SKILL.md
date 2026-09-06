---
name: architecture-design
description: Design or review voiseup components, boundaries, and ADRs. Use before new services, API contracts, or telephony integration.
---

# Architecture Design

## When

- New package or service
- Boundary change (e.g. voiseup ↔ IMVERA Core)
- Telephony stack selection
- Any decision that survives >1 sprint

## Process

```text
context → requirements → options → decision → ADR → interfaces → readiness gate
```

## Requirements Checklist

- [ ] Single owner per layer (AGENTS.md)
- [ ] Transport cannot generate Vera speech
- [ ] Verdicts owned by Core, not voiseup
- [ ] Hot path free of sync DB/S3
- [ ] `generation_id` for cancel/barge-in
- [ ] canonical text == spoken text traceable
- [ ] Failure modes explicit (STT down, TTS down, LLM timeout)
- [ ] Elder consent model respected

## ADR Template

Create `docs/adr/NNN-short-title.md`:

```markdown
# ADR-NNN: Title

Date: YYYY-MM-DD
Status: proposed | accepted | superseded

## Context
## Decision
## Consequences
## Alternatives Considered
```

## Options Analysis

For each option provide:

| Criterion | Option A | Option B |
|-----------|----------|----------|
| Latency | | |
| Ops complexity | | |
| Vendor lock-in | | |
| Russian language quality | | |
| Pilot cost | | |

## Output

- ADR file path
- Interface sketches (events, HTTP, audio frame format)
- NEXT GATE for implementation

## Forbidden

- Big-bang rewrite proposals without vertical slice
- «We'll use X» without `ai-model-evaluation` or `dependency-research` when X is STT/TTS/LLM
