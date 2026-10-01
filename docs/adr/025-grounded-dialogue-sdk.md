# ADR-025: Grounded dialogue SDK and canonical act adjudication

Date: 2026-09-30
Status: accepted for implementation; live voice acceptance NOT VERIFIED
Branch: `feature/voice-zoiper-m5`

## Decision and authorization

Owner requested smarter dialogue SDK, bug fixes, competitor review and agent
integration guidance on m5, with commit/push. Explicit constraint: models
understand meaning; the deterministic engine decides and formulates. No
generative LLM during the live dialogue. ADR-023 replacement law applies;
ADR-024 bounded ranking/proof contract remains intact.

This slice strengthens existing owners. It adds no FSM, scheduler, language
generator, model vendor or hidden fallback. No deployment is claimed.

The old ADR-020 generative bridge path is retired: `_maybe_compose_bridge`,
its deadline constant and policy eligibility helper are removed. Engine
delivery goes straight to validated TTS, even if an old environment still
sets `IMVERA_COMPOSER_BRIDGE=1`. Historical `SpeakEffect.bridge_llm_allowed`
remains only for serialized compatibility and is never consulted. The old
bridge validator moves to `tools/voice_lab`, outside the live runtime. Four
composer capability tests are migrated to two canonical-delivery tests
that forbid any LLM call with either value of the obsolete flag.

## Displaced behavior → existing owner

| Previously | Now |
| --- | --- |
| Environment flag could enable a generative rewrite before engine TTS | Engine text goes directly to TTS; composer runtime and eligibility removed |
| CallActor called an act vote used while the reducer consumed an unchanged RichUserTurn | TurnUnderstandingV2 adjudicates the vote into canonical RichUserTurn; trace separates proposed/used/reason |
| Slot answer updated compatibility fields but left mission lifecycle/answer stale | policy.apply_slot_answer updates the same accepted answer in goal progress; mission_result reads its current SlotRecord quote |
| Semantic-only not-recalled handling, rich episode repeated the question | Both paths use reducer._resolve_unknown_answer; unanswered evidence remains separate from symptom facts |
| Delivered general free-text accepted a health interruption as its requested value | Deterministic mission understanding preserves the issue and extracts a single remaining exact answer span, or abstains |
| Custom missions recorded health complaints but continued asking unrelated goals | Existing mission flow delegates health needs to the shared episode planner and resumes the delivered goal afterwards |
| Real evidence quote could sit next to invented free-text value | mission_grounding checks both the quote and its extractive value |
| Goodbye erased earlier polite refusal in outcomes | mission_result preserves DECLINED call outcome without inventing future-consent revocation |
| Finished questioning with explicit current=active could lose care signal | Active symptom evidence continues to floor the candidate at YELLOW |

These old branches/assignments are replaced in place; there is no rollout
flag selecting a second dialogue owner. The legacy planner for non-engine
sessions is outside this slice.

## Contracts

`GoalDefinition.semantic_scope` defaults to `general`; applications declare
`speaker_health` for free-text questions soliciting health complaints. Daily
wellness declares that scope. This is task data, not a reply phrase bank or
a domain-specific verb dictionary. The default guard only rejects recognized
health interruptions; it is not a universal semantic relevance classifier.

`RichUserTurn.not_recalled` carries an act meaning. The reducer discharges
the delivered question with unresolved evidence. On an episode,
`unanswered_attributes[attribute]` contains the actual quote; no clinical
"unknown" value is inserted into `known_attributes`. Product planning skips
that already discharged question, while new grounded values can clear the
unanswered marker. Custom goals explicitly skipped this way stay PARTIAL.

`apply_act_candidate` admits answer/backchannel/repair only after checking
confidence, evidence, deterministic control and grounded meaning. A model
cannot create a slot value or control goodbye, safety, consent or stop.
A delivered yes/no answer retains precedence over a backchannel vote. An
answer act alone does not prove relevance to the pending question.

`DialogueEngine.build_rich_turn` supports explicit non-generative act
candidates through the same resolver as CallActor. Without a candidate,
the SDK keeps its existing grounded text builder. Model warming/inference
remains the runtime's responsibility; SDK construction does not load models.

## Verification and limits

Use the same synthetic text scenarios before/after, real CallActor with fake
STT and controlled classifier votes, full existing suite, corpus 500,
hard battery, agent dialogue gate and policy differential. Results and exact
commands: [current task](../current-task.md). Actual replies can be reproduced
with `python scripts/dialogue_sdk_demo.py`; they come from the engine.

Live artifacts for act/polarity/relation are not included in the checkout.
The Linux review environment has no torch or those weights. Tests depending
on them must remain visible failures, not be skipped or replaced with fake
warmth. Integration tests prove vote routing, not classifier accuracy.

The GigaAM existing-artifact unit test previously left its tokenizer absent
and unexpectedly downloaded it over external TLS. Its complete-cache fixture
now asserts zero downloads; a separate test verifies exactly one download
of a missing tokenizer without network. Checksum assertions are preserved.

Inherited daily snapshot `partial` uses seven admission checks whereas
candidate status assumes contact/consent from completion. This slice does
not fabricate admission evidence to reconcile them. Core admission and
consent evidence integration remains a separate required slice.

Live acceptance requires the model artifacts, runtime SHA match, warmup,
five real SIP scenarios, cancellation/played-text traces and end-to-end
latency. Audio/capacity claims cannot come from this text simulation.

## Rollback

Revert the slice commit. No schema migration, new service, provider credential
or off-switch is required. New Pydantic fields have backward-compatible defaults.
