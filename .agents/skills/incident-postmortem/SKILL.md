---
name: incident-postmortem
description: Analyze production or pilot incidents with blameless root cause and action items. Use after call failures, false alerts, or outages.
---

# Incident Postmortem

## Trigger

- Wrong status shown to family (false GREEN / missed RED)
- Mass NO_CONTACT or TECHNICAL
- Audio one-way / silent Vera
- Secret leak or data exposure
- Pilot user-reported failure

## Timeline (required)

```text
T+0  first symptom (who noticed)
T+?  detection method (alert / user / log)
T+?  mitigation applied
T+?  full resolution
```

## Analysis Sections

### Impact

- calls affected (count, call_ids)
- families affected
- duration
- data integrity (recordings lost? wrong verdict persisted?)

### Root Cause

Use `debug-root-cause` chain. One primary root cause.

### Contributing Factors

- missing gate, config drift, provider outage, etc.

### What Went Well / Poorly

### Action Items

| Action | Owner | Priority | Due |
|--------|-------|----------|-----|
| regression test | | P0 | |
| runbook update | | P1 | |

## VoiseUp-Specific Checks

- Was runtime truth captured at incident time?
- Did voiseup set verdict locally (violation)?
- canonical text vs played audio mismatch?
- generation_id stale playback?
- trunk vs app failure (NO_CONTACT vs TECHNICAL correct?)

## Storage

`docs/incidents/YYYY-MM-DD-short-title.md`

Blameless tone. Facts and artifacts, not names.

## Output

Postmortem doc + linked regression tests + ADR if architecture change needed.
