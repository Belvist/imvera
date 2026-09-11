# ActionPolicy production operability runbook

Kill switch and rollback without code redeploy (env reload / worker restart per platform).

## Runtime truth (must log at worker start)

```text
action_policy.mode
action_policy.mode_raw
action_policy.cutover_enabled
action_policy.soft_percent
action_policy.policy_version          # action-policy-phase1-v8
action_policy.frozen_policy_sha       # c0fa158bd2ffb4109d1f0776c3b3245cdff31ce4
action_policy.decision_scope          # conversation_scheduler
deployment / git SHA
```

## Kill switch → legacy (no redeploy of image if env hot-reloadable)

```bash
# Immediate safe mode
export IMVERA_ACTION_POLICY_MODE=off
# or
export IMVERA_ACTION_POLICY_MODE=legacy

# Also disable soft/policy even if MODE left on soft/policy:
export IMVERA_ACTION_POLICY_CUTOVER_ENABLED=0
```

Reload/restart voice workers so env is picked up.

## Enable shadow (plumbing / acceptance)

```bash
export IMVERA_ACTION_POLICY_MODE=shadow
# CUTOVER must stay off
export IMVERA_ACTION_POLICY_CUTOVER_ENABLED=0
```

## Soft cohort (only after real shadow hard gate)

```bash
export IMVERA_ACTION_POLICY_CUTOVER_ENABLED=1
export IMVERA_ACTION_POLICY_MODE=soft
export IMVERA_ACTION_POLICY_SOFT_PERCENT=1   # then 5, 10, …
```

Never percentage outer-guard turns — they never enter DecisionRouter.

## Full policy mode (after soft stabilization)

```bash
export IMVERA_ACTION_POLICY_CUTOVER_ENABLED=1
export IMVERA_ACTION_POLICY_MODE=policy
```

## Find policy / shadow errors

Event types:

- `ACTION_POLICY_SHADOW` — per scheduler decision
- `ACTION_POLICY_SHADOW_HEALTH` — per completed call

Useful filters:

```text
shadow_status=error
critical_violation=true
policy_constraint_violation
authoritative_fallback_legacy
policy_influenced_output=true|false
divergence_class=unclassified
telemetry_complete=false
frozen_policy_sha != expected
```

## Incomplete telemetry

`telemetry_complete` requires:

```text
produced == persisted
AND dropped == 0
AND buffer_remaining == 0
```

Incomplete calls are **not** acceptance evidence.

## Pending obligation violations

Look for:

```text
critical_violation_flags contains critical_pending_discard
divergence_class=critical_pending_difference
```

v7 expected this under live pending; v8 must be 0 on acceptance evidence.

## Rollback deployment

1. Env kill switch to `MODE=off` / `CUTOVER_ENABLED=0`
2. If image is bad: redeploy previous voice image SHA
3. Confirm runtime truth shows legacy + expected frozen SHA (or N/A when off)

## Do not

- Soft/policy cutover on v7
- Count outer-guard turns as ActionPolicy evaluations
- Use incomplete telemetry as gate evidence
- Claim FULL PROD VERIFIED from unit tests alone
