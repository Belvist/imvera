# E10 — Security & legal checklist (ROADMAP)

> Engineering checklist. Legal items require a human lawyer — marked
> **LAWYER**. Knowledge-model notes on 152-FZ / 41-FZ — verify.

## Threat model (top risks)

| Risk | Mitigation in code/ops |
|------|------------------------|
| Toll fraud on public SIP | ACL, kill-switch, no intl outbound (E7) |
| IDOR on household data | Product API membership checks (E4) |
| Webhook forgery | HMAC `MOSS_WEBHOOK_SECRET` fail-closed |
| Provider SSRF | HTTPS-only URL validation in delivery.py |
| Secret leak in git | `scripts/check_secrets.sh` in CI |
| PII in logs | No raw transcripts in operational logs |
| Auth bypass on :9400 | `MOSS_INTERNAL_API_TOKEN` + rate limit |
| OOM / DoS upload | Body size limits 8MB / 413 |

## Pentest checklist

- [ ] External svmap against SIP; unauthorized REGISTER fails
- [ ] Product API without token → 401; cross-household GET → 403
- [ ] Oversized body → 413; invalid JSON → 400
- [ ] Webhook without signature → 503/401
- [ ] Dependency scan (pip-audit / safety) clean for prod pins
- [ ] Backup restore drill documented

## 152-FZ / personal data (**LAWYER**)

- [ ] Notify Roskomnadzor as personal-data operator
- [ ] Privacy + consent texts on imvera.ru match actual processing
  (audio, transcripts, phones)
- [ ] Data residency in RF
- [ ] Retention periods published; retention worker enforces
- [ ] Subject deletion cascade (PG + S3) tested
- [ ] Written statement: voice not used for biometric identification

## 41-FZ telephony (**LAWYER** + operator)

- [ ] ИП/ООО registered
- [ ] Call marking contract (label IMVERA)
- [ ] Mass automated calls contract
- [ ] Consent proof export for operator audits (E3)

## Non-medical positioning

- App Store / site / Vera speech: not a medical device; call 112 if life threat
- No diagnoses in dialogue prompts

## Paid launch extras

- [ ] Offer / terms of service
- [ ] Payment provider (YooKassa / CloudPayments / T-Bank) + 54-FZ receipts
- [ ] Apple IAP vs web subscription decision for App Store

## Status

Engineering mitigations partially in tree (E0 hardening, delivery URL
validation, internal token). Lawyer/operator boxes remain owner actions.
