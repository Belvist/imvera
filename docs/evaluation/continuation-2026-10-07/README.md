# Open invitation and closing ownership

Target **feature/voice-zoiper-m5**, baseline
**c827d9dde92da9e4206b437842855f5af48c97d4**. Source changes, not deployed M5
acceptance. [Plan](../../plans/continuation-ownership-2026-10-07.md),
[before](before.json), [after](after.json), [paired runner](replay.py).

## First wrong decisions and replacement

Reducer's existing ITS consumer only understood decline/exclusive reference;
an admitted personal story still went into the legacy UNCLEAR branch. That
reserved ITS again and exhausted its question budget. One partial-close
continuation invitation could not save the following turns.

The same consumer now accepts a heard invitation's source-admitted personal
reply, releases the answered question and calls the same existing selector.
ActionPolicy owns continuation; Renderer realizes invite/listen. No new brain,
FSM, phrase bank, model/provider stage, live generator or global medical cutover.
The invitation flag does not satisfy medical/mission goals or assert health.
The bounded discourse ring remains literal conversation context.

SUMMARY previously reused summary_delivered even after accepting new facts.
Reducer now invalidates this completion scope when current-turn content is
actually admitted. Mission/SDK slot and routine coverage paths are included.
No summary is marked heard by this transition. New delivery must complete;
generation/revision/identity guards still reject the old completion and cancel.

Full-suite failures exposed boundaries that the focused cut did not yet cover:
an exclusive clinical reference was incorrectly offered as a story, and a
meal/medication report could consume the invitation as narrative. The existing
reference relation owner excludes clinical references from generic story
admission. The consumer uses the existing answer class and accepts narrative
only from UNCLEAR, not NEW_GROUNDED_INFORMATION. Old assertions stay intact.
Whole polite floor completion is not retained as a personal statement.

## Actual paired SDK exchanges

Both sides start with the same heard routine (wellness, food, medication,
mood, sleep) and the same open invitation. Delivery in these captures is
simulated; these are not transcripts of phone calls.

| User | Before | After |
|---|---|---|
| Вчера дочь приехала, мы смотрели фотографии. | Я вас слушаю. Если хотите, можете сказать, что ещё для вас сейчас важно. | Про дочь поняла. Расскажите, я слушаю. |
| Долго сидели и вспоминали дачу. | Про дачу поняла. Расскажите, я слушаю. | Поняла про дачу. |
| А потом пили чай и смеялись. | Спасибо, всё записала. До свидания. | Я вас слушаю. |
| Она рассказала про поездку к морю. | call already closed | Спасибо, что рассказали про поездку. |

All six substantive story turns now keep the call open. They add no health
question and do not fill plans or rewrite earlier health records. Explicit
topic completion returns to the existing summary/required-need owner.

After a heard summary, `Сегодня буду гулять.` previously emitted goodbye_final.
It now preserves the accepted plans record and emits a fresh summary. A story
after this summary re-enters listening. That refreshed phrase still says
«На сегодня всё»; this fixes state/closure, not ideal spoken transitions.

## Evidence boundaries and handoff

[Checks and exact commands](checks.json) contain source hashes, baseline/final
results, paired SDK timing and exact-source CI when available. Baseline12 FAIL /
14 PASS on the identical26 new tests; no missing new APIs account for failures.
The CallActor cases use actual SDK/outbox/playback/cancellation and controlled
PCM, not a real speech model or SIP transport. They cover heard/cancelled ITS
and summary, preservation of the previous heard question, and story admission.

Reproduce source capture:

```sh
python docs/evaluation/continuation-2026-10-07/replay.py /tmp/continuation.json --checkout .
python -m pytest tests/test_continuation_ownership.py -q
```

CHANGED: existing discourse/reducer/semantic invitation ownership, scope comment
and rich gate registration. VERIFIED: see checks. NOT VERIFIED: actual M5
loaded SHA/image/providers/flags, CallActor/FreeSWITCH real audio, human warmth,
end-of-speech→firstPCM, total model invocations and100-call capacity. Cloud has
no configured M5 secret/outbound identity; access information requested.
Available Linux TTS image is an HTTP adapter requiring a separately provisioned
Qwen speech server; it is not evidence of a usable resident voice model.

REMAINING RISKS: protocol minima/ordered optional routine questions remain;
open-question answers remain bounded rather than unrestricted human dialogue;
refreshed-summary wording and listening timing require heard acceptance.
The current-field/generic speech extraction limitations are not solved by this
change. SDK timing on shared cloud CPU does not establish target performance.

NEXT GATE: exact-revision target audio/trace. Integrating agent: fetch the m5
commit; confirm deployed image/source, endpoints and actual flags; follow
[existing launch/handoff](../../production-dialogue-handoff.md). During a safe
call window load the new bridge code, warm real providers, then record these
calls: story after ITS (>6 continuations), volunteered fact/story after summary,
critical symptom during story, refusal, explicit goodbye and mid-speech
interruption. Verify canonical speech against raw playback/STT/trace, pending
clinical needs, delivery identities and p50/p95 firstPCM. Do not replace these
calls with text replay, raise admission or announce full production acceptance.
