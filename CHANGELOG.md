# Changelog

## Unreleased — 2026-10-03

- Bound TTS production with disconnect-aware backpressure and async HTTP consumption; preserve actual model completion and reject overload before headers.
- Propagate relative TTS deadlines, honor request-ID cancellation and reject truncated audio streams without replaying another voice.
- Add opt-in batch sentence streaming, real TCP/CallActor delivery-and-cancel tests, and a real-worker first-PCM p50/p95 benchmark. M5/audio acceptance remains pending.

- Shield actual SDK executor completion through cancellation/shutdown, preserving caller context and the policy lock until the writer settles.

- Ground routine reactions in actual current-turn polarity and heard question ownership; never congratulate negative/unknown intake or treat a story/refusal as a food answer.
- Let existing ActionPolicy suspend a nonurgent routine question for a grounded story and return to the same unresolved need; remove the duplicate length-based invitation selector.
- Preserve separate answer/story evidence, scoped refusals and unknown dispositions; replay quality checks through canonical SDK adjudication.
- Keep medical/safety authority and models unchanged; record paired SDK traces and M5 audio acceptance requirements.

## Unreleased — 2026-10-01

- Preserve peer m5 onset/hedge/repair/dedup updates; prevent medication or plan clocks from filling symptom onset and keep clock time distinct from elapsed duration.
- Preserve genuine elapsed duration beside clock evidence; add 17 temporal ownership cases and the peer's seven live-call regressions to the rich CI gate.

- Drain call-owned tasks, enforce configured STT/TTS deadlines, reject stale generation failures and fence SDK mutations against disconnect.
- Recover inference admission after queued cancellation/submission failure without a second blocked thread pool.
- Bound STT cancellation IDs, PCM/request lifetime and total HTTP budget; reject malformed output instead of fabricating text or GOOD quality.
- Retain complaints and addressed current-call refusal quotes at closing, preserving safety/consent controls and Core verdict ownership.
- Make grounded ResponsePlan answer composition idempotent.
- Remove failure-driven TTS engine swaps; verify configured readiness and real CallActor product path.
- Install semantic/runtime dependencies in CI/images, carry explicit image revision and support boot without git; exclude runtime artifacts/secrets from build context.
- Add production regression gates and M5 startup/failure/rollback handoff. Actual model artifacts, SIP audio, capacity and live acceptance remain pending.

- Wire opt-in bounded STT prefix previews through the existing worker/provider/CallActor; advertise revisable prefix_batch, not native streaming.
- Keep previews observational, discard late output, require authoritative final and skip busy checkpoints without replica retry.
- Fix queued cancellation/deadline checks and WAV lifetime on HTTP cancellation; address provider cancellation and report real STT queue load.
- Add 28 STT preview/cancellation/finality contracts and document the default-OFF M5 load gate.
- Add a same-WAV paired HTTP STT probe with hashes, explicit worker metadata and six WAV/request-boundary checks; phone latency remains a separate live gate.

- Forward runtime interruption to the existing SDK playout-cancel event; release the question and reject late completion without inventing delivery.
- Add two real SDK/runtime cancellation-and-resumption cases to the runtime CI gate.

- Count VAD-observed silence once at endpointing and retain speech resumed in post-roll.
- Invalidate and stop cancelled audio before remote LLM cancellation or outbox storage.
- Keep protected turn policies authoritative under barge-in; preserve detection ordering and user speech phase.
- Bound transport cancellation waits and distinguish command ACK from audible stop.
- Measure first TTS PCM and first transport send at actual boundaries; read the runtime timeline schema.
- Replace the final-only STT partial stub with an explicit unsupported error.
- Add 20 PCM/runtime contracts, an eight-input PCM probe and the Realtime v1 agent handoff.

- React to fully accepted complaints and new reports before summary without adding questions.
- Preserve dizziness/numbness in multi-report speech instead of inventing headache from anatomy.
- Name the next complaint after strong pain; tolerate trailing punctuation in accepted-degree reactions.
- Require a confirmed current-turn speaker observation for relief; invite personal stories using the existing hook once.
- Render summary acknowledgments once, share canonical speech components and avoid duplicate gratitude.
- Add 28 responsive-dialogue cases and the peer's three warmth tests to the rich CI gate.

- Keep pain/tremor owners distinct across ingest, observations and recap; preserve literal nonpain predicates and reject other-person clinical fills.
- Protect canonical repair from erroneous model answer votes without bypassing safety/control.
- Accept grounded endurance answers and single-owner elliptical degree without unnecessary severity re-asks.
- Explain an unclear severity question in ordinary words while preserving its identity and obligation.
- Follow explicit requests to discuss a known open episode, retaining the interrupted episode and its unknown values.
- Prevent topic-preference “лучше про...” from fabricating clinical recovery and clinical answers from triggering story follow-ups.

- Compose conversational acknowledgments from grounded symptom clauses; preserve plural and unfamiliar labels.
- Reflect accepted duration/severity before a follow-up, name the headache explicitly and explain the question on clarification.
- Keep custom-mission repair with the delivered question; do not clear it through normal advancement.
- Name episode handoffs, avoid duplicate positive reactions and wire conversational continuity into the rich CI gate.
- Keep semantic status inside sentence/contrast boundaries; food/sleep assessments cannot resolve a different complaint.
- Retain explicit spoken duration evidence, excluding pronoun references and unknown answers.
- Clear interrupted background coverage and avoid general concern re-asks after recorded symptoms.
- Preserve reflexive tremor, distinct symptoms at one site and grammatical plural labels in speech/recaps.
- Add the fs-2baf87ec regression and adjacent semantic cases to the mandatory kernel CI gate.
- Reject untyped clinical fills from coarse classifier/personal memory and repair clarification requests without inventing severity.
- Acknowledge discharged unknown answers and explain actual custom-goal resumption.
- Prefer negative sleep/mood facts over positive wellness in the same rendered turn.
- Keep neutral acknowledgments proportionate and remove extra asks/unsupported severity.
- Recognize polite “разговаривать” refusal in the existing DECLINE matcher.
- Preserve a grounded same-turn complaint before existing closing controls.
- Add a frozen 16-case comparison suite with attributable transcript import and elder-care research.
- Keep live audio, human warmth ratings, model readiness and competitor runs explicitly unverified.

## Unreleased — 2026-09-30

- Route bounded NLP act votes into canonical dialogue turns with truthful usage trace.
- Retire generative bridge rewriting; deliver canonical SDK speech directly to TTS.
- Keep accepted slots, mission progress and current evidence coherent.
- Preserve polite refusal after goodbye without inferring future-consent revocation.
- Discharge not-recalled episode/custom questions with explicit unanswered evidence.
- Suspend custom missions for health clarification, then resume the original goal.
- Require extractive free-text values; separate health interruptions from general task answers.
- Retain the care signal for explicitly active symptoms after questioning finishes.
- Correct summary noun-list grammar and custom greeting name addressing.
- Add SDK integration/agent guidance, competitor research and reproducible text demos.
- Keep GigaAM cache tests offline while verifying missing-tokenizer downloads explicitly.
- Fetch pinned policy history in the CI differential job without weakening its gate.

Live voice acceptance and model-artifact verification remain pending; this is a
development-branch change, not a deployed release.
