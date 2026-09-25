# ADR-021: Care Dialogue Kernel (CDK) — protocol-first voice dialogue

Date: 2026-09-25
Status: proposed

## Context

Live calls (fs-4d8f5a8b) proved three P0 dialogue failures: greeting-back
scold loop, double goodbye, skipped severity probe. At the same time the
system must scale to 100+ concurrent calls on commodity hardware, where
every LLM-in-the-hot-path millisecond multiplies. ADR-004 (FSM owns
facts) and ADR-020 (LLM never authors Vera speech) already constrain the
space; this ADR names the target architecture on top of the existing
`dialogue_engine`.

## Decision

Build the Care Dialogue Kernel: a care protocol, not a chat.

Pipeline (one brain, no second FSM):

```text
audio → STT → Understand (rules + classifiers → acts, never Vera text)
     → Reduce (sole writer of EngineState)
     → NeedQueue / Policy (what MUST still be asked)
     → Action (ASK | ACK | SOFT_ACK | ITS | SUMMARY | GOODBYE | SAFETY)
     → PhraseSelect (banks + templates + per-call anti-repeat)
     → TTS → (after call) StatusEngine → family
```

Layers:

1. **Protocol** (product law, not copy): slot → required for
   GREEN/YELLOW/RED. Pain without severity may not reach ITS (except
   explicit decline); RED phrases hijack to SAFETY.
2. **Understand**: closed intent lattice (GREETING_ONLY, WELLNESS_OK/BAD,
   ISSUE_SITE, TEMPORAL, SEVERITY, DECLINE, AFFIRM, BACKCHANNEL, FAREWELL,
   NOISE, UNCLEAR). Classifiers (incl. semantic NLP heads) emit labels
   only — never Vera's words.
3. **NeedQueue**: priority SAFETY > active issue probes
   (onset → severity → current) > volunteered follow-up > coverage gaps
   (scored) > ITS > SUMMARY > GOODBYE. One action per turn. Mandatory
   gate: no ITS/SUMMARY while severity is open on non-urgent pain.
4. **PhraseSelect**: 5–12 phrases per ActionId + `{name}`/`{site}`/
   `{food}` templates; pick by hash(call_id, turn), last-K signatures
   banned per call. Empathy = banks, not LLM. CPU cost ~zero, so dialogue
   is never the scaling bottleneck (STT/TTS are).
5. **Terminal discipline**: SUMMARY carries no farewell; exactly one
   GOODBYE (goodbye_final); user "пока" → same GOODBYE or silence.
6. **Truth = live path**: golden = CallSession/trace replay of reference
   lines (P0d: trace fs-4d8f5a8b). Demo MP4s are shop window only.

Forbidden: Lua/TTS choosing lines; summary saying goodbye; second
scheduler in transport; LLM authoring Vera speech; fine-tuning a
generator on lab calls; raising max_active_calls before live-parity+soak.

## Consequences

- Dialogue stays cheap and deterministic at scale: horizontal growth =
  N bridge workers + sticky call_id + STT/TTS replica pools.
- Every behavior fix lands as: red test on action_id → code →
  corpus/differential gates.
- Deferred (P1+): PhraseSelect extracted to one module; Protocol as data
  (YAML/JSON) for new domains (pressure, teeth); family notify.

## Alternatives Considered

- LLM renderer/composer for liveliness: rejected on metrics
  (prompt-contract v1 failed) and ADR-020.
- Second policy in ScenarioRunner: rejected — one scheduler only.
- Bigger prompt instead of banks: rejected — cost scales with users,
  determinism lost.
