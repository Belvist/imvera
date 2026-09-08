# ADR-014: Architecture Freeze + Production Acceptance Gates

**Status:** accepted  
**Date:** 2026-09-08  
**Amends:** [ADR-013](013-production-telephony-freeswitch.md) (path unchanged; acceptance defined)  
**Does not supersede:** ADR-009 (LLM vs code ownership), ADR-010 (directional media)

## Context

The expensive decisions are already made: FreeSWITCH as telephony core, media separated from AI, dialogue moving into a single-writer `DialogueEngine`. Remaining failures look like residual bugs on `DialogueEngine ↔ CallActor ↔ playout`, not proof that the stack is wrong.

A fourth system (new telephony core, new dialogue brain, new model stack, new “better” architecture) is forbidden. Perfect voice systems do not exist. A **stable production system** exists only after the gates below pass **in sequence**, on the frozen path.

P0-A tone soak (`440/880`, no Vera) is **not** this ADR’s telephony gate. This ADR accepts only full calls: answer → hear → understand → no hang → no replay → scenario → goodbye → hangup.

## Decision

### Frozen production path

```text
SIP operator
→ FreeSWITCH
→ mod_imvera_audio
→ CallActor
→ VAD
→ GigaAM
→ DialogueEngine
→ local LLM only when needed
→ Silero TTS
→ FreeSWITCH
→ caller
```

Do not change this diagram without a new ADR that **explicitly supersedes this one**. Alternatives already rejected for production stay rejected: Asterisk snoop, LiveKit SIP, Telnyx/Twilio media, commercial bidirectional `mod_audio_stream` as the production WRITE path, dual dialogue brains, cloud STT/TTS/LLM.

### Feature freeze until 100 consecutive full calls

Until gate 1–3 pass on the frozen path (100 consecutive complete calls, see below):

**Forbidden**

- new product features
- new call scenarios beyond daily-check
- voice design / persona / copy rewrites except bugfix of broken spoken text
- new STT / TTS / LLM models or providers
- new architecture, “fourth system”, or parallel dialogue owner
- expanding `packages/dialogue/planner.py` as a production brain

**Allowed**

- residual bugfixes on `DialogueEngine ↔ CallActor ↔ playout`
- completing timer/wait into `DialogueEngine` (no legacy dual-owner wait)
- stale-safe effect delivery (`generation_id` / revision)
- moving remaining daily-check edges into the reducer
- soak / forensic / readiness / failure-path work required by the gates
- ops: health, logs, `call_id` trace, restart, image pins — only for gate 7, after 1–6

### Acceptance labels (claim only after gates)

Do **not** write these as current status. Write them only when the matching gate is VERIFIED:

```text
ARCHITECTURE = FROZEN
TELEPHONY = ACCEPTED
DIALOGUE_ENGINE = ACCEPTED
VOICE_RUNTIME = ACCEPTED
PRODUCTION PILOT = READY
```

Until then: **architecture is chosen; it is not accepted.** Dual path (`planner_legacy` vs `DialogueEngine`) is a remaining risk, not a feature.

## Gates (must pass in order)

### 1. Telephony gate

100/100 calls: answer, uplink, downlink, cleanup. 0 hung channels. 0 silent calls.

Evidence: `fs_cli` (`show channels`, `show calls`), bridge session close, recordings / traces per `call_id`.

### 2. Dialogue gate

Daily-check goes **only** through `DialogueEngine`: no planner fallback, no repeated opening, no lost summary/goodbye, no stale effects.

### 3. Scenario gate

`wellness → mood → sleep → plans → summary → goodbye`, plus: «алло», barge-in, silence, repeat, bad recognition, unexpected answer.

### 4. Latency gate

Short phrase does **not** go through LLM. STT + decision + start of reply at conversational pace (product SLO in ADR-008 §15 / `PROJECT_CONTEXT.md`).

### 5. Reliability gate

Many real calls in a row: no restarts, leaks, cross-call audio, hangs, duplicated TTS, lost turns.

### 6. Failure gate

If STT / TTS / LLM dies: Vera does not stay silent or hang. She reports the error and ends the call. FreeSWITCH still answers; AI unavailability is a local prompt + hangup (ADR-013).

### 7. Production gate

Real SIP trunk/number, Linux server, pinned image versions, health/readiness, logs, `call_id` trace, automatic restart, monitoring.

## Residual work (not architecture)

| Area | Honest status (working tree, 2026-09-08) |
|------|------------------------------------------|
| Live e2e to `goodbye_final` accepted | **NOT VERIFIED** |
| Timer/wait | Hybrid: engine emits `TimerEffect` / handles `TimerExpired`; CallActor still schedules wait — **partially legacy** |
| Non-daily-check in reducer | Consent / can_talk / risk / complaint / pause **not** in `packages/dialogue_engine/reducer.py` — freeze says do not add new scenarios; only daily-check edges needed for gates 2–3 |
| Effect delivery stale-safe | Reducer has `_stale()`; CallActor delivery must drop stale effects — **NOT VERIFIED** live |
| Real call soak | **NOT VERIFIED** |
| Planner still in repo | Tests / flag-off path. Production must not use it once gate 2 is claimed |

## Consequences

- Agents treat “improve architecture” as a violation of this ADR.
- `docs/current-task.md` tracks the next residual gate, not a new stack.
- ADR-003 / ADR-006 remain historical model-selection records. They are **not** a license to swap GigaAM or Silero during this freeze.
- `docs/ARCHITECTURE.md` Phase-1 Asterisk diagram is historical spec, not the production path.

## Alternatives considered

| Option | Verdict |
|--------|---------|
| New telephony / dialogue / model stack | **Reject** — fourth system |
| Keep planner as silent production fallback | **Reject** — dual brain |
| Claim FROZEN/ACCEPTED from unit tests | **Reject** — tests green ≠ production |
| Feature work in parallel with soak | **Reject** until 100 consecutive full calls |

## Verification status

| Claim | Status |
|-------|--------|
| ADR-014 accepted (decision) | CHANGED |
| Architecture path frozen | CHANGED (decision only) |
| Gate 1–7 | **NOT VERIFIED** |
| `ARCHITECTURE = FROZEN` as acceptance stamp | **NOT VERIFIED** — do not claim |
