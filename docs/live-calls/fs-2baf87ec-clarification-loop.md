# Live call fs-2baf87ec (2026-10-01 11:40 MSK) — strange clarification loop

Owner dialed 7000 after the SIP re-reg. Transcript below is verbatim from
`.run/traces/fs-2baf87ec.jsonl` (216 events, `renderer.phrase_ready` /
`stt.final`). Bridge 04cf7ba. Please reproduce via ScenarioRunner before
patching; do not weaken the pinned ideal-call tests.

## Transcript

1. VERA: Здравствуйте. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
2. USER: Я чувствую себя хорошо.
3. VERA: Как сегодня с едой — нормально поели?
4. USER: Ой, поел нормально? Вот у меня что-то голова болит и руки ноют.
5. VERA: Хорошо. Рука ноют — когда появилась эта боль — сегодня или раньше?
6. USER: Это уже две недели продолжается так.
7. VERA: Жалобы есть какие?
8. USER: Жалобы, руки постоянно трясутся и кровят.
9. VERA: Что именно беспокоит?
10. USER: Конкретнись и по поводу первого.
11. VERA: Хорошо. Что-то ещё хотите сказать?
12. USER: Нет.
13. VERA: Спасибо, Тамара Юрьевна. Я записала: головная боль и рука ноют. На сегодня всё. Берегите себя.

## Defects (owner-visible)

D1. Clarification loop after an answered probe (turns 6–9). The duration
answer produced zero grounded output (verified: `build_rich_turn_from_text`
on turn 6 yields no mentions and no facts), so the onset probe could not
advance and the ladder fell back to «Жалобы есть какие?» then «Что именно
беспокоит?» — asking for a transcription of what was already said.
Out-of-order DURATION is discarded; only out-of-order severity is kept
(`_record_out_of_order_value`, severity-only by design). Suspected owner:
pending-attribute consumer for the episode onset/duration path.
Expected: «две недели» lands as duration evidence, next step is severity
or ITS — never a re-ask of the complaint.

D2. Broken agreement out loud (turns 5, 13): «Рука ноют». The generic
rule built label `рука ноют` (singularized site + raw plural verb) and
the ack/summary spoke it verbatim. Suspected owner: label construction
in `issue_mention_extract._GENERIC_BODY_PAIN` branch
(`f"{site} {_agree_verb(site)}"` vs raw verb). Expected: «Руки ноют»
(or the canonical «боль в руках» shape the ack bank already uses).

D3. Doubled mentions for one clause (turn 4 → 4 mentions: `голова болит`
+ `головная боль` + `рука ноют` + `руки болят`). Per-site rules and the
generic fallback both fire. Suspected owner: missing dedup between the
specific rules and `_GENERIC_BODY_PAIN`. Expected: one mention per
site per clause.

D4. Tremor lost (turn 8): «руки постоянно трясутся и кровят» yields zero
mentions — `тряс*` is in no verb list (`дрож\w*` does not cover it), and
`кровят` (possibly STT for `крутят`/`болят` — uncertain) is uncovered too.
Expected at minimum: tremor grounds as a mention; STT-uncertain words
must never silently vanish (record unknown explicitly per the find-out
ladder contract).

## Pointers (verified, not guesses)

- Turn 6 → `([], [])` (mentions, facts); turn 8 → `([], [])`.
- Turn 4 → 4 mentions listed above (labels/sites/kinds).
- Summary spoke the broken label verbatim (turn 13), so the ack/summary
  path has no agreement guard — transport never rewrites, renderer owns it.
- Gates on 04cf7ba were green (full 2084/0, corpus 500/500); these are
  live-only gaps the offline batteries did not cover.

## Suggested verification (not a prescription)

- ScenarioRunner replay of turns 1–13 asserting: duration evidence after
  turn 6, no `probe_concern`/`clarify` after a grounded duration, single
  mention per site for turn 4, tremor mention for turn 8, agreement-clean
  ack/summary strings.
- Full gates after the fix (suite + corpus + hard1000 + battery), bridge
 Historical note: our local battery (54 phrases) covers single-clause
  complaints; multi-clause + duration-out-of-order + agreement are the
  holes this call exposed.
