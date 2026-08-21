# Инженерный план MossVoice → IMVERA (до продуктового уровня)

Статус: v1 · 2026-08-19 · Входные данные: `HYPOTHESES.md` (125 гипотез, 30 подтверждённых багов), ревью IMVERA Core, завершённые Шаги 1–2 (декомпозиция, 69 тестов зелёные).

Принцип метода журнала: **каждое инженерное решение ссылается на номер гипотезы.** Идентификаторы в скобках — это источники решения.

---

## 0. Цель: что значит «продуктово готово»

Продукт: **автоматический дозвон/приём звонков пожилым подопечным, определение их состояния (Core) и уведомление семьи (TG/SMS/голос).** «Готово» = система держит реальную эксплуатацию без человека в контуре каждый день:

1. Реальный звонок по SIP (Exolve/аналог) → LiveKit → streaming STT → диалог → streaming LLM → streaming TTS → barge-in.
2. Вердикт и инциденты решает **Core**, а не голосовой рантайм (A1, S5).
3. Всё состояние в **Postgres** (единственный источник истины), Redis — только locks/кэш/очередь (A4, A5).
4. Уведомления не теряются при падении очереди/TG (outbox) (A6, A7).
5. Безопасность персданных: consent, retention, шифрование, аудит, исполнимость удаления (P8, P9).
6. Техническая ошибка **никогда** не выглядит как NO_CONTACT или GREEN (S9, I6, D15).
7. Наблюдаемость и восстановление: сбой любого сервиса → деградация, а не потеря звонка (A4–A8, F5).
8. Метрики продукта замеряемы (успешность дозвона, SLA эскалации, доля ложных RED, стоимость/звонок).

Критерий выхода к продуктовому плану: **вертикальный срез «звонок → событие → PG → вердикт → инцидент → TG» работает на failure-drills, а SafetyEngine даёт 0 ложных GREEN на регрессионном корпусе.**

**Скорость — отдельный продукт-гейт, решается на Фазе 4 цифрами, а не архитектурой (см. §14).** Текущий CPU-стек (Qwen3-1.7B + Whisper-small + MOSS-TTS-Nano на CPU) даёт ~10–30 с на реплику и НЕ сравним с newo.ai; target-стеки (GPU-конвейер / realtime-модель) — в §14.

---

## 1. Подходы к доставке (рассмотренные варианты)

| Вариант | Путь успеха | Путь провала | Вердикт |
|---|---|---|---|
| **V1. Big-bang**: сразу весь Core-скелет + перенос всей логики, потом голос | чистая архитектура с 1-го дня | месяцы без работающего продукта; регресс не локализуем; нарушает «voice spike рано» (F8, T1) | ❌ отклонён |
| **V2. Walking skeleton**: вертикальный срез через всё на работающей декомпозиции, логика переносится в Core по одному контексту | постоянно работающая система; каждая фаза шипится | нужен жёсткий контракт событий; риск двух систем | ✅ выбран |
| **V3. Patch-in-place**: починить только S1–S25 в `Agent` и остановиться | дёшево, быстро | архитектурную границу не закрывает: вердикт в голосе, нет аудита, нет инцидентов → продукт не построить | ❌ только как Track A |
| **V4. Parallel tracks**: SafetyEngine как первый Core-модуль + перенос остального параллельно | быстрый фикс безопасности + чистая граница | нужно жёстко держать контракт | ✅ (внутри V2) |

**Выбранный путь:** V2 (+V4 внутри): **первой вертикалью Core становится SafetyEngine** — он рождается сразу как модуль Core, а не очередной патч `_classify`. Голосовой рантайм (MossVoice) остаётся как есть, но начинает эмитить события `{question, raw_text, confidence, source}` (U10, A2, A3) вместо вердикта.

### Риски пути и откат
- **Риск «двух систем»**: гасится единым контрактом событий + `test_invariants.py` с самого первого коммита (F6). Откат на любом этапе = вернуться на прошлый образ (images pinned, F-уровни тестов держат).
- **Риск застревания на декомпозиции**: жёсткий критерий выхода на каждую фазу (ниже), фаза без критерия не считается готовой.
- **Внешние зависимости**: LiveKit Cloud и ключи OpenAI/ElevenLabs могут отсутствовать — план даёт локальные альтернативы на каждой фазе (см. §12).

---

## 2. Целевая архитектура (bounding contexts)

```
┌──────────────────────────  voice-runtime (MossVoice)  ──────────────────────────┐
│ LiveKit worker · StreamingSTT · DialogueEngine (Agent) · StreamingTTS · Recorder│
│ SessionStore (Memory/Redis) · call_agent facade (9400)                          │
│ НЕ ставит вердикт. Эмитит события. Только «разговаривает».                       │
└───────────────┬─────────────────────────────────────────────────────────────────┘
                │ события {provider_event_id, call_id, kind, question,
                │         raw_text, confidence, source, ts}
                ▼
┌────────────────────────────  core (IMVERA Core)  ───────────────────────────────┐
│ Postgres = источник истины (A4)  ·  Redis = locks/кэш/очередь (A5)              │
│ SafetyEngine (S10) · Rules Engine (A9) · PersonMemory (A11)                     │
│ webhook-inbox provider_events (идемпотентно, A7) · outbox_messages (A6)         │
│ Incident Engine (I1–I7): OPEN→ACK→CHECKING→RESOLVED/FALSE_ALARM, RED=latch (I2) │
└───────────────┬─────────────────────────────────────────────────────────────────┘
                │ outbox → очередь
                ▼
┌────────────────────────────  delivery  ─────────────────────────────────────────┐
│ TG notifier · SMS (Exolve SMS) · голосовой неотложный дозвон (Exolve call)      │
└──────────────────────────────────────────────────────────────────────────────────┘
┌────────────────────────────  admin  ────────────────────────────────────────────┐
│ Dashboard: звонки/инциденты/правила · Auth+RBAC+audit (actor+reason) (P9, I3)   │
│ Consent и retention UI (P8)                                                     │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### Контракт события (стабильный, первый коммит Core)
```json
{
  "provider_event_id": "uuid",        // идемпотентность: webhook может прийти 100 раз (A7, P6)
  "kind": "user_turn",                // user_turn | call_started | call_ended | no_speech | error
  "call_id": "uuid",
  "caller_id": "+7...",
  "ts": "ISO-8601",
  "question": "Как вы себя чувствуете?",
  "raw_text": "мне плохо",
  "confidence": 0.87,                 // из STT; low → UNCERTAIN, не RED/GREEN (U9, U6)
  "source": "stt:whisper-small"
}
```
**Вердикта в событии нет** (S5, A1). «unknown» и «пусто» — явные виды `kind`, никогда не превращаются в attention/GREEN (S9, D15).

---

## 3. Фазы и критерии выхода

### Фаза 0 — Фундамент ✅ (завершено)
OOM-fix, декомпозиция `call_agent.py`, 69 тестов зелёные, журнал 125 гипотез.

### Фаза 1 — SafetyEngine (первая вертикаль Core) · ~4–6 дней
> **СТАТУС: ВЫПОЛНЕНО (Stage 0A, 2026-08-19).** `core/safety_engine.py` реализован,
> `_classify` в Core удалён, `Agent` потребляет VerdictEvent. Корпус 78+5 фраз,
> инварианты I1–I12, 1000 seeded monotonic-конверсий; офлайн-сьют **106 тестов OK**
> (включая test_session_isolation). Открыто: **U9** — STT ещё не отдаёт confidence
> (Observation получает `confidence=None`), проброс запланирован на Фазу 2/4.

Что: новый модуль `core/safety_engine.py` (чистая детерминированная машина), **не** патч `_classify`.

Проектировка — из подтверждённых багов:
1. **Токенизация + окно отрицания ±3 токена** — `не/нет/ничего/без/никогда/нельзя`. Проверка на границах токенов, а НЕ подстрокой (чинит S11–S15: «мне плохо», «мне нужна помощь», «мне требуется», «мне надо», «мне очень»; S20; S21).
2. **Субъект**: self (`я/мне/у меня/мой`) vs third (`сосед/бабушка/он/она/сын/сестра`) — third-person НЕ даёт RED (S2, S22).
3. **Расширенные списки**: `болит/болело/болеет/боль/больно`, идеация `хочу умереть/не хочу жить/умираю/покончить`, падежи `скорая/скорую/скорой/врача`, `кружится голова` (S16–S19, D14).
4. **Машина** `NONE → POSSIBLE_RED → CONTROL_QUESTION → CONFIRMED_RED | UNCERTAIN_RED` (S10). POSSIBLE_RED заставляет задать контрольный вопрос; CONFIRMED_RED не понижается (S6, I2).
5. **Latch и guard**: после вердикта машина замораживается; `done=True` не даёт ходам менять вердикт (S6, S24).
6. **NODATA**: пустой/роботный транскрипт → `kind=no_speech`, не ok (D15, B4-1).
7. Выход SafetyEngine — **событие**, а не статус (S5, U10).

Критерий выхода: регрессионный корпус (F7, ~100 фраз из S1–S25 + типовые диалоги) даёт **0 ложных GREEN** и **0 ложных RED** на эталонных сценариях; `test_invariants.py` вводится в этот же коммит (F6).

### Фаза 2 — Core-скелет (данные и события) ✅ (реализовано 2026-08-20)
Что: Postgres-схема (P1), миграции (P4), Redis (DEGRADED) (A5), MinIO (P2), event-inbox, outbox (P7, A6), идемпотентность (A7).

Реализовано:
- `telephony/migrations/001_core_schema.sql` — идемпотентная схема (P4); таблицы: `call_sessions`, `call_attempts` (+ unique `callout_id`), `dialogue_turns` (+ `source`, `confidence`, `audio_key`), `dialogue_answers`, `call_results`, `incidents`, `incident_actions`, `consents`, `person_memory`, `audit_log`, `provider_events` (PK = event_id, INSERT-игнор), `outbox_messages` (status, attempts, `next_attempt_at`, частичный unique `dedup_key`).
- `core/migrate.py` — ручной идемпотентный раннер (применяет только новые файлы по `schema_migrations`).
- `adapters/pg.py` `PgStore` — connection pool (psycopg3), guarded-переходы `UPDATE ... WHERE status = ANY(...)`, методы recorder, ингест provider-событий, outbox enqueue/claim/resolve.
- `adapters/redis_store.py` — **DEGRADED** семантика (A5): Redis пал → `degraded=True` в `/health`, громкие логи, НЕТ тихого фолбэка в RAM.
- `core/provider_events.py` + `legacy/call_agent_http.py /webhook/provider` — durable inbox: ingest + guarded-переходы в одной транзакции, outbox-запись с `dedup_key='provider:<event_id>'`, `reconcile_unprocessed()` для crash-окна.
- `core/outbox_worker.py` — lease `FOR UPDATE SKIP LOCKED`, retry с backoff, dead-letter после `max_attempts`, thread в `Serve` при `pg_available`.
- `adapters/pg_recorder.py` — `PgRecorder` вместо файлового recorder: turn'ы + confidence пишутся в PG, финализация закрывает сессию и ставит `call.result` в outbox.
- `adapters/s3_recordings.py` — MinIO-аплоад при `MOSS_MINIO_*` (ленивый клиент, SHA-256 checksum), иначе диск.
- `docker/docker-compose.yml` — сервисы `db` (postgres:16-alpine), `cache` (redis:7-alpine), `storage` (MinIO); `Makefile` — `db-up/db-down/test-db`.

Критерии выхода (drill'ы в `tests/test_data_core.py`, реальный Postgres, 12 тестов):
- webhook 100× по HTTP → 1 строка `provider_events`, 1 outbox-сообщение ✅
- поздний `answered` после `completed` игнорируется (guarded transition) ✅
- `timeout` не срабатывает дважды / не создаёт вторую попытку ✅
- outbox копит пока downstream лежит, доставляет после восстановления, dead-letter после лимита, dedup уникален ✅
- `reconcile_unprocessed()` добивает события из crash-окна ✅
- Serve + реальный PG: new_call → turn'ы (с confidence) → end_call → `call_results` + outbox `call.result` ✅

Полные прогоны: локально 138 тестов OK (офлайн 13 skip; с PG 1 skip), docker `make test-fast` 138 OK (5 skip).

### Фаза 3 — Инциденты и уведомления ✅ (реализовано 2026-08-20)
Что: Incident Engine (I1), эскалация через outbox (I5), таймеры (I7), actor+reason (I3, P9), «уведомлено ≠ решено» (I4), RED-latch на уровне инцидента (I2), техническая ошибка ≠ NO_CONTACT (I6).

Реализовано:
- `core/incidents.py` `IncidentEngine` — машина `open → ack → checking → resolved | false_alarm` (guarded-переходы `WHERE status = ANY(...)`), actor+reason на каждом переходе, `audit_log` на шаг.
- Открытие инцидента от RED-вердикта (`alert`) через outbox `call.result` (замена no-op `_dispatch_outbox`); план эскалации = упорядоченные `incident_actions` (telegram → sms → call), контакты из household (Фаза 4; пока env `MOSS_FAMILY_CHAT_ID`/`MOSS_FAMILY_PHONE`).
- `core/delivery.py` — каналы: **Telegram REAL** (Bot API через urllib, `MOSS_TG_BOT_TOKEN`), SMS/voice структурированы до провайдеров (fail-fast → движет эскалацию).
- Доставка строго через outbox: `incident.notify` с `dedup_key='incident:<id>:<action_id>'` — рестарт/дубль webhook никогда не двойной уведомляет. Падение канала → fallback на следующий канал; все каналы исчерпаны → `escalation_level+1`.
- Таймеры: дедлайны из PG `now()` + `tick()` на каждом poll outbox-воркера (`OutboxWorker(tick=...)`): no-ACK за `MOSS_INCIDENT_ACK_SECONDS` (180) → эскалация на следующий канал; ack/checking за `MOSS_INCIDENT_RESOLVE_SECONDS` (900) → пометка оператору.
- HTTP: `GET /incidents`, `POST /incidents/<id>/ack|resolve|false-alarm`.
- Миграция `002_incident_delivery.sql` (идемпотентные ALTER).

Критерии выхода (drill'ы в `tests/test_incidents.py`, реальный Postgres, 10 тестов):
- RED-вердикт → durable incident + упорядоченный план ✅
- Telegram упал → fallback SMS → ACK родственника → resolved + полный audit (opened→notify.failed→notify.sent→ack→checking→resolved) ✅
- ACK до дедлайна → resolved без эскалации ✅
- Нет ACK за дедлайн → escalation_level+1 → следующий канал (таймерный drill) ✅
- Рестарт между enqueue и доставкой → pending notifier добивает ✅
- Дубль notify не двойной отправляет ✅ · out-of-channels → эскалация ✅ · false_alarm терминален ✅
- Полная проводка `end_call(RED)` → `call.result` → `_dispatch_outbox` → инцидент (Serve-уровень) ✅
- HTTP `/incidents/<id>/ack` над реальным сервером ✅

Полные прогоны: локально 148 тестов OK (офлайн 23 skip; с PG 1 skip), docker `make test-fast` 148 OK (5 skip).

Дальше (следующий блок): реальный voice/telephony gate (Фаза 4 — LiveKit/SIP/Exolve) — доказываем цепочку настоящим звонком.

### Фаза 3.5 — Рефокус: Этап A «Разговор» (решение 2026-08-20)

> **ЕДИНЫЙ МАРШРУТ (директива 2026-08-21, отменяет параллельные планы).**
> Больше не прыгаем: один маршрут, остальное подчинено ему.
>
> ```text
> 1. ВЫБРАТЬ ГОЛОС  (voice-bench: 500 фраз, RTF/RAM/WER + уши)
> 2. ПРОИЗНОШЕНИЕ   (VeraSpeechFrontend: нормализация, словарь ударений)
> 3. CONTINUOUS AUDIO  (убить record→WAV→HTTP→playback из hot path)
> 4. STREAMING STT  (распознавание во время речи, endpointing)
> 5. STREAMING TTS + BARGE-IN (100–250 мс до тишины)
> 6. <1–1.5 с до первого звука (latency trace на каждую реплику)
> 7. 20 × 5-мин звонков без единого сбоя
> 8. РАЗМОРОЗКА PRODUCT CORE (consent/schedule/UI/billing)
> 9. SCALE/CELLS (по §16)
> ```
>
> **Заморожено до маршрута:** новые таблицы, billing, UI, Kubernetes,
> Temporal, cell router, новые safety-правила, новые арх-документы,
> обучение VeraVoice (R&D не отменён — заморожен).
> Silero остаётся fallback-голосом; базовая линия арены:
> `voice-bench/` — Silero RTF 0.015 / Piper RTF 0.026 (500 фраз,
> round-trip WER 0.27/0.28). Голос меняется только через победу
> в blind test по гейтам из `docs/TTS_ARENA.md`.

> **Ошибка последних двух недель:** делали backend, safety, телефонию и Веру
> одновременно — много кода, а основной продукт (разговор) всё ещё плох:
> анкета «шаг 0 → шаг 1 → конец», дубль реплики в истории LLM, инструкция
> движка как сообщение `user`, обязательный вопрос после каждой реплики,
> голое «да» = просьба о помощи, «встала/кровать/купила» = экстренные случаи.
>
> **Решение:** разговор — продукт №1. Порядок этапов жёсткий, гейты не
> смешиваются:
>
> - **Этап A — Conversation (СДЕЛАНО 2026-08-20, 169 тестов OK):** режимная
>   машина вместо шагов (`companion` по умолчанию, `check_in`, `clarify`,
>   `safety_confirm`, `safety_active`, `closing`); разговор заканчивается
>   только при явном прощании / confirmed_red / внешнем end_call. 4 бага
>   LLM-истории исправлены (дубль реплики, интент в system-контексте,
>   без вопроса после каждой реплики, без авто-завершения). Создан
>   `voice-lab/` — текстовый полигон (REPL + корпус 100 сценариев из 20
>   категорий + отчёт Gate 1). SafetyEngine почищен от ложных срабатываний,
>   найденных гейтом: «встала» ≠ RED (RED = «не встаю/не могу встать»),
>   «кровать» ≠ «кровь», прошедшее время («купила хлеб», «позвонила
>   дочери») ≠ запрос помощи, «листья/снег/дождь падают» ≠ падение человека
>   (инварианты I13–I16). **Gate 1: 90/100 сценариев выглядят нормально
>   для человека** (оценка — человеком, отчёт `voice-lab/reports/`).
> - **Этап A2 — Сильная модель + скриптовый safety (СДЕЛАНО 2026-08-20, 170 тестов OK):**
>   Qwen3-1.7B → **Qwen3-4B-8bit (MLX)** на 9500 (мутанты «Дождь — это нечто
>   несчастное» / «Позвоните в близких» ушли; сравнение корпуса: отчёты
>   `gate1_20260820_050044.md` (1.7B) vs `gate1_20260820_050414.md` (4B)).
>   В `safety_confirm`/`safety_active` LLM-фразы отключены полностью —
>   контрольный вопрос и реплики при опасности всегда точные скриптовые
>   (фикс гейта #62: модель больше не сломает петлю подтверждения).
>   Промпт усилен: один прямой вопрос для «уточнить», без «ты/вы» вперемешку,
>   «позвать близких» только при жалобах/опасности, тёплое прощание.
> - **Этап C0 — Голос: Silero TTS (СДЕЛАНО 2026-08-20):** MOSS-TTS-Nano
>   (шипение, артефакты «ауауауауа») заменён на **Silero TTS ru v5** —
>   женский голос (default `kseniya`, запасные `baya`/`xenia`), 48 кГц, CPU,
>   синтез фразы 0.06–0.4 с, первый фрейм `/stream` ~0.07 с. Бэкенд:
>   `runtime/scripts/moss_runtime/silero_tts_backend.py`, выбор `--model
>   silero` (nano остаётся как `--model moss-tts-nano`). Ограничение:
>   voice-clone из референсов у silero нет (стандартный голос вместо клона —
>   именно это и нужно продукту). Остаток Этапа C (нормализатор текста,
>   словарь ударений, корпус 500 фраз) — после Gate A.
> - **Этап B — Latency:** VAD-endpointing вместо хопов 3 с, streaming LLM,
>   сегментация предложений, streaming TTS; бюджет «конец речи → первые
>   звуки»: идеал <700 мс, норма <1 с, плохо >1.5 с; latency-trace на звонок
>   (`speech_end/stt_final/llm_first_token/llm_first_sentence/tts_first_audio/
>   playback_start`). Gate: p50 < 1 с, p95 < 1.5 с.
> - **Этап B0 — Docker-микросервисы + стриминговый телефонный путь (СДЕЛАНО
>   2026-08-21, 169 тестов OK):** весь стек в compose (db/cache/storage/
>   voice/answers/telephony), модели в volume (не в образе), `make update`
>   пересобирает без перекачивания весов. Бэкенды: **llama.cpp llama-server**
>   (образ `ghcr.io/ggml-org/llama.cpp:server`) + Qwen3-4B Q4_K_M GGUF
>   (~2.4 ГБ, скачивается entrypoint при первом старте), OpenAI-совместимый
>   API (`MOSS_LLM_PROTOCOL=openai`, SSE); **Silero TTS** в voice; **faster-
>   whisper small int8, beam_size=1** вместо transformers-пайплайна
>   (17.9 с → ~3 с на 11 с речи). Закрытые баги: thinking Qwen3 съедал весь
>   лимит токенов → пустой ответ → шаблонный фолбэк («амнезия после 2
>   вопросов») — `enable_thinking=false`; /health llama.cpp без `ready` →
>   агент ждал 180 с и деградировал в скрипты; `openai/whisper-small` не
>   маппился в `small` для faster-whisper → тихий fallback на transformers.
>   Телефонный путь: **выдача по предложениям** — агент пишет готовые
>   предложения в `/tmp/mossvoice/segs_*/seg-NNNN.wav` (16 кГц под G722,
>   атомарный rename), `moss_agent.lua` играет сразу (фоновый curl + опрос);
>   тишина записи 10 с → 2 с; для телефонии STT одноразовый (hop-режим —
>   только веб-приложению). Замер: **ход (11 с речи) 6.2–6.5 с, первый
>   сегмент 5.7 с** (было ~25–30 с). Правило «без ложной надежды»: Вера
>   никогда не обещает «я вызову/позвоню/отправлю» — только «я записала,
>   близкие увидят» (промпт, safety-скрипты, сценарии). Сценарии —
>   `telephony/vera_scenarios.txt` (volume-маунт, правка без пересборки).
>   Диалплан: копировать `moss_dialplan.xml` в FS `dialplan/default/` +
>   `reloadxml` (путь до lua в правиле — абсолютный, репозиторный).
> - **Этап C — Voice (остаток):** нормализатор текста перед TTS (время, даты,
>   номера), pronunciation dictionary + корпус 500 фраз («звонИт»,
>   «договОр», имена/отчества/города); однопроходный синтез фразы целиком
>   уже сделан (посегментный резал интонацию — «несвязный» голос). Gate: без
>   системных шипений, 99% словаря приемлемо, понятно пожилому с первого раза.
> - **Этап D — Realtime phone:** убрать `record WAV → HTTP → playback WAV` из
>   hot path, непрерывный media stream + barge-in ~100–250 мс. Это же даёт
>   2–3 с до первого звука (сейчас пол ~4–7 с: 2 с тишина + STT после конца
>   речи). Gate: 20 пятиминутных разговоров подряд без развала сессии.
> - **Этап E — Reliability:** 1000 synthetic runs (provider/network/STT/LLM/
>   TTS fail, hangup, double event, timeout, restart). Gate: без зависаний,
>   двойного playback, потерянных turns, garbage audio, бесконечных retries.
>
> **Замораживается до прохождения Этапов A–E:** billing, UI, новые incidents,
> новые таблицы, household, MinIO improvements, новые абстракции, новые
> safety-гипотезы. Postgres/Redis/outbox работают сбоку от горячего пути
> (события), НЕ внутри него.
>
> Первый milestone без телефона: `voice-lab` — «текст → LLM → текст»; после
> Gate 1 — эталонный голос через сильную модель как benchmark, затем
> спуск вниз по размеру модели.

### Фаза 4 — Живой голос (LiveKit) · 7–10 дней (зависит от внешних аккаунтов)
Что: LiveKit Cloud **или** self-hosted LiveKit; SIP-транк Exolve → LiveKit; worker (реально существующий `worker/`); streaming STT/LLM/TTS; **barge-in через `/stream-cancel` по `stream_id`** (V9, T9); Recorder → аудио в MinIO (P3).

Критерий выхода: реальный звонок e2e (SIP 4400 / /turn_stream), latency по стадиям замерян (T1–T8, F8), запись в MinIO, событие `call_started/ended` в PG.

### Фаза 5 — Two-layer Вера · ~5–6 дней
Что: Layer A (контролируемый check-in 30–60 с, анкета → `dialogue_answers`) + Layer B (свободная беседа) (D10, A11, L2). PersonMemory отдельно (A11). `LLM` возвращает только `{spoken_response, conversation_intent}`, действия — Rules Engine (A10, L7).

Критерий выхода: «помощь в середине беседы Layer B» переводит диалог в Core-поток без потери контекста; 50-фразовая оценка связности (L1, L5).

### Фаза 6 — Админка и управление правилами · ~6–8 дней
Что: dashboard звонков/инцидентов; Rules Engine версионируемый (A9); consent/retention UI (P8); аудит (P9).

Критерий выхода: оператор закрывает инцидент → audit_log с actor+reason; изменение правил не требует редеплоя телефонии.

### Фаза 7 — Продуктовая обвязка · ~5–7 дней
Что: auth/RBAC (см. §6), observability (§9), backup/DR (§10), 5 уровней тестов + все failure-drills (F1–F8), нагрузочное тестирование, cost-caps, runbook.

**Критерий входа в продуктовый план:** всё из §0 п.1–8 выполнено и замеряемо метриками из §11.

---

## 4. Безопасность (полный спектр)

### 4.1 Аудио и персональные данные
- В транзите: TLS на всех внешних границах (Exolve webhook, admin, TG webapp). Внутри docker-сети — TLS или изолированная сеть.
- В покое: аудио в MinIO/S3 с **SSE** (server-side encryption), checksum, ACL по контексту (голос/админ). PG хранит только ссылку (P2).
- Consent: до записи/передачи голосовое и письменное согласие; `consent` таблица; retention-политика на запись и на транскрипт (P8).
- Автоудаление по retention cron; удаление по запросу субъекта (152-ФЗ) — каскад с честным удалением из S3.
- PII-минимизация: в PG не хранить лишний персданные; `caller_id` — ключ, а не данные; транскрипты с чувствительными полями — отдельные столбцы (pgcrypto при необходимости).

### 4.2 API и входящие данные
- Exolve webhook: **проверка подписи (HMAC)** + секрет в env; идемпотентность `provider_event_id` (A7).
- `/turn`, upload-эндпоинты: валидация как в `save_upload` (внешние пути/траверс/multipart-без-boundary → отклонено, C7 — уже подтверждено), лимиты размера, максимальная длительность звонка, rate-limit по caller_id (DoS).
- Внутренние сервисы (voice:9600, answers:9500) не выставляются наружу; telephony bинд loopback (уже так, compose).

### 4.3 Админка
- Auth: OAuth2 (Telegram identity) или пароль+2FA; RBAC: operator / admin / auditor; сессии с ротацией; весь доступ в `audit_log` (actor+reason).
- Запрет массового экспорта без причины; аудит экспорта.

### 4.4 Секреты
- Никаких секретов в репозитории (уже: токены через env). В проде — docker secrets / секрет-менеджер; ротация ключей; ключи только у сервисов, которым нужны.

### 4.5 Телефония
- SIP: TLS/SRTP; верификация номеров (anti-spoofing, SIP Identity); ограничение длительности; лимиты исходящих (неотложный дозвон) с kill-switch.

### 4.6 Мониторинг безопасности
- Алёрты на подозрительные паттерны (массовые звонки с одного номера, ошибки подписи webhook, аномальный доступ к админке), audit trail, retention audit.

---

## 5. Данные: миграции, резерв, восстановление

- **Миграции**: Alembic; идемпотентные; применяются при деплое автоматически; downgrade-план для каждой.
- **Backup**: nightly `pg_dump` + WAL-архивирование (PITR); MinIO versioning; restorable на staging; drill восстановления раз в квартал (F5).
- **Retention-задачи**: отдельный cron-контейнер (удаление записей по consent/retention, чистка outbox, compaction).
- **Индексы** по горячим путям: `provider_events(provider_event_id)`, `outbox(status)`, `incidents(status)`, `dialogue_turns(call_id)`.

---

## 6. Надёжность и деградация

| Сервис | Жив? | Поведение без него | Гипотезы |
|---|---|---|---|
| Postgres | нет | звонки в режиме «hold»: принимаем, не эмитим вердикты до восстановления; события буферизуются | A4, I6 |
| Redis | нет | **DEGRADED**: MemorySessionStore + флаг; PG остаётся истиной | A5, C4 |
| LLM | нет | scripted-ответы; вердикт от SafetyEngine не зависит от LLM | L8 (подтверждено), L7 |
| STT | нет | `kind=no_speech/error` — техническая ошибка ≠ NO_CONTACT | S9, U11, I6 |
| TTS | нет | LLM-ответы отдаём текстом/повтором (не вешать звонок) | V9 |
| TG | нет | outbox копит; SMS/голосовой fallback-канал | A6, I5 |
| Очередь | нет | outbox polling-worker (без брокера) | P7, A6 |
| LiveKit | нет | отказ приёма звонка фиксируется в `call_attempts`, ретрай с backoff | A8 |

Ключевые принципы: **идемпотентность** (A7), **retry с backoff и экспоненциальной паузой**, **circuit breakers** на адаптерах (LLM/STT/TTS), **health checks** (уже паттерн в compose), supervisor + TTL-sweep (C3 подтверждено).

---

## 7. Наблюдаемость

- **Структурированные логи** с `call_id`/`request_id` (корреляция по всей цепочке).
- **Метрики** (Prometheus): успешность дозвона, доля эскалаций, SLA «call→уведомление», WER, latency по стадиям (T1–T8), длина очереди outbox, доля scripted-ответов, false-RED rate.
- **Трейсы** (OpenTelemetry) через все адаптеры.
- **Алерты**: RED-инцидент = page; ошибки подписи webhook; очередь outbox растёт; звонок без события >N мин; диск/CPU.
- **Дашборды** (Grafana): операционная + продуктовая (метрики из §11).
- **Runbook** на каждый drill F5.

---

## 8. Тестирование (5 уровней + инварианты)

| Уровень | Что | Ключевые тесты |
|---|---|---|
| L1 Unit | правила, переходы, парсинг, SafetyEngine | корпус S1–S25: **0 ложных GREEN/RED**; машина POSSIBLE_RED→…; latch; done-guard; NODATA |
| L2 Contract | адаптеры STT/TTS/LLM/Exolve/LiveKit/MinIO | мок-серверы (как batch2b: wire-парсинг, cancel) |
| L3 Integration | PG+Redis+outbox+webhook | идемпотентность 100×, outbox при падении TG, DEGRADED Redis |
| L4 E2E | реальный звонок | /turn_stream, запись в MinIO, события в PG |
| L5 Drills | падения сервисов | F5: каждое — одно правильное конечное состояние |
| Инварианты | 15–20 правил | `test_invariants.py` вводится с Фазой 1 (F6) |
| Корпус | регрессия диалогов | F7 (из S1–S25, ~100 фраз) |
| Harness | latency/WER/естественность | F8 (SPIKE): замер по стадиям, еженедельный прогон |

Правило: **failures drills и инварианты зелёные — обязательное условие каждого PR в core/.**

---

## 9. Оперирование

- **Окружения**: dev / staging (compose, мок-Exolve) / prod (compose v2 или k8s по росту).
- **Деплой**: pinned образы + миграции в деплой-шаге; healthcheck-gating; откат = прошлый образ.
- **Скрипты**: backup cron, retention cron, restore drill, runbook-шпаргалка.
- **Single-host MVP**: docker compose v2 (PG/Redis/MinIO/outbox/worker в той же сети) — достаточно до ~сотен звонков/день; **k8s** — при росте (горизонтальный скейл voice-runtime).

---

## 10. Телефония: выбор стека и открытые решения

| Решение | Вариант A (рекоменд.) | Вариант B | Критерий |
|---|---|---|---|
| Реалтайм-медиа | **LiveKit Cloud** (быстро, TURN/NAT решены) | Self-hosted LiveKit (VPS с публичным IP, TURN) | время запуска; бюджет; контроль |
| SIP-транк | **Exolve** (уже целевой, SMS+голос+верификация) | Mango/др. | покрытие номеров; стоимость |
| Вычисление | **CPU 6–10 ядер / 16–24 ГБ** (решение пользователя, см. §15) | GPU — если позже захотим > 3 с к первому звуку | скорость (F8) vs бюджет |
| LLM | **Qwen3 GGUF Q4 через llama.cpp/Ollama** (10–20 ток/с на CPU) | Qwen3-0.6B Q4 (быстрее, ниже качество) | качество (L1, L2) vs скорость (T4) |
| STT | **faster-whisper (CTranslate2) int8**, streaming-хопы | Whisper-large-v3-turbo int8, если WER не устроит | WER на телефонном аудио (U1), скорость (T3) |
| TTS | **MOSS-TTS-Nano, шаги 6–8, `--no-style`, кэш референса** | Piper (быстрее, грубее голос) | качество (V1–V3, V7) vs скорость (V4) |

**Решение пользователя зафиксировано: CPU 6–10 ядер / 16–24 ГБ, без GPU/облака.** Детальный трек «как выжимать» — в §15. Целевые числа: первый звук ответа ≤ 4 с, полный ход ≤ 8 с, приветствие < 2 с (замеряются на Фазе 4, F8).

---

## 11. Продуктовый план (целевой) — как инженерный план в него встраивается

Продуктовый план отдельным документом, но его **входные метрики и гейты — из этого плана**:

- **Persona/JTBD**: оператор сервиса заботы (дозвон и контроль), семья (уведомление о состоянии), подопечный (контролируемый check-in).
- **MVP-фичи**: реальный звонок + Core-вердикт + уведомление семьи + консоль оператора + consent/retention.
- **Продуктовые метрики** (замеряются с Фазы 4): успешность дозвона (≥X%), SLA «событие→уведомление» (<T мин, эскалация по I7), доля ложных RED (<Y% — напрямую из SafetyEngine-корпуса F7), стоимость/звонок (из замеров T1–T8), WER (U1), retention.
- **Гейты запуска**: 0 ложных GREEN в корпусе; все drills F5 зелёные; восстановление из бэкапа проверено; аудит работает; метрики собираются ≥2 недель на staging с мок-Exolve.
- **Роадмап после MVP**: свободная Вера (Layer B), телеграм-бот оператора, авто-правила на истории, мультиязычность.

---

## 12. Риски и открытые вопросы (решения — по ходу фаз)

1. **LiveKit Cloud/аккаунт Exolve/ключи** — без них Фаза 4 только мок-тесты; самохост LiveKit — запасной путь.
2. **Скорость против newo.ai — главный риск продукта** (подробно §14). Текущий CPU-стек НЕ достигает даже «отдалённо похожего» уровня. Решение принимается цифрами на Фазе 4 (F8): если целевая латентность > 3 с → GPU/облако обязательны; если решено «reliability-first» (check-in, 2–5 с норм) → CPU-трек допустим, но это продукт-решение, не техническое.
3. **ASR на телефонном аудио**: WER может быть высок (U1); fallback — облачный ASR или окно подтверждения (U6, U7).
4. **Цена облака** против локального трека (L1, U1, V1, V8) — решать после замеров, не заранее.
5. **Юридическое**: запись/передача голоса требует consent и retention (P8); консультация до продуктива.
6. **Спам/спуфинг номеров**: верификация + лимиты + kill-switch (§4.5).

---

## 13. Дорожная карта с дозами

| Фаза | Длит. | Выход (измеримый) | Ссылки |
|---|---|---|---|
| 0 Фундамент | ✅ | декомпозиция, 69 тестов, журнал 125 гипотез | — |
| 1 SafetyEngine | 4–6д | корпус 0 GREEN/RED + test_invariants | S1–S25, D15, S10, I2, F6, F7 |
| 2 Core-скелет | 5–7д | PG/Redis/MinIO/outbox/идемпотентность на drills | A4–A8, P1–P7 |
| 3 Инциденты | 4–5д | эскалация+таймеры+actor+reason на drills | I1–I7, P9 |
| 4 Живой голос | 7–10д | реальный звонок, записи в MinIO, latency-замеры (F8) + **CPU-оптимизация (§15): бэкенды quantized + перекрытие + barge-in; гейт «первый звук ≤ 4 с, приветствие < 2 с»** | V9, T1–T9, F8, P3 |
| 5 Two-layer Вера | 5–6д | check-in+беседа, PersonMemory | D10, A10, A11, L1–L5 |
| 6 Админка/Rules | 6–8д | dashboard, версии правил, consent UI | A9, P8, P9 |
| 7 Обвязка | 5–7д | auth/RBAC, observability, backup, drills, метрики | F1–F8, §4, §7, §9 |
| **→ Продуктовый план** | | все гейты §0, метрики §11 на staging ≥2 нед | §11 |

Итог: **~5–7 недель** от сегодня до входа в продуктовый план при полном локальном треке; Фазы 1–3 не требуют ни одного внешнего ключа и могут стартовать немедленно.

---

## 14. Скорость против newo.ai — честная оценка (обновление 2026-08-21)

Сверено с newo.ai (сайт, 2026): они позиционируют «sub-second latency, reasoning during speech», поднятие трубки за 2 с, Gen3 voice-to-voice «на индустриальном масштабе» (облако, GPU-классы, параллельная обработка, шумоизоляция, interruption handling). Их скорость — свойство **вычислительного стека**, а не архитектуры.

### Оценка латентности на реплику (замеры 2026-08-21, CPU 10 ядер, Docker)

| Стек | STT | LLM первая фраза | TTS первый звук | Итого на реплику |
|---|---|---|---|---|
| **Было (transformers, последовательно):** whisper-small fp32 + Qwen3 через transformers + MOSS-Nano | 8–18 с | 6–14 с | 5–15 с | **~25–30 с** (при галлюцинациях STT — до 90 с) |
| **Сейчас (СДЕЛАНО, Этап B0):** faster-whisper small int8 beam1 + Qwen3-4B Q4_K_M llama.cpp (thinking off) + Silero, выдача по предложениям | 1.2–3 с | 1.5–3 с | 0.1–0.3 с | **ход 6.2–6.5 с (11 с речи); первый звук в трубке ~4–7 с** (2 с тишина + STT + первое предложение) |
| **CPU-потолок (Этап D):** STT во время речи (FS media stream) + barge-in | ~0.3 с после конца речи | 1.5–3 с | 0.1–0.3 с | **~2–4 с до первого звука** |
| **GPU-конвейер / realtime voice-to-voice** | 0.2–0.4 с | 0.5–1.5 с | 0.3–0.8 с | **~0.5–1.5 с** (уровень newo.ai) |

### Выводы
1. **«Хоть отдалённо похоже на newo.ai» = ~1.5–3 с на реплику → GPU обязателен** (одна 3090/4090, или облачный инстанс ~$100–300/мес, или realtime-API по минутам). Без GPU — никак: это не вопрос архитектуры.
2. **Целевой трек: CPU 6–10 ядер.** Достигнуто: ход ~6 с, первый звук ~4–7 с. Остаток (2–3 с) упирается в физику «STT после конца речи»: 2 с тишина записи + 1.2–3 с STT. Дальше только Этап D (стриминг аудио из FS, распознавание во время речи).
3. **«Субсекунда» newo.ai недостижима pipeline-стеком вообще** — только realtime voice-to-voice модель. Для check-in продукта это избыточно.
4. **Сценарий разный**: newo.ai — ресепшн. IMVERA — check-in пожилому: 4–7 с на ответ уже естественен; важнее надёжность (0 ложных GREEN), понятный голос и неупущенный дистресс (S1–S25).
5. **Поднятие трубки и приветствие < 2 с** — сделано: приветствие скриптовое, кэшируется при старте контейнера (pre-warm), играется из готового WAV.

---

## 15. CPU-трек 6–10 ядер / 16–24 ГБ: как выжимать (обновление 2026-08-21)

Цель: минимальная латентность без GPU. Статус замен:

### 15.1 Узкие места — статус

| Компонент | Было | Стало (2026-08-21) | Результат |
|---|---|---|---|
| **STT** | whisper-small через transformers (fp32, batch 8) | **faster-whisper small int8, beam_size=1, condition_on_previous_text=false** (адаптер `FasterWhisperAdapter` в tts_common) | 17.9 с → ~3 с на 11 с речи; сегменты несут no_speech_prob/compression_ratio/avg_logprob → confidence U9 работает |
| **LLM** | Qwen3 через transformers CPU | **Qwen3-4B Q4_K_M через llama.cpp llama-server**, 8 потоков, `enable_thinking=false` | 5.8 с → 2–4 с первая фраза; память 3.0 ГБ |
| **TTS** | MOSS-TTS-Nano (шипение, артефакты) | **Silero ru v5**, однопроходный синтез фразы | 0.1–0.4 с на предложение, чистый голос |
| **Конвейер** | всё последовательно, ответ целиком | **выдача по предложениям**: LLM-стрим → TTS первого предложения → seg-файлы → Lua играет сразу | первый звук = тишина + STT + 1 предложение |

### 15.2 Что осталось до 2–4 с (Этап D)
1. **STT во время речи** — FreeSWITCH стримит аудио в агент (websocket/mod_audio_fork), faster-whisper декодирует хопы в реальном времени; финализация ~0.3 с после конца речи. Сейчас STT начинается только после записи (2 с тишина + POST).
2. **Barge-in** — обрывать TTS при новой реплике (механика `/stream-cancel` по stream_id есть, в телефонном Lua-пути пока не подключена).
3. Тишина записи 2 с — уже минимум для пожилых пауз; в Этапе D заменяется endpointing'ом на стриме.

### 15.3 Бюджет RAM (фактический, Docker VM 12 ГБ)
voice ~1.4 ГБ (Silero + whisper-small int8) + answers ~3.0 ГБ (Qwen3-4B Q4) +
db/cache/storage/telephony ~0.6 ГБ ≈ **5 ГБ занято из 11.7** — запас есть.

### 15.4 Открытые решения по замерам (F8)
- Whisper **small vs large-v3-turbo** (int8): WER на реальных телефонных записях (U1). small сейчас точен на синтетике; решить на живых звонках.
- Qwen3-4B **Q4_K_M vs Q5**: качество реплик против скорости (сейчас 2–4 с — в бюджете).
- Silero **kseniya** подтверждена пользователем; запасные baya/xenia в `MOSS_SILERO_SPEAKER`.

**Выход CPU-трека (внутри Фазы 4):** на 6–10 ядрах CPU: поднятие+приветствие < 2 с; конец речи → первый звук ответа ≤ 4 с (цель 2–3 с); полный короткий ход ≤ 8 с. Измеримо harness'ом F8.
---

## 16. Продуктовая архитектура: cells + voice plane (директива 2026-08-21)

**Решение владельца продукта:** проектировать по предельным нагрузкам и
failure domains, запускать сначала одну ячейку. Критерий «достаточно ли
этого сейчас» больше не применяется. Новый стандарт для каждого компонента:

> **Есть ли у компонента понятный scale unit, ownership state, capacity
> limit, failure boundary, backpressure, HA strategy и способ горизонтального
> расширения без изменения бизнес-логики?** Если хоть одного нет — компонент
> архитектурно не готов.

Текущий код сохраняется как **основа доменной логики** (диалог, SafetyEngine,
инциденты, outbox-семантика). Текущий deployment — нет: `docker-compose.yml`
официально понижен до **dev environment** (одна реплика всего, один узел).

### 16.1 Единица масштабирования — concurrent calls, не пользователи

```text
registered households / active elders   — данные, не нагрузка
CONCURRENT CALLS                        — главная единица проектирования
turns/sec · audio sec/sec               — производные
STT realtime factor · LLM tokens/sec · TTS audio sec/sec
DB txn/sec · provider calls/sec · notification deliveries/sec
```

Ориентиры: 100k звонков × 3 мин за 12 ч ≈ 417 concurrent (×4 вечерний пик ≈
1 667). 1M пользователей ≈ 4 167 avg / ~16 700 burst. Под эти числа — cells.

### 16.2 Целевая топология

```text
                    GLOBAL CONTROL PLANE (тонкий)
                 auth / billing / cell registry / routing
                            │
        ┌───────────────────┼────────────────────┐
        ▼                   ▼                    ▼
      CELL 01             CELL 02              CELL N
   Core API ×N         Core API ×N          Core API ×N
   Workflow ×N         Workflow ×N          Workflow ×N
   PG+PgBouncer HA     PG+PgBouncer HA      PG+PgBouncer HA
   Redis HA            Redis HA             Redis HA
        └───────────────────┬────────────────────┘
                  REALTIME VOICE PLANE
              SIP/LiveKit nodes → Admission Router
             ┌──────────────┼──────────────┐
         Pool A          Pool B          Pool N
         Voice ×N / STT ×N / LLM ×N / TTS ×N
```

Ключевые принципы:
- **Cell** — фиксированная независимая единица с сертифицированным лимитом
  (AWS cell-based). Рост = +cell; blast radius сбоя = одна cell.
- **Voice plane отдельно от business core.** STT/LLM/TTS — отдельные pools
  со своими concurrency limit, таймаутами, autoscaling, fallback и circuit
  breaker'ами. Падение TTS не убивает STT.
- **Call = actor**: один call_id → один VoiceWorker до конца звонка
  (single ownership); node draining — новые звонки не назначаются.
- **Никакого /tmp как контракта**: continuous media transport
  (PCM/Opus-фреймы), записи — async chunk writer → S3.
- **Business core = stateless modular monolith** (domain/households, elders,
  consent, schedules, calls, safety, incidents, notifications, billing) за
  LB. НЕ дробить на 15 сервисов.
- **Admission control прежде autoscaling**: VOICE CAPACITY = min(STT, LLM,
  TTS); сверх лимита — отказ/перенос/другой cell, никогда не деградация всех
  активных звонков (Google SRE, load shedding).
- **Control plane тонкий**: его падение не прерывает идущий звонок.
- **Durable workflows промышленно** (Temporal-класс): CallWorkflow, Incident-
  Workflow (OPEN→TG→ACK 2m→SMS→…→terminal). Не threads, не cron, не sleep().
- **Routing keys с первого дня**: `tenant_id`, `household_id`, `cell_id`,
  `call_id` во всех durable контрактах; большие append-таблицы
  (dialogue_turns, provider_events, audit, delivery_attempts) — партиции по
  времени/cell. Cell → свой PG-кластер, шардинг не «спустя два года».

### 16.3 Дорожная карта (12 шагов)

| # | Шаг | Статус |
|---|---|---|
| 1 | compose → официально dev environment | ✅ 2026-08-21 |
| 2 | `tenant_id/household_id/cell_id/call_id` во всех durable контрактах (миграции PG) | ⬜ |
| 3 | убрать cross-process `/tmp/*.wav` → continuous media transport (= Этап D) | ⬜ |
| 4 | voice → отдельные STT/TTS pools; answers → масштабируемый LLM pool | ⬜ (частично: LLM уже отдельный сервис) |
| 5 | VoiceWorker: stateless между звонками, single-owner на звонок | ⬜ |
| 6 | Outbox/incidents из telephony в отдельный worker deployment; далее durable workflow runtime | 🔶 сделано выделение (`workflow` deployment, `MOSS_OUTBOX_INPROCESS=0`); Temporal — следующим шагом |
| 7 | PgBouncer + PG HA, Redis HA, настоящий S3 | ⬜ |
| 8 | Admission Controller + hard capacity limits до autoscaling | 🔶 минимум сделан: `MOSS_MAX_CONCURRENT_CALLS`, 503 `capacity` на /calls, `calls_active/calls_limit` в /health; pools-агрегат — в шаге 4 |
| 9 | K8s deployment: HPA по своим метрикам (active sessions/worker, pending audio sec, outbox lag) | ⬜ |
| 10 | load-test harness: capacity одной cell (сертификация лимита, HEADROOM 30%) | ⬜ |
| 11 | cell router + вторая идентичная cell | ⬜ |
| 12 | 500 → 1 000 → 5 000 → 10 000 concurrent synthetic calls; failure одной cell под нагрузкой | ⬜ |

Порядок жёсткий: 2 → (4,5,6) → 8 (полный) → 3 → 7 → 10 → 9 → 11 → 12.
Шаг 3 (media transport) совпадает с Этапом D из §3.5 и выполняется один раз
на оба трека.
