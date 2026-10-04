# IMVERA conversation product: current owners, cuts and acceptance

Target: `feature/voice-zoiper-m5`. Audited baseline:
`2f18791c155079efde6c967d7292e488ecc74bac`. Work proceeds on the latest m5
source; main and the deployed Mac are not assumed equivalent.

## What is proved, what still fails

Previous source `a15dc36` passed11 CI jobs,3259 tests. Its floor correction is
proved in SDK and controlled CallActor admission; actual phone delivery and
human quality remain unaccepted. The latest call report's4165ms engine turn
requires raw trace, configuration and provider identity to diagnose.

A fresh whole-exchange reproduction:

```text
USER: Вчера дочь приезжала, мы смотрели старые фотографии.
VERA: Про дочь поняла. Расскажите, я слушаю.
USER: Потом вспоминали нашу деревню и соседей.
VERA: Поняла про деревню.
USER: А что я рассказывала про дочь?
VERA: В этом разговоре у меня нет подтверждённого ответа об этом.
USER: А про деревню что я говорила?
VERA: В этом разговоре у меня нет подтверждённого ответа об этом.
```

Neither reply reflects the available current-call story. `discourse.py` keeps
one200-character statement; each continuation replaces it. The shared recall
owner `mission_flow._grounded_answer_recall` searches mission slots and confirmed
observations, excluding ordinary narrative. Literal narrative recall must not
be confused with asserting a new health/family fact.

## Current production ownership

| Concern | Actual owner / restriction |
|---|---|
| Meaning + question recognition before admission | TurnUnderstandingV2, Semantic Kernel; Actor reuses prepared result |
| Fact, consent, episode and delivery application | Reducer funnel / EngineState; models propose, do not write |
| Personal story moves | Existing ActionPolicy v10 through DecisionRouter in all modes |
| Clinical/routine/custom selection by default | Existing legacy scheduler; global policy promotion still gated |
| Routine coverage | coverage.py + protocol table: minima3 content exchanges /3 domains, relevance scorer and fixed tie order |
| Clinical next need | product/planner.py: family plan, known-evidence skips, caps, pending need |
| Call/grounded answer | mission_flow.answer_user_question_text; unsupported world questions abstain |
| Surface | ResponsePlan renderer, questions.py / realization.py; no generative live renderer |
| Voice / interruptions / heard text | CallActor, provider queues, ledger, generation/revision; text replay cannot accept audio |

The person can keep telling a story, but the generic ACK surface, missing
narrative recall and routine coverage minima still limit conversational quality.
Default ActionPolicy mode does not transfer global medical authority. A bank of
full questions continues to supply most routine wording. These are distinct
limitations; a warmer voice cannot alone resolve them.

## Keep / change / remove

Keep EngineState, Reducer, safety/consent/evidence, shared understanding, existing
selector, ResponsePlan and heard-delivery machinery. Do not add another engine,
FSM, scheduler or transport-side speaker.

Change bounded discourse memory and read-only contextual retrieval first. Then
change optional-vs-required information choice and semantic realization through
the existing contracts. Retire displaced owners according to ADR023; do not
leave a competing experimental runtime path.

No new phrase-bank expansion, generator trained on flawed lab dialogues or
unmeasured flag flip constitutes this migration.

## Ordered cuts and work status

| Cut | Status | Intended change / acceptance |
|---|---|---|
| 0. Runtime evidence | OPEN live | Exact SHA/image/providers/flags; full audio + raw trace for warmth, stage latency, interruptions; reproduce4165ms decision |
| 1. Grounded conversation context | SOURCE + CI VERIFIED; live OPEN | Source af8df7b, all11 CI jobs PASS,3286/0/3. Existing discourse retains6 source-scoped excerpts; existing answer owner recalls a previous topic. [Paired evidence](evaluation/personal-context-2026-10-04/README.md); no clinical/cross-call writes |
| 2. Information-driven selection | pending-compatibility source cut; global cutover OPEN | Shared askable set now includes canonical pending product needs; delivered QuestionNeed is authoritative. Fresh product need completeness, protocol minima/optional classification and divergence acceptance remain open. [Evidence](evaluation/volunteered-needs-2026-10-04/README.md) |
| 3. Semantic realization | OPEN | ResponsePlan expresses acknowledgment/reference/question/transition; one semantic need; reusable morphology and grounded fragments, rather than additional full-sentence banks |
| 4. Optional constrained local surface | BENCHMARK proposal only | ADR028 B: existing worker, bounded ContextPack, complete grounding check, cancellation/deadline, deterministic fallback; real target quality/latency/RAM before activation |
| 5. Realtime acceptance | OPEN live | Actual end-of-speech→first PCM p50<1s/p95≤2s, heard interruption p95<250ms; batch STT preview must not be called streaming STT |
| 6. Load / replicas | OPEN hardware | Measure admitted concurrent calls, provider service/queue time, RAM, throughput, failure recovery; scale worker replicas/shards without duplicate call/state ownership |

A blocked live measurement does not block independently verifiable source
work. It does block claims of production/human/capacity acceptance. Cut1 uses
existing owners and does not depend on lifting the no-generative-live rule.

## Cut1 memory contract (written before implementation)

Discourse owns a small ring of accepted personal statements inside EngineState:
up to6 entries of at most200 characters, each with utterance identity and call
scope. The reducer invokes discourse once for the accepted turn. Feedback,
questions, refusals, controls, noise and clinical facts do not become narrative
facts. No reader mutates the ring. Existing semantic corrections conservatively
invalidate narrative recall until fresh accepted content arrives.

The answer owner retrieves only literal evidence relevant to the requested
topic. Mission/clinical recall keeps its stricter existing owner and ambiguity
rules; a failed medical recall cannot be rescued using narrative text. Bare
unscoped recall must not present an older story as the latest health answer.
Previous-call requests and foreign/missing-source entries abstain. The ring is
not projected into cross-call memory, health slots, mission completion or Core
verdicts. Serialized state remains backward compatible with an absent ring.

This creates a bounded source for a future read-only ContextPack. It does not
enable generation or unrestricted questions and answers.

## Cut2 audit: what actually makes the next question mandatory

`coverage.coverage_met` combines at least3 content exchanges with at least3
covered domains. `coverage.score_domain` assigns every missing domain the same
`information=1.0`; a lexical topic match adds2.0, and position contributes
`-0.1 * order_index`. This is topic preference plus fixed ordering, not measured
information gain. `product.planner.next_product_need` explicitly owns ordered
family-plan questions. Neither scorer establishes whether uncertainty changes
the next safe decision. These owners must be reconciled before changing scores.

`decision_router.route_schedule_next_action` sends custom missions to legacy
and uses ActionPolicy for eligible personal stories in every mode. Clinical,
routine and custom selection have not been globally promoted. Merely changing
the mode flag would conceal unresolved ownership and divergent plan semantics.

The next source cut must first enumerate each protocol need as safety-critical,
mission-required, or optional conversational coverage, with its existing
definition and the decision it can change. Preserve required obligations and
unknown/refused dispositions. A safe optional question should lose to an
unanswered user question or engaged story; a critical need retains priority.
Measure whole-dialogue topic jumps, repeated/necessary questions, question
burden and mission completion before selecting weights. Do not remove minima
or enable global policy authority merely to obtain a warmer text replay.

The historical [need compatibility audit](evaluation/personal-context-2026-10-04/policy-need-audit.json)
finds9 distinct product dimensions outside ActionPolicy's four generic askable
needs: associated, pattern, daytime_impact, intake, barrier, intensity,
social_context, status_today, needs_help. This does not prove every actual turn
loses these needs: medical selection defaults to legacy, and other paths may
handle them. It does establish a global cutover blocker. A synthetic read-only
snapshot with all four generic needs known and pending `associated` has
`outstanding_pending_obligation=True`, but generates no episode question and
chooses ACK_ONLY. First reconcile canonical pending/product need representation,
with real reducer/selector dialogue reproduction, before scorer tuning or
promotion. Adding heavier ranking cannot select an absent legal candidate.

The next correctness cut on d0bfac6 repairs canonical pending compatibility:
one currently_askable_needs set supplies generation, utility and transitions;
all nine pending dimensions become candidates in the same isolated snapshots.
This resolves the demonstrated pending gap, not the fresh product-plan/legal-set
gap or full medical authority. Default-live grounding now also retains volunteered
degree/current status and rejects anatomical spelling guesses. Actual source
checks, full exchanges and closing/outcome corrections are in the
[new report](evaluation/volunteered-needs-2026-10-04/README.md).

Personal recall in Cut1 is literal inflected-topic lookup, not semantic retrieval
for arbitrary paraphrases. Its6-entry retention may evict an older story; a
canonical correction conservatively clears even unrelated narrative. Those
limits are deliberate and visible, not evidence that broad dialogue is solved.

## Cost model and scale

The ring and lookup are bounded, per call. Semantic normalization uses the
existing cached morphology. No new model call, transcript prompt or database
operation is added to the live decision. Measure actual SDK timings, label them
as SDK only; real model calls and latency need provider instrumentation.

Registered users and simultaneous calls require different resources. Millions
of registrations cannot establish a capacity claim about one Mac or one worker.
Keep validated per-process admission and benchmark model/voice replicas before
raising it. Cross-shard call ownership must be explicit; no shared shard with
independent local orphan sweepers.

## Acceptance and reporting

Maintain safety/state suites and exact delivery/cancellation assertions.
Test whole exchanges for volunteered multi-facts, daughter/day story, a question,
topic switch/return, unknown, ambiguity, correction, interruption, slow speech,
symptom in story, one-question refusal, explicit stop and chat without complaint.
Check quote provenance and obligations, not just a prettier expected string.

Retain attributable before/after transcripts per cut; record replaced owner,
actual tests, latency scope and invocation-count basis. Then use the same phone
scenarios and paired blind listening for questionnaire feel/warmth. External
competitor quality remains NOT_RUN without captured comparable calls.

Never label a cut human or finished solely from green tests. Update
`docs/current-task.md`, cut evidence and the integration handoff after each cut.
