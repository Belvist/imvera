# E11 — Pilot 20–50 families playbook

## Goals
Measure (from imvera.ru /investor):
- Contact & status quality (6 statuses distribution, false RED rate)
- Escalation reliability (time-to-ack, delivery success)
- Willingness to pay (survey + test price)
- OpEx (minutes, server, SMS, cost per successful contact)
- Usage & feedback (NPS, retention)

## Entry criteria
- [ ] E1 media gate (or accepted interim Lua path with echo-guard)
- [ ] E2 statuses live
- [ ] E3 consent call works
- [ ] E4 Product API + TestFlight app usable
- [ ] E5 scheduler dry-run then live with kill-switch
- [ ] E6 at least Telegram + one fallback channel
- [ ] E7 DID or Level-1 tunnel for real phones
- [ ] E10 lawyer review started

## Weekly ritual
1. Export call_results status histogram
2. Review all RED + TECHNICAL manually
3. Survey 5 families
4. Cost sheet: trunk minutes + SMS + infra
5. Kill-switch drill once

## Exit gate
- ≥80% calls end GREEN/YELLOW/RED (not TECHNICAL)
- False RED below agreed threshold after human review
- Known cost per successful contact
- ≥N families willing to pay stated price

## Support
Telegram @judogia + email egordemin98@gmail.com (site). SLA: best-effort
during pilot; no 24/7 promise.
