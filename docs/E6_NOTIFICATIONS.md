# E6 — Contacts from DB + escalation channels

## Default channel order
`MOSS_INCIDENT_CHANNELS=push,telegram,sms,call`

## Contact resolution
`DeliveryRouter.resolve_contacts(rows)` reads `contacts` table rows
`(channel, address, escalate_order)`. Empty → ENV legacy
`MOSS_FAMILY_CHAT_ID` / `MOSS_FAMILY_PHONE`.

## Push (APNs)
Device tokens in `device_tokens`. Sending goes through
`MOSS_APNS_GATEWAY_URL` (HTTP/2 bridge) because CPython urllib is HTTP/1.1.
Sandbox keys: `MOSS_APNS_KEY_PATH`, `MOSS_APNS_KEY_ID`, `MOSS_APNS_TEAM_ID`,
`MOSS_APNS_BUNDLE_ID=ru.imvera.app`.

## Telegram deep-link bind
1. Family opens bot → `/start bind_<household_token>`
2. Bot stores `chat_id` into `contacts` channel=telegram
3. Incidents use that chat_id (not global ENV)

## «Я проверю»
Product API `POST /api/v1/incidents/{id}/ack` with actor=user_id →
`IncidentEngine.ack`. DTMF 1 on family auto-call → same ack.

## Auto-call via ESL
`MOSS_CALL_VIA_ESL=1` → `VoiceChannel` uses `originate_to_number` instead of
HTTP call provider. TTS script for family: status summary + «нажмите 1,
если берёте на себя».

## Status after every call
Outbox topic `call.result` → notify household with `summary_for_family`
(not raw transcript) for GREEN/YELLOW/RED/NO_CONTACT/TECHNICAL/DECLINED.
