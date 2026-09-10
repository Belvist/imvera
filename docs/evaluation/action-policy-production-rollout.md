# ActionPolicy production rollout evidence

Living changelog. Do not claim VERIFIED for production without real-call evidence.

Statuses:

| Status | Meaning |
|--------|---------|
| CODE READY | Code + CI gates green |
| STAGING READY | Deploy artifacts/runbook ready for operator |
| SHADOW VERIFIED | Real shadow canary/acceptance evidence |
| SOFT ROLLOUT VERIFIED | Soft cohort evidence |
| FULL PROD VERIFIED | mode=policy stable with kill switch |

---

## Phase 1 — Shadow M1.2 (scheduler instrumentation)

**decision:** continue on PR #10 (`feature/action-policy-shadow-m1`)

### Targets
- Lightweight transport (`action_policy_shadow_buffer.py`) — session/engine never import heavy evaluator
- Persist ImportError as `ACTION_POLICY_SHADOW`
- Persist `ACTION_POLICY_SHADOW_HEALTH` at call finalize
- Privacy-safe structural fingerprint
- Latency split: `policy_choose_latency_ms` / `shadow_total_latency_ms`
- Live outer-guard coverage (control/repair/closing/timer/backchannel)
- `divergence_class=unclassified` ⇒ `cutover_eligible=false`
- Frozen v7 unchanged

### Evidence
| Field | Value |
|-------|-------|
| phase | M1.2 |
| commit SHA | `886b028c9d787e7234ed0cbe009991a382ea3156` |
| CI run | [34539222747](https://github.com/Belvist/imvera/actions/runs/34539222747) success |
| tests | CI full pytest **1088 passed, 4 skipped**; `action-policy-shadow` green |
| frozen diff | empty vs `61e17934…` on M1.2 commit |
| decision | **M1.2 CODE READY** |
| next gate | Phase 2 short plumbing canary (operator) |

**v7 cutover candidate:** NO (pending/repeat P0 remains)

---

## Phase 2 — Short plumbing canary

**NOT a quality gate for v7.** Plumbing only.

### Operator sequence
1. Deploy code with `IMVERA_ACTION_POLICY_MODE=off`
2. Run a few normal voice calls
3. Set `IMVERA_ACTION_POLICY_MODE=shadow` for controlled cohort
4. Collect 5–10 calls / 30–100 scheduler decisions
5. Return `MODE=off`

### Canary PASS criteria
- `policy_influenced_output=0`
- shadow exceptions / snapshot errors / persistence errors = 0
- `produced == persisted`, `dropped=0`, `buffer_remaining=0`
- `ACTION_POLICY_SHADOW_HEALTH` present on completed calls
- correct `frozen_policy_sha` / `policy_version`
- known v7 pending defect may appear in telemetry (not instrumentation failure)

### Evidence
| Field | Value |
|-------|-------|
| phase | canary |
| status | **READY FOR OPERATOR DEPLOY** |
| runbook | `docs/runbooks/action-policy-shadow-canary.md` |
| real-call evidence | **NOT VERIFIED** (no production access in agent session) |
| decision | do not start 100/1000 on v7; operator runs canary |
| next gate | Phase 3 ActionPolicy v8 (code started in parallel) |

---

## Phase 3 — ActionPolicy v8 (in progress)

Branch: `feature/action-policy-v8`

### Semantic change
- Separate `last_delivered_question_need` from `pending_episode_attribute`
- Live `build_policy_snapshot` no longer copies pending into delivered need
- `repeat_question` cannot eliminate hard pending obligation candidate

### Evidence
| Field | Value |
|-------|-------|
| phase | v8 implementation |
| freeze | not yet (COMMIT A only) |
| challenge | forbidden until freeze |
| next gate | CI green on v8 → freeze manifest (COMMIT B) → independent challenge |

---

## Current overall readiness

| Status | State |
|--------|-------|
| CODE READY | Shadow M1.2 YES; v8 candidate in progress |
| STAGING READY | Canary runbook YES — awaiting operator |
| SHADOW VERIFIED | NOT VERIFIED (no real calls) |
| SOFT ROLLOUT VERIFIED | NOT VERIFIED |
| FULL PROD VERIFIED | NOT VERIFIED |
