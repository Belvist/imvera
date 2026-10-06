# Implicit clinical subject ownership — 2026-10-05

Target feature/voice-zoiper-m5, baseline0abdc460f892498a3f025be2a2e74ab7d3acf532.
Source-bound synthetic SDK; no actual M5/audio/STT/TTS/image access established.
[Plan and journal](../../dialogue-and-capacity-plan-2026-10-05.md).
[Checks and source fingerprints](checks.json), [before](before.json), [after](after.json).

## Cause and replacement

Understand → kernel.resolve_subject → observation_memory → canonical RichUserTurn
→ Reducer/issue_memory/atomic projection → existing scheduler → ResponsePlan/renderer
→ CallActor/providers/playback. Kernel defaulted every implicit ISSUE clause to the
caller. Legacy merge separately considered only the quote, dropping discourse.
Scheduler/ack/summary treated unknown as caller. SDK payload could bypass binding.

Existing subject_resolver now binds issue positions in original clauses. After a
relative's clause, ambiguous continuation is UNKNOWN; explicit own reports and
anatomical contrastive returns remain. A conjunction alone after a relative
does not prove an implicit sleep complaint belongs to the caller. Additive return requires an earlier owned complaint.
Literal quoted words do not establish self reports. Existing legacy/payload binder
shares this owner; unique original quotes rebase filtered offsets, ambiguous
duplicate quotes abstain. No second brain/interpreter/scheduler/state writer.

Routine facts use clause scope whenever a foreign subject appears, even without
an explicit self marker elsewhere. Initial implicit own assessments retain their
existing interpretation. Whole-turn contextual/payload proposals cannot resurrect
foreign facts. Existing scheduler/ack/summary require a speaker subject. Unknown
reports remain recorded; explicit correction can resolve a unique inactive report
through existing issue_memory and receives a question-free acknowledgement.

## Actual paired examples

USER: Я чувствую себя хорошо. Дочь приехала. Плохо спала.
BEFORE: Плохой сон — записала, спасибо. А покушать сегодня уже успели?
AFTER: Рада это слышать. А покушать сегодня уже успели?

USER: Нет, я про дочь.
BEFORE: Про дочь поняла. Расскажите, я слушаю.
AFTER: Спасибо, что рассказали.

USER: Дочь рассказала: «У меня живот болит. Голова тоже болит».
BEFORE: Поняла вас. Головная боль и боль в животе — это неприятно,
давайте уточним по порядку. Когда это началось — сегодня или раньше?
AFTER: Про дочь поняла. А кроме этого — по самочувствию ничего не тревожит?

`Живот болит. Внук приезжал. А ещё спина.` retains both own complaints
and its original onset question. Explicit poor sleep, contrastive own headache,
three clinical complaints, canonical urgent and goodbye retain meaning.

## Evidence and limits

20 regressions assert ownership, original evidence, accepted facts, question need,
summary and correction. Previous existing assertions unchanged. On baseline:
13 FAIL/7 PASS (four missing new resolver APIs, nine behavioral failures).
Current20 PASS. Full/gates/CI results are recorded in checks and current-task.

Identical13 scenarios,31 user turns ×10 =310 SDK turns each. All playback completion
is simulated. Baseline p50/p95 2.397/4.854ms; after2.448/7.444ms on shared CPU while
other tests ran. This is not STT/NLP/phone latency or an acceleration claim.
Question-bearing turns21→20 in this small text set, solely a mechanical count;
not questions/minute, topic jump, human questionnaire-feel or a quality score.
No new provider/model stage; total live model invocation count NOT_MEASURED.

Unclosed: family-only then `А у меня всё нормально` still asks wellness repair;
`трудно дышать` still lacks accepted breathing handling in this replay (canonical
`Не могу дышать` stays urgent). Lexical coverage/ordered product minima still
control flow; arbitrary unpunctuated/implicit person/reference understanding is
not proved. Unknown ownership is not clinical resolution; Core's candidate/safety
projections remain unchanged. Multiple ambiguous reports cannot be corrected by
guessing one. Native quote STT has no punctuation guarantee. Phone acceptance,
end-of-speech→PCM and100 model-backed calls remain NOT_RUN.

## Integration and next gate

Use the same canonical SDK/CallActor builders; never set subject or reconstruct
caller facts from an entire mixed narrative in adapters. No new env flags, model
invocations or global ActionPolicy promotion. Keep production admission unchanged.
Update target bridge only after drain/runtime SHA/provider readiness verification;
this workspace performed no target restart/deployment. Compare own/foreign sleep,
quoted complaint, additive return, explicit correction, multi-complaint/stop/urgent
with actual recorded speech and delivered trace. Revert the source commit to roll
back; no schema migration. Grounded coverage and clinically approved breathing
wording are the next source gates, then real audio/latency/concurrent load.
