# ADR-032: Grounded revisions and answered-question dispositions

Date: 2026-10-09
Status: source verified; v11 core frozen after exact-source CI; live acceptance NOT VERIFIED
Target: feature/voice-zoiper-m5, parent c1b3f1a35d41b78fd0ee7109ddbbe6efc0df04de

Verified source:4274a45149c46b2141cb5fe2d3e2dfce37b90cdc,
[CI37979468470](https://github.com/Belvist/imvera/actions/runs/37979468470):11/11 SUCCESS,
3647 PASS/0 FAIL/3 SKIP. Subsequent pin changes provenance/evidence only.

## Evidence and decision

The actual SDK retained positive sleep after an explicit correction and selected
an obsolete summary. The existing fact writer skipped filled fields; correction
speech could precede the new evidence. Re-admit current caller sleep/mood facts
through the same Reducer writer before response selection. Validate the literal
value, original quote, subject, asserted scope and source turn. Built-in mission
corrections use the same grounding boundary. Accepted new evidence reopens the
old summary; foreign/history/quote/question/conditional proposals cannot revise it.

The existing sleep topic owner must use current caller clauses, not whole-turn
words or another complaint's time anchor. Post-verbal poor sleep is a sleep
episode, not a general negative wellbeing assessment. No second writer or FSM.
Source replay exposed a second role error: the old contextual sleep matcher also
matched a pain/activity clock («пять часов»). Share its explicit sleep-report
predicate separately from bare contextual answers. A quantity with another
predicate cannot create/revise sleep; a bare quantity needs the sleep question.
The mission projection also honors an existing typed care record even when its
default goal lifecycle has not been synchronized. It cannot overwrite that record
as a fresh free-text answer.

Within-turn current pain restatements keep their sole immediately preceding
anatomical owner. The existing relation parser carries the degree/current
meaning, with its ambiguity/person/activity/negation/sentence-boundary guards.
Original kernel span/relations reach mention conversion: identical symptom words
cannot all use the first global occurrence. Compatibility proposals lacking
source spans need an unambiguous exact quote; absence is not a guessed location.

## Existing policy revision

Version the existing ActionPolicy as **v11 candidate**, retaining immutable v9
and v10 manifests and pins. Snapshot projects unanswered attributes separately
from known medical values. Temporal and status aliases share disposition. Unknown,
refusal and recorded temporal exhaustion exclude an ASK in the single canonical
legal set, including stale pending projections. They never become known facts.
The existing Reducer unavailable-answer writer accepts canonical local clinical
refusal as well as unknown recall. Its observation suffix and goal disposition
remain distinct; new facts, user questions and risk evidence are not swallowed.
Actions, scoring weights, safety/control precedence and authority scope stay the
same. The historical differential retains all ten core files and explicit
versions; `v9-current` replaces the outdated default comparison label. The older
`v9-v10` CLI label remains a compatibility alias.

Functional-impact questions now have their actual meaning in the existing product
renderer and a grounded literal answer path in existing issue memory. The heard
question supplies the referent, not evidence for the answer; a current caller
capability/activity predicate is still required. No medical judgement is inferred.
Literal «да/нет» may answer the heard functional yes/no question. Reducer carries
its delivered semantic need and episode in the existing turn-scoped receipt;
the writer never reconstructs that meaning from an intent name. Backchannels
and missing/cancelled delivery cannot authorize the value.

Global medical authority stays gated by the existing cutover switch. Candidate
is not a claim of deployment. Pin only after observing exact published source CI;
do not repin historical code merely to satisfy the hash guard.

## Urgent delivery truth and acceptance

Urgent canonical speech cannot promise family notification without receipt. Keep
the existing urgent signal/persistence path and provide a direct route to close
contacts and 112 when immediate help is needed. This does not implement Core
delivery, assert acceptance, or send a message from this development session.

Required source checks: adversarial revision/ownership/disposition tests, real
SDK delivered-question replay, existing medical/safety/stop/corpus/runtime gates,
whole-policy differential and full genuine-model CI. Five baseline medical topics
remain required in opt-in full check-in. No live generator/model/FSM is introduced.

Independent product gate: exact target bridge/image/profile/provider identity,
original CallActor/FreeSWITCH WAV+trace, cancelled and interrupted playback,
Core acceptance and test-recipient receipt, then full-call/load/listening gates.
Local text/controlled-PCM checks cannot certify those external boundaries.

## Long speech and report integrity

A long sleep narrative previously exceeded the 500-character FactCandidate value
limit before reaching the Reducer. Keep an original bounded sleep/plans fragment
with matching source offsets; do not truncate the entire semantic input. Oversized
contextual proposals cannot overwrite this canonical extraction. Explicit remote
sleep history is rejected by both typed daily facts and built-in goal adjudication.

The optional whole-turn polarity vote now abstains before model loading/forward
on input longer than that bound. Running a truncated classifier for several
seconds and then discarding its late output was neither grounding nor a fast path.
Literal reports and honest unknown polarity remain available; all model deadlines
and the genuine-model verification suite stay unchanged.

The Telegram demo cannot show GREEN on TECHNICAL/NO_CONTACT/unfinished calls and
does not log token-bearing exception strings. Its existing local ledger now
records individual transport acceptances with a process lock and atomic writes;
partial acceptance is incomplete, successful recipients are not resent on ordinary
retry, corrupt state blocks sending, and dry-run cannot persist acceptance. Tests
mock the transport; no external message was sent. Historical call-only markers
cannot prove old per-recipient delivery. This is not a production dispatcher:
Core acceptance and real per-recipient receipts remain external gates, and a crash
between Telegram acceptance and local persistence can still duplicate a retry.
