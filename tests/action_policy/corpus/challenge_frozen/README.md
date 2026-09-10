# Challenge-frozen corpus (not for tuning)

This directory is reserved for a **second** ActionPolicy scenario set that must be
frozen **after** `DEFAULT_WEIGHTS` and the development/held-out corpora are locked.

Rules:

- Do not tune weights against scenarios in this split.
- Do not add cases here while iterating on Phase 1 weights.
- Promotion to a gate requires an explicit freeze commit with date and policy version.

Until that freeze happens, automated tests do not read this directory.
