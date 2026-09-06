---
name: production-readiness
description: Verify deploy and release claims for voiseup. Use before stating a build works in production or pilot.
---

# Production Readiness

## Cannot Claim «Production Ready» Until

- [ ] **Image truth** — `docker inspect` SHA matches git tag
- [ ] **Config truth** — env vars match runbook; no dev endpoints
- [ ] **Engine truth** — active dialogue engine name logged at startup
- [ ] **SIP E2E** — real call completed with recording + trace
- [ ] **Latency** — p50 turn < 3s on target hardware (see PROJECT_CONTEXT)
- [ ] **Barge-in** — demonstrated on live call
- [ ] **Failure drills** — STT down, TTS down, LLM timeout → graceful degrade
- [ ] **Verdict path** — Core receives events; voiseup does not fake GREEN
- [ ] **Consent flow** — tested: family cannot bypass elder consent
- [ ] **Secrets** — rotated; not in repo or logs
- [ ] **Rollback** — previous image tag documented

## Pilot Gate (20–50 families)

Additional:

- [ ] PSTN trunk with failover documented
- [ ] Concurrent call capacity measured
- [ ] Recording retention policy implemented
- [ ] Incident escalation tested end-to-end with Core
- [ ] On-call runbook exists

## Report Template

```text
DEPLOY TARGET: ...
IMAGE SHA: ...
GIT SHA: ...
GATES PASSED: ...
GATES FAILED / SKIPPED: ...
REMAINING RISKS: ...
ROLLBACK: ...
```

## Forbidden

- «Works on my machine» without image SHA
- Pilot with loopback-only verification
- Skipping SIP gate because «unit tests pass»
