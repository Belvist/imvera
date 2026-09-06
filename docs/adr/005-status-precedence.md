# ADR-005: Status Model — 4 Axes, Precedence, False-Alarm Protocol

**Status:** accepted  
**Date:** 2026-09-06

## Context

Single enum cannot represent «contact was made but technical failed» or «RED then STT died». False STT alarms must not permanently mark calls RED.

## Decision

### Internal axes

```text
delivery_state:  NOT_ATTEMPTED | RINGING | ANSWERED | NOT_ANSWERED | FAILED
technical_state: OK | DEGRADED | FAILED
care_state:      UNKNOWN | GREEN | YELLOW | RED
consent_state:   UNKNOWN | ACTIVE | DECLINED
```

### Safety sub-state (in-call)

```text
highest_signal_seen:  NONE | POSSIBLE | YELLOW | RED  (monotonic, log immutable)
active_risk:          NONE | YELLOW | RED             (may clear on protocol)
signal_resolution:    UNRESOLVED | CONFIRMED | CONFIRMED_FALSE_ALARM
```

### Public status mapping (examples)

| delivery | technical | care (active) | consent | → public |
|----------|-----------|---------------|---------|----------|
| NOT_ANSWERED | OK | * | ACTIVE | NO_CONTACT |
| NOT_ATTEMPTED | FAILED | * | * | TECHNICAL |
| ANSWERED | FAILED | UNKNOWN | ACTIVE | TECHNICAL |
| ANSWERED | FAILED | RED | ACTIVE | **RED** |
| ANSWERED | OK | GREEN | ACTIVE | GREEN |
| ANSWERED | * | * | DECLINED | DECLINED |

Precedence when mapping to public:

```text
active credible RED  >  YELLOW  >  DECLINED  >  GREEN
NO_CONTACT and TECHNICAL derived from delivery + technical — never GREEN
```

### NO_CONTACT definition

```text
Call was successfully delivered to subscriber endpoint,
but conversational contact with the person was not established.
```

Not the colloquial Russian «дозвонились» (= person answered).

### TECHNICAL definition

```text
Cannot assert that a valid contact attempt completed.
(e.g. trunk down before ring, media broken, total pipeline failure before meaningful contact)
```

Trunk down before dial → **TECHNICAL**, never NO_CONTACT.

### False-alarm protocol

1. `highest_signal_seen` set to RED on signal (never lowered).
2. Control question (deterministic template).
3. On `CONFIRMED_FALSE_ALARM` via rules (explicit denial + plausible alternative + no corroborating signals):
   - `active_risk` may → NONE
   - `care_state` updated per rules (not auto-GREEN if mandatory checks incomplete)
4. Event log retains original RED signal.

### Final status authority

`StatusEngine` only — not LLM, not transport.

## Consequences

- Phase 2 unit tests S01–S10 assert `PublicCallStatus`
- Scenario S10 requires explicit expected outcome table after protocol implementation

## Verification status

✅ Logic specified; implementation Phase 2.
