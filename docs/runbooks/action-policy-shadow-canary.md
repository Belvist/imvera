# ActionPolicy Shadow plumbing canary runbook

**Purpose:** verify telemetry plumbing only — not v7 quality / cutover.

**Forbidden:** soft/hard cutover; 100-call acceptance on v7.

## Runtime config

```bash
# Default / safe
export IMVERA_ACTION_POLICY_MODE=off

# Plumbing canary only
export IMVERA_ACTION_POLICY_MODE=shadow
```

Unknown values fail-safe to `off`.

Runtime truth must show:

```text
action_policy.mode
action_policy.policy_version=action-policy-phase1-v8
action_policy.frozen_policy_sha=c0fa158bd2ffb4109d1f0776c3b3245cdff31ce4
action_policy.decision_scope=conversation_scheduler
action_policy.cutover_enabled=false
```

For M1.2 plumbing-only canary on older image still pinning v7, expect v7 SHA instead — do not treat v7 as cutover candidate.

## Kill switch (no redeploy)

```bash
export IMVERA_ACTION_POLICY_MODE=off
# restart voice workers / reload env per deployment process
```

## Deploy sequence

1. Deploy PR #10 M1.2+ with `MODE=off`
2. Confirm normal calls (answer → scenario → goodbye)
3. Enable `MODE=shadow` for lab/controlled traffic only
4. Target: **5–10 completed calls**, **30–100** `ACTION_POLICY_SHADOW` events
5. Set `MODE=off` again

## SQL / event checks (adjust to your store)

Look for event types:

- `ACTION_POLICY_SHADOW`
- `ACTION_POLICY_SHADOW_HEALTH`

Per completed call health payload must include:

```text
records_produced
records_persisted
retry_count
persist_failed_count
dropped_count
buffer_remaining
telemetry_health
telemetry_complete
```

Complete evidence requires:

```text
produced == persisted
dropped == 0
buffer_remaining == 0
telemetry_complete == true
```

Incomplete telemetry calls are **not** cutover evidence.

## Known v7 signal (expected if pending appears)

If `pending_episode_attribute` lives through `build_policy_snapshot`, shadow may record:

```text
divergence_class=critical_pending_difference
critical_violation=true
cutover_eligible=false
```

That is a **policy** defect (v7), not a plumbing failure.

## Canary PASS / FAIL

PASS:
- speech still legacy-owned (`policy_influenced_output=false` always)
- no shadow exceptions / snapshot / persist failures
- health complete for finished calls
- correct SHA/version

FAIL → keep `MODE=off`, fix instrumentation, do not proceed to soft cutover.

## After PASS

Proceed to **ActionPolicy v8** (new freeze + live-builder challenge).  
Do **not** run 100/1000 acceptance on v7.
