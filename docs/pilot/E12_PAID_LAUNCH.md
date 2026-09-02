# E12 — Limited paid launch checklist

Depends on E11 exit gate metrics.

## Pricing
- Set monthly price from pilot willingness-to-pay + cost per contact × margin
- Document what's included (N elders, M calls/day, escalation channels)

## Billing
- [ ] Provider chosen (YooKassa / CloudPayments / T-Bank)
- [ ] Subscription + receipts 54-FZ
- [ ] Dunning / pause on non-payment (stop scheduler, keep data retention window)

## App Store
- [ ] Privacy nutrition labels
- [ ] Health claims avoided; 112 disclaimer
- [ ] Push + Time Sensitive entitlement justification
- [ ] TestFlight → production

## Android
Decision after pilot data: native Kotlin vs cross-platform. Not blocking
limited iOS paid launch.

## Scale (§16 ENGINEERING_PLAN)
- [ ] First cell capacity certified (load test)
- [ ] STT/LLM/TTS pools + admission
- [ ] Second FreeSWITCH node optional
- [ ] Cell router only after one cell is boringly stable
