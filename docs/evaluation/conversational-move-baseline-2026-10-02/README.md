# Cut0: conversational move baseline

Audited branch `feature/voice-zoiper-m5`, source 09cff20133fcf77b32bf9b32357ee0dd1922daa2.
[Architecture audit](../../conversational-move-architecture-2026-10-02.md) was
written before this measurement cut. No production owners or flags changed.

## Artifacts

* [legacy.json](legacy.json), [shadow.json](shadow.json), [policy.json](policy.json):
  exact same 15 input sequences, same explicit short preset, same date/hour copy
  settings, actual canonical SDK speech/effects/question IDs, rich understanding,
  pre/post turn state and simulated delivery. Source fingerprints and actual
  effective flags identify the run despite an uncommitted measurement tool.
* [summary.json](summary.json): actual per-case counts and missing evidence.
* [legacy-vs-policy.md](legacy-vs-policy.md): actual paired replies/SDK outcomes;
  differences are not automatically errors or measured human improvement.
* [selector-microbench.json](selector-microbench.json): existing 10k CPU selector
  benchmark, Linux x86_64. Not M5 model/telephony/capacity data.

Only unused **per-decision** state fields were projected away for storage;
all captured turn-state/effect/understanding fields remain. The raw capture
hash is retained. The same measurement function returns exactly the same result
before/after projection. Input suite hash validates exact wording; IDs/timestamps
are actual generated values and naturally differ on a rerun.

## Reproduce with the existing tool

Use the repository Python environment. Run each command as an isolated offline
process: these are NOT service launch settings or authorization for a live
policy cutover.

```bash
PYTHONPATH=. IMVERA_ACTION_POLICY_MODE=legacy IMVERA_ACTION_POLICY_CUTOVER_ENABLED=0 IMVERA_COVERAGE_LADDER=0 python tools/voice_lab/dialogue_comparison.py --suite tools/voice_lab/fixtures/conversational_moves_v1.json run --decision-metadata --label IMVERA-legacy --output /tmp/moves-legacy.json
PYTHONPATH=. IMVERA_ACTION_POLICY_MODE=shadow IMVERA_ACTION_POLICY_CUTOVER_ENABLED=0 IMVERA_COVERAGE_LADDER=0 python tools/voice_lab/dialogue_comparison.py --suite tools/voice_lab/fixtures/conversational_moves_v1.json run --decision-metadata --label IMVERA-shadow --output /tmp/moves-shadow.json
PYTHONPATH=. IMVERA_ACTION_POLICY_MODE=policy IMVERA_ACTION_POLICY_CUTOVER_ENABLED=1 IMVERA_COVERAGE_LADDER=0 python tools/voice_lab/dialogue_comparison.py --suite tools/voice_lab/fixtures/conversational_moves_v1.json run --decision-metadata --label IMVERA-policy --output /tmp/moves-policy.json
PYTHONPATH=. python tools/voice_lab/dialogue_comparison.py --suite tools/voice_lab/fixtures/conversational_moves_v1.json metrics --capture /tmp/moves-legacy.json --output /tmp/moves-legacy-metrics.json
PYTHONPATH=. python tools/voice_lab/dialogue_comparison.py --suite tools/voice_lab/fixtures/conversational_moves_v1.json compare --left /tmp/moves-legacy.json --right /tmp/moves-policy.json --output /tmp/moves-compare.md
PYTHONPATH=. python scripts/benchmark_action_policy.py --iterations 10000 --json
PYTHONPATH=. python -m pytest -q --tb=short tests/test_dialogue_comparison.py tests/test_dialogue_measurements.py
```

SDK Understand+Reduce timing excludes speech, STT, actor admission, TTS and
physical playback. Generative/model invocation counts, memory, phone latency,
questions/minute, topic appropriateness, evidence correctness, safety error rate
and questionnaire-feel remain **NOT_RUN**. A missing measurement is not zero.
Non-question speech includes summary/goodbye, so its count is not empathy quality.
Repeated question keys may be appropriate after unknown answers: diagnostics
require semantic/evidence review, not automatic rankings.

## Handoff to the M5 agent

1. Preserve the current working tree/peer commits and use m5, never main.
   This cut adds measurement tools; it does not require a runtime restart.
2. Establish **loaded** bridge source/image, engine, STT/TTS/model revisions,
   media mode and effective flags. Checkout SHA alone is insufficient. Keep
   policy promotion disabled while pending/ITS lifecycle is uncorrected.
3. Capture the 15 required scenario types through real CallActor/FreeSWITCH with
   audio+JSONL using existing recording/forensic and consent procedures from
   [production handoff](../../production-dialogue-handoff.md). Check missing or
   truncated events. Slow/barge fixtures here do not validate acoustic behavior.
4. Keep SDK and actor rich-turn captures separate until producer parity is
   proven. Include literal input, proposals vs adjudicated meaning, accepted
   quotes, selected owner, pending needs and actual question delivery identity.
5. Collect turn-keyed acoustic-end/endpoint/STT/decision/firstPCM/playout events.
   Existing first-mark call timeline and answer→opening histogram cannot provide
   end-of-user-speech→reply latency. Count delivered asks, not planned texts.
6. Before any generation decision, check the actual local LLM worker/checkpoint
   and extend the existing bench with cold/warm repeated samples, RAM/RSS/MLX,
   queue/throughput/cancellation and grounded Russian task cases. Do not stream
   the old `/render` output straight to TTS; it lacks complete grounding validation.
7. Next production cut: common reducer-owned plan commitment, then producer/QA/
   current-severity/global-stop fixes with original safety/state gates. Avoid
   new phrase banks, a second scheduler and an unmeasured policy flag flip.

Final voice acceptance needs attributable before/after recordings and blinded
listening; this baseline does not claim that IMVERA became human or beat Newo.
