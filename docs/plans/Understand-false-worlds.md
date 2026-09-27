# Understand — false-worlds map (pilot closed)

Date: 2026-09-27 (~04:35 MSK). HEAD baseline `1c2365f` closes rows 3–6; dream≠pain `2e515bc`.
Law: `docs/OPERATING_BRIEF.md`, ADR-021 CDK. **Acts > phrases.**

## Purpose

Closed pilot map of **frames that must NOT become health complaints**
(no `ISSUE_SITE`, no pain/onset/severity/site probes, no `wellness_concern`
from the framed utterance, no summary «сегодня беспокоили …»).

Prefer one closed Act + YAML effects / mention suppress. New Russian
wordings = examples of the same frame, not new `if` in policy.

## Priority (normalize_act)

`DECLINE` > non-complaint frames (`SIDE_TOPIC` / suppress) > `ISSUE_SITE` >
`ISSUE_SEVERITY_ANSWER` > `WELLNESS_SO_SO` > `WELLNESS_OK`.

Real present-tense **speaker** complaint pivots still fall through to
`ISSUE_SITE` (e.g. «После фильма голова разболелась»).

## Frame table

| # | Frame | Act | Forbids (YAML / effect) | Example utterances (RU) | Gate scenario | Status |
|---|---|---|---|---|---|---|
| 1 | Dream / sleep narrative | `SIDE_TOPIC` | pain/concern via mention suppress (YAML `SIDE_TOPIC` forbids still empty) | «Сталина во сне видела. Приходил ко мне руку тянул.»; «Снилось, что нога отнялась.» | `dream_hand_stalin` (+ `dream_narrative_gate`) | **DONE** `2e515bc` / fs-80cf029f |
| 2 | Film / book / TV fiction | `SIDE_TOPIC` (+ movie defuse belt) | same class as dream; no RED from «умирали» in film | «Смотрела фильм, там все умирали.»; «В книге герой умирал от рака.»; «В сериале все болели.» | `movie_dying` | **DONE** (hard-battery PASS; same `is_narrative_fiction_frame`) |
| 3 | Third-party illness (чужой) | `SIDE_TOPIC` (or speaker-slice only) | `pain_site_probe`, `concern_probe` for other-only turns; never write speaker episode | «У внука голова болит сильно.»; «У мужа голова болит.»; «Это не у меня, у дочери живот болит.» | `third_party_pain` | **DONE** `1c2365f` — other-person frame + mention suppress; bare relative noun alone is companion, not patient |
| 4 | Joke / hyperbole | `SIDE_TOPIC` (or `DECLINE` if explicit «шучу / не болит») | no urgent/RED, no onset from joke death/pain | «Да я сейчас умру от смеха.»; «Голова раскалывается — шучу конечно.»; «Хоть вешайся, шутка.» | `joke_hyperbole` | **DONE** `1c2365f` — joke/hyperbole → `SIDE_TOPIC`; explicit «шучу / не болит» still `DECLINE` via priority |
| 5 | Past tense «раньше болело» vs current | non-complaint when **past+resolved / explicit non-current** (`SIDE_TOPIC` / decline path); **not** active `ISSUE_SITE` | no onset/site for past-resolved; summary must not «сегодня беспокоили» | «Раньше болела голова, сейчас всё хорошо.»; «Голова болела раньше, сейчас нормально.»; «Позавчера болело, сегодня норм.» | `past_pain_resolved` | **DONE** `1c2365f` — intentional: bare past alone (e.g. «Раньше болело.» / «Вчера ухо заложило.») is **NOT** a false world — needs explicit non-current/resolved; only past-resolved is suppressed |
| 6 | Side topic / off-protocol chatter | `SIDE_TOPIC` | no wellness_concern, no pain probes | «Суп сегодня вкусный был, борщ варила.»; «Внуки приезжали вчера.» (no symptom) | `side_topic_chatter` | **DONE** `1c2365f` — `is_side_topic_chatter` → `SIDE_TOPIC` when no symptom language |
| 7 | Explicit decline / negated pain | `DECLINE` | `pain_site_probe`, `concern_probe`; clear open_probe | «Ничего не болит, всё хорошо.»; «Меня ничего не беспокоит сегодня.»; «Да нет, ничего не болит.» | `decline_*` / `false_red_negation` / `new_decline_phrase` | **DONE** `c8b385c` + `209fdb0` |
| 8 | `WELLNESS_SO_SO` without site | `WELLNESS_SO_SO` | must **not** become `ISSUE_SITE` / onset; soft clarify_wellness at most once; YAML forbids still `[]` | «Более-менее.»; «Так себе сегодня.»; «Средне.» | `so_so_then_decline` (decline leg); unit state×text→act | **DONE** act split (`f21ed85`); soft clarify OK — do **not** invent site from so-so |

## Proof notes (Layer A probes, 2026-09-27)

| Utterance | Observed (post-`1c2365f`) | Wanted |
|---|---|---|
| dream / film / book | `SIDE_TOPIC`, mentions `()` | keep |
| «У внука/мужа голова болит» | `SIDE_TOPIC` / suppress mentions | keep |
| «Раньше болела голова, сейчас всё хорошо» | past-resolved → non-complaint (`SIDE_TOPIC` / decline) | keep |
| «Раньше болело.» (bare past, no resolved) | grounding kept; **not** suppressed (intentional) | keep — only past-resolved is a false world |
| «Более-менее» / «Так себе» | `WELLNESS_SO_SO`, no episode | keep |
| «Ничего не болит…» | `DECLINE` | keep |

## Out of scope (this map)

- Phrase banks / Character / PSTN / `max_active_calls` / OTel
- Real speaker complaint after pivot («а сейчас голова болит»)
- CDK redesign beyond false-world Understand frames

## NEXT

Rows 3–6 closed in `1c2365f` (shared non-complaint frame → act + suppress +
gates; hard-battery scenarios included). Remaining hygiene: keep map in sync
with HEAD; no further false-world classes on this pilot.map.

Intentional rule (do not «fix»): bare past alone is **not** a false world —
suppression needs explicit non-current/resolved. Real present pivots after
past («а сейчас голова болит») still fall through to `ISSUE_SITE`.
