# Volunteered meaning, pending needs and closing ownership

Branch: `feature/voice-zoiper-m5`; clean baseline
`d0bfac667f6a97426d42974c60127b1958a673d5`.
Implementation replay was captured on the dirty baseline before its source
commit; exact published-source checks are recorded in [checks.json](checks.json).
This is SDK/state and controlled Actor evidence, not phone/audio acceptance.

## Root causes and replaced behavior

The existing semantic parser used four-letter spelling prefixes as anatomical
and verb evidence. `Я потеряла ключи` could become a clavicle/sweating issue.
Morphological lemmas and the existing surface grammar now own that recognition;
the unsafe prefix fallbacks are removed. Exact inflections, ё/е normalization
and legacy diminutive evidence retain regressions.

The existing one-antecedent clause relation omitted the grammatical modifiers
`довольно` and status-only `всё`. Consequently volunteered degree was lost and
a resolved earlier complaint could be probed as current. That same relation
owner now admits these modifiers with its existing separate-person, activity,
negation and multi-issue guards. A current continuation cannot become onset.
Literal evidence and turn identity remain attached to each observation.

The same parser also accepts an anatomical nominal sensation predicate using
shared morphology/concept metadata. `Голова какая-то тяжёлая со вчера` is a
sensation, not invented pain or a severity. The existing generic symptom plan
asks current status only if it is actually unknown. Object/fiction/other-person
predicates do not become a speaker complaint. No second clinical planner.

ActionPolicy previously generated and scored only four generic needs even
when the reducer already held another pending product need. The existing
`currently_askable_needs` now supplies candidate generation, remaining ask
utility and transition evaluation, including the canonical active pending
need. Nine actual product dimensions are derived from FAMILY_PLANS in the
tests/audit, not duplicated in a new production registry. Delivered question
meaning uses its QuestionNeed; intent inference is compatibility only for
old serialized questions. Planned/playing questions are not heard questions.
Safety, control, repair and user-answer precedence and scorer weights remain.

After an actually heard summary, a whole-utterance no-more acknowledgment
now closes through the existing reducer closing owner. It cannot restart
routine coverage. Bounded completion grammar excludes unknown, additional
story/health words and questions; an unheard summary cannot imply consent
to close. The original summary remains nonterminal until a closing response.

A new closing test exposed a separate outcome bug: an accepted immediate
urgent action after earlier positive wellness could still produce GREEN.
The existing outcome owner now gives the reducer's URGENT + urgent-close
pair priority over earlier positive facts and stale external GREEN/YELLOW.
It reports a RED candidate; Core still owns the final verdict. No new medical
fact, consent or EngineState writer is introduced.

## Actual exchanges

```text
USER: Голова болит со вчера, довольно сильно.
BEFORE: Жаль, что голова болит. Сейчас голова болит сильно или терпимо?
AFTER: Головная боль — понимаю, терпеть такое трудно. Ещё что-то беспокоит?

USER: Голова болела, но сейчас всё прошло.
BEFORE: Жаль, что голова болит. А сейчас голова ещё болит или уже почти прошла?
AFTER: Слышу вас: головная боль. Что-то ещё важное есть?

USER: Я потеряла ключи.
BEFORE: [clinical onset question for a false clavicle issue]
AFTER: Про ключи поняла. Расскажите, я слушаю.

[after heard summary]
USER: Нет, больше ничего.
BEFORE: Как сегодня с едой — нормально поели?
AFTER: [goodbye_final, no further question]

[after earlier positive wellness and heard summary, SDK closing test]
USER: Нет, больше ничего. Не могу дышать.
BEFORE: urgent_close speech; candidate_family_status=GREEN
AFTER: urgent_close speech; candidate_family_status=RED
```

The paired replay uses coverage=1 and reaches that urgent turn before summary:
its outcome changes YELLOW→RED. The separate completed-mission closing test
reproduces GREEN→RED with the same engine; do not conflate the contexts.

Complete actual text/state/outcomes are in [before.json](before.json) and
[after.json](after.json), using [11 cases](cases.json), 300 SDK turns per run,
30 representative turns. Candidate compatibility snapshots are separately
labeled synthetic in [policy-before.json](policy-before.json) and
[policy-after.json](policy-after.json). All nine pending needs change from
ACK_ONLY to the corresponding ASK_EPISODE when generic needs are already known.
Default medical authority remains legacy; this does not prove deployed need loss
or justify global cutover.

## Verification and truthful freeze

Initial volunteered cases: 9 FAIL/8 PASS before changes. Initial pending cases:
18 FAIL/8 PASS after correcting a new test's unsupported repair argument.
Removing fuzzy spelling exposed one existing diminutive-evidence regression;
the merge implementation was corrected, retaining its original assertion.
A new legs-sensation test initially demanded current status despite already
known current evidence; corrected the new test to respect that evidence.
The final added urgent-after-summary test failed on GREEN and was fixed in
the outcome owner; the safety assertion was retained.

The mandatory freeze-order test previously assumed every release was frozen,
blocking the documented candidate → exact source CI → metadata pin workflow.
It now exercises the unchanged strict guard on a real temporary Git commit,
real ten-file hashes and available historical objects. No fake Git responses,
skip or weaker freeze hash assertion. Historical v9/v10 manifests remain intact.
The active v10 correctness manifest uses the same action/weight schema and
is published as candidate before pinning an actual CI-verified source SHA.

Local checks: rich807 PASS,11.47s; runtime316 PASS,20.02s; policy266 PASS,6.14s;
isolated historical-v9/current-v10 diff12 expected/0 unexplained; corpus500/500,
5.86s. Ruff and whitespace PASS. Full local and exact source CI details/limitations
are recorded in checks.json; genuine relation-LFS readiness is never substituted.

```sh
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
  /workspace/imvera-review-venv/bin/python \
  docs/evaluation/conversation-floor-2026-10-04/replay.py /tmp/before.json \
  --checkout /tmp/clean-d0-checkout \
  --cases docs/evaluation/volunteered-needs-2026-10-04/cases.json
# Repeat on the implementation checkout for after.json.
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
  /workspace/imvera-review-venv/bin/python \
  docs/evaluation/personal-context-2026-10-04/audit-policy-needs.py /tmp/policy.json \
  --checkout /tmp/source-checkout
```

SDK p50/p95: before2.432/5.447ms, after1.926/4.048ms. One synthetic run,
overlapping host checks, establishes no speed improvement or target latency.
Model stages added by source review:0. Controlled Actor admission retains
one kernel, mission attachment and act proposal; it is not real neural inference.
Provider counts NOT_MEASURED, end-of-speech→PCM NOT_RUN. Candidate set remains
bounded by existing episodes/generic needs plus one pending need. No new network
service, generator, model dependency, raw-transcript metric or cross-call storage.

## Remaining risks and next gate

Fresh product needs outside the generic optional set are still a global policy
cutover blocker. Routine coverage minima and ordered product plans still direct
many transitions; surface realization remains deterministic. Bare `Уже отпустило`
after the active clinical episode has been left is not safely bound to an old
episode. Arbitrary stories/questions/paraphrases remain outside these proofs.
These fixes do not claim unrestricted human conversation or million-user capacity.

Integrate through the existing SDK producer/reducer/renderer, never copy
extraction into CallActor or rewrite canonical speech in TTS. No new flag is
needed for default-live grounding/closing fixes; do not globally promote medical
ActionPolicy merely because pending compatibility passes. Verify deployed SHA.

Next gate: actual CallActor/FreeSWITCH recordings + raw traces for these cases,
heard question identities, urgent/refusal/stop, slow speech and interruption;
measure stage p50/p95, actual provider calls, RAM/concurrent admissions and blinded
warmth/questionnaire ratings. No target stack was restarted from this workspace.
