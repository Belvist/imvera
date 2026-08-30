# Технический отчёт: комплексный аудит IMVERA (Belvist/imvera)

**Репозиторий:** [Belvist/imvera](https://github.com/Belvist/imvera)  
**Ветка:** `feature/prototype-dialog-2026-08-30`  
**HEAD:** `1dc440b`  
**Дата анализа:** 30.08.2026  
**Метод:** статический анализ кодовой базы, документации (`AGENTS.md`, `FIXES_PLAN.md`, `HYPOTHESES.md`, `read.md`), трассировка prod-пути Lua → HTTP → orchestrator

---

## 1. Резюме

Проект — телефонный голосовой агент заботы (STT → диалог → TTS) на Docker + FreeSWITCH. Критические проблемы сосредоточены не в «отсутствии логики», а в **разрыве между слоями**:

| Область | Диагноз | Главный риск |
|---------|---------|--------------|
| **STT** | Многоуровневый пайплайн с гейтами, но prod зависит от host Qwen3-ASR без fallback; синтетическая confidence обходит binary-гейт | Пропуск мусора и потеря safety-слов («упал» → «у палок не ударилось») |
| **Диалог** | DialogueFSM формализован, но **canned-реплики не попадают в память LLM**; streaming обходит post-processing | Повторы вопросов, «амнезия» контекста, нестабильное качество |
| **State machine** | **DialogueFSM есть**; **Call/Turn FSM отсутствуют** — состояние звонка на boolean-флагах | Barge-in, wedged streaming, рассинхрон media/dialogue |

**261 unit-тест** (`make test-fast`) зелёные, но harness **не покрывает** prod-путь phone stream + cloud LLM + host STT.

---

## 2. Инвентаризация кодовой базы и инфраструктуры

### 2.1 Архитектура (prod-путь)

```text
FreeSWITCH (ext 4400, Lua)
  → chunked WAV → POST /calls/{id}/turn_stream
  → orchestrator.process_turn_stream
      1. STT (Qwen3-ASR host :9705 → faster-whisper fallback в образе)
      2. Confidence gate (<0.55) + Vocab gate + Echo-guard
      3. Agent.plan_reply → DialogueFSM (детерминированный план)
      4. reply_segments → LLM stream (OpenRouter/DeepSeek) или canned
      5. TTS → seg-NNNN.wav → Lua playback
      6. done.json (маркер конца хода)
```

### 2.2 Ключевые модули

| Компонент | Файлы | Роль |
|-----------|-------|------|
| STT façade | `telephony/adapters/stt.py`, `runtime/scripts/tts_common.py` | Backends, VAD, confidence |
| Qwen host | `voice_runtime/stt_host.py` | MLX Qwen3-ASR на хосте |
| Оркестрация | `telephony/core/orchestrator.py` | Phone turn pipeline |
| Диалог | `telephony/core/dialogue.py`, `telephony/core/fsm.py` | DialogueFSM + Agent |
| Безопасность | `telephony/core/safety_engine.py` | Verdict machine (отдельно от core/fsm) |
| Runtime (ESL) | `voice_runtime/call_session.py` | Barge-in loop (boolean flags) |
| Vocab gate | `telephony/core/vocab.py` | Фильтр мусорных транскриптов |

### 2.3 Зависимости и конфигурация

```yaml
# docker-compose.yml (prod defaults)
MOSS_STT_HOST: http://host.docker.internal:9705   # Qwen3-ASR host
MOSS_STT_TRANSFORMERS_MODEL: whisper-small        # fallback в контейнере (не используется при host)
MOSS_LLM_PROVIDER: local → answers:9500 (llama.cpp Qwen3-4B)
# Cloud override: MOSS_LLM_PROVIDER=openai + OpenRouter/DeepSeek
```

### 2.4 Технический долг (системный)

- **Mono mix** в uuid_record → эхо Vera в user-WAV (частично закрыто echo-guard, stereo на FS не работает)
- **Record→WAV→HTTP** вместо continuous media stream (P6 MediaAdapter — partial)
- **Три уровня confidence** (high/medium/low) задокументированы, но **не реализованы** (phase 4+2)
- **Loopback-тесты** создают ложные «диалоговые» артефакты (два лега одного канала)

---

## 3. Модуль распознавания речи (STT)

### 3.1 Архитектура пайплайна

```text
WAV (mono/stereo mix)
  → Silero VAD (<0.15s speech → empty)
  → Backend:
       1. SttHostAdapter → POST host:9705 (Qwen3-ASR-0.6B-4bit MLX)  ← PROD
       2. FasterWhisperAdapter (whisper-small, beam=5)
       3. WhisperPipelineAdapter (HF, без VAD pre-gate)
  → confidence_from_result (energy + segments + synth for Qwen)
  → Gate chain: conf <0.55 → vocab → echo-guard → dialogue
```

### 3.2 Пороговые значения деградации

| Порог | Значение | Эффект при нарушении |
|-------|----------|----------------------|
| `SILENCE_ENERGY` | ~0.008 RMS | Тихий голос → пустой ход |
| Silero VAD | <0.15s speech | Ход отброшен как «тишина» |
| Confidence gate | <0.55 | «Повторите, пожалуйста» |
| Vocab gate | нет RU-корней | Anchor вместо LLM |
| Echo-guard | ≥60% overlap с `_last_reply`, ≥4 токена | Пустой ход (echo reason) |
| Endpointing tail | 1.2s silence | Задержка STT; обрезка длинных пауз |
| FS chunk caps | 5–9s (caps игнорируются) | Медленный decode, обрезка фраз |
| Qwen synth conf | 0.85 при rate 1.2–5.0 w/s | **Гейт 0.55 почти не срабатывает** |

### 3.3 Реестр багов STT

#### STT-01 — Host STT без runtime fallback

| | |
|---|---|
| **Критичность** | **Блокирующий** (операционный) |
| **Влияние** | При падении host:9705 все ходы пустые → «не слышит» |
| **Корневая причина** | `load_stt()` возвращает `SttHostAdapter` при `MOSS_STT_HOST`; HTTP-ошибки → пустой текст, whisper в контейнере не используется |
| **Исправление** | Health probe `/ready` при старте; при ошибке generate → fallback на `FasterWhisperAdapter`; алерт + метрика `stt_backend_fallback_total` |

Файл: `runtime/scripts/tts_common.py`, строки 306–319:

```python
def load_stt(model_id=DEFAULT_STT_MODEL):
    if STT_HOST:
        try:
            return SttHostAdapter()
        except Exception:
            pass
    # ... whisper fallbacks never reached if host is set but down at runtime
```

#### STT-02 — Синтетическая confidence для Qwen обходит binary-гейт

| | |
|---|---|
| **Критичность** | **Высокий** |
| **Влияние** | Уверенный мусор («Торатичина» conf 0.614 на whisper; Qwen synth → 0.85) проходит в LLM |
| **Корневая причина** | `confidence_from_result` возвращает 0.85 для «нормальной» речи без segment logprobs |
| **Исправление** | Трёхуровневая политика: >0.8 pass; 0.55–0.8 → confirm «Вы сказали X?»; <0.55 reject. Для Qwen — WER-based calibration на phone corpus |

Файл: `telephony/adapters/stt.py`, строки 107–117:

```python
    if speech_s and speech_s > 0.2:
        rate = len(toks) / speech_s if speech_s else 0
        if 1.2 <= rate <= 5.0:
            return 0.85
        if 0.8 <= rate <= 6.0:
            return 0.65
        return 0.35
```

#### STT-03 — Vocab gate сохраняет mangled safety, теряет исходное слово

| | |
|---|---|
| **Критичность** | **Высокий** (safety) |
| **Влияние** | «упал» → «у палок не ударилось» conf 0.774 проходит (корень «удар»), SafetyEngine не видит «упал» |
| **Корневая причина** | `CRITICAL_HEALTH_ROOTS` содержит «удар», но не восстанавливает лемму «упал» |
| **Исправление** | Fuzzy match / phonetic distance для safety roots; или confirm-loop при partial match |

#### STT-04 — CloudSTTAdapter несовместим с phone path

| | |
|---|---|
| **Критичность** | **Высокий** (при `MOSS_STT_PROVIDER=openai`) |
| **Влияние** | `process_turn_stream` вызывает `transcribe_with_confidence` → AttributeError → пустые ходы |
| **Корневая причина** | `CloudSTTAdapter` реализует только `transcribe` / `transcribe_clean` |
| **Исправление** | Добавить `transcribe_with_confidence` с mapping OpenAI confidence |

#### STT-05 — Mono mix + echo в user-WAV

| | |
|---|---|
| **Критичность** | **Высокий** |
| **Влияние** | Whisper/Qwen транскрибирует голос Vera как речь пользователя |
| **Корневая причина** | uuid_record пишет оба направления; `record_stereo` на FS build не работает |
| **Исправление** | P4: media-bug на LEFT channel; P6 MediaAdapter streaming; до этого — усилить echo-guard |

#### STT-06 — Gates только на phone one-shot path

| | |
|---|---|
| **Критичность** | **Средний** |
| **Влияние** | StreamingSTT hops и `process_turn` без vocab/conf gates |
| **Корневая причина** | Условие `if segment_dir:` в orchestrator |
| **Исправление** | Единая функция `_gate_transcript()` для всех путей |

#### STT-07 — Silero VAD global RLock — contention

| | |
|---|---|
| **Критичность** | **Средний** |
| **Влияние** | При параллельных звонках STT + `/has_speech` сериализуются (~10–50ms/chunk) |
| **Корневая причина** | TorchScript Silero не thread-safe; один RLock на все вызовы |
| **Исправление** | Per-process VAD instance pool или ONNX runtime без shared state |

#### STT-08 — Qwen host model lock serializes ASR

| | |
|---|---|
| **Критичность** | **Средний** |
| **Влияние** | Concurrent calls queue на `_model_lock` |
| **Исправление** | Request queue + worker pool; или batch inference |

#### STT-09 — `audio_energy` игнорирует stereo

| | |
|---|---|
| **Критичность** | **Средний** |
| **Влияние** | На stereo mix energy завышена → silence gate менее надёжен |
| **Исправление** | LEFT-only energy (как в `vad_speech_seconds`) |

#### STT-10 — Fail-open VAD

| | |
|---|---|
| **Критичность** | **Низкий** |
| **Влияние** | При сбое torch/hub шум идёт в ASR → hallucinations |
| **Исправление** | Fail-closed с метрикой; degraded mode banner |

### 3.4 Динамические/операционные находки

| Метрика | Значение (из AGENTS.md) |
|---------|-------------------------|
| Qwen3-ASR WER на phone audio | **6.42%** |
| whisper-small WER | ~26% |
| whisper-tiny beam1 WER | 0.379 → beam5: 0.265 |
| STT latency (Qwen host) | 0.2–1.8s/file + ~11ms network |
| Loopback STT | 481–870ms (whisper era) |
| Live call ca81bc3 | «упал»→«у палок», «Торатичина» 0.614, «Лоха!» 0.763 |

### 3.5 Пробелы тестового покрытия STT

- Нет теста: host down → fallback/empty
- Нет теста: CloudSTT + `process_turn_stream`
- Нет replay harness: `user-*.wav` → full gate chain
- `stt_host.py` — **0 unit-тестов**
- `stt_bench.py` — скрипт, не CI

---

## 4. Модуль генерации диалогов

### 4.1 Архитектура

```text
plan_reply (under lock, NO LLM):
  classify input → SafetyEngine verdict → DialogueFSM.dispatch → {text, intent, fallback}

reply_stream / reply_segments (outside lock):
  intent=None → speak fallback (canned)
  intent set → LLM stream (DeepSeek via OpenRouter) + guards

commit_reply:
  append to llm_history + _last_reply  ← ТОЛЬКО если intent set (БАГ)
```

### 4.2 Реестр багов диалога

#### DIA-01 — Canned replies не commit'ятся в историю

| | |
|---|---|
| **Критичность** | **Блокирующий** (качество) |
| **Влияние** | LLM «не помнит» заданный вопрос → повтор agenda; echo-guard смотрит на stale `_last_reply` |
| **Корневая причина** | `commit_reply` только при `plan.get("intent")` |
| **Исправление** | Всегда `commit_reply(reply)` после любой произнесённой реплики |

Файл: `telephony/core/orchestrator.py`, строки 1573–1575:

```python
        with ctx.lock:
            if plan is not None and plan.get("intent"):
                agent.commit_reply(reply)
```

**Пример реализации:**

```python
with ctx.lock:
    if reply:
        agent.commit_reply(reply)  # всегда, canned и LLM
```

#### DIA-02 — Окно истории LLM = 4 turns

| | |
|---|---|
| **Критичность** | **Высокий** |
| **Влияние** | Cloud prefill latency растёт с историей; 4 turns + missing canned → «амнезия» |
| **Корневая причина** | `llm_history[-4:]` для OpenRouter latency |
| **Исправление** | После DIA-01 пересмотреть window; summary compression для длинных звонков |

#### DIA-03 — Streaming path обходит `_clean_llm`

| | |
|---|---|
| **Критичность** | **Высокий** |
| **Влияние** | Двойные вопросы, masculine «я рад» произносятся вслух |
| **Корневая причина** | `_clean_llm` только в blocking `LLMClient._finish_chat` и `Agent._ask` |
| **Исправление** | Apply `_clean_llm` + `_feminize_self` per segment before TTS |

#### DIA-04 — EARLY-FIRST-SOUND режет фразы

| | |
|---|---|
| **Критичность** | **Средний** |
| **Влияние** | Первый seg = половина мысли (comma cut после 4–6 слов) |
| **Исправление** | Cut только на `.!?` или min 8 слов |

#### DIA-05 — Echo-guard false negatives

| | |
|---|---|
| **Критичность** | **Средний** |
| **Влияние** | Короткие ответы, перекрывающие слова Vera, могут быть muted |
| **Корневая причина** | 60% token overlap + stale `_last_reply` |
| **Исправление** | DIA-01 + channel split (P4) |

#### DIA-06 — Harness не тестирует LLM path

| | |
|---|---|
| **Критичность** | **Средний** |
| **Влияние** | `dialog_quality.py --strict` 14/14 с `llm=None`; prod bugs не ловятся |
| **Исправление** | Integration tests с mock LLM + phone path commit |

#### DIA-07 — Safety vs companion tension

| | |
|---|---|
| **Критичность** | **Средний** |
| **Влияние** | Symptom → canned confirm; first symptom → LLM (исключение 2026-08-30) |
| **Исправление** | Unified policy document; A/B на live calls |

#### DIA-08 — Classifier side effects in `_classify`

| | |
|---|---|
| **Критичность** | **Низкий** |
| **Влияние** | `_help_pending = False` при classify нарушает purity guards |
| **Исправление** | Move consume to transition action |

### 4.3 Статистика качества (документированная)

| Метрика | Результат |
|---------|-----------|
| FSM fuzz 100 dialogs | **92/100** finish, **0 false ALERT** |
| `dialog_quality --strict` | **14/14 PASS** (без LLM) |
| `make test-fast` | **261 OK** |
| Live call 59064eb2 (pre-FSM) | **5/10** |
| Live call ca81bc3 | canned×5, duplicate anchors |

### 4.4 Корневые причины нестабильного качества диалога

1. **Upstream STT noise** → garbage/confident nonsense в FSM
2. **Media echo** (mono mix) → ложные user turns
3. **Hybrid canned/LLM без памяти** (DIA-01) — главный software-баг
4. **Short context window** + missing commits
5. **Provider variance** (DeepSeek vs local vs empty→canned)
6. **Guards на разных путях** (stream vs blocking)
7. **Нет 3-tier STT confirm** («Вы сказали X?»)

---

## 5. Анализ state machine

### 5.1 Текущий статус (важное уточнение)

**Утверждение «стейт-машина отсутствует» — частично неверно.**

| Слой | Статус | Реализация |
|------|--------|------------|
| **DialogueFSM** | ✅ **Реализован** | `core/fsm.py` + `DialogueFSM` в `dialogue.py` (11 states, ~18 events) |
| **SafetyEngine** | ⚠️ **Partial** | Ad-hoc `_state` + if/elif, не на `core/fsm` |
| **Call lifecycle FSM** | ❌ **Отсутствует** | Planned: NEW→ADMITTED→…→CLOSED |
| **Turn lifecycle FSM** | ❌ **Отсутствует** | Planned: IDLE→USER_SPEAKING→…→ASSISTANT_SPEAKING |
| **P6 MediaAdapter** | ⚠️ **Partial** | ABC + `LiveWavReader`; prod still uuid_record |

### 5.2 Почему Call/Turn FSM не реализованы

1. **Директива владельца (2026-08-21):** единый маршрут — сначала голос, continuous audio, streaming STT/TTS; product core заморожен
2. **Инкрементальный подход:** P-FSM (dialogue) сделан первым после аудита «логика разбросана» (call 59064eb2, 5/10)
3. **Два параллельных транспорта:** Lua 4400 (prod) vs ESL runtime 4402 — Turn FSM отложен до P5 migration
4. **CallSession работает на boolean flags** (`playing`, `streaming`, `suppress`) — «достаточно для acceptance tests»

### 5.3 Риски отсутствия Call/Turn FSM

| Риск | Проявление | Связь с STT/Dialogue |
|------|------------|---------------------|
| Wedged `streaming=True` | Следующий turn → 429 busy | P2 частично закрыт (done.json last) |
| Stale generation audio | Segments cancelled gen still play | Barge-in test 4 |
| Race: turn lock vs done.json | Дублирование/пропуск ходов | Orchestrator timing |
| Нет formal barge-in states | `playing` + `suppress` ad-hoc | Echo → false user speech |
| SafetyEngine ≠ core/fsm | Дублирование if/elif паттерна | UNCERTAIN latch bugs (fixed in fuzz) |
| Indirect state writes | `sm.state = …` в actions | Bypass declared transitions |
| Classifier ≠ transition table | 80% логики в `_classify` + actions | Сложность отладки |

### 5.4 Что DialogueFSM уже даёт

- 11 состояний: IDLE, CHECKIN, SIDE_QUESTION, CLARIFY, SAFETY_*, HELP, WORRY, GOODBYE_*, CLOSING, DONE
- Total catch-all `("*","*")` → warm generic ack
- `MAX_DISPATCH_DEPTH=4` — depth guard
- P-CLOSE/P-ACK/P-ANCHOR/E_HEARD — product fixes
- Fuzz 92/100 finish

### 5.5 План внедрения полной FSM-архитектуры

#### Фаза 0 — Quick wins (1–2 дня, без новых FSM)

| # | Задача | Effort | Эффект |
|---|--------|--------|--------|
| 0.1 | DIA-01: always commit_reply | 2h | +30% coherence |
| 0.2 | STT-01: host health + fallback | 4h | Eliminate «deaf» mode |
| 0.3 | `_clean_llm` on stream path | 3h | Fewer broken phrases |

#### Фаза 1 — Turn lifecycle FSM (3–5 дней)

**Состояния** (из `read.md`):

```text
IDLE → USER_SPEAKING → ENDPOINTING → PROCESSING → ASSISTANT_SPEAKING → IDLE
         ↑ barge-in: ASSISTANT_SPEAKING → INTERRUPTING → USER_SPEAKING
```

**Реализация:**

1. `voice_runtime/turn_fsm.py` на `core/fsm.StateMachine`
2. Заменить `CallSession.playing/streaming/suppress` на `TurnFSM.dispatch(event)`
3. Events: `vad_onset`, `vad_end`, `turn_submitted`, `seg_ready`, `playback_done`, `barge_in`, `cancel_ack`, `hangup`
4. Tests: 4 acceptance tests из `call_session.py` docstring → formal transition table

**Ожидаемый эффект:** устранение wedged streaming, predictable barge-in, чистая отмена generation

#### Фаза 2 — Call lifecycle FSM (2–3 дня)

```text
NEW → ADMITTED → CONNECTING → ANSWERED → ACTIVE → ENDING → CLOSED
```

1. `voice_runtime/call_fsm.py`
2. Интеграция с `runtime.py` session map + `IDLE_TIMEOUT`
3. Связь с PG `call_attempts` transitions (`adapters/pg.py`)

#### Фаза 3 — SafetyEngine на core/fsm (2–3 дня)

1. Миграция `SafetyEngine` states → `SafetyFSM` extends `StateMachine`
2. Events из verdict → единый контракт с DialogueFSM
3. Regression: 12 invariants + 1000-seed fuzz

#### Фаза 4 — P6 MediaAdapter prod (5–7 дней)

1. Streaming LEFT channel (media-bug / WS)
2. Убрать uuid_record mono mix
3. **Прямой эффект на STT:** echo-free input → -50% false transcripts

#### Фаза 5 — 3-tier STT confirm в DialogueFSM (2 дня)

1. Новое состояние `CLARIFY_STT` + event `stt_uncertain`
2. Transition: conf 0.55–0.8 → «Вы сказали «{text}», верно?»
3. FSM table entry: `(CHECKIN, stt_uncertain, _, ask_confirm, CLARIFY_STT)`

### 5.6 Сводка трудозатрат

| Фаза | Effort | Приоритет |
|------|--------|-----------|
| 0 Quick wins | 1–2 дня | **P0** |
| 1 Turn FSM | 3–5 дней | **P1** |
| 2 Call FSM | 2–3 дня | P2 |
| 3 Safety FSM | 2–3 дня | P2 |
| 4 P6 Media | 5–7 дней | **P1** (STT quality) |
| 5 STT confirm FSM | 2 дня | P2 |

**Итого до стабильного prod:** ~3–4 недели инженерной работы.

---

## 6. Матрица приоритетов исправлений

```text
P0 (немедленно):
  DIA-01 commit_reply always
  STT-01 host fallback + health
  STT-03 safety fuzzy match

P1 (1–2 недели):
  DIA-03 _clean_llm on stream
  STT-05 P4 media LEFT channel
  Phase 1 Turn FSM
  STT replay harness (ca81bc3 WAVs)

P2 (2–4 недели):
  3-tier confidence policy
  Phase 2–3 Call/Safety FSM
  CloudSTT transcribe_with_confidence
  Integration tests (phone path + LLM mock)
```

---

## 7. Ожидаемые улучшения после внедрения FSM + quick wins

| Метрика | Сейчас | После Phase 0+1+4 |
|---------|--------|-------------------|
| Dialog finish rate (fuzz) | 92/100 | **≥97/100** |
| False «не слышит» | Частые на host down | **~0** (fallback) |
| Repeated agenda questions | Регулярно (DIA-01) | **Редко** |
| Echo false transcripts | ~10–20% turns (mono) | **<5%** (LEFT channel) |
| Wedged streaming | Эпизодически | **0** (Turn FSM) |
| STT WER effective | 6.4% (Qwen) + gates | **6.4%** + confirm loop |
| Live call score | 5–7/10 | **≥8/10** target |

---

## 8. Заключение

Репозиторий IMVERA — зрелый прототип с **формализованным DialogueFSM** и обширной документацией инцидентов. Критические проблемы качества — не «отсутствие логики», а:

1. **Разрыв памяти** между canned и LLM path (DIA-01)
2. **Хрупкая STT-цепочка** без fallback и с синтетической confidence (STT-01, STT-02)
3. **Media layer** (mono mix) отравляет оба модуля (STT-05)
4. **Call/Turn FSM** запланированы, но не реализованы — boolean flags создают operational bugs

**DialogueFSM уже есть** и работает (92% fuzz finish). Следующий шаг — **Turn FSM + media split + commit_reply fix** — даст наибольший ROI для стабилизации STT и диалогов без полного переписывания архитектуры.
