# Grounded routine coverage — 2026-10-07

Target feature/voice-zoiper-m5; baseline ee92a719. No main source changes or
target deployment. [Plan and counter-migration blocker](../../plans/grounded-coverage-2026-10-07.md).

## Changed owner, same live path

Understand → canonical RichUserTurn → Reducer/EngineState → existing scheduler
→ ResponsePlan/renderer → CallActor. The scheduler's existing routine-answer
writer now retains decisive volunteered medication evidence, alongside food.
coverage.covered_domains reads accepted slot/coverage records, confirmed own
mission observations and evidenced own current episodes. Aggregate lexical
history reader _all_user_text was removed. Asked is not answered; unknown and
declined dispositions remain separate. Negative intake is known negative
information, not a positive outcome. Medication records do not claim adherence.

Original-clause speaker ownership is shared with goal extraction for food,
medication and domain relevance. Family continuations, quotes, past events,
conditional/future/uncertain intake cannot fill today's personal record.
The existing uncertainty owner recognizes kernel's `вроде`/`может быть` cues,
including a separate cue clause. No new phrase pool or model/provider stage.

## Actual SDK exchanges

Same input, source-bound [before](before.json)/[after](after.json); simulated
audible completion, not phone/audio evidence:

> USER: Мне хорошо. Сегодня поела, таблетки уже приняла.
>
> BEFORE: Хорошо, что поели. Есть ли у вас лекарства, которые вы обычно принимаете?
>
> AFTER: Хорошо, что поели. А какое у вас сегодня настроение?

The redundant medication screen is gone. The mood question remains: this cut
does not remove the existing check-item minimum or establish unrestricted talk.

> USER: Вчера дочь приехала, мы смотрели фотографии.
>
> VERA: Про дочь поняла. Расскажите, я слушаю.
>
> USER: Долго сидели и вспоминали дачу.
>
> VERA: Поняла про дачу.
>
> USER: А потом пили чай и смеялись.
>
> VERA: Я вас слушаю.

This existing listening path remains available after the corrected fact intake.
It is not a newly invented transcript or proof of perceived warmth. Foreign
sleep/food no longer satisfy personal coverage, and clinical sugar does not
stand in for eating. Canonical urgent/goodbye speech in these replays is unchanged.

## Checks

Exact commands and source/model provenance: [checks.json](checks.json).
New36 regressions: baseline13 FAIL/23 PASS; final36 PASS. No historical assertion
changed, deleted or skipped. Rich898 PASS, kernel294 PASS, corpus500/500 plus8
gate tests; policy diff12 expected/0 unexplained; repository Ruff/whitespace PASS.
Full/model/CI results are recorded separately in checks rather than inferred.

Paired14 synthetic scenarios,260 SDK turns each. Source fingerprints pin runtime
bytes even though the after capture's HEAD names its precommit parent. The
baseline worktree is dirty only because the new regression file was copied in;
baseline runtime fingerprints match ee92a719. SDK timings are process-local
cloud CPU measurements under shared load; no phone-speed gain or100-call
capacity claim. End-of-speech→PCM, listener ratings and real model invocation
counts remain NOT_RUN/NOT_MEASURED. No extra model stage was added by this code.

## Handoff and remaining work

Deploy the exact tested m5 revision through the existing bridge deployment
procedure and record the loaded revision/providers/flags. No new switch is
required. Transport/TTS must receive the canonical engine text unchanged.
Do not enable global medical ActionPolicy or generation, repin the frozen
manifest or raise admission on the strength of this coverage correction.

A broad trial counting food/medication as check exchanges was removed: earlier
ITS entry exposed a specific-question guard and repeated-prompt reservation
close while the person continued a story. Late positive content after heard
summary exposed a second closing shortcut. Keep these as a separate obligation
migration with recorded before/after delivery events; do not bless it by editing
old exact-intent expectations. Plain medication habit still does not complete
today's status and may be screened again. Existing ordered clinical packs,
check minima, deterministic surface and arbitrary ASR ambiguities remain.

NEXT GATE: migrate ITS/summary/listening ownership so a substantive story keeps
the floor and new information cannot be mistaken for completion. Then reduce
optional questioning and validate on a real CallActor/FreeSWITCH recording with
raw trace, interruptions, latency and listeners. Text tests alone do not accept
the product's human conversational quality.
