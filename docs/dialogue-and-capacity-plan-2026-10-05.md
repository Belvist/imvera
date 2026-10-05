# Диалог и100 одновременных звонков: план и журнал

Target: feature/voice-zoiper-m5. Baseline0b87de7285a59f62ceb3b2e45498d71d2a0833aa.
План записан до production изменений этого cut. Actual deployed M5/audio/trace
не доступны; диагноз ниже — source-bound SDK/client reproductions. Main untouched.

## Уже сделано и доказано

| Cut | Source/verification | Live status |
|---|---|---|
| Current-call personal memory/recall | af8df7b,3286/0/3,all11CI | phone OPEN |
| Volunteered clinical facts/pending question ownership/closing | dc72d6e,3362/0/3,all11CI | phone OPEN |
| Multi-complaint progression/hedged clocks/digest6 | c11674e,3392/0/3,all11CI | phone OPEN |
| Real Linux GigaAM load curve | image2e78b54;2CPU, working-set1.46GiB, best measured1.889 successful req/s for4.088s WAV | STT only, not call capacity |
| Startup checksum buffer | actual checkpoint Python allocation428MiB→261KiB, integrity intact | worker RSS saving not claimed |

Evidence links: docs/evaluation/{personal-context,volunteered-needs,multi-complaint}-2026-10-04.
No no-generative-live rule change, new FSM/state writer/brain or model deployment.

## Current audited path and first wrong decisions

Audio → CallActor admission → canonical Understand/kernel → extract_goal_facts →
Reducer/atomic projection → EngineState → legacy/product or existing ActionPolicy
→ ResponsePlan/renderer → validated canonical text → HTTP providers → playback ledger.

1. `issue_mention_extract.extract_goal_facts` splits mixed subjects with its own
   comma/contrast regex that does not separate sentence boundaries. It concatenates
   kept text and assigns whole-text evidence. Reproduction: `Мне хорошо. Дочь
   плохо спала, а я выспалась` produces a sleep quote contaminated by daughter's
   poor sleep and reaction `Понимаю, ночь была тяжёлая`. No source supports saying
   the caller had a bad night. Existing mission clause splitter already preserves
   original offsets; existing subject resolver already distinguishes owners.
   Contextual TurnUnderstanding subsequently overwrites raw-valued narrowed
   sleep evidence with whole-turn evidence; the Reducer compatibility complaint
   branch also writes whole wellness for a foreign sleep mention. After narrowing
   the record, `_advance_after_fills` still primes topics from the whole mixed
   utterance. All three boundaries must consume the accepted source.
2. `ReplicaPool` starts idx0 in every instance. Each CallActor constructs its own
   HttpSTT/HttpTTS adapters.100 newly live client objects with identical endpoint
   config choose first replica100 times. Per-instance rotation is not process-wide
   balanced serving. Optional STT prefixes also always use urls[0]. Existing
   failover/deadline/cancellation/no-midstream-retry contracts must remain.
3. `coverage.covered_domains` scans aggregated lexical text; clinical sugar can
   become nutrition coverage and asked medication can count without an answer.
   This needs a grounded optional-vs-required coverage migration, not word patches.
   It remains an explicit follow-up; do not claim this cut fixes full questionnaire.

## Decisions for this cut

- Keep one understanding producer/fact extractor. For mixed-subject routine facts,
  reuse existing `split_mission_clauses` and subject resolver, process speaker-owned
  clauses, rebase Evidence offsets into original utterance. The existing mission
  wellness binder shares this boundary; contextual fallback cannot resurrect
  rejected foreign facts; mixed compatibility concern/topic selection uses own
  evidence. Plans retain the existing original-span/tense owner. Non-mixed
  clinical compatibility remains unchanged after full-suite regressions exposed
  that it also initializes existing topic flows. No new interpreter/phrase bank.
  Owner remains Understand → Reducer → same state/renderer.
- Share replica cursor only between concurrently live pools for identical ordered
  URL membership in one process. Weak registry prevents retaining obsolete endpoint
  configurations indefinitely; lock registry creation and selection. Each request
  preserves selected endpoint/cancel identity. Prefix optional work uses rotation
  once, no added retries. One URL retains behavior. No distributed/global scheduler.
- Preserve production admission1 and one model-owning lane per worker. Controlled
 100-client routing proves fair first choices, not100 admitted SIP calls. Separate
  compute backends must actually exist; HTTP aliases sharing Qwen still one lane.

## Next cuts and acceptance

| Stage | Change | Proof required |
|---|---|---|
| Now | Mixed-subject facts/source; client-start balancing | original failures + negatives, full gates, exact sourceCI |
| Next | Grounded coverage and optional needs, retire displaced lexical coverage owner | clinical vs nutrition/speaker vs relative/unknown/refusal, full exchanges, critical divergence |
| Then | Relevance/continuity/information gain through existing selector | user question first, story continuity, no repeats, protocol obligations preserved |
| Surface | Semantic realization and optional constrained small model research | explicit ADR decision, hardware latency/RAM/grounding benchmark before activation |
| Realtime | Full heard audio/partial/barging | real CallActor/FreeSWITCH/audio/trace, human ratings and stage p50/p95 |
| Scale | isolated10→25→50→100 load soak | actual admission, model concurrency, bursts, failure recovery, canonical hearing, queue/service/RSS/VRAM |

##100-call resource model (planning, not acceptance)

Simultaneous calls C, actual final STT requests per call per minute T,
extra previews/final P: arrival_STT = C*T/60*(1+P).
Replicas >= ceil(arrival_STT/(measured_service_throughput*target_utilization)).
For C100,T4,P0,u0.6 and prior4.088s-WAV throughput1.889req/s,
arrival6.667req/s and preliminary minimum6 STT replicas. Defaults budget
6×2CPU=12CPU and6×4GiB=24GiB **limits**; measured1.46×6≈8.76GiB
post-load working-set is not peak/model startup/full-system RAM. Longer speech
or preview work changes requirements.100 calls at T2 →3 replicas, at T6 →9.
These are formula examples with assumed T/u, not100-call capacity or a server quote.
With one additional preview per final (P1), the T4 planning value doubles to12
replicas; preview is currently optional/default OFF and batch-prefix recomputes
work, not native incremental ASR. More previews must earn their latency benefit.

Bursts are a separate gate: six queue4 workers admit at most24 running+waiting
jobs instantaneously; retrying100 simultaneous finals does not create throughput.
Even the idealized100/(6×1.889)≈8.8s drain time exceeds the release turn p95≤2s.
An idealized STT-only2s drain would require≥27 such lanes, before TTS/NLP/network
and without proof of queueing SLO. This is a lower-bound calculation, not an
accepted deployment. The release end-to-end2s budget is not all available toSTT.
GPU/batching/native incremental ASR are research/benchmark options for better
burst economics; no throughput benefit claimed until actual decoder/audio tests.
Do not enlarge queues or enable100 admissions merely to hide overload.

TTS: measure actual resident backend firstPCM/service/RTF on the proposed server;
arrival_TTS counts canonical phrases, not just user turns. Replicas from actual
service time/batching/latency SLO, not count of HTTP endpoints. One historical
Metal RTF line cannot size GPU capacity. NLP/bridge needs actual warm model
service rate, executor queues and working-set; SDK milliseconds exclude neural
startup/real runtime delays. FS/network/PG need separate measurements.

Initial core/STT pilot candidate8CPU/16GiB + separate accepted voice backend.
100-call CPU-STT tier likely separate16CPU/32GiB candidate under above assumptions;
bridge/FS/PG and voice resources additionally provisioned and benchmarked.
GPU24GB/32GiB RAM is a voice benchmark candidate only; compatibility/throughput
unmeasured. Bounded trace budgets, resident shared models, idle-only previews,
thread caps and sticky single-call ownership remain requirements.

## Journal

- 2026-10-05: fetched m5; source unchanged0b87de7, worktree clean. Baseline SDK
  contamination and newly constructed replica idx0 verified by source/reproduction.
- Tests/code/actualCI entries will be appended after execution. Live proof remains
  separate; no stage is accepted by increasing flags or announcing «100 calls».

## Optimizations in order of evidence

1. Eliminate wrong/repeated questions and repeated semantic work before optimizing
   words: fewer needless turns reduces both STT and TTS workload. This cut adds
   no generative model/provider stage; total live model invocations remain unmeasured.
2. Keep NN weights resident/shared per process; warm actual readiness before
   admitting calls. Startup checksum allocation was already bounded; it does not
   remove resident model RAM. Preserve existing one-writer call ownership.
3. Shared replica rotation is this cut's implementation. Next measure health-aware
   routing and connection reuse through existing provider lifecycle; current
   rotation is process-local, not queue-aware or a cross-process load balancer.
4. Count actual HTTP attempts (including failover) separately from logical adapter
   calls. Measure queue wait/inference, voice firstPCM/completePCM, CPU/RSS/VRAM,
   per-call PCM/trace retention and cancellation recovery during a10→100 soak.
5. Reproduce long/slow elder speech and final STT errors with source-bound phone
   WAVs; text replay cannot optimize recognition accuracy or endpointing.

Known unclosed dialogue boundaries: subjectless continuation after a relative can
still become a speaker clinical episode in the existing kernel/legacy merge, even
though routine sleep-fact extraction now abstains; quoted/report speech and implicit
first-person variants need a kernel subject ownership cut, not more phrase banks.
Coverage still scans lexical history (clinical sugar can count as nutrition),
protocol minima/ordered product packs still constrain flow. This cut fixes the
explicit mixed-subject reproduction; it does not claim free human conversation.

- Final implementation: source-bound17 regressions fail16/pass1 on original0b87
  runtime and pass on the changed runtime. Local full3401/2 inheritedLFS/9skip;
  rich842, runtime322, corpus500/500, policy diff12 expected/0 unexplained, Ruff PASS.
  Original clinical/topic tests unchanged; a broad attempted compatibility cut
  caused15 regressions and was narrowed before acceptance. See checks for exactCI.
- Paired12-case/380-turn SDK exchanges retain explicit OPEN counterexamples:
  subjectless foreign-story sleep episode and urgent wording «трудно дышать».
  These block product acceptance; canonical urgent handling remains intact.
  Replays do not establish phone warmth/recognition, target latency or100-call load.
