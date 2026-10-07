# Convenience-first conversation: grounded coverage cut

Target feature/voice-zoiper-m5, baseline ee92a719. Existing authoritative
EngineState/Reducer/scheduler/renderer retained; frozen ActionPolicy and
safety/control/consent are outside this source cut. This is an offline SDK
reproduction, not a diagnosis of the currently deployed M5 stack.

## Experience and boundaries

The person can supply several answers at once, continue their story, decline
one question or finish the call. Required information constrains legal actions;
it should not cause a question whose answer is already accepted. An invitation,
short reaction and listening pause are existing moves. No new brain or phrase
bank is needed for this cut. Full conversational quality still needs selector
continuity and actual audible timing/interruptions.

## Reproduced before production edits

`Мне хорошо. Сегодня поела, таблетки уже приняла.` currently has only wellbeing
and nutrition coverage, content count1, then asks the medication screen again.
`Мне хорошо. Сегодня не ела. Таблетки не принимаю.` does the same. Conversely,
clinical `Сахар сегодня высокий` counts as food, ambiguous daughter's sleep
counts as the caller's sleep, and medication_asked alone counts as answered.

## Existing owners and replacement

coverage.covered_domains/content_exchanges currently derive facts by rescanning
aggregate observation strings, topic clauses and episode labels. Replace that
read with accepted slot/coverage records, confirmed personal observations and
owned evidenced episodes. Delete displaced aggregate-text reader. Asked,
declined and unknown dispositions remain separate from known answers.

The scheduler's existing _apply_coverage_reply already writes source-attributable
nutrition records. Extend this writer for decisive volunteered medication
reports using the existing medication classifier and clause/subject/temporal
owners. Do not infer medication adherence or clinical polarity. Preserve the
conditional medication screen/today question when the answer is still needed.
No new model or provider call; bounded reads of existing state only.

## Acceptance and limits

Reproduce own3-fact/negative intake, clinical sugar, unknown/foreign/quoted/past
sleep/medication, correction/refusal/unknown, and existing personal listening.
Keep old safety/state assertions, full rich/kernel/runtime/corpus/policy gates.
Capture paired full SDK exchanges with simulated delivery; record exact source,
flags, timings and model-count limitations. This does not change protocol
minima, globally promote medical ActionPolicy, enable live generation, deploy
the target, measure100-call capacity or prove heard warmth.

## Scope correction after paired replay

Counting answered food/medication as additional check-slot exchanges advanced
ITS/summary earlier. The existing ITS-specific guard rejected an otherwise
grounded personal thread; repeated ITS prompts exhausted reservations and
partial-closed an engaged story. A separate late positive fact also reached
the already-delivered-summary close shortcut. This blocked a broad counter
migration; that proposed change was removed before publication. The existing
check-slot minimum remains, now excluding foreign/unknown/planner-only episodes.
No historical test assertion is changed to bless premature closure. Do not
claim that this cut removed the questionnaire or fixed the ITS/closing owners.

NEXT GATE: these source regressions and full gates, then migrate ITS/closing
obligation ownership with full conversation/delivery evidence before relaxing
check-slot minima. Then exact-revision
CallActor/FreeSWITCH audio+trace for volunteer/story/clinical interruption.
