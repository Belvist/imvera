---
name: testing-verification
description: Design and run tests, benchmarks, and quality gates for voiseup. Use before merge claims and release gates.
---

# Testing Verification

## Test Layers

| Layer | Purpose | Gate |
|-------|---------|------|
| Unit | Pure logic, slots, validator | `make test` |
| Contract | STT/TTS/LLM HTTP schemas | provider mocks |
| Dialogue | Turn sequences, slot lifecycle | `make test-voice` |
| Integration | orchestrator + fake providers | CI |
| SIP lab | Real FreeSWITCH + softphone | `make test-sip` |
| Live pilot | PSTN, elderly speech profile | manual owner gate |

**Unit green ≠ any upper layer passed.**

## Dialogue Test Requirements

Every pending-question scenario must assert:

- slot status after turn (OPEN / FILLED / DECLINED)
- `answer_judgement` (VALID / NO_ANSWER / SIDE_TOPIC / etc.)
- pending_question unchanged unless VALID close

Mandatory negative cases:

```text
"ага" with pending wellness question → slot stays OPEN
"алло" → NO_ANSWER
silence → NO_ANSWER, not VALID
side question → SIDE_TOPIC, pending unchanged
```

## Voice Quality Gate

Run `tools/voice_lab/` scenarios (when implemented):

- greeting before wellness question
- closing loop terminates
- safety phrases emit observation, not local RED

## Latency Baseline

Capture per turn:

```text
speech_end, endpoint, stt_final, planner_done,
llm_first_token, text_commit, tts_first_pcm, playback_start
```

Compare to targets in `PROJECT_CONTEXT.md`.

## Report Format

```text
VERIFIED:
  - command: ... result: ...

NOT VERIFIED:
  - ... reason: ...

NEXT GATE:
  - ...
```

## Forbidden

- Deleting failing tests to go green
- `@skip` without issue link and expiry
- Claiming SIP E2E from loopback mic only
