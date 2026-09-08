# Current task — finish the frozen path (ADR-014)

**Outcome:** One production path, 100 consecutive full calls. **No fourth system.**

```text
SIP operator → FreeSWITCH → mod_imvera_audio → CallActor
→ VAD → GigaAM → DialogueEngine → local LLM only when needed
→ Silero TTS → FreeSWITCH → caller
```

Nearest goal (not new features):

```text
позвонил → Вера сняла → услышала → правильно поняла
→ не зависла → не повторилась → дошла по сценарию
→ попрощалась → корректно положила трубку
```

**100 times in a row.** Then, and only then: `ARCHITECTURE = FROZEN` / `TELEPHONY = ACCEPTED` / `DIALOGUE_ENGINE = ACCEPTED` / `VOICE_RUNTIME = ACCEPTED` / `PRODUCTION PILOT = READY`.

## Allowed now

Residual bugs on `DialogueEngine ↔ CallActor ↔ playout`:

- live daily-check through `goodbye_final` (no planner fallback, no second opening, no lost summary/goodbye)
- timer/wait fully owned by `DialogueEngine` (CallActor only fires the timer)
- stale-safe effect delivery
- soak + hangup cleanup evidence

## Forbidden now

New features, scenarios, voice design, models, or architecture. See ADR-014.

## NOT VERIFIED

- Telephony gate 100/100 full calls (answer, uplink, downlink, cleanup, 0 hung channels, 0 silent)
- DialogueEngine-only live path to `goodbye_final`
- Scenario matrix (алло / barge-in / silence / repeat / bad STT / unexpected)
- Latency: short phrase without LLM; conversational STT→reply start
- Reliability soak (leaks, cross-call audio, dup TTS, lost turns)
- Failure path STT/TTS/LLM down
- Production: real trunk, Linux, pinned images, health, restart, monitoring
- P0-A tone 100/100 (ADR-013) — still not a substitute for ADR-014 gate 1

## NEXT GATE

One live daily-check on the frozen path to `goodbye_final` with `call_id` trace: no `planner_legacy`, no repeated opening, hangup cleanup. Then repeat toward 100.
