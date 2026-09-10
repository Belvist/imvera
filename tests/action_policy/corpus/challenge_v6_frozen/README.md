# v6 independent challenge corpus (frozen after v6 policy freeze)

Frozen **after** `action-policy-phase1-v6` weights and development/held-out corpora.

Rules:

- Do not tune v6 weights against scenarios in this split.
- Do not patch v6 against failures in this corpus while calling it independent.
- Labels are immutable after freeze commit.
- v5 challenge (`challenge_frozen/`, commit `e21cf6e`) remains regression evidence only.

Target gate (single run after freeze):

- `forbidden_count = 0`
- `constraint_violation_count = 0`
- P0-like pass rate = 100%
- overall pass rate >= 95%

Re-run only via `scripts/run_action_policy_challenge.py --corpus challenge_v6_frozen`.

Independent challenge result (v6, local run):

- **PASSED_INDEPENDENT_CHALLENGE**
- 61/61, `forbidden_count=0`, `constraint_violation_count=0`
- Report: `docs/evaluation/action-policy-phase1-v6-challenge.json`
