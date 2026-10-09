# Medical completeness correction — 2026-10-09 UTC

User steering: IMVERA is a medical service; retain the check-in questions while
making their timing and wording natural. Competitor sales-agent flows are not
an authority for clinical completeness. This supersedes the three-domain
completion target published in cdb3e7c/866b072 and the 2026-10-08 handoff.

## CHANGED

Existing `coverage.coverage_met` now requires all five configured baseline
care domains in explicitly enabled full mode. No minimum number of replies:
one accepted multi-fact report can answer everything. Missing topics remain
eligible; unknown/refusal is not fabricated and is not repeatedly asked.
Personal stories pause the check and can resume its remaining topics. Urgent
and stop controls retain precedence; the short preset remains short.

Existing `topic_tracker._clause_has_sleep` no longer combines an arbitrary
negation with the substring «спал» inside positive «выспалась». The reproduced
report «Мне хорошо. Сегодня поела. Таблетки не принимаю. Настроение хорошее.
Выспалась.» previously produced `topic_sleep_quality`, despite accepted positive
sleep. It now yields the open invitation after five evidenced domains.
No second scheduler/Reducer, phrase banks, new flags, generative model or
frozen policy-core modification.

## VERIFIED

`test_medical_checkin_coverage.py`: unchanged ten cases reproduced 7 FAIL/3 PASS
on baseline866b072. Changing only the coverage target gave8 PASS/2 FAIL; those
two failures exposed the sleep scope issue. After repair medical+topic tests
26 PASS. Follow-up counterexamples prevented a regression in post-verb
negation: «Спала не очень хорошо» and «Я спал не нормально». Those five
additional scope tests reproduced2 FAIL/3 PASS; the refined shared negative
quality predicate is used both for detection and inference, retaining the
reported quality without re-asking it. Medical+topic tests now31 PASS. Fixtures for full-mode invitation/cancelled-playback and corpus tests
now include all five answers while retaining their control/evidence assertions.
The prior three-topic coverage fixture now correctly asserts incomplete full
coverage; the invitation fixture with an extra required goal uses plans.
Actual paired SDK captures: [before](before.json), [after](after.json),
[checks](checks.json), using the existing coverage harness with nine identical
cases/25 turns per side and explicit full/legacy/ML-off flags. Delivery is
simulated; after capture binds the dirty working tree by source hashes.
Single-run SDK timing is not an audio latency benchmark or a speedup claim.

| Input / continuation | Baseline response | Corrected response |
| --- | --- | --- |
| Well + ate + medication | Open invitation | Ask still-unknown mood |
| Well + good mood + rested | Generic sleep-quality probe | Ask still-unknown food |
| All five baseline topics | Generic sleep-quality probe | Open invitation, no repeat |
| Story ends after first three topics | Summary | Resume mood check |

Final local gates: full3558 PASS/0 FAIL/9 SKIP/166.90s; rich974/13.27s;
runtime338/21.92s; kernel294/1.69s; topic68/0.78s; corpus500/500/6.28s
and8 regression tests/29.12s. Policy diff12 expected/0 unexplained.
Lint/contracts/whitespace PASS. Captured production source hashes match the
final working tree. Exact published-source CI is recorded separately.

## NOT VERIFIED

Actual deployed M5 flags/SHA, phone STT/TTS/audio latency, Core/family receipts,
100 complete calls, clinician acceptance or perceived human warmth. Text/SDK
replay is not phone acceptance. Runtime short/default flags were not changed.

## REMAINING RISKS

Legacy explicit sleep correction/late detail still drops updated information;
experimental global-policy temporal unknown disposition and generic functional
impact prompts still block promotion. These defects remain tracked, not
certified repaired by this cut. Safety completeness beyond the tested pack
requires continued counterexample evaluation and clinical review.

## NEXT GATE

Sequential repository full/rich/runtime/kernel/corpus/policy/lint/contracts;
source publication, then actual target configuration and real call traces.
The longer product plan keeps realtime, delivery, load and blind-listening
requirements. Never advertise all-known-defects closed or production ready
from this narrower medical coverage correction.
