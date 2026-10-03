# Grounded reactions and real topic suspension

Base: `f566cec64b5262f7a4956522ea6b7d0145aa2ef8` on
`feature/voice-zoiper-m5`. This is SDK/text evidence, **not phone acceptance**.
The peer's composer, varied reactions, address/name guards and neutral unknown bank
are preserved. Latest peer commits b48c35b/f566cec are incorporated. Their
unknown-to-positive promotion on engagement is replaced by actual current-turn
evidence: answering about a topic does not prove a positive outcome.

## First wrong decisions

1. A coverage observation had no polarity. `realization._domain_reaction`
   treated the missing record as positive: `Не поел.` → `Хорошо, что поели.`
2. The legacy coverage executor accepted any substantive answer act. A story
   about daughter/photos became `coverage_nutrition`, and a local refusal could
   also become an eating answer.
3. The personal selector rejected delivered routine questions as specific
   obligations. A second, length-based `_follow_person_plan` offered one extra
   exchange after the legacy ladder had already consumed the story as an answer.
4. `conversation_quality.replay_call` used raw kernel projection instead of
   canonical SDK understanding. Weather questions could be reflected as nouns
   rather than answered. Text reaction proxies are not listener ratings.

## Owners and replacement

`EngineState` and reducer admission remain authoritative. Admission captures
the actual delivered answer slot before scheduling can replace it. A bare yes/no
cannot assert intake against a merely planned/unheard question. Explicit
speaker statements can still volunteer facts independently of question delivery.

Routine evidence consumption moves from the legacy-only branch to the shared
`schedule_next_action` execution boundary, before either selector. Domain
relevance, local refusal and unknown remain distinct. The old coverage block is
removed. `coverage_records` uses existing `SlotValue` with original quote/turn
identity; topic coverage alone does not set positive polarity. Food inference
uses cached morphology, existing clause/subject/uncertainty/negation owners and
a small set of ingestion predicates. Old/future/third-party/fiction/uncertain
statements abstain; drinking alone never asserts that someone ate.

Existing discourse owns the separately asserted story following an answer:
`Да, поела. А вчера дочь приезжала…` keeps both purposes and a contiguous story
source. Existing ActionPolicy v10 chooses invitation/listen in grounded,
nonurgent routine contexts. The duplicate `_follow_person_plan`, character
thresholds and its one-invitation mid-check-in counter are removed. Its selector
is not replaced with another scheduler. Medical/custom authority flags and all
ten frozen ActionPolicy core blobs remain unchanged.

The unfinished routine domain survives a genuine story and resumes after the
person finishes. Actual answers are retained and never reasked on that return.
`Не помню` discharges the heard question as unknown without a fabricated value.
The bounded post-exhaustion `_open_continuation` remains; it is not an unlimited
free-talk capability. Clinical/control/safety owners keep priority.

Renderer uses current-turn evidence, never an older record to colour a new
answer. Unknown polarity has a neutral reaction; negative plans do not imply
difficulties. Negative intake says `Поняла, пока не ели.` without guessing why.
Unpolarised sleep is acknowledged before a positive general-wellness bridge.

Two integration defects are corrected: product current-proof ignores known
legacy string observations instead of crashing; tense extraction abstains when
morphological metadata is absent. Neither invents evidence to pass a gate.

## Paired examples

| User | Before | After |
|---|---|---|
| Не поел. | Хорошо, что поели. … | Поняла, пока не ели. … |
| Не хочу отвечать про еду, но хочу поговорить. | Хорошо, что поели. Расскажите, я слушаю. | Расскажите, я слушаю. No eating fact; scoped refusal. |
| Story about daughter/photos, then Больше нечего добавить. | Story stored as nutrition answer; move to medication. | Story/listening; then return to the still-unanswered meal question. |
| Да, поела. А вчера дочь приезжала… | Same invitation surface, selected by length fallback. | Intake evidence retained; separate story selected by existing ActionPolicy. |
| Не помню. | Unknown ACK, next topic. | Same behaviour, unknown disposition explicit; no reask/value. |

`before.json` and `after.json` contain the actual canonical SDK/CallSession
replies, question flags, coverage evidence, slots and owner counters. Inputs are
**16 synthetic cases / 36 user turns**, not 16 new real phone calls. Six speech
sequences change; equal wording can still have a different, correct evidence
owner. No warmth percentage or superiority score is inferred.

Replay in an isolated checkout with the same genuine optional classifier and
flags:

```bash
PYTHONPATH=. python docs/evaluation/conversational-grounding-2026-10-03/replay.py /tmp/replay.json
```

For the base checkout, invoke that same script by its absolute path. Keep
trained artifacts identical. `sources.json` fingerprints package/service Python
sources in both checkouts and identifies the local LFS limitation.

## Verification and limits

Commands and final measured results are recorded at the top of
[`current-task.md`](../../current-task.md). Initial regressions in medication,
unknown discharge and over-eager routine resumption were fixed; original
medical/snapshot/delivery assertions were retained. One exact phrase assertion
is deliberately updated: absence of eating does not prove inability to eat.

No new generative/model service, model invocation, prompt containing the whole
transcript, provider, transport or timer is added. Cached morphology is extra
CPU work. [Warm helper measurement](intake-cpu.json),2000 iterations on this Linux:
p50=.113217ms,p95=.313735ms,p99=.372051ms. It measures this helper only,
not full-turn/M5 latency or capacity. M5 end-of-speech latency, RAM, full-turn model counts and concurrent
throughput are **NOT_RUN**. Current local relation encoder is still a genuine
Git LFS pointer; two readiness checks fail rather than claim `all_hot`.

The first genuine-LFS CI run passed3115 tests but failed one unchanged legacy
200ms out-of-order runtime assertion. The actor/session/legacy code is unchanged
from the peer. Original assertion/deadline passed30 local repetitions and73
related runtime tests; [diagnostic record](runtime-recheck.json). The timing
failure was not reproduced locally. A second attempt repeats that same failure (3115 PASS,1 FAIL,3 SKIP,176.58s).
The test now reports actual coroutine await sites, buffered ordering and lock
state on the unchanged200ms failure. No result/deadline is weakened. Local
LFS fetching is blocked by the download endpoint; no substitute weights are used.
This is not evidence that all runtime timing instability has been eliminated.

NOT VERIFIED: loaded M5 revision, STT/TTS/PCM, interruptions, acoustic warmth,
blind listener ratings, Core end-to-end acceptance or competitor superiority.
The composer still has bounded wording and conservative abstentions; this does
not establish unrestricted human conversation or million-user capacity.

NEXT GATE: install the exact CI-verified source on M5 via the existing handoff,
then capture a CallActor/FreeSWITCH call with audio, runtime truth and trace.
