# Personal context: topic return with attributable evidence

Branch: `feature/voice-zoiper-m5`. Baseline
`2f18791c155079efde6c967d7292e488ecc74bac` (clean detached checkout).
Implementation source and exact CI are recorded in [checks.json](checks.json)
after publication. [Product architecture/next cuts](../../conversation-product-plan-2026-10-04.md).

## Reproduction and changed ownership

Previously discourse retained only the latest200-character story, while
`mission_flow._grounded_answer_recall` had no ordinary-story evidence source.
After a topic change, the shared answer owner denied having the previous story.

The same reducer-invoked discourse writer now retains6 immutable, literal
excerpts with call ID, accepted utterance ID and turn number in EngineState.
The same answer owner can retrieve a matching current-call topic. No second
state writer/scheduler, health/family fact projection, database query, provider
call, flag change or live generator was added. No former full-text bank was
expanded; the existing grounded quote response is reused.

```text
USER: Вчера дочь приезжала, мы смотрели старые фотографии.
USER: Потом вспоминали нашу деревню и соседей.
USER: Что я рассказывала про дочь?
BEFORE: В этом разговоре у меня нет подтверждённого ответа об этом.
AFTER: В этом разговоре вы сказали: «Вчера дочь приезжала, мы смотрели старые фотографии.».
USER: А что я говорила про деревню?
BEFORE: В этом разговоре у меня нет подтверждённого ответа об этом.
AFTER: В этом разговоре вы сказали: «Потом вспоминали нашу деревню и соседей.».
```

Complete canonical exchanges/state are in [before.json](before.json) and
[after.json](after.json), using the same [nine cases](cases.json). Feedback
does not replace the story. A personal question can suspend an existing clinical
need without satisfying it. Missing/evicted/foreign-time topics and medical
questions without evidence still abstain; urgent and stop paths still close.

## Actual checks

Initial11 new cases:7 FAIL/4 PASS before source changes. Initial rich attempts
exposed two mistakes in new test construction (missing RichUserTurn fields and
nonexistent SuspendedObligation property); corrected to real contracts. Existing
assertions were not weakened. Final25 context cases plus2 controlled Actor cases
are included in the rich gate.

```sh
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
  make test-dialogue-rich PYTHON=/workspace/imvera-review-venv/bin/python
# 759 passed, 11.49s
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
  make test-dialogue-runtime PYTHON=/workspace/imvera-review-venv/bin/python
# 316 passed, 20.17s
```

Corpus500/500 PASS,5.79s; policy diff12 changed/12 expected/0 unexplained.
Ruff and whitespace PASS. Full local suite before the final5 test additions:
3273 PASS/2 FAIL/9 SKIP,151.92s. Both failures are inherited genuine relation-LFS
readiness checks; no waiver, model substitution or fake readiness was introduced.
Exact published-source CI with genuine LFS is a separate required gate.

The existing canonical-understanding parity fixture exercises actual CallActor
admission with controlled STT/act outputs, requiring one kernel, one mission
attachment and one act proposal. This proves producer reuse, not neural
recognition quality or phone/audio delivery. Correction invalidation is also
tested with a canonical typed RichUserTurn; correction-model accuracy is not
inferred from it.

## Replay and cost scope

```sh
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
  /workspace/imvera-review-venv/bin/python \
  docs/evaluation/conversation-floor-2026-10-04/replay.py \
  docs/evaluation/personal-context-2026-10-04/before.json \
  --checkout /tmp/imvera-context-baseline-2f \
  --cases docs/evaluation/personal-context-2026-10-04/cases.json
# Repeat for after.json on the implementation checkout, omitting --checkout.
```

Each run390 SDK turns,10 repeats. Synthetic SDK-turn p50/p95:
before2.215/3.452ms; after1.967/3.076ms. This single comparison does not establish
a speed improvement. Speech/model/queue/phone time is outside measurement;
`provider_model_invocations=NOT_MEASURED`, `end_of_speech_to_PCM=NOT_RUN`.
SDK ScenarioRunner simulates heard completion. Real playback is not proved.

Storage is bounded to6×200 quote characters plus bounded identifiers; these
cases reached6 entries/294 quote characters. Morphology/topic lookup reuses the
existing normalization and adds no model stage by source inspection. Actual
provider counts, RAM and concurrent throughput require runtime measurement.

## Remaining limits and next gate

Lookup matches inflected literal topic words, not arbitrary paraphrases or
open-ended reasoning. Retention evicts older topics; canonical correction
conservatively clears unrelated stories too. Routine coverage minima, ordered
clinical plans, deterministic surface and unsupported world questions remain.
This cut repairs missing narrative recall; it does not accept a human dialogue.

Next source work: classify optional versus decision-required information in
the existing selectors and measure full-dialogue burden/divergences before
authority changes. Next live gate: repeat these exchanges through actual
CallActor/FreeSWITCH with exact SHA/providers/flags, recording and raw trace,
including symptoms/correction/refusal/stop. Investigate the earlier4165ms
engine turn. Warmth, interruption, target latency, competitor comparison and
million-user/concurrent capacity remain NOT VERIFIED.
