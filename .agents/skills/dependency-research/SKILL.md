---
name: dependency-research
description: Research libraries, SIP providers, and infrastructure options before adoption. Use when evaluating FreeSWITCH clients, Python SIP libs, or cloud APIs.
---

# Dependency Research

## When

- Before adding a new pip/npm/system dependency
- Before signing a telephony trunk contract
- Before «let's use library X» in ADR

## Process

1. **Need** — what problem, what interface boundary
2. **Candidates** — ≥2 options including «build thin wrapper ourselves»
3. **Criteria** — license, maintenance, security history, fit, ops burden
4. **Spike** — time-boxed POC (≤4h), not production code
5. **Decision** — ADR or explicit reject

## Evaluation Table

| Criterion | Weight | Option A | Option B |
|-----------|--------|----------|----------|
| License | | | |
| Last release | | | |
| Open issues / security | | | |
| Russian telephony fit | | | |
| Team familiarity | | | |
| Lock-in risk | | | |

## Red Flags

- No releases >12 months, critical open CVEs
- GPL in SaaS path without legal review
- Vendor without SLA for PSTN
- Wrapper thicker than owned code would be

## Output

```text
RECOMMENDATION: adopt X | reject all | defer
ADR: docs/adr/NNN-...
POC RESULT: ...
PIN VERSION: ...
```

## VoiseUp Preferences

- Pin versions in lockfile
- Prefer boring, operable tools for telephony edge
- Avoid `latest` in production images
