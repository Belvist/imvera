# Challenge-frozen corpus (not for tuning)

This directory is reserved for a **second** ActionPolicy scenario set that must be
frozen **after** `DEFAULT_WEIGHTS` and the development/held-out corpora are locked.

Rules:

- Do not tune weights against scenarios in this split.
- Do not add cases here while iterating on Phase 1 weights.
- Promotion to a gate requires an explicit freeze commit with date and policy version.

Corpus frozen at commit `e21cf6e` (54 cases). Labels are immutable after freeze.

Independent challenge run (frozen policy `0271c62`, v5):

- Result: **FAILED_INDEPENDENT_CHALLENGE**
- Report: `docs/evaluation/action-policy-phase1-v5-challenge.json`
- Pass rate: 52/54 (96.3%) — below gate due to `forbidden_count=1`
- Failures: `ch_no_repeat_severity`, `ch_functional_impact_pending`

Automated regression tests do not read this directory during CI.
Re-run only via `scripts/run_action_policy_challenge.py` for audit.
