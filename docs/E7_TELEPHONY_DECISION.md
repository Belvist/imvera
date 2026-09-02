# E7 — Telephony transport decision + legal gate

## Decision matrix (owner must pick)

| Criterion | A: Own FreeSWITCH + SIP trunk | B: CPaaS (API + media) |
|-----------|-------------------------------|-------------------------|
| Minute price | Usually lower | Higher |
| Marking / mass-call contract (41-FZ) | Via trunk operator | Via CPaaS |
| Media control / barge-in | Full (matches Architecture v1) | Depends on stream API |
| Ops burden | High (VPS, ACL, fail2ban) | Lower |
| Fits ADR «FreeSWITCH остаётся» | Yes | Needs ADR exception |

**Recommendation for pilot:** A — keeps MediaAdapter path; use VPS+WireGuard
bridge from `AGENTS_PLAN_20260831.md` while compute stays on Mac.

## Operator RFP checklist (send to 2–3 providers)

Ask for written answers:
1. SIP trunk + Russian DID (+7)
2. Call marking (41-FZ) for ИП, label «IMVERA» ≤32 chars
3. Separate mass automated call (МАВ) contract + consent proof requirements
4. G.711 / SIP TLS / SRTP support
5. Price: number/mo + per-minute inbound/outbound
6. IP ACL / registration mode
7. SLA and anti-fraud / toll limits

Candidates to contact: Exolve, Zadarma, MTT, Mango Office (verify current
offers — do not assume).

## Hardening before public SIP (mandatory)

See also `AGENTS_PLAN_20260831.md` Level 2:
- [ ] Firewall: 5060/RTP only from trunk IP ranges
- [ ] Separate sofia profile + unique password (not in git)
- [ ] fail2ban on auth failures
- [ ] International outbound blocked / kill-switch
- [ ] Route only purchased DID (no wildcard)
- [ ] `scripts/install_freeswitch.sh` applied after P4 pass

## Owner actions (not automatable)

- [ ] Register ИП or ООО
- [ ] Sign marking + mass-call contracts
- [ ] Buy DID
- [ ] Provision VPS + WireGuard
- [ ] Run 3 live calls from real mobile + landline

## Interim: Level 0–1 (no DID money)

Follow WireGuard tunnel steps in `AGENTS_PLAN_20260831.md` to call Mac
runtime from a phone without public SIP.
