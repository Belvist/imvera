# Experimental telephony spikes (NOT production)

## Telnyx (`telnyx_*.py`, `/telnyx/media`)

**Status:** rejected per [ADR-012](../../docs/adr/012-self-hosted-telephony-livekit.md).

Managed voice API — violates self-hosted-only policy. Code kept for parser/codec/reorder reference.

**`/telnyx/media` is not registered** unless `IMVERA_ENABLE_EXPERIMENTAL_TELNYX=1`.

Local tests only: `make telnyx-media-gate`

## Production path

See ADR-012: **LiveKit SIP + LiveKit Server** (self-hosted) → `CallActor`.

## Lab reference

Asterisk + `chan_websocket` — forensics only, not production uplink.
