# ADR-028: Evolve the existing conversational move authority

Date: 2026-10-02
Status: proposed; audit/Cut0 measurements authorized, authority promotion NOT VERIFIED
Branch: feature/voice-zoiper-m5

## Context

The owner requests communication rather than a questionnaire: audit first,
then the first safe evolutionary cut. The existing EngineState/Reducer and
DecisionRouter/ActionPolicy remain the only state and selection authorities.
[Audit at09cff201](../conversational-move-architecture-2026-10-02.md) reproduces
missing pending-target/ITS commits in authoritative policy mode, incomplete
thread candidates, SDK/actor producer differences and semantic admission defects.

## Decision proposed

1. Cut0 extends existing offline comparison tooling with attributable decision,
   delivery/state and question metrics. It is neither a production controller
   nor proof of phone naturalness. No production flag changes.
2. Before promotion, make the existing reducer-owned application boundary commit
   a pure selected ResponsePlan's obligation/target/identity, replacing displaced
   legacy scheduler mutations once. Keep deterministic safety/control/evidence.
3. Extend existing ActionPolicy/discourse/ResponsePlan in versioned small cuts;
   do not create a second scheduler, reducer or FSM. Mandatory nonurgent information
   is not necessarily an immediate question. Retain sufficient-evidence/unknown.
4. A (no live generation) remains operational. B (eligible local constrained
   surface only) is a benchmark proposal, NOT enabled or an amendment of the
   current no-generative-live constraint. It requires actual M5 cost/quality,
   bounded ContextPack provenance and complete validation before canonical/TTS.
5. Reject C as state/control owner. No model writes facts, severity, mission,
   consent, Core verdicts or actions. Do not restore the retired composer.

## Consequences

Frozen v9 cannot simply be enabled or silently repinned. Cut0 may reveal failing
behavior; it must report it rather than train on it or weaken checks. Real
CallActor/FreeSWITCH audio/trace and human listening remain acceptance gates.
ADR023 replacement law applies; no competing runtime owners are introduced.

## Alternatives considered

More phrase banks, another planner, a full LLM brain and an unmeasured policy
flag flip are rejected. Pure deterministic composition can improve continuity,
but does not itself establish arbitrary free conversation. B remains conditional.

## Next gate

Recorded baseline plus common reducer-owned authority lifecycle and canonical
SDK/actor parity proof; no soft/policy promotion or generative adoption by this ADR.
