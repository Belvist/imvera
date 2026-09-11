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

### Evidence
| Field | Value |
|-------|-------|
| phase | canary |
| status | **READY FOR OPERATOR DEPLOY** |
| runbook | `docs/runbooks/action-policy-shadow-canary.md` |
| real-call evidence | **NOT VERIFIED** (no production access in agent session) |
| decision | do not start 100/1000 on v7; operator runs canary |
| next gate | Phase 3 ActionPolicy v8 |

---

## Phase 3–5 — ActionPolicy v8 + freeze + independent challenge

Branch: `feature/action-policy-v8` · PR #11

### Semantic change
- Separate `last_delivered_question_need` from `pending_episode_attribute`
- Live `build_policy_snapshot` no longer copies pending into delivered need
- `repeat_question` cannot eliminate hard pending obligation candidate

### Evidence
| Field | Value |
|-------|-------|
| phase | v8 impl + freeze + challenge |
| policy SHA (COMMIT A) | `c0fa158bd2ffb4109d1f0776c3b3245cdff31ce4` |
| CI (COMMIT A) | [34539702387](https://github.com/Belvist/imvera/actions/runs/34539702387) — 1104 passed, 5 skipped |
| freeze commit (COMMIT B) | `822c391bc7da1fe3aad57e261f962718cd633132` |
| freeze manifest | `docs/evaluation/action-policy-phase1-v8-freeze-manifest.json` |
| challenge commit | `f2f0821b4156a269a716badd3ad5dac5797b1565` |
| challenge report | `docs/evaluation/action-policy-phase1-v8-challenge.json` |
| challenge gate | **PASSED** — 20/20, P0-like 100%, forbidden=0, constraint_violations=0 |
| corpus | `tests/action_policy/corpus/challenge_v8_live/` (EngineState→snapshot→choose) |
| decision | **v8 CODE READY as cutover candidate (offline)** |
| next gate | Phase 2 operator canary (plumbing) then Phase 6 real shadow 100/1000 on **v8** |

---

## Phase 6 — Real shadow acceptance (v8)

| Field | Value |
|-------|-------|
| status | **NOT VERIFIED** — requires operator deploy + real calls |
| hard gates | see user brief / operability runbook |
| incomplete telemetry | exclude from evidence |
| next | after canary plumbing healthy |

---

## Phase 7 — DecisionRouter (code)

| Field | Value |
|-------|-------|
| module | `packages/dialogue_engine/decision_router.py` |
| modes | `legacy` (`off` alias) / `shadow` / `soft` / `policy` |
| kill switch | `MODE=off\|legacy` **or** `CUTOVER_ENABLED=0` |
| soft % | `IMVERA_ACTION_POLICY_SOFT_PERCENT` (default 0) |
| metamorphic tests | `tests/action_policy_shadow/test_decision_router.py` |
| soft/policy in prod | **blocked** until Phase 6 shadow hard gate + explicit `CUTOVER_ENABLED=1` |
| decision | router CODE READY; soft/policy NOT enabled |

---

## Phase 8–9 — Soft / full policy

| Field | Value |
|-------|-------|
| status | **NOT VERIFIED** — blocked on real shadow evidence |

---

## Phase 10 — Operability

| Field | Value |
|-------|-------|
| runbook | `docs/runbooks/action-policy-production-operability.md` |
| canary runbook | `docs/runbooks/action-policy-shadow-canary.md` |
| status | docs CODE READY |

---

## Current overall readiness

| Status | State |
|--------|-------|
| CODE READY | Shadow M1.2 YES; v8 frozen+challenge YES; DecisionRouter YES |
| STAGING READY | Canary + operability runbooks YES — awaiting operator |
| SHADOW VERIFIED | **NOT VERIFIED** (no real calls) |
| SOFT ROLLOUT VERIFIED | **NOT VERIFIED** |
| FULL PROD VERIFIED | **NOT VERIFIED** |

### STOP: READY FOR OPERATOR DEPLOY

Agent cannot access production. Required operator actions:

1. Deploy voice build with `IMVERA_ACTION_POLICY_MODE=off` (smoke calls)
2. Short plumbing canary `MODE=shadow` (5–10 calls) — verify HEALTH + produced==persisted
3. After healthy plumbing: real shadow acceptance on **v8** (100 complete calls / 1000 scheduler evals)
4. Only then enable soft via `CUTOVER_ENABLED=1` + percent ladder
