# Technical audit against m5 — 2026-10-08

Baseline **361972eb0f12b1402bed619c5b43eb7b664efa19**, exact local/origin/GitHub
agreement before edits. GitHub compare returned ahead198/behind0. Baseline HEAD
[CI37647011108](https://github.com/Belvist/imvera/actions/runs/37647011108)
is completed/success. Its tested source is unchanged from
[f7b748ca / CI37645641929](https://github.com/Belvist/imvera/actions/runs/37645641929),
whose recorded full result is3499 PASS/0 FAIL/3 SKIP. The historical count is
not the count for this subsequent safety/cache cut. Exact new checks and source
fingerprints are in [checks.json](checks.json).

## Evidence boundary

This checks the supplied technical review against source, original measured
artifacts, new baseline regressions and real SDK/CallSession/worker execution.
No actual M5 image, loaded SHA, providers, environment flags, SIP route, waveform
or family receiver is observable here. The managed cloud reports no configured
secrets/runtime variables/outbound identities; network policy has no configured
VPN. There is no diagnosis or deployment claim for the actual Mac.

Captured synthetic [before](before.json)/[after](after.json) contain literal
engine output and exact source hashes. Playback in the SDK recorder is simulated
completed playback. The cache tests use controlled upstream PCM; they execute
the actual Qwen worker producer, not a resident speech model. None measures
phone warmth, end-of-speech→firstPCM, family notification or100-call capacity.

## Supplied claims, checked individually

| Claim | Verdict and actual boundary | Source/evidence |
| --- | --- | --- |
| Work on m5, HEAD361972eb,198 commits ahead main | CONFIRMED at baseline; «6 since previous review» has no identified comparison SHA | GitHub branch/compare APIs; git fetch/rev-parse |
| CI11/11 and3499 tests | CONFIRMED baseline CI success;3499/0/3 is recorded for exact f7 source, not a phone gate | linked runs; previous listener checks |
| FreeSWITCH→bridge→CallActor→VAD/STT→engine→TTS | CONFIRMED source flow; actual target route unknown | packages/telephony/freeswitch_bridge.py; services/imvera_media_bridge/callactor.py; packages/voice_runtime/call_actor.py |
| GigaAM v3 RNNT | QUALIFIED: configured model is v3_e2e_rnnt, CPU in both checked profiles; deployed revision unknown | config/voice-m5.yaml; config/voice-linux-cpu.yaml |
| Silero VAD32ms / about650ms silence | CONFIRMED defaults; total endpoint time also involves utterance-builder tail/post-roll and actual flags | packages/voice_runtime/silero_vad.py; utterance_builder.py; docs/realtime-conversation-v1.md |
| Mostly final STT; partial prefix opt-in | CONFIRMED: IMVERA_STT_PREVIEW default0; prefix_batch repeats accumulated prefixes, not stateful incremental RNNT | services/stt/worker.py:capabilities; CallActor build/preview path |
| TurnUnderstandingV2 active | CONFIRMED: CallActor prepares kernel, resolves canonical RichUserTurn and adjudicates candidate act; no model owns state | call_actor.py interpret path; turn_understanding.py |
| Example simultaneously supplies wellness/story/headache/medication | QUALIFIED: illustrative schema is not actual output. Replay extracts own wellness and headache/onset/severity; does not emit separate daughter/story or medication record for that whole mixed sentence | replay.py → actual_rich_turn and accepted_state in after.json |
| Understand arbitrary paraphrases | NOT ESTABLISHED. The supported semantic representation and deterministic evidence binders remain bounded | turn_understanding.py; semantic_kernel; actual counterexamples |
| Distinguish own/foreign complaints and bad film/poor sleep | CONFIRMED for existing scoped regressions, not a universal guarantee over arbitrary speech | mixed_subject_routine_facts, implicit_subject_ownership, clinical_ellipsis_grounding, semantic_kernel tests |
| Multiple complaints | CONFIRMED source progression/episode-scoped needs; real current STT accuracy remains unknown | issue_memory.py; tests/test_multi_complaint_progression.py; prior multi-complaint evidence |
| Volunteered food/meds prevents repeat; sugar≠nutrition | CONFIRMED source. Actual replay still asks mood, so this alone does not remove questionnaire flow | coverage.py; test_grounded_coverage.py; grounded-coverage-2026-10-07; after.json |
| Personal conversation can exceed six statements | CONFIRMED in new eight-statement SDK capture; all eight remain open; this is not unlimited semantic memory/free chat | discourse.py; decision_router.py; after.json eight_story_turns |
| «Нет, ничего» finishes topic, not call consent | CONFIRMED; capture gives summary with call still open for farewell | listener-completion-2026-10-07; after.json |
| One EngineState/Reducer, three kinds of memory | QUALIFIED: Reducer is the authoritative dialogue funnel; discourse writes occur inside it, Postgres persists projections. Memory is not an associative universal brain | state.py/reducer.py/discourse.py; packages/core/pg_store.py |
| Discourse six literal records, eviction, conservative correction | CONFIRMED; ring stays6 after eight narrative replies; correction clears old excerpts | discourse.py:retain_personal_statement; personal_context_recall tests |
| Prior-call context | CONFIRMED bounded evidence/digest and person scope; cross-call retrieval/correction on actual target not run | packages/dialogue/session.py; caller_memory.py; prior result projection |
| ActionPolicy v10 rules/weights; personal authority, legacy ordinary check-in | CONFIRMED. Eligible personal path runs before mode routing; mode off→legacy; medical cutover false unless explicitly enabled | decision_router.py; action_policy_shadow_config.py; action_policy/scorer.py |
| Three exchanges/three domains, ordered health plan | CONFIRMED for enabled coverage ladder; not an unconditional minimum on every call/mode. FILLER_ORDER ties and product need order remain | coverage.py:coverage_ladder_satisfied/scored_next_domain; product/planner.py |
| Renderer is deterministic / canonical text | CONFIRMED; ResponsePlan and realization compose canonical surface; retired composer is not called | response_plan.py; realization.py; ADR025/026/028; canonical-delivery tests |
| Mac MLX vs resident Qwen vs Silero paths | CONFIRMED paths/profiles; actual target choice unknown. Silero lab label is not proof of upstream artifact license | services/tts/worker.py; qwen_gguf.py; gen_params.py; profiles |
| Streaming TTS | CONFIRMED contract/client PCM streaming; no current audible latency/prosody acceptance | qwen_gguf.py; bounded streaming/HTTP tests |
| Barge-in mechanism exists, default OFF, echo gate≠AEC | CONFIRMED. generation cancellation/ledger/reference checks exist; audible stop p95<250ms NOT VERIFIED | voice_perception/echo_ref_gate.py; CallActor; transport-cancel tests |
| «Мне сейчас трудно дышать» missing urgent detection | CONFIRMED BASELINE DEFECT; repaired in both detectors with shared fragment and existing guards | new breathing_scope tests; before/after.json |
| RED observation/handoff phrase proves family delivery | REJECTED. CallSession emits RED_SIGNAL and persists original quote; Postgres inserts outbox. A Telegram demo exists under tools, but no deployed Core/outbox receiver or recipient receipt is established | session.py; pg_store.py; migrations/001_initial.sql; tools/family_notify/telegram_report.py; new session test |
| Qwen cache64 count, FIFO, missing revision/deadline | CONFIRMED BASELINE DEFECTS; repaired, including effective default-voice identity and per-frame cancellation | services/tts/worker.py; test_qwen_cache_bounds.py |
| Linux STT1/2/4/8 client numbers | CONFIRMED stored measurement on older2e78b543 source,2vCPU quota/4GiB limit,4.0875s WAV; at8,p95 includes only4 successes,20/24 are429 | ../multi-complaint-2026-10-04/stt-load.json |
| Old live engine p95≈4.2–5.7s | NOT REPRODUCED: no attributed raw report supporting these exact numbers was identified. Do not relabel SDK microbench or STT HTTP latency as current phone latency | supplied review omits a call/report ID; fresh target trace required |
|100 HTTP clients≠100 calls; bridge cap1 | CONFIRMED. Rotation test covers independent HTTP adapters; configured aliases may share one model lane | test_replica_start_distribution.py; linux profile; subject-and-replicas report |
| Main/README/older architecture text stale | CONFIRMED; root README falsely said branches identical and barge-in absent. Current entry-point status now corrected; historical ADRs remain history | README.md; PROJECT_CONTEXT.md versus current code/ADR025/028/029 |

## Root-cause repairs, existing owners

**Breathing:** both independent lexical surfaces omitted difficulty wording.
`packages/safety/patterns.py` supplies one shared breathing-difficulty fragment
(both word orders) to `check_path._URGENT_ACTION` and `rules.RED_PATTERNS`.
Existing third-person/negation/past guards remain authoritative. The shared
third-person guard now includes daughter/husband inflections and third-person
pronouns; without these, admitting the new wording would create false caller
emergencies. No speech bank, model, verdict owner or policy-manifest repin.
This is the explicitly requested safety defect repair, not a relaxation of
consent/control or RED model authority. Existing assertions remain unchanged.

Important discovered contract difference: direct rich/semantic SDK input emits
urgent_close. `CallSession` first ingests a deterministic RED signal and calls
the existing SafetyInterrupt owner, which deliberately asks a safety confirmation
for descriptive signals. Explicit help requests still close immediately; the
existing «yes to help» tests keep handoff. The new session regression verifies
RED_SIGNAL and persisted original risk quote with in-memory storage. Neither
path proves Core acknowledgement or family receipt.

The Telegram demo polls ended call snapshots, renders a clearly labelled
dialogue candidate and calls Telegram sendMessage. Its existing tests check
message content only. It is not an outbox consumer/Core verdict projection,
and it has no durable per-recipient receipt: report_call returns success when
at least one configured chat succeeds, while watch marks the whole call sent.
Thus a failed second chat is not retried for that call by the current watcher.
This is a concrete demo limitation, not evidence of any actual missing alert.
No external messages were sent or notification deployment altered in this audit.

**Qwen cache:** the existing producer now retains at most64 entries and16MiB
of PCM, evicts the least recently used entry (hits update recency), and scopes
keys by endpoint, accepted worker model_revision, effective voice, language and
canonical text. The previous unspecified voice key could wrongly reuse bytes
after config/environment selected another voice. This is now resolved before
both lookup and synthesis. No new model stage/provider/fallback.

Deadline is checked before any cached output and before each PCM frame, including
newly generated split frames. Cancellation is checked between those frames.
Partial/error/cancelled/expired renders never enter cache. A phrase exceeding
the budget keeps streaming, but its accumulation is released and never retained.
Warmup bypass remains bypass. The limit bounds cached PCM, not whole worker RSS,
Python object overhead, transient stream buffers or the resident model.

Accepted model_revision is presently a resident model ID, not an immutable
weights/voice-artifact hash. A same-ID backend/clone replacement requires operator
revision discipline and worker restart; cache keys cannot infer such a replacement.
No actual inference/voice quality or speedup is claimed by controlled-PCM tests.

## Verification

Commands/results and fingerprints: [checks.json](checks.json). Same final37 new
tests on baseline: **21 FAIL/16 PASS**, using the same existing built slot-answer
artifact. After repair plus original safety/Qwen tests: **105 PASS**. This proves
actual behavior changes, not merely new expected strings. The initial collection
typo was corrected before the baseline and is not counted as defect evidence.

Initial parallel verification exposed one runtime test deadline and a model
candidate abstention under its unchanged300ms budget. Both original assertions
passed on focused recheck. No production budget or test expectation was increased.
Sequential final verification: full3530 PASS/0 FAIL/9 SKIP/173.70s,
runtime338 PASS/22.92s, kernel294 PASS/1.66s. Rich951 PASS/69.71s,
corpus500/500/17.50s plus8 tests, policy diff12 expected/0 unexplained.
Actual results, including initial failures, remain in checks rather than concealed.

`make lint` covers packages/services/tests/scripts and passes. An additional
`ruff check .` included historical archive/audits and found16 pre-existing errors;
they are outside that gate, unchanged by this cut. The replay script is linted
separately. Source CI results are recorded only after that exact source run passes.

## Remaining product gates

CHANGED: shared safety surface/attribution, Qwen producer cache/delivery checks,
new regression files in mandatory rich/runtime gates, root status and handoff.
VERIFIED: exact commands/results in checks; paired SDK captures above.
NOT VERIFIED: actual M5 deployment/audio/STT/TTS/SIP/firstPCM/prosody/barge-in,
real Postgres→Core ack→notification recipient, total model invocation counts,
whole-stack RAM/VRAM, sustained100 complete calls.
REMAINING RISKS: routine coverage minima/legacy selection; bounded semantic/free
language/memory; same-ID resident artifact replacement; live/Core/load acceptance.
NEXT GATE: target recorded call + RED event through the test Core to a test
recipient, with image/loaded SHA/profile/backend provenance. Access/receiver
information requested; not supplied in this session.

Then remove optional-question pressure through the existing information-need
policy, measuring critical divergence before medical cutover. ADR028 option B
remains a proposal: current authorization still forbids generative live speech.
It cannot be silently enabled by citing an architectural comparison to Newo.
Endpointing/barge-in/prosody and10→25→50→100 load need actual hardware evidence.
Keep admission1; do not restart FreeSWITCH/Postgres just to load this Python cut.
