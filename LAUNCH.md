# Launch Guide — VoiseUp Phase 1 → Phase 2

> **Architecture Freeze v1** — [PLAN.md](docs/PLAN.md) v1.2  
> Phase 1 complete when this checklist is green.

## Prerequisites

- Python **3.12+**
- `git` (optional)

## Quick start (5 minutes)

```bash
cd /Users/earflow/Downloads/voiseup

# 1. Install dev dependencies
make install

# 2. Verify contracts import
make contracts-check

# 3. Run Phase 1 gate tests
make test
```

Expected:

```text
contracts OK
.....                                                                    [100%]
```

## What Phase 1 delivered

| Artifact | Path |
|----------|------|
| Master plan | [docs/PLAN.md](docs/PLAN.md) |
| Architecture | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Audio contract | [docs/AUDIO_CONTRACT.md](docs/AUDIO_CONTRACT.md) |
| Dialogue spec | [docs/DIALOGUE_SPEC.md](docs/DIALOGUE_SPEC.md) |
| ADR 001–005 | [docs/adr/](docs/adr/) |
| Pydantic contracts | [packages/contracts/](packages/contracts/) |
| Agent constitution | [AGENTS.md](AGENTS.md) |

## Phase 1 gate checklist

- [x] ADR-001..005 written
- [x] AUDIO_CONTRACT full-duplex rule documented
- [x] 4-axis status model in ADR-005
- [x] Provider protocols (STT/TTS/Renderer + cancel + errors)
- [x] Event contract (event_id, sequence_no, idempotency_key)
- [x] `make test` green
- [ ] Human review: Architecture Freeze v1 accepted

## Next: Phase 2 (domain core)

Tell the agent:

```text
начинай Phase 2
```

Agent will implement:

```text
packages/dialogue/   — FSM, Planner, State, Validator
packages/safety/     — Rules, SafetyEngine
packages/status/     — StatusEngine (4 axes → 6 public)
packages/incident/   — incident state machine
tests/               — 12 scenarios S01–S12 (final public_status)
```

**No audio, no Asterisk in Phase 2** — pure logic + unit tests.

## Phase roadmap (summary)

| Phase | Focus | Gate |
|-------|-------|------|
| 0 ✅ | Agent system | skills + AGENTS.md |
| 1 ✅ | Contracts + ADR | `make test` |
| 2 | Dialogue + StatusEngine | 12 scenario tests |
| 3 | STT/TTS speech lab | Silero 8k vs 24k benchmark |
| 4 | voice-runtime loopback | latency p50/p95 |
| 5 | Asterisk SIP | echo self-barge-in gate |
| 6 | backend-mock HTTP | events + idempotency |
| 7 | PSTN pilot | IMVERA Voice Benchmark |

## For a new Cursor agent

1. Read [AGENTS.md](AGENTS.md)
2. Read [docs/PLAN.md](docs/PLAN.md) § Architecture Freeze
3. Open skill matching task in `.agents/skills/`
4. Report: CHANGED / VERIFIED / NOT VERIFIED / REMAINING RISKS / NEXT GATE

## Changing the foundation

Forbidden without new ADR:

- dual dialogue brain
- Silero 16 kHz
- LLM authority on RED/GREEN
- mixing inbound/outbound for STT
- silent provider fallback
