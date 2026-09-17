# ADR-018: Stage 2 — Production Hardening of the Frozen Path

**Status:** proposed
**Date:** 2026-09-17
**Amends:** nothing. **Does not supersede** ADR-014 (freeze stays in force).
Works **inside** the ADR-013/014 frozen diagram.

## Context

Lab contour works (local SIP lab calls, 1494 passed / 17 baseline-failed, fail-safe
dialogue semantics proven offline). Nothing is accepted: ADR-014 gates 1–7 are
0/7. Two PSTN attempts are blocked outside code (VoxImplant 403 CallerID;
Novofon silently drops SIP from our IP). `mod_imvera_audio` sources are absent
from the checkout; lab runs on `mod_audio_stream` (forbidden as production
WRITE path). Cancelled generations still reach the wire
(`tests/test_downstream_cancel_gap.py` pins the defect). Core inbox and
result→status projection are not wired. No prod server, GPU, or monitoring.

## Decision

Stage 2 builds the production contour **without changing the frozen diagram**.
Five workstreams, in priority order:

### 1. Transport stop/ack + generation purge (M2 closure, gate 5 prerequisite)

- Contract: every downstream PCM chunk carries `generation_id`; bridge keeps a
  per-generation queue; `stop(generation_id)` purges unsent chunks and acks;
  in-flight chunk finishes (bounded ≤20ms), nothing from cancelled generations
  starts after ack.
- Implementation location undecided (see Alternatives): either obtain/write
  `mod_imvera_audio`, or implement stop/ack at the Python-bridge ↔ FreeSWITCH
  boundary with existing primitives (`uuid_break`, stream control).
- Barge-in stays OFF until this contract is proven by an offline regression
  (cancel → purge → ack → wire silence), then a live trace.

### 2. Core wiring: result → status → family (M3)

- Wire `CallResultSnapshot` → `packages/status/engine.py` resolver → Core inbox.
  No new verdict logic in voiseup: UNCLEAR stays PARTIAL, never GREEN;
  consent refusal only from explicit call-level refusal.
- Escalation channel (one pilot channel: TG bot) tested end-to-end.
- Family app pilot minimum: call list + 6 statuses + observations + consent state.

### 3. PSTN unblock (M4, owner actions first)

- VoxImplant: CallerID verification in panel → relaunch scenario.
- Novofon: enable external SIP for employee 0144031 in cabinet
  («ВАТС и данные стороннего оборудования») + outgoing allowed + balance.
- Then: rented number / trunk with failover documented.

### 4. Deploy target (gate 7)

- Linux + GPU server (BM Ryzen 9950X/128/2TB + RTX 5090 assessed: 20–30
  comfortable concurrent calls, 40–60 ceiling; pilot peak is single digits).
- Pinned images, compose deploy, auto-restart, Postgres, recording retention,
  centralized logs, metrics + alerts + on-call runbook.

### 5. Gates 1–6 evidence

- 100 consecutive full calls on the frozen path; scenario/latency/reliability/
  failure drills per ADR-014. No acceptance label before evidence.

## Consequences

- No new dialogue brain, no provider swaps (GigaAM + Silero stay), no new
  scenarios beyond daily-check until gates 1–3 pass.
- `mod_audio_stream` remains lab-only. If it must serve Stage 2 temporarily,
  that needs an explicit ADR amendment — not a silent slide.
- Every workstream ends with a trace/log proof, not green unit tests.

## Alternatives Considered

| Option | Verdict |
|--------|---------|
| Write `mod_imvera_audio` from scratch | Consider — needs C/FreeSWITCH expertise estimate |
| Stop/ack at Python-bridge boundary with existing FS primitives | **Investigate first** — cheapest if primitives suffice |
| Cloud STT/TTS for speed | **Reject** — forbidden by ADR-014, silent-fallback risk |
| 500-concurrent architecture now | **Reject** — pilot needs single digits; revisit post-pilot |
| Merge stale Asterisk-era branches | **Reject** — done cleanup 2026-09-17, branches deleted |

## Verification status

| Claim | Status |
|-------|--------|
| ADR-018 proposed | CHANGED (this file) |
| Any Stage 2 workstream complete | **NOT VERIFIED** |
