# Phase B — PJSUA2 transport + live gate

Primary **external** live gate backend. Replaces host pyVoIP hacks.

## Transport gate (first)

```bash
make pjsua2-transport-gate
```

PASS criteria (no DialogueEngine):

```text
sip_registered = true
sip_confirmed = true
rtp_tx_packets > 0
rtp_rx_packets > 0
caller_downlink_bytes > 0
```

Artifact: `.run/pjsua2_transport_gate/transport_gate_result.json`

## Media model (headless)

```text
AudioMediaPlayer(WAV) → startTransmit → call AudioMedia
call AudioMedia → startTransmit → AudioMediaRecorder → caller_downlink.wav
```

No sound card. See [PJSIP audio media docs](https://docs.pjsip.org/en/2.17/pjsua2/using/media_audio.html).

## Codecs

Start with **PCMU / PCMA** only. Record in `result.json`:

```text
offered_codecs
negotiated_codec
negotiated_clock_rate
```

G.722 only after PCMU soak passes and SDP proves negotiation.

## Backend selection

```bash
export IMVERA_BLACKBOX_SIP_BACKEND=pjsua2
make live-debug-1
```

## Build note

`pjsua2` Python module is built from pjproject (not bundled in `[sip-lab]`). Install per platform before transport gate.

## Ladder (after transport PASS)

```text
1/1 full daily-check
→ 10/10
→ 100/100 (same SHA, stop on first fail)
```
