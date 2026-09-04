# Latency baseline (F8 harness)

> **Status:** harness landed 2026-09-03 (`voice-lab/latency_baseline.py`).  
> Owner gate: re-run after stack changes and on live Zoiper calls (parse docker logs).

## What we measure

**Primary metric:** `first_audio_ms` — wall time from **speech_end** to the first audible Vera frame (first `seg-*.wav` on the phone path or first `wav_b64` on WebApp).

Aligned with `ENGINEERING_PLAN.md` §14–15 and orchestrator `_maybe_latency_trace`:

| Stage | Source | Notes |
|-------|--------|-------|
| endpointing | Lua record tail / VAD | Modeled as 2000 ms default (`MOSS_ENDPOINTING_MS`) on phone path |
| stt | `transcribe_with_confidence` (phone) or `StreamingSTT` hops (WebApp) | Phone path: one-shot batch (faster e2e) |
| plan | `plan_reply` FSM | Deterministic; no LLM under `ctx.lock` |
| gen+tts | `reply_stream` / `reply_segments` → TTS first frame | First sentence only for latency |
| **first_audio** | sum to first PCM | Log line: `LATENCY … first_audio=…` |

Production log format (telephony container):

```text
[call-agent] LATENCY <call_id>: turn=<n> gen=<n> stt=<ms> plan=<ms> gen+tts=<ms> first_audio=<ms>
```

## Gates

| Profile | first_audio p50 | first_audio p95 | Source |
|---------|-----------------|-----------------|--------|
| **CPU (current)** | ≤ 4000 ms | ≤ 4000 ms | `ENGINEERING_PLAN.md` §15.4 |
| **GPU / realtime (future)** | ≤ 2000 ms | ≤ 2000 ms | Track B / Newo-class target |

Greeting (pre-cached WAV, not a dialogue turn) target remains **< 2000 ms** (§14).

## Harness modes

```bash
# Offline synthetic (plan + mock STT/TTS) — always runnable
python3 voice-lab/latency_baseline.py

# With live backends when telephony stack is up
python3 voice-lab/latency_baseline.py --real-stt --real-tts --trials 5

# Full phone-path pipeline (process_turn_stream + segment_dir)
python3 voice-lab/latency_baseline.py --mode e2e --trials 3

# Ingest live LATENCY lines from docker logs
docker logs telephony 2>&1 | python3 voice-lab/latency_baseline.py --parse /dev/stdin
# or:
python3 voice-lab/latency_baseline.py --parse /path/to/telephony.log
```

Outputs:

- `voice-lab/reports/latency_baseline.json`
- `voice-lab/reports/latency_baseline.md`

Exit code 1 when CPU p50 gate fails (`--strict` behaviour by default on gate).

## Methodology notes

1. **speech_end** is not a hardware timestamp today — the harness models endpointing delay on the batch phone path. Stage D (streaming STT) should shrink this to ~300 ms post-VAD.
2. **Synthetic mode** isolates dialogue + TTS when STT/TTS daemons are down; numbers are a **floor** for plan+TTS, not production e2e.
3. **e2e mode** uses the same `process_turn_stream` code as `moss_agent.lua` (`segment_dir` + one-shot STT).
4. **parse mode** is the authoritative source for live Zoiper/loopback baselines.

## Baseline snapshot (2026-09-03)

Run: `python3 voice-lab/latency_baseline.py --trials 5` (synthetic, mock STT/TTS).

| Stage | p50 (ms) | p95 (ms) |
|-------|----------|----------|
| endpointing | 2000 | 2000 |
| stt (mock) | 1 | 1 |
| plan | ~0.4–1.7 | ~1.6 |
| gen+tts (mock) | ~0.02 | ~0.03 |
| **first_audio** | ~2002 | ~2003 |

Interpretation: with modeled 2 s endpointing, **CPU gate PASS/FAIL is dominated by endpointing + real STT**, not dialogue planning. Re-measure with `--mode e2e --real-stt --real-tts` when `make up telephony` and host STT/TTS are healthy.

Historical live reference (`AGENTS.md`, ENGINEERING_PLAN §14): **4–7 s** first_audio on CPU (2 s silence + STT 1.2–3 s + first sentence).

## Weekly cadence

1. `make up telephony` (if stack changed)
2. `python3 voice-lab/latency_baseline.py --mode e2e --trials 10`
3. One Zoiper call → `docker logs telephony 2>&1 | grep LATENCY | tail -20`
4. Archive JSON under `voice-lab/reports/latency_YYYYMMDD.json`

## Related

- `ENGINEERING_PLAN.md` §14–15, §15.2 Stage D
- `docs/STT_STREAMING_SPIKE.md` — removing endpointing wait
- `docs/DIALOGUE_30_VALIDATION.md` — dialogue quality (orthogonal to latency)
