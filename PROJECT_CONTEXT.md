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

**Out of scope (until integrated):**

- External IMVERA Core deployment (use in-repo `services/core` per ADR-008 until verified API exists)
- Family mobile app UI (use `apps/family-web` when no external client)

**Previously out of scope — now in-repo per ADR-008:**

- Minimal Core API (`services/core`): families, consent, scheduler, call results for app
- Postgres `voice.*` and `core.*` schemas (see `migrations/`)

**Still out of scope:**

- Notification delivery implementation beyond one pilot channel (TG bot)
- Safety verdict final authority — Core `SafetyEngine` projection

## Target Architecture (production path — ADR-013 / ADR-014)

Chosen. **Not accepted** until ADR-014 gates. Do not start a fourth system.

```text
SIP operator
→ FreeSWITCH
→ mod_imvera_audio
→ CallActor
→ VAD
→ GigaAM
→ DialogueEngine
→ local LLM only when needed
→ Silero TTS
→ FreeSWITCH
→ caller
```

Transport (SIP/RTP) never generates Vera speech. `canonical_assistant_text == phone_spoken_text`.  
LLM is interpretation assist, not owner of state or verdicts.  
Feature freeze until 100 consecutive full calls — see ADR-014.

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
| End-to-end turn | **p50 < 1 s** | **p95 ≤ 2 s** | release profile (ADR-008 §15) |
| Barge-in stop playback | p50 < 150 ms | p95 < 250 ms | live / mic |

> **Single SLO source:** release profile in ADR-008 / product spec §15. Older per-stage gates are diagnostic only.

## Audio Contract (v1.2 — ADR-008)

**Production path during ADR-014 freeze:** GigaAM (STT) + Silero TTS. ADR-003 / ADR-006 are historical benchmarks — not a license to swap models until gates pass.

Provider selection records: **ADR-003 (STT), ADR-006 (TTS)**.

```text
PSTN / SIP trunk → FreeSWITCH → PCM S16LE (directional)
  STT: GigaAM v3 RNNT (local)
  TTS: Silero (local) → FreeSWITCH → caller
```

**20 ms frame sizes (PCM16):**

```text
16 kHz → 320 samples → 640 bytes
 8 kHz → 160 samples → 320 bytes
```

TTS mode: streaming PCM chunks when adapter supports it; phrase-chunked acceptable with honest latency accounting.

See [docs/AUDIO_CONTRACT.md](docs/AUDIO_CONTRACT.md) and [docs/adr/008-product-milestones-voice-core.md](docs/adr/008-product-milestones-voice-core.md).

## Deployment Phases (ADR-008 milestones)

1. **M0** — ADR-008, doctor, doc sync
2. **M1** — Mic loopback: real STT + LLM interpretation + TTS + PostgreSQL
3. **M2** — Dialogue/audio integrity (barge-in, ledger, single CALL_ENDED)
4. **M3** — Core inbox, family app, scheduler, notification channel
5. **M4** — Asterisk SIP lab → PSTN trunk
6. **M5** — Pilot deploy, load, rollback evidence

## Technology Constraints (initial)

- Language: **Python 3.12+** for runtime services (fast iteration, team familiarity)
- Telephony: **FreeSWITCH** + `mod_sofia` + PCM WebSocket bridge — ADR-013 (production)
- Telephony lab: Asterisk (`lab/asterisk/`), LiveKit (`archive/telephony/livekit/`) — not production
- STT: **Qwen3-ASR** primary candidate per ADR-003; benchmark before release
- TTS: **CosyVoice3** primary candidate per ADR-006; benchmark before release
- LLM: interpretation (SemanticPayload) + Renderer; local inference workers; no verdict authority
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
