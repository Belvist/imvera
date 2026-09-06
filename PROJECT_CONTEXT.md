# IMVERA VoiseUp — Project Context

> Greenfield voice + telephony stack for [IMVERA](https://imvera.ru/).
> This repository is **not** a fork of any prior voice codebase.

## Product

IMVERA — семейный сервис заботы о пожилых близких на расстоянии.

- Семья настраивает профиль, расписание и цели звонка.
- Пожилой человек **только отвечает на обычный телефонный звонок** — без приложений.
- После разговора семья получает понятный статус: GREEN / YELLOW / RED / NO_CONTACT / TECHNICAL / DECLINED.
- При тревоге запускается эскалация (push / Telegram / SMS / автозвонок).

## Scope of This Repository (`voiseup`)

**In scope:**

- SIP/PSTN telephony edge (inbound + outbound)
- Real-time voice pipeline: VAD → STT → dialogue → TTS → playback
- Barge-in, turn management, cancellation (`generation_id`)
- Dialogue engine for Вера (structured conversation, not raw LLM chat)
- Event emission to IMVERA Core (verdicts and incidents are **not** decided here)
- Observability: latency traces, call recordings, dialogue logs

**Out of scope (separate services / repos):**

- Family mobile app UI
- Households, auth, billing
- Postgres schema for product data (consume via Core API)
- Notification delivery (TG/SMS/push) — Core + delivery layer
- Safety verdict final authority — IMVERA Core `SafetyEngine`

## Target Architecture (v0 — design intent)

```text
PSTN / mobile / SIP trunk
        │
        ▼
Telephony Edge (SIP/RTP only)
  - answer / hangup / DTMF / codecs / NAT
  - NO dialogue logic
  - NO Vera speech generation
        │
        ▼ continuous PCM16 mono 16 kHz / 20 ms frames
VoiceRuntime (one process per node)
  - 1 CallSession actor per active call until hangup
  - VAD / endpointing / barge-in / playback queue
  - generation_id hard boundary for cancel + stale drop
  - NO business SQL in hot path
        │
   ┌────┴────┬────────┐
   ▼         ▼        ▼
  STT     Dialogue    TTS
          Brain
            │
            ▼
           LLM (renderer assist only — not the owner of state)
        │
        └── async CallEvents ──► IMVERA Core API
```

## Ownership Model (non-negotiable)

```text
ONE RESPONSIBILITY → ONE OWNER

Planner   → what happens next (intent, slot progression)
State     → what is true (facts, slots, pending question)
Renderer  → how to say it (surface text, prosody hints)
Validator → whether it may be said (policy, length, safety handoff)
Realtime  → delivery, timing, cancellation
Transport → SIP/RTP/media bridge only
```

## Status Semantics (product contract)

| Status | Meaning |
|--------|---------|
| GREEN | Контакт подтверждён, тревожных сигналов нет |
| YELLOW | Семье нужно обратить внимание |
| RED | Явная опасность / запрос помощи |
| NO_CONTACT | Не удалось связаться после попыток — **не** «всё ок» |
| TECHNICAL | Ошибка системы — состояние человека **неизвестно** |
| DECLINED | Человек отказался от регулярных звонков |

**Hard rule:** TECHNICAL и NO_CONTACT never map to GREEN.

**NO_CONTACT (точная формулировка):** вызов был успешно доставлен до абонента, но контакт с человеком не установлен. Не использовать «дозвонились» в смысле «ответил».

## Status model (internal — 4 axes)

See [docs/PLAN.md](docs/PLAN.md) v1.2 §6:

```text
delivery_state:  NOT_ATTEMPTED | RINGING | ANSWERED | NOT_ANSWERED | FAILED
technical_state: OK | DEGRADED | FAILED
care_state:      UNKNOWN | GREEN | YELLOW | RED
consent_state:   UNKNOWN | ACTIVE | DECLINED
```

StatusEngine maps axes → 6 public statuses. RED active risk wins over TECHNICAL when both apply.

## Consent

- Регулярные звонки разрешены только после **собственного** согласия подопечного (voice/DTMF).
- Семья не может согласиться за него.
- Молчание ≠ согласие.

## Latency Targets (pilot)

| Metric | P50 | P95 | Gate |
|--------|-----|-----|------|
| speech_end → stt_final | < 800 ms | — | measured |
| stt_final → planner_done | < 500 ms | — | measured |
| phrase_commit → tts_first_pcm | < 200 ms | — | Silero phrase-chunked |
| End-to-end turn | **< 1 s** | **< 1.5–2 s** | live SIP |
| Barge-in stop playback | < 150 ms | < 250 ms | live SIP |

## Audio Contract (v1.1)

**Silero `v5_5_ru` supports 8000 / 24000 / 48000 Hz — not 16000.**  
See [docs/AUDIO_CONTRACT.md](docs/AUDIO_CONTRACT.md) and [docs/PLAN.md](docs/PLAN.md) §3.

```text
PSTN 8kHz → Asterisk → transport → PCM S16LE
  STT branch: resample → 16kHz → Whisper
  TTS branch: Silero @ 8k or 24k → resample if needed → 8kHz → PSTN
```

TTS mode: **phrase-chunked** `apply_tts()` — not native token streaming.

## Deployment Phases

1. **Phase 0** — Agent system + architecture docs (this repo skeleton)
2. **Phase 1** — Loopback voice pipeline (no PSTN): mic → STT → dialogue → TTS
3. **Phase 2** — SIP lab (softphone / local FreeSWITCH)
4. **Phase 3** — PSTN trunk (test numbers)
5. **Phase 4** — Core integration (events, no local verdicts)
6. **Phase 5** — Pilot readiness gate (20–50 families)

## Technology Constraints (initial)

- Language: **Python 3.12+** for runtime services (fast iteration, team familiarity)
- Telephony: **Asterisk ≥22.6** + PJSIP + ARI + ExternalMedia (`chan_websocket`, fallback AudioSocket) — ADR-001
- TTS: **Silero v5_5_ru** phrase-chunked (`apply_tts`) @ 8k or 24k — ADR-002
- STT: faster-whisper large-v3-turbo + streaming wrapper — ADR-003, benchmark required
- LLM: RendererProvider only (no verdict authority); local-first for dev
- StatusEngine: pure domain logic in Phase 2 (not Phase 6)
- Persistence: async only in voice hot path; durable spool for recordings

## What We Learned (constraints, not code to copy)

These are **anti-patterns** from prior experiments — forbidden in voiseup:

- Two FSMs or two dialogue brains in production
- Transport layer generating Vera speech
- Lua (or any dialplan script) as conversation owner
- Hidden or silent cloud fallback
- `generated text == heard text` assumed without trace proof
- `tests green == production ready`
- Fixing production bugs without runtime truth (SHA, active engine, endpoint)

## Repository Layout (target)

```text
voiseup/
├── AGENTS.md
├── PROJECT_CONTEXT.md          ← this file
├── docs/
│   └── adr/                    ← architecture decision records
├── packages/
│   ├── voice_runtime/          ← CallSession, media, barge-in
│   ├── dialogue/               ← Planner, State, Renderer, Validator
│   ├── telephony/              ← SIP edge adapter
│   └── contracts/              ← shared event schemas
├── services/
│   ├── stt/                    ← STT service contract + impl
│   ├── tts/                    ← TTS service contract + impl
│   └── orchestrator/           ← wires runtime + providers
├── tools/
│   └── voice_lab/              ← offline eval, latency bench
└── .agents/skills/             ← agent engineering processes
```

## External Links

- Product: https://imvera.ru/
- Investor / roadmap docs: local copies in team storage (not in repo)
