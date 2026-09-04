# Latency baseline (F8) — 2026-09-03T02:07:22Z

- **Mode:** `synthetic`
- **Trials:** 5
- **Endpointing model:** 2000 ms (speech_end delay before STT)

## Stack probe

```json
{
  "stt_ready": false,
  "tts_ready": false,
  "llm_ready": true,
  "stt_host": "",
  "stt_model": "",
  "llm_provider": "local"
}
```

## Aggregates (ms)

| Stage | p50 | p95 | mean | min | max |
|-------|-----|-----|------|-----|-----|
| endpointing_ms | 2000 | 2000 | 2000 | 2000 | 2000 |
| stt_ms | 1 | 1 | 1 | 1 | 1 |
| plan_ms | 1 | 2 | 1 | 0 | 2 |
| gen_tts_ms | 0 | 0 | 0 | 0 | 0 |
| first_audio_ms | 2002 | 2003 | 2002 | 2001 | 2003 |

## Gates

- CPU first_audio p50 gate: **≤ 4000 ms** — measured **2002 ms** (PASS)
- CPU first_audio p95 gate: **≤ 4000 ms** — measured **2003 ms** (PASS)
- GPU target p50: **≤ 2000 ms** (FAIL)

## Methodology

Aligned with `ENGINEERING_PLAN.md` §14–15:

1. **speech_end** — caller stops speaking (+ modeled endpointing tail on phone path)
2. **stt_ms** — `transcribe_with_confidence` (phone) or hop stream (WebApp)
3. **plan_ms** — `plan_reply` FSM (deterministic, no LLM lock)
4. **gen+tts_ms** — first LLM sentence + TTS first frame (`seg-0001.wav` or `wav_b64`)
5. **first_audio** — sum to first audible Vera output

Live production logs emit the same breakdown:
`[call-agent] LATENCY <call_id>: stt=… plan=… gen+tts=… first_audio=…`
