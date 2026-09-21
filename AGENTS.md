# AGENTS.md — IMVERA VoiseUp Constitution

> **Greenfield project.** No legacy voice codebase. No imports from prior repos.
> Read `PROJECT_CONTEXT.md` before any implementation.

## Mission

Build the **voice + telephony layer** for IMVERA: real phone calls to elderly relatives,
natural dialogue with Вера, reliable handoff to IMVERA Core for verdicts and incidents.

## Agent Identity

You are an engineering agent working on **voiseup**. You follow skills in `.agents/skills/`.
You do not improvise architecture. You do not ship without verification gates.

## Cursor Workflow (active task)

For multi-step voice/SIP work, keep `docs/current-task.md` updated (outcome, branch/SHA, decisions, criteria, next op).

```text
1. Reproduce failure with runtime truth (SHA, endpoints, trace) before patching
2. Fix root cause — never weaken e2e assertions to pass
3. Verify full chain (unit tests + relevant gate script) with commands recorded
4. Report CHANGED / VERIFIED / NOT VERIFIED / REMAINING RISKS / NEXT GATE
5. No bare «готово» — every claim maps to a verified command or is NOT VERIFIED
```

## Status Vocabulary (mandatory in every completion report)

Never say «готово» based only on green tests. Always report:

| Label | Meaning |
|-------|---------|
| **CHANGED** | What files/modules were modified |
| **VERIFIED** | What was actually run and passed (command + output) |
| **NOT VERIFIED** | What was not tested and why |
| **REMAINING RISKS** | Known gaps |
| **NEXT GATE** | Single next blocking gate |

If a claim is not in VERIFIED — mark it NOT VERIFIED. Do not guess.

## Runtime Truth (before any production bug analysis)

Before diagnosing a live/production issue, establish:

```text
git SHA / branch
container image SHA (if deployed)
active dialogue engine name + version
STT provider + endpoint URL
TTS provider + endpoint URL
LLM provider + endpoint URL
feature flags (explicit list)
dialplan / routing path (which code handles the call)
```

If any of these are unknown → **stop and verify first**. Do not patch symptoms.

## Architecture Invariants

### One owner per concern

```text
Planner   → what happens next
State     → what is true
Renderer  → how to say it
Validator → whether it may be said
Realtime  → delivery / cancellation
Transport → SIP/RTP only
```

### Hard prohibitions

```text
❌ two FSMs in production
❌ two dialogue brains in production
❌ transport speaks as Vera
❌ dialplan scripts (Lua/etc.) as conversation owner
❌ hidden fallback providers
❌ silent cloud fallback
❌ assuming generated text == heard text without trace
❌ tests green == production ready
❌ phrase length == semantic answer
❌ TECHNICAL or NO_CONTACT displayed as GREEN
❌ family consent replacing elder consent
❌ silence == consent
❌ pass-stubs, fake return ok, TODO in prod paths
❌ fourth system / new architecture while ADR-014 gates are open
❌ new features, scenarios, voice design, or models before 100 consecutive full calls
```

### Voice dialogue invariants

```text
"ага" ≠ answer to pending question
"алло" ≠ answer to pending question
noise ≠ answer
side question ≠ answer to pending question
VALID semantic answer → only then close slot

canonical_assistant_text == phone_spoken_text
(transport never rewrites Vera's words)
```

### Verdict boundary

Voiseup **emits observations and events**. IMVERA Core **owns verdicts**.
Voiseup must never locally set GREEN/RED for product-facing status without Core ack.

## Work Order

```text
1. Read PROJECT_CONTEXT.md + relevant ADR
2. Run codebase-recon skill (if touching existing code)
3. architecture-design skill (if new component or boundary change)
4. implementation skill
5. testing-verification skill
6. code-review skill (self-check minimum)
7. production-readiness skill (before any deploy claim)
```

Skip steps only with explicit user approval and documented reason.

## Skills Map

| Situation | Skill |
|-----------|-------|
| First time in repo / unfamiliar area | `codebase-recon` |
| New service, boundary, ADR | `architecture-design` |
| Writing code | `implementation` |
| Bug / unexpected behavior | `debug-root-cause` |
| Tests, benchmarks, gates | `testing-verification` |
| Before merge / self-review | `code-review` |
| Refactor without behavior change | `refactor-safely` |
| Deploy / release claim | `production-readiness` |
| PII, auth, secrets, consent | `security-privacy` |
| Latency, barge-in, streaming | `performance-realtime` |
| Dialogue quality, slot logic | `voice-dialogue-quality` |
| STT/TTS/LLM choice | `ai-model-evaluation` |
| SIP, PSTN, RTP | `telephony-integration` |
| Library / provider research | `dependency-research` |
| Commits, tags, changelog | `git-release` |
| Post-incident analysis | `incident-postmortem` |

## Key Decisions Log

Record irreversible decisions here. Format: `ADR-NNN: title (date) — one line`.

```text
ADR-008: Product milestones, Core in monorepo, semantic contract (2026-09-06)
ADR-009: LLM understanding + code state policy, QuestionLedger (2026-09-07)
ADR-012: Self-hosted LiveKit + LiveKit SIP — lab/spike only (2026-09-08)
ADR-013: Production telephony FreeSWITCH + PCM WS bridge (2026-09-08)
ADR-014: Architecture freeze + 7 acceptance gates; no fourth system (2026-09-08)
```

## Commands (when implemented)

```text
make test          # unit + contract tests
make test-voice    # dialogue + voice quality gates
make test-sip      # SIP lab E2E (requires local FS)
make lint          # ruff / mypy
make trace-bench   # latency baseline
```

Until these exist, agent reports exact commands run.

## Communication Rules

- Be honest: if unknown, say «не знаю» or «не проверено».
- Do not claim live SIP works without trace log or recording.
- Do not recommend a model/vendor without `ai-model-evaluation` evidence.
- Prefer one verified path over three speculative options.

## Reliability boundary finding (2026-09-17)

- Exhausted wellness UNCLEAR/PARTIAL survives result serialization; the explicit
  `wellness_unknown` note is now retained too. Slot DECLINED alone does not
  establish consent refusal or public DECLINED. No active Core inbox/result-to-status
  projection was found in this checkout; `packages/core` provides persistence.
  See the top of `docs/current-task.md` for exact offline evidence and remaining gaps.

## Correction / mood boundary finding (2026-09-17)

- Bare `Плохо.` in wellness context falsely filled mood before the positive
  correction. Existing negative mood matcher now requires mood context;
  explicit mood phrases remain valid. Reducer correction changes preserved.
- Exact full correction conversation passes without xfail; ITS xfail remains.
  Full suite measured pre/post: 18→17 failures, 1455→1462 passes (six new cases),
  6 skips and 1 ITS xfail. Repo lint still 199 errors; touched Ruff passes.
- Separate replay found wellness correction contaminating pending episode onset;
  complaint retention is not proof of temporal correctness. See current-task top
  for commands, narrow evidence, and next ITS gate. No production acceptance.

## ITS anaphora completion finding (2026-09-17)

- `Только это было.` now completes ITS via the existing kernel REFERS_TO
  relation + closed grammatical categories (`is_exclusive_topic_reference` in
  `reference_resolver.py`); classifier `TOPIC_COMPLETE` gated on delivered ITS
  question and a single evidenced speaker episode. ITS xfail removed only
  after the original expectation passed under `--runxfail`; expectations
  unchanged. Negative controls and 15 context guards added; full suite 17
  failures unchanged, 1494 passed, 0 xfailed; repo lint still 199 errors.
- New documented instance of free-text temporal contamination: with a pending
  onset probe, the anaphora string was written verbatim as episode onset.
  Unfixed — belongs to the pending-attribute observation boundary, not ITS.
  See top of `docs/current-task.md` for commands, scope, and next gate.

## CI pytest extras + missing-sklearn fixture (2026-09-17)

- `dialogue-rich` and `semantic-kernel` CI jobs now install `.[dev,test]`;
  conftest `_ensure_slot_answer_model` no longer catches ImportError, so a
  missing sklearn fails session setup instead of silently disabling the judge.
  Regression in `tests/test_add_quote.py` (temp sklearn stub); isolated temp
  fixture build verified, live pkl untouched, local gates green.
  Full evidence: top of `docs/current-task.md`. No commit/push by agent.

## Local preview restart (2026-09-17)

- Authorized host bridge-only restart at 01:16:31 UTC: PID 57135 → 68416,
  current dirty source on HEAD e81aeb8; native Darwin environment recovery,
  unchanged launch environment, selected new-PID flags verified. Bridge/STT/TTS
  readiness HTTP 200; new PID persisted at 69 seconds. FS/providers untouched.
- Local preview, not production acceptance. Preflight marker absent; no tests or
  manual call rerun; old loaded code cannot be rolled back from HEAD alone.
  Full evidence and verification limitations: top of `docs/current-task.md`.

## Stage A summary delivery finding (2026-09-18)

- `summary_spoken` remains the emitted flag; new `summary_delivered` is set only
  by valid current-generation PlayoutCompleted and reset on summary emission.
  Backchannel cannot close an undelivered summary; cancelled summary recovery
  re-emits it. Original stale_speak corpus assertions pass unchanged.
- Final delivery tests: 103 passed; full suite: 17 failed / 1527 passed / 6 skipped.
  Corpus now blocked at so_so-self_correction: hardcoded ITS expectation conflicts
  with negative/uncertain concern probing. Do not bypass probing or alter corpus
  expectations without owner disposition. v8 pin and policy files untouched.
- Touched Ruff clean, repo Ruff 197 errors; no typecheck command found. Local
  uncommitted work on 6b88e78, no deployment/production acceptance. Exact commands,
  regression evidence and next gate are at the top of `docs/current-task.md`.

## Stage A concern-answer finding (2026-09-18)

- Scheduler safety net emits probe_concern without probe_phase; semantic path
  dropped grounded complaints into probe_concern_options. Shared
  `apply_concern_answer` in check_path.py now owns the verdict (rich
  _probe_concern delegates); reducer bridge v2 grounds complaints with
  duration follow-up, routes UNCLEAR/ANSWER-non-complaint to the net.
- Corpus contract explicit: probe + complaint + duration + ITS for
  so_so/okay/bad (CORPUS_VERSION 1.1.0); 500/500 pass. Full suite 1 failed
  (frozen guard by design) / 1548 passed / 6 skipped; differential 92/4/4/0;
  challenge 1.0; review round 1 BLOCK → v2 APPROVE. Commit 1229dd6 pushed.
- NEXT: commit B freeze (manifest + repin + evaluator baseline decoupling).
  B–J untouched. Evidence: top of `docs/current-task.md`.

## Stage A closure finding (2026-09-18)

- v9 promoted (254f0ba: scorer version) + frozen (cb2eb61: manifest with
  tested_sha + per-file/tree hashes, FROZEN SHA repin c0fa158→254f0ba,
  evaluator V8 baseline decoupled). scorer.py is guard-frozen, hence two
  commits. Both pushed; tree clean.
- VERIFIED at freeze: full suite 0 failed / 1551 passed / 6 skipped;
  differential 92/4/4/0; challenge 1.0; corpus 500/500; guard green.
- NEXT: CI green on cb2eb61 → Stage A closed → Stage B live stop/ACK probe.
  DialogueEngine work stops here. B–J untouched.

## TTS decision + license provenance (2026-09-18)

- Owner: Silero stays as the working voice (others do not pull their weight).
  Lab runs `IMVERA_TTS_ENGINE=silero_lab`; committed default unchanged
  (mlx_customvoice); lab env and prod/default config stay separate per plan.
- Do NOT assert CC-BY-NC-SA as established fact: current upstream
  snakers4/silero-models marks TTS models MIT, but our loader pins NO
  revision (`torch.hub.load repo_or_dir="snakers4/silero-models"`,
  local v5_ru cache of unknown provenance). Repo docstrings claiming NC
  are stale relative to upstream.
- REQUIRED before Stage G: provenance of the actually-running v5_ru
  (upstream commit/tag, artifact URL/hash, license of that exact version),
  then a production licensing decision. Until then Silero is lab-only
  in practice, without asserting which license applies.

## Semantic NLP finding (2026-09-20)

- RuModernBERT-base act classifier v2 live as candidate-only: 13 acts,
  [Q]+[U] context input, frozen encoder + head, 246 expert seeds,
  held mean ~0.93 (seeds 7/11/23), warm latency ~15ms, threshold 0.55.
  Safety acts (stop/user_question) never overridden; deterministic
  validator supreme; any error/timeout → legacy path. No off switch.
- Proven by measurement: raw embeddings useless (all pairs 0.9+);
  unfreezing collapses training; random splits make the gate luck
  (stratified deterministic split locked). Artifact in models/semantic_nlp/v2
  (gitignored per repo convention); seed + train script tracked.
- Known limitation v2: goodbye-with-pending-question confuses to stop at
  low conf (safe: stop excluded → rules answer correctly). Needs
  contrastive Q-fixed sets in v3. "No failure" = pipeline always answers
  (fallback chain), model fires where confident+right.
- CrossEncoderV1 first experiment (offline/shadow only, no cutover):
  [Q]+[G]+[U] input, frozen encoder, masked heads
  (relevance/value/act/correction). Held rel F1 0.292 (39 wrong-goal FPs,
  mostly wellness over-fire), unseen-goal 0.0. Artifact metadata carries
  real counts + dataset sha256, no promoted claims. Priority queue for
  next labeling derived from errors (wellness-negatives, onset-positives).
- CrossEncoderV2 round (frozen, counterfactuals, PR-AUC): relation STILL
  not learned (held PR-AUC ~0.1→0.0). Unfreezing collapses (PR-AUC 0.059);
  bi-encoder interaction features worse (53 unseen FPs). Verdict after 4
  experiments: ~100 positive pairs cannot train goal↔utterance relation
  regardless of head architecture. Path forward is DATA order-of-magnitude
  (contrastive pairs), not architecture. Act classifier (0.95) stands as
  the proven component; goal binding stays deterministic until data exists.
- CrossEncoderV3 (reviewer-caught defects fixed): the v2 "unfreeze"
  never trained (no_grad + CPU cut the gradient — invalid evidence);
  auto-negatives were label poisoning (multi-intent utterances marked
  false). Fixed with true gradient path (verified grad norms), pair-native
  supervision (explicit labels only; auto-false solely for closed-world
  control acts), curated contrastive pairs. Result: held F1 0.885,
  AP 1.0, 0 wrong-goal FPs; unseen-goal F1 0.571, AP 0.909 (diagnostic).
  Previous "data-only" verdict was premature — clean supervision +
  real fine-tuning was never actually tested until now.
- NEXT: live-call evidence (interpret.nlp_candidate stages in traces) →
  expand seeds from misses → v3. Slot/entity heads after act proves out.

## Related Files

- `docs/PLAN.md` — master implementation plan v1.2 (historical freeze candidate)
- `docs/adr/014-architecture-freeze-acceptance-gates.md` — active freeze + 7 gates
- `PROJECT_CONTEXT.md` — product + architecture context
- `README-AGENT-SYSTEM.md` — how to use skills and rules
- `.cursor/rules/00-project-core.mdc` — Cursor always-on rule
- `.agents/skills/` — repeatable engineering processes
