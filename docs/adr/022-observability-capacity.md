# ADR-022: Operating Law — Observability Tiers & Capacity Doctrine

Date: 2026-09-26
Status: proposed

## Context

Dialogue is now cheap and deterministic (CDK, ADR-021), but the lab
still thinks as "one laptop + full forensic per call". Measured on live
call fs-5b509b4f: 222 events / 63 KB JSONL, of which 171 × `stage.timing`.
At 50 concurrent that is CPU on `json.dumps`, disk, and silent queue
drops killing exactly the investigations we need. `max_active_calls: 1`
is declared in YAML but not enforced in code — the ceiling was never
measured. Scale plans so far are hardware braces without an operating
law; ADR-014 gates stay open while features grow.

## Decision (the Operating Law, one page)

1. One state writer: `dialogue_engine.reducer`.
2. Vera speaks only PhraseSelect / banks. LLM out of the speech path.
3. Protocol GREEN/YELLOW/RED is ONE table (P1: YAML — short/full/complaint
   → required slots → status impact). Until then: `21c61be` mode rule
   (required-ness follows check-in mode) is the law; mission goals +
   FILLER_ORDER + StatusEngine must not contradict it.
4. Observability tiers, enforced by env `IMVERA_OBS_MODE`:
   - `debug` (lab, 1–3 calls): everything — full JSONL, STT dumps,
     forensic wav. Goal: any bug reproducible by `call_id` in 5 minutes.
   - `pilot` (5–30 elders): all events EXCEPT chatty stage timings;
     errors/degradations always; full JSONL only for RED/TECHNICAL,
     status≠expected, 5–10% sample, or per-elder debug flag (flag
     mechanism: future slice, not this ADR).
   - `prod` (load): only error/degraded/completion events + one
     structured line per turn + time-series metrics. Full trace only
     on incident budget.
5. Hot path never waits on disk for debugging. Debugging is bought with
   budget, never "always everything". Drops are never silent:
   `dropped_events` + queue depth are exposed in `/health` and alerts.
6. Scale = replicate the frozen path: N bridge workers + sticky
   `call_id`/`fs_uuid` + STT/TTS replica pools + PG pool. Never a fourth
   dialogue brain, never prompt-smart scaling, never silent cloud STT.
7. Acceptance is a live artifact (call + metrics), never a pytest count.

## Consequences

- `record_event` filters by tier + event class (chatty/error); default
  stays `debug` so lab behavior is unchanged until ops flips the env.
- `/health/ready` exposes trace queue depth + dropped count.
- Capacity floors (honest): lab 1 call/DEBUG; pilot 5–10/PILOT+PSTN;
  single GPU box 15–30 comfort/PROD metrics; two GPU ~50–80; 100+ only
  after a measured probe (separate ADR with evidence, not here).
- `max_active_calls` stays 1 until the capacity probe measures the real
  ceiling on current hardware; raising it blind is forbidden.

## Alternatives Considered

- OTel/Loki/ClickHouse now: deferred — tiers first, sinks when PILOT
  volume justifies them (JSONL per tier until then).
- Per-call 32KB forensic budget with truncation counter: accepted as a
  follow-up slice (metric `trace_truncated_total`).
- 100k design: explicitly out of scope (ADR-018 stands).

## Verification

- Tier unit tests (chatty dropped in pilot/prod, errors kept everywhere).
- Live 1-call DEBUG trace unchanged byte-for-byte in shape.
- `/health` shows trace stats; drop counter alertable.
