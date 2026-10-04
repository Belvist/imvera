# Live call fs-fd317c1c (2026-10-04, ~1 min) — multi-complaint + memory write

Verbatim from `.run/traces/fs-fd317c1c.jsonl` (120 events). Every claim
below verified against trace + PostgreSQL row.

## What was said, exactly

1. VERA: Здравствуйте. Это сервис Амвера. Тамара Юрьевна, как себя чувствуете сегодня?
2. USER: Плохо.
3. VERA: Сочувствую. Где болит или что тревожит?
4. USER: Рука болит опухла, что-то давление ещё, и этот сахар поднялся.
5. VERA: Жаль, что рука болит. Когда появилась эта боль — сегодня или раньше?
6. USER: Понятно. В 12 вроде.
7. VERA: Я вас слушаю. Когда появилась эта боль — сегодня или раньше?
8. USER: Не знаю, как будто бы в 12:00 сегодня.
9. VERA: Спасибо, Тамара Юрьевна. Я записала: рука болит, давление и сахар. На сегодня всё. Берегите себя.

## Verified (trace + DB)

- One turn, three complaints grounded: arm pain + swollen, pressure,
  sugar. Summary speaks all three, verbatim.
- Hedged onset («Не знаю, как будто бы в 12:00 сегодня») accepted as
  onset evidence — no second re-ask, no loop. The turn-7 repeat carries
  a «Я вас слушаю» prefix (repair, not a byte-identical echo).
- Empathy on «Плохо» («Сочувствую»), no false cheer.
- Persisted: `past_episodes = "рука болит@рука:open | давление:open"`,
  `symptom_followup = "давление"`, full concern quote. Next call will
  open with the pressure follow-up. Outcomes: COMPLETED / YELLOW.
- No errors, trace intact. One slow engine turn (p95 5721 ms).

## Honest gaps (seen, not hidden)

- Sugar did not fit the 2-slot digest (arm + pressure kept) — spoken in
  summary and stored in the concern quote, but no dedicated carryover.
- Turn 6 («Понятно. В 12 вроде.») needed one repair round-trip; the
  hedged form only landed on the second try.

## Verdict

Correct multi-complaint handling with working cross-call memory write.
