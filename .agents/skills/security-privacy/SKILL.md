---
name: security-privacy
description: Audit voiseup for PII, consent, secrets, and attack surface. Use for auth, storage, telephony exposure, and compliance-sensitive changes.
---

# Security & Privacy

## Data Classification

| Data | Examples | Rules |
|------|----------|-------|
| PII | name, phone, voice recording | encrypt at rest, minimize retention |
| PHI-adjacent | wellness answers, fall reports | treat as sensitive; audit access |
| Secrets | SIP creds, API keys, ESL passwords | env/vault only; never commit |
| Telemetry | latency metrics | no raw transcript in metrics |

## Consent (product law)

- Elder must consent to regular calls — voice or DTMF
- Family cannot consent on behalf
- Silence ≠ consent
- DECLINED status must block future scheduled calls

## Telephony Surface

- SIP credentials: least privilege trunk account
- ESL/admin ports: bind localhost or VPN only
- No debug endpoints on public interfaces
- Rate limit inbound call initiation APIs

## Voice Pipeline

- Recordings: encrypted object storage, TTL per policy
- Transcripts: access logged; not in application logs at INFO
- LLM: no PII in prompts beyond necessary context; no training on user data without consent

## Checklist

- [ ] Input validation on all HTTP/API (size limits, schema)
- [ ] Parameterized queries if SQL used
- [ ] CORS deny by default
- [ ] TLS 1.2+ for external APIs
- [ ] `check_secrets` or equivalent in CI
- [ ] Dependency scan (SCA) on lockfile

## Incident

If secret leaked → rotate immediately, document in `incident-postmortem` skill.

## Output

```text
FINDINGS: severity (critical/high/medium/low) + file + remediation
CONSENT IMPACT: ...
PII FLOW: ...
BLOCKERS FOR DEPLOY: ...
```
