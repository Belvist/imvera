# IMVERA VoiseUp — Master Plan v1.2 (Architecture Freeze candidate)

> **Статус:** Phase 0 ✅. Phase 1 — contracts + ADR (не pipeline code).  
> **Дата:** 2026-09-06  
> **Ревизия v1.2:** full-duplex topology, 4-axis status model, RED false-alarm protocol, realtime provider contracts, event consistency, LLM wording fix.  
> **Продукт:** [IMVERA](https://imvera.ru/)  
> **Ориентир по голосу:** [Newo.ai](https://newo.ai/) — их метрика (~800 ms), не независимый бенчмарк.

---

## Architecture Freeze v1

После принятия v1.2 **фундамент замораживается**. Любое изменение ownership, audio topology, status axes, event contract или provider interfaces — **только через новый ADR** с explicit supersede.

Запрещено агентам: второй dialogue brain, silent fallback, менять sample-rate boundaries без ADR, ставить LLM authority на RED/GREEN.

---

## Ревизии (changelog)

### v1.2 (2026-09-06)

| # | Изменение |
|---|-----------|
| 1 | **Full-duplex audio topology** — inbound STT ≠ outbound TTS; echo self-barge-in gate Phase 5 |
| 2 | **4 оси статуса** — `delivery_state` + `technical_state` + `care_state` + `consent_state` (вместо `contact_result`) |
| 3 | **RED false-alarm protocol** — `highest_signal_seen`, `active_risk`, `signal_resolution` (ADR-005) |
| 4 | **Provider contracts** — `AsyncIterator[AudioChunk]`, `cancel()`, deadlines, typed errors |
| 5 | **LLM wording** — in latency hot path, NOT in authority path |
| 6 | **Event consistency contract** — event_id, sequence_no, idempotency_key; durable-before-side-effect |
| 7 | Опечатка PCMU/**PCMA**; уточнение формулировки **NO_CONTACT** |

### v1.1

Audio contract Silero 8/24/48k; phrase-chunked TTS; Asterisk chan_websocket; StatusEngine Phase 2; asr_quality; playback accounting; SLO p95.

### v1.0

Базовая гибридная схема FSM + LLM + Safety parallel.

---

## 1. Миссия

Voice + telephony для IMVERA: естественный разговор · детерминированный исход · p50/p95 latency · False GREEN = метрика №1.

### Продуктовые статусы (наружу, 6 штук)

| Статус | Значение |
|--------|----------|
| `GREEN` | Контакт установлен, mandatory checks OK, нет active risk |
| `YELLOW` | Нужно внимание семьи |
| `RED` | Опасность / запрос помощи |
| `NO_CONTACT` | Вызов **доставлен до абонента**, контакт с человеком **не установлен** |
| `TECHNICAL` | Нельзя достоверно утверждать, что нормальная попытка контакта состоялась |
| `DECLINED` | Отказ от регулярных звонков |

> **Языковая оговорка:** «дозвонились» по-русски часто = человек ответил. В коде и UI используем формулировку **«вызов доставлен, контакт не установлен»**, не «дозвонились».

### Ownership (конституция)

```text
Planner       → что делать
State         → что известно
Renderer      → как сказать (LLM assist, NO authority)
Validator     → можно ли говорить
Realtime      → timing, cancel, playback accounting
Transport     → media delivery only
SafetyRules   → deterministic signals
SafetyEngine  → merge → active_risk
StatusEngine  → 4 axes → public_status (6 enum)
```

### Correlation IDs (сквозные)

```text
call_id → turn_id → generation_id → phrase_id → event_id → sequence_no
```

---

## 2. Архитектура (frozen topology)

```text
              PSTN (PCMU/PCMA 8 kHz)
                    ↓
                 Asterisk
                    ↓
    ┌── INBOUND audio (far-end only) ──┐
    │              ↓                    │
    │         TurnManager               │
    │              ↓                    │
    │             STT                   │
    │              ↓                    │
    │           Planner                 │
    │              ↓                    │
    │        FSM / State                │
    │              ↓                    │
    │         Renderer ← LLM            │
    │              ↓                    │
    │         Validator                 │
    │              ↓                    │
    │       PhraseChunker               │
    │              ↓                    │
    │            TTS                    │
    │              ↓                    │
    └── OUTBOUND audio (Vera only) ────┘

Parallel:
  STT/events → SafetyRules + semantic_signals → SafetyEngine → FSM interrupt

  State/events → StatusEngine → public_status

Async:
  Event log (durable) → side effects (incident, API)
```

---

## 3. Full-duplex audio topology (v1.2 — КРИТИЧНО)

### Проблема

Если STT получает outbound TTS Веры как «речь пользователя»:

```text
Vera speaks → STT hears Vera → VAD=true → barge-in → Vera interrupts herself
```

### Правило (обязательно в AUDIO_CONTRACT.md + ADR-001)

```text
INBOUND AUDIO  = far-end only (подопечный)
OUTBOUND AUDIO = Vera TTS only
STT NEVER receives outbound TTS as user speech
```

### Реализация (proposed, ADR-001 spike)

Официальный [Asterisk External Media ARI](https://docs.asterisk.org/Development/Reference-Information/Asterisk-Framework-and-API-Examples/External-Media-and-ARI/) поддерживает media in/out на ExternalMedia channel. Для production AI voice **не смешивать** capture и inject в один undifferentiated stream без echo control.

**Рекомендуемый паттерн (dual-leg, проверено в production AI+Asterisk практике):**

```text
Caller channel
    │
    ├── Capture leg: Snoop(inbound) → ExternalMedia IN → voice-runtime STT input
    │
    └── Inject leg:  voice-runtime TTS output → ExternalMedia OUT → mixing bridge → caller
```

Альтернатива V1: **chan_websocket** с явным разделением inbound/outbound WebSocket streams (если transport поддерживает direction per connection — зафиксировать в ADR-001 spike).

**Не полагаться** на «Asterisk сам уберёт эхо» без теста.

### Gate Phase 5 (обязательный)

```text
TEST: Echo self-barge-in
  Vera speaks 10 sec, elder silent

EXPECTED:
  VAD user_speech = false
  STT user transcript = empty (no Vera text)
  barge_in triggered = false
  playback continues normally
```

FAIL → блокер релиза SIP lab.

### Audio sample rates (verified)

Silero `v5_5_ru`: **8000 / 24000 / 48000 Hz** — [silero-models README](https://github.com/snakers4/silero-models). **Не 16000.**

```text
PSTN PCMU/PCMA 8 kHz
    ↓ Asterisk
PCM S16LE @ negotiated rate (typically 8 kHz slin)
    ├── STT: resample → 16 kHz mono → Whisper
    └── TTS: Silero @ 8 kHz OR 24 kHz → resample if needed → 8 kHz → PSTN
```

ADR-002a: benchmark Silero 8k direct vs 24k→resample на PSTN (Phase 3).

---

## 4. TTS — Silero v5 phrase-chunked

- Модель: `v5_5_ru`, speaker: `kseniya` (ADR-002)
- API: `apply_tts()` — [официально](https://github.com/snakers4/silero-models), **не** native token streaming
- Четыре слоя: text streaming · phrase chunking · TTS inference · audio to phone

---

## 5. Telephony — ADR-001

```text
Primary:   PJSIP + Asterisk ≥22.6 + ARI/Stasis + ExternalMedia + chan_websocket
Fallback:  AudioSocket (TCP_NODELAY mandatory)
Avoid V1:  raw RTP timing in Python without ADR justification
```

Sources: [chan_websocket docs](https://docs.asterisk.org/Configuration/Channel-Drivers/WebSocket/), [External Media ARI](https://docs.asterisk.org/Development/Reference-Information/Asterisk-Framework-and-API-Examples/External-Media-and-ARI/).

Scale caveat (community, not official): chan_websocket degradation reported at 90+ concurrent — monitor on pilot growth.

---

## 6. Status model — 4 оси (v1.2)

### Внутреннее хранение

```text
delivery_state:
    NOT_ATTEMPTED | RINGING | ANSWERED | NOT_ANSWERED | FAILED

technical_state:
    OK | DEGRADED | FAILED

care_state:
    UNKNOWN | GREEN | YELLOW | RED

consent_state:
    UNKNOWN | ACTIVE | DECLINED
```

### Safety sub-model (во время звонка)

```text
highest_signal_seen:
    NONE | POSSIBLE | YELLOW | RED     # монотонно растёт, event log immutable

active_risk:
    NONE | YELLOW | RED                 # может снижаться только по protocol

signal_resolution:
    UNRESOLVED | CONFIRMED | CONFIRMED_FALSE_ALARM
```

**Монотонность `highest_signal_seen`:** `NONE → POSSIBLE → YELLOW → RED`, never decreases.

**`active_risk`:** может стать `NONE` после `CONFIRMED_FALSE_ALARM` по **deterministic confirm protocol** (повторный вопрос + explicit denial + rule match). Event history **не переписывается**.

### Пример false alarm (ADR-005)

```text
STT: "я упала" → highest_signal_seen=RED, active_risk=RED
Human: "Нет, я сказала: я УБРАЛА таблетки"
Protocol: CONFIRMED_FALSE_ALARM (deterministic rules, not LLM alone)
→ active_risk = NONE (or YELLOW if other signals remain)
→ highest_signal_seen = RED (unchanged in log)
→ final public_status: NOT auto-RED if active_risk cleared + care=UNKNOWN/GREEN path
```

Точная таблица final mapping — в ADR-005. **Обязательно до Phase 2 tests.**

### StatusEngine mapping (примеры)

| delivery | technical | care | consent | → public |
|----------|-----------|------|---------|----------|
| NOT_ANSWERED | OK | UNKNOWN | ACTIVE | **NO_CONTACT** |
| NOT_ATTEMPTED | FAILED | UNKNOWN | * | **TECHNICAL** |
| ANSWERED | FAILED | UNKNOWN | ACTIVE | **TECHNICAL** |
| ANSWERED | FAILED | **RED** | ACTIVE | **RED** (RED wins) |
| ANSWERED | OK | GREEN | ACTIVE | **GREEN** |
| ANSWERED | OK | * | DECLINED | **DECLINED** |

**Precedence для public_status:**

```text
credible active RED  >  YELLOW  >  DECLINED  >  GREEN
TECHNICAL / NO_CONTACT — отдельная логика из delivery + technical axes
```

Сценарий №7: `ANSWERED + technical=FAILED + care=UNKNOWN` → **TECHNICAL** (контакт был, исход неизвестен).  
Сценарий №8: `ANSWERED + technical=FAILED + care=RED` → **RED**.

---

## 7. Safety

```text
LLM Observer      → semantic_signals only (NO authority on RED)
STT + Rules       → deterministic_signals
SafetyEngine      → merge → active_risk + highest_signal_seen
```

LLM **in latency hot path, NOT in authority path** (см. §11).

---

## 8. STT contract

```json
{
  "text": "...",
  "is_final": true,
  "avg_logprob": -0.31,
  "no_speech_prob": 0.02,
  "critical_terms": [],
  "asr_quality": "GOOD"
}
```

`asr_quality` — наша функция, не сырой Whisper confidence.

---

## 9. Playback accounting

Per `phrase_id`: generated_text, played_samples, interrupted, heard_text_estimate.  
Renderer не считает инструкцию услышанной при `interrupted=true`.

---

## 10. Provider contracts (v1.2 — realtime-oriented)

### Interfaces (Phase 1 `packages/contracts/providers.py`)

```python
class STTProvider(Protocol):
    async def transcribe_partial(...) -> STTPartial: ...
    async def transcribe_final(...) -> STTResult: ...

class TTSProvider(Protocol):
    async def synthesize(
        text: str,
        *,
        generation_id: str,
        deadline: float,
    ) -> AsyncIterator[AudioChunk]: ...
    async def cancel(generation_id: str) -> None: ...

class RendererProvider(Protocol):
    async def render_stream(
        ...,
        generation_id: str,
        deadline: float,
    ) -> AsyncIterator[str]: ...
    async def cancel(generation_id: str) -> None: ...
```

Silero impl: `apply_tts()` → full phrase PCM → **adapter slices to AudioChunks** → AsyncIterator.

### Typed errors

```text
ProviderTimeout
ProviderUnavailable
ProviderCancelled
ProviderInvalidOutput
```

Runtime uses `generation_id` + `cancel()` for barge-in — must be in contract, not only in diagram.

Voice-runtime **не знает** Silero/Whisper/OpenAI — only providers.

---

## 11. LLM — hot path vs authority path

```text
LLM:
  IN latency hot path     (STT final → Planner → Renderer → phrase → TTS)
  NOT IN authority path   (no RED/GREEN/RED resolution; semantic_signals only)
```

Оптимизация Renderer latency — **обязательна** для SLO.

---

## 12. Event consistency contract (v1.2)

Phase 1: define contract only. NATS/Postgres cluster — не сейчас.

### Critical event fields

```json
{
  "event_id": "evt-uuid",
  "call_id": "call-123",
  "sequence_no": 48,
  "occurred_at": "2026-09-06T12:00:00Z",
  "event_type": "RED_SIGNAL_CONFIRMED",
  "schema_version": 1,
  "payload": {},
  "idempotency_key": "call-123:red:48"
}
```

### Rule

```text
critical state transition
    ↓
event durably recorded (spool)
    ↓
side effect (incident, notification)
```

Never: side effect first → crash → no event.  
Never: retry without idempotency → duplicate family alerts.

`sequence_no` monotonic per `call_id`.

---

## 13. SLO

| Metric | P50 | P95 |
|--------|-----|-----|
| end-of-speech → first phone audio | <1.0s | <1.5–2.0s |
| barge-in stop | <150ms | <250ms |

Operational: TTS queue starvation, dropped frames (MEDIA_XOFF), STT/LLM/turn timeouts.

---

## 14. Tech stack

| Component | V1 |
|-----------|-----|
| Telephony | Asterisk ≥22.6, dual-leg media |
| STT | faster-whisper large-v3-turbo (hypothesis until PSTN benchmark) |
| TTS | Silero v5_5_ru phrase-chunked |
| LLM | RendererProvider (latency hot path, no authority) |
| Dialogue | FSM + Planner + Validator (Phase 2) |
| Status | StatusEngine 4-axis (Phase 2) |

4 blocks: `telephony` · `voice-runtime` · `speech-services` · `backend-mock` (Phase 6)

**Не строить сейчас:** Kubernetes, NATS cluster, speech-to-speech V3, own PSTN operator.

---

## 15. Фазы

### Phase 0 ✅ Agent system

### Phase 1 ✅ Contracts + ADR

- [x] `docs/ARCHITECTURE.md`
- [x] `docs/AUDIO_CONTRACT.md`
- [x] `docs/DIALOGUE_SPEC.md`
- [x] ADR-001..005 (+ 002a plan)
- [x] `packages/contracts/`
- [x] `pyproject.toml` + `LAUNCH.md`
- [x] **Gate:** `make test` — 5 passed

### Phase 2 — Domain core (no audio) ← NEXT

FSM, Planner, Validator, SafetyEngine, **StatusEngine (4 axes)**, incident SM, 12+ tests with **final public_status**.

### Phase 3 — Speech lab

STT/TTS providers, Silero 8k vs 24k benchmark, asr_quality.

### Phase 4 — Realtime runtime

CallSession, TurnManager, barge-in, provider cancel, playback accounting, loopback latency.

### Phase 5 — Asterisk SIP

Dual-leg media, **echo self-barge-in gate**, Zoiper E2E.

### Phase 6 — Backend mock

HTTP API, durable event spool, idempotency.

### Phase 7 — PSTN pilot

Linux GPU, trunk, IMVERA Voice Benchmark, production-readiness.

---

## 16. Тест-корпус (расширенный)

| # | Сценарий | public_status |
|---|----------|---------------|
| 1 | Check-in OK | GREEN |
| 2 | «голова кружится» | YELLOW |
| 3 | «упала, не могу встать» | RED |
| 4 | Отказ | DECLINED |
| 5 | Звонил, не ответил | NO_CONTACT |
| 6 | Trunk down | TECHNICAL |
| 7 | Ответил, 40s, STT died | TECHNICAL |
| 8 | Ответил, STT died, active RED | **RED** |
| 9 | «не звоните» + «упала» | **RED** |
| 10 | False alarm «упала»→«убрала таблетки» | per ADR-005 |
| 11 | Vera 10s, silent elder | echo gate PASS |
| 12 | Barge-in real speech | stop <250ms p95 |

---

## 17. Источники (проверено)

| Утверждение | Источник | Статус |
|-------------|----------|--------|
| Silero 8/24/48 kHz, not 16k | [silero-models](https://github.com/snakers4/silero-models) | ✅ verified |
| Silero `apply_tts()` | [silero-models](https://github.com/snakers4/silero-models) | ✅ verified |
| External Media ARI in/out | [Asterisk docs](https://docs.asterisk.org/Development/Reference-Information/Asterisk-Framework-and-API-Examples/External-Media-and-ARI/) | ✅ verified |
| chan_websocket framing | [Asterisk WebSocket driver](https://docs.asterisk.org/Configuration/Channel-Drivers/WebSocket/) | ✅ verified |
| Dual-leg capture/inject for AI | Industry pattern (MYLINEHUB, community) | ⚠️ practice, ADR-001 spike required |
| chan_websocket 90+ call caveat | [Asterisk forum](https://community.asterisk.org/t/audio-distortion-lag-with-chan-websocket-externalmedia-at-90-concurrent-calls-asterisk-22-8-2/112483) | ⚠️ community report |
| Whisper PSTN elderly Russian WER | — | ❌ not verified — benchmark Phase 3/7 |

**Правило:** если нет ✅ — писать «гипотеза» / «требует spike», не «будет работать».

---

## 18. Вердикт

**v1.2 — Master Plan, Architecture Freeze candidate.**

После принятия: Phase 1 = контракты только.  
Silero V1 — да. Whisper — гипотеза до benchmark.  
Asterisk + ARI + separated media legs — да для пилота.

**Следующая команда:** «начинай Phase 1» → `packages/contracts/` + `AUDIO_CONTRACT.md` + ADR-001..005.
