# Black-box live E2E voice assets

Uplink WAV files for the external SIP caller (`tools/blackbox_caller`).

## L3-A smoke — Vera self-call (allowed for first SIP path test)

For **L3-A** (pyVoIP / G.711 → FreeSWITCH), you may synthesize uplink WAV with **the same Silero Xenia voice** Vera uses:

```bash
# Requires IMVERA TTS up (Silero xenia @ :9102)
python3 scripts/blackbox_synthesize_vera_voice.py
```

This writes `wav/*.wav` and sets manifest metadata:

```json
"source": "vera_tts_smoke"
```

**Honest limits:**

- Uplink is Vera TTS → STT hears Vera's voice, not independent human acoustic diversity
- Does **not** prove STT on elderly / noisy / multi-speaker speech
- Does **not** replace production voice acceptance

Use this only to validate: **SIP/RTP → FS → CallActor → DialogueEngine → TTS → RTP → caller recording**.

## L3-B / L4 — human voice bank (required for real acceptance)

For G.722 (PJSUA2) and PSTN gates, record **25–40 real human phrases** from **2–3 speakers**:

```bash
python3 scripts/blackbox_record_prompts.py --list
python3 scripts/blackbox_record_prompts.py --record wellness_good_01
```

Do **not** use IMVERA Silero TTS for L3-B/L4 uplink assets.

## Format

- Mono WAV, 16 kHz preferred (ffmpeg normalizes to 8 kHz u8 for pyVoIP uplink)
- Natural pace; phone-distance mic for human recordings

## Gate behavior

`make live-call-1` **FAILS** if any manifest entry is missing from `wav/`.

After Vera synthesis, all manifest files must exist before the gate runs.

## Independent oracle (downlink)

Downlink is transcribed with **non-GigaAM** ASR:

```bash
export IMVERA_BLACKBOX_ASR_CMD='whisper {wav} --language Russian --output_dir /tmp'
```

Primary evidence: `caller_downlink.wav` + external transcript + server trace (triangulation).
