# GitHub Copilot Instructions

This repository is **IMVERA VoiseUp** — greenfield voice + telephony for elderly care phone calls.

## Required Reading

- `AGENTS.md` — constitution and invariants
- `PROJECT_CONTEXT.md` — architecture and product scope

## Rules

1. Do not copy patterns from any prior voice project.
2. Enforce single ownership: Planner / State / Renderer / Validator / Realtime / Transport.
3. SIP/transport layer must never generate assistant speech.
4. Voiseup emits events; IMVERA Core owns GREEN/YELLOW/RED verdicts.
5. Never claim production readiness from unit tests alone.
6. Use `.agents/skills/` workflows for non-trivial tasks.

## Completion Format

Always report: CHANGED / VERIFIED / NOT VERIFIED / REMAINING RISKS / NEXT GATE.
