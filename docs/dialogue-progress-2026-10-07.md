# Dialogue progress and next cut — 2026-10-07

Audited source **81f3272be67207581e55b7ba0b9a97e63dca2feb**, target
feature/voice-zoiper-m5. Main untouched. Read-only source/CI/report audit followed
by this metadata update; no deployed runtime changes.

## What is already in this tree

- Original-clause caller/relative ownership, quotes and unknown continuations,
  same SDK payload binding, owned-only clinical probes/recap, unique report
  correction. All10 implementation/test/gate hashes from the bbef evidence match.
- Earlier multi-complaint acknowledgement/progression, volunteered attributes,
  original evidence, unanswered values and six-episode carryover digest.
- Process-local shared replica cursor; independent adapters stop all selecting
  replica0 first. This is routing verification, not100 model-backed calls.
- Peer merged source with two help-affirmation regressions. New report
  [fs-844600d2](live-calls/fs-844600d2-help-yes-handoff.md) says old c8370aa
  bridge plain-closed after the elder affirmed needing help, current SDK hands
  off and bridge moved to ce1b95b. Actual after-restart audio/trace not available
  in this review. Spoken handoff is not proof of delivered family notification.
- Peer added exact voice/language/text PCM cache,64 entries; startup warmup
  bypasses it, and Darwin launchd adds --max-batch2. This reduces repeated
  synthesis work when hits occur, not a measured general response-speed gain.

## Actual verification

[bbef CI37327811889](https://github.com/Belvist/imvera/actions/runs/37327811889):
all11 jobs SUCCESS; full3429 PASS/0 FAIL/3 SKIP/237.71s, readiness63 PASS/7.47s.
[latest81f CI37555647610](https://github.com/Belvist/imvera/actions/runs/37555647610):
all11 jobs SUCCESS; full3433 PASS/0 FAIL/3 SKIP/204.87s, readiness63 PASS/7.79s.
Both full job logs include genuine LFS fetch. No fresh full suite run in this
metadata-only review; results are captured GitHub runs on the exact sources.
The20 ownership regressions and13-case/310-turn paired SDK evidence remain
[here](evaluation/implicit-subject-2026-10-05/README.md); delivery simulated.

## Why the conversation still feels like a questionnaire

1. coverage.covered_domains still scans aggregate lexical history/episode labels
   without requiring own domain evidence; medication_asked counts as coverage.
   Clinical sugar can look like nutrition; foreign sleep can count as own sleep
   even after ownership correctly blocks a personal clinical probe.
2. product.planner still chooses ordered family steps. Recognized meaning is not
   sufficient to change the natural priority of the next conversational move.
3. Existing DecisionRouter gives grounded personal threads ActionPolicy authority
   in all modes, but broad medical default remains MODE=off→legacy, with explicit
   cutover gate. Do not claim ActionPolicy is entirely inactive or flip a global
   switch before critical comparison and live proof.
4. One model-free canonical renderer still relies on deterministic realization;
   no constrained generative surface was enabled by this work. Optional model
   remains a separate ADR/benchmark decision, not assumed paid authorization.

## Next implementation cut

Replace aggregate lexical coverage with existing accepted own SlotRecord/typed
Observation/evidenced coverage records. Distinguish answered, unanswered, declined
from asked; protocol obligation is separate from evidence. Do not repair this with
a new food-word denylist or a second state writer. Preserve safety/control and
question refusal. Reproduce clinical sugar versus food, daughter's sleep versus
own sleep, all volunteered facts, and `А у меня всё нормально` after a foreign
story. Exact initial clinical question identity must remain grounded. Unknown
remains unknown; no unnecessary question solely to complete a data structure.

Then evolve the existing selector's legal moves/utility around unresolved user
question, current topic, genuinely needed health information, burden and continuity.
Preserve a single Reducer/EngineState; compare shadow/soft/policy changes with
explained critical divergences. Do not introduce a parallel scheduler or solve
free talk with another large phrase bank.

## Realtime and scale work alongside this cut

Audit new cache before scaling: cache-hit branch checks cancellation but bypasses
the synthesize_stream deadline enforcement; entry count is not a byte budget;
cache key omits resident backend/model revision; dict hits do not refresh eviction
order (FIFO, despite LRU docstring). These are source findings, not reproduced
production failures or measured throughput/RAM. Cancellation/fault tests, byte
budget/model identity and real burst/load measurements must accompany hardening.
--max-batch2 is a Darwin launcher setting, not a proved Linux100-call deployment.

Establish actual bridge/image/config/backend revisions before live acceptance;
repeat complete SDK scenarios through CallActor/FreeSWITCH with audio and raw
trace. Measure endpoint/STT/semantic queue/firstPCM separately, release p50<1s,
p95≤2s, and barge-in p95<250ms. Finally run target-server10→25→50→100 actual
model-backed calls with bursts, recovery and RSS/VRAM/queue metrics. Historical
GigaAM isolated1.889req/s/1.46GiB working-set and six assumed average-load CPU
replicas are planning inputs only. Total whole-stack and voice capacity unknown.

## Status

CHANGED: status/evidence/next-cut documentation only in this review.
VERIFIED: exact source GitHub jobs/log summaries and retained file hashes.
NOT VERIFIED: post-restart phone/audio, family notification delivery, target
latency/warmth, total model invocations/memory and100 admitted calls.
REMAINING RISKS: breathing wording `трудно дышать`, lexical coverage, positive
own return after a foreign story, unpunctuated references and cache boundaries.
NEXT GATE: grounded coverage cut with full exchanges and existing safety/state
gates, then heard audio/runtime-truth acceptance.
