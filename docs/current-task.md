# Current task — Grandmother call validation (Stage B/C)

## How Vera knows her voice (always-listen)

| Level | What | Verdict for Daniil |
|-------|------|--------------------|
| **Mute (half-duplex)** | Mic off while TTS plays | Dumb but stable — friend’s MVP; feels «deaf» |
| **Text `_is_assistant_echo`** | Drop STT if transcript ≈ Vera’s phrase | Weak — STT already wrong on echo (`Сд.`/`Сейчас`) |
| **Reference PCM gate (now)** | Ring of injected downlink PCM; NCC/energy vs uplink | Right lab path for always-listen without self-talk |
| **True WebRTC AEC / ML speaker-ID** | Full AEC or X-vector | Later — **not** claimed; not in repo |

**Flags (lab defaults — 2026-09-08 emergency deaf fix):**

- `IMVERA_LAB_HALF_DUPLEX=0` — default OFF (always-listen; mic stays open during Vera TTS)
- `IMVERA_ECHO_REF_GATE=1` — default ON (reference PCM gate drops echo; UNCERTAIN passes during opening)
- **Opening wellness exception:** during `opening_wellness` TTS, UNCERTAIN uplink frames reach VAD (not fail-safe dropped); echo drops → preroll
- `IMVERA_UPLINK_PREROLL_MS=2000` — replay speech captured during half-duplex mute when listen opens (rest of call)
- `IMVERA_LAB_BARGE_IN=0` — hear user during Vera; do not cut Vera unless explicitly enabled
- TTS: `silero_lab:silero:v5_ru:xenia` (torch+omegaconf); **not** `macos_say:Milena`
- Opening cache fingerprinted by engine; legacy/macos_say PCM deleted on `voice_up`
- Fail-safe unmute: `_force_listen_enabled` in `finally` + auto-expire pause gate + VAD.reset on listen.enabled

**Agent fight 2026-09-08 (honest):** agents flipped half-duplex ↔ always-listen. **Emergency fix (`9bb2b4dd`):** always-listen + echo-ref ON by default; preroll on echo-drop/flush; VAD 0.15 + RMS fallback 350. Live SIP **NOT VERIFIED** until user re-dials 7000.

**Incident 2026-09-08 robot voice:** health showed `silero_lab:macos_say:Milena` (torch missing). Fixed: `pip install -e ".[lab-silero]"` + omegaconf; config `v5_ru`/`xenia` (local cache; `v5_5_ru` SSL-blocked).

## Primary assignment

Live Zoiper **7000** — wellness dialogue on real audio.  
**Incident 2026-09-08 00:08 (`sip-31365dee13`):** echo self-barge-in — greeting cut ~187ms; STT `Сд.`/`Сейчас`; no `playback.completed`. Cause: `8accf9a` R1 unmuted uplink during TTS.  
**Incident 2026-09-08 ~01:55 (`sip-72d8d1a9ab`):** capture OK (`rms=7559`), но STT `Ответ.`/`Пять вы` вместо «хорошо»; ложный `speech.started` во время приветствия; `listen_rms_peak=0.2` на первом answer-wait. **Fix:** finalize segment before VAD reset; suppress echo speech.started during opening; planner clarify on LOW/garbage STT; diagnose verdicts.  
Policy matrix: `tests/test_wellness_call_scenarios.py`.  
**1k corpus + load harness:** `make test-corpus-1k` / `scripts/run_dialogue_corpus.py` (Session/Planner scale proof; **NOT** live SIP×1000).  
Architecture: [ADR-009](adr/009-llm-understanding-state-policy.md).

## Why friend's MVP works vs our SIP path

Honest gap list (friend solved local mic loop first; we jumped to Asterisk/Zoiper):

| Friend (local MVP, ~3h) | Our Zoiper/SIP path |
|-------------------------|---------------------|
| sounddevice mic/speakers first | Asterisk + ExternalMedia + snoop + softphone |
| Strict half-duplex: speak → finish → pause → **then** mic | Was default; now optional via `IMVERA_LAB_HALF_DUPLEX=1` |
| Whisper local + WebRTC VAD | MLX STT + Silero/energy VAD over RTP |
| Silero Xenia (`kseniya`) | Lab often falls back to **macos say** (robotic) if torch missing |
| Dialogue orchestrator owns flow | Same Planner/Session; **Core owns GREEN/YELLOW/RED** — we must not copy friend's verdict ownership into voiseup |
| One failure mode: acoustic loop | ×10: echo, snoop mix, codec, inject lag, capture loss, finalize races |

Same root bug class (hearing Vera). **Correct engineering:** reference echo gate from known TTS PCM — not permanent mute, not text-only filter.  
**Lab defaults now:** `IMVERA_LAB_HALF_DUPLEX=0`, `IMVERA_ECHO_REF_GATE=1` (always-listen + echo-ref; preroll safety net).

### Trace diagnostics (deaf / mute)

After dial, check `.run/traces/<call_id>.jsonl` for:

| Stage | Meaning |
|-------|---------|
| `playback.completed` | Vera finished speaking |
| `listen.enabled` | Mic unmuted — **must** follow playback |
| `speech.started` / `stt.final` | User heard |
| `uplink.summary` | On answer timeout: `listen_rms_peak` — **&lt;120** ≈ dead mic/capture |
| `capture.summary` | On hangup: gateway `capture_rms_peak`, `capture_bytes` |

```bash
python3 scripts/diagnose_call_trace.py <call_id>
```

## Branch / SHA — truth table

| Field | Value |
|-------|-------|
| Branch | `fix/dialogue-stage-b` (local) |
| **HEAD (before this corpus commit)** | `fd2170b` — wellness scenario matrix |
| Telephony gate commit | `69edab5` — macOS say lab TTS + gateway `/health/ready` (**PASSED**) |
| Prior dialogue stage | `e0e86b0` — QuestionLedger / answer-wait |
| Included in corpus commit | Stage B dialogue (empathy / topic-refuse / multi-phrase / `release_question_attempt`) + `tests/corpus/` + runner |
| Last pushed (historical) | `e0e86b0` — do not assume remote has Stage B |
| Push policy | **Do not push** unless user asks |

### Dialogue behavior under corpus proof

- **«не очень» / «плохо»** → wellness FILLED + `reflect_report` empathy
- **«хорошо» / «нормально»** → wellness FILLED + `check_mood`
- Backchannel «ага»/«алло»/«угу» → never fills pending slot
- Topic refuse, pause, stop-call phrases
- **CallActor:** sequential multi-phrase TTS; reservation release on TTS fail (mock TTS load)

## Reproduce 1k proof (tomorrow / Daniil)

```bash
cd /Users/earflow/Downloads/voiseup
git rev-parse HEAD
make test-corpus-1k
# or:
python3 scripts/run_dialogue_corpus.py --workers 4 --minimum 1000
python3 -m pytest tests/corpus/ -q
python3 -m pytest tests/ -q   # full suite
```

Expect: **1000/1000** corpus pass + CallActor load green.  
Label: **CallSession dialogue scale** — not Zoiper/SIP×1000.

## Tomorrow checklist — dial 7000 (Zoiper)

### Before the call

```bash
cd /Users/earflow/Downloads/voiseup
git rev-parse HEAD
git status -sb
make voice-up
make zoiper-info
curl -s http://127.0.0.1:9200/health/ready
curl -s http://127.0.0.1:9101/health/ready
curl -s http://127.0.0.1:9102/health/ready
curl -s http://127.0.0.1:9103/health/ready
make dialogue-smoke
make test-corpus-1k          # scale proof (text Session path)
```

Runtime truth: `git rev-parse HEAD` + `git status -sb`, profile `config/voice-m5.yaml`, STT `:9101` (**GigaAM v3_e2e_rnnt**, engine `gigaam`), TTS `:9102`, LLM `:9103`, gateway `:9200`.

### Call script (say in order)

| Step | Vera asks (approx.) | You say | Expect |
|------|---------------------|---------|--------|
| 0 | Opening / identity / consent / can talk | «Да» (if prompted) | `opening_wellness` → `DAILY_CHECK` |
| 1a | Как себя чувствуете? | **«хорошо»** or **«нормально»** | wellness FILLED → mood (`check_mood`) |
| 1b | (alt) Как себя чувствуете? | **«не очень»** or **«плохо»** | wellness FILLED → **`reflect_report`** |
| 2 | Настроение? | «хорошее» (or «плохое» if 1b) | mood FILLED → sleep |
| 3 | Сон? | «спал нормально» / «спала плохо» | sleep FILLED → plans |
| 4 | Планы? | «дома посижу» / «дома» | plans FILLED → summary |
| 5 | (optional) | «до свидания» → «да» | `goodbye_confirm` → `goodbye_final` |

**Extra probes:** mixed side question; complaint «голова болит»; backchannel «ага»; soft stop «закончим разговор».

### Where traces go

```text
.run/traces/<call_id>.jsonl
curl -s http://127.0.0.1:9200/calls/<call_id>/trace | jq '.events[].type'
```

### Pass criteria (live)

- [ ] Greeting before wellness question
- [ ] STT ≈ utterance
- [ ] «хорошо» advances; «не очень»/«плохо» empathy then advance
- [ ] No 3+ identical wellness questions
- [ ] Complaint mirrored without praise
- [ ] Four slots filled OR explicit UNRESOLVED close
- [ ] Goodbye terminates

## Local verification (this session)

```bash
python3 scripts/run_dialogue_corpus.py --workers 4 --minimum 1000
# → 1000 passed / 0 failed, ~4200–4500 scenarios/sec (ProcessPool)

python3 -m pytest tests/corpus/ -q
# → corpus gate + CallActor load

python3 -m pytest tests/ -q --ignore=tests/test_llm_live_dialogue.py
# → 220 passed, 2 skipped

make dialogue-smoke   # gateway/providers ready; live LLM gates OK when stack up
```

## NOT VERIFIED

| Item | Why |
|------|-----|
| **SIP / Zoiper ×1000** | Not feasible tonight; corpus is Session/Planner text path |
| Live STT elderly speech | Corpus injects text |
| Live TTS audibility / barge-in on softphone | CallActor load uses **mock** TTS |
| End-to-end latency p50/p95 | No timed live baseline |
| Real LLM for all 1000 cases | Rule interpreter; semantic matrix is separate |
| Remote/main parity | Branch local; do not push unless asked |

## NEXT GATE

1. **`make voice-down && make voice-up`** — STT must show `gigaam:v3_e2e_rnnt@cpu` in `voice_doctor`.
2. **Zoiper 7000** — «хорошо» + «не очень»; `python3 scripts/diagnose_call_trace.py <call_id>`.
3. **`python3 scripts/stt_probe.py`** — regression: «не очень» must not become «Ниотин» (GigaAM probe OK on say/Milena).
4. Re-run `make test-corpus-1k` after dialogue changes.
