# MossVoice / IMVERA — голосовой агент заботы

Телефонный голосовой агент для пожилых людей: звонок → распознавание →
диалог с памятью → вердикт безопасности → уведомление семьи. Всё на CPU,
полностью в Docker-микросервисах.

**Голос:** Silero TTS ru v5 (женский `kseniya`, 48 кГц) · **LLM:** Qwen3-4B
GGUF через llama.cpp (OpenAI-совместимый API) · **STT:** faster-whisper
(CTranslate2 int8) · **Правило продукта:** Вера никогда не обещает «вызову /
позвоню / отправлю» — она записывает, записи видят близкие в приложении.

## Архитектура

**Dev environment** (этот compose) — одна нода, по одной реплике каждого
сервиса. Продуктовая архитектура (cells, voice worker pools, admission
router, PgBouncer/PG-HA, K8s HPA) определена в
`ENGINEERING_PLAN.md` §16 и будет строиться отдельно от этого файла.

| Сервис | Порт | Назначение |
|---|---|---|
| `voice` | 127.0.0.1:9600 | Silero TTS + faster-whisper STT (`tts_server.py`) |
| `answers` | 127.0.0.1:9500 | llama.cpp `llama-server`, Qwen3-4B Q4_K_M, `/v1/chat/completions` |
| `telephony` | 127.0.0.1:9400 | диалоговый движок (`call_agent.py`): STT → LLM → TTS |
| `workflow` | — | outbox-доставка + эскалация инцидентов (отдельный deployment) |
| `db` / `cache` / `storage` | 5432 / 6379 / 9000 | PostgreSQL (истина) + Redis (кэш) + MinIO (аудио) |
| `tg` (профиль telegram) | 8600 | Telegram WebApp WS-мост |

Поток звонка: FreeSWITCH (ext **4400**, `telephony/moss_agent.lua`) →
`/calls/{id}/turn_stream` → STT → LLM (стрим токенов) → TTS по предложениям →
Lua играет каждое предложение **сразу**, пока остальное генерируется.
Ответы и приветствие пишутся в общий каталог `/tmp/mossvoice` (одинаковые
пути для контейнера и FreeSWITCH на хосте).

## Запуск (Docker — основной способ)

```bash
make up        # собрать и поднять ВЕСЬ стек: db cache storage voice answers telephony
make ps        # статус сервисов
make logs      # логи (Ctrl-C — выход)
make update    # обновить: пересобрать образы и перезапустить (модели не перекачиваются)
make stop      # остановить (данные в volume сохраняются)

cd docker && ./tg_up.sh   # + Telegram-профиль (опционально)
```

Модели живут в volume `models`, НЕ в образе: первый старт скачивает их
(Silero ~0.4 ГБ + whisper-small ~0.5 ГБ + Qwen3-4B GGUF ~2.4 ГБ), обновления
образов их не трогают. Всё на CPU; **Docker Desktop ≥ 12 ГБ RAM**
(Settings → Resources → Memory; при 8 ГБ начинается swap и деградация).

## Телефония (FreeSWITCH)

Локальный SIP-агент отвечает на номер **4400**. Подключение диалплана:

```bash
cp telephony/moss_dialplan.xml \
   /opt/homebrew/etc/freeswitch/dialplan/default/mossvoice.xml
fs_cli -x reloadxml
```

Тест без телефона: `fs_cli -x "originate loopback/4400/default 4400 XML default"`.

## Сценарии и правила Веры

- `telephony/vera_scenarios.txt` — сценарии разговоров (ежедневная проверка,
  свободный разговор, жалоба на здоровье, просьба о помощи, беспокойство за
  близких). Смонтирован в контейнер: правите файл → `docker compose restart
  telephony`, без пересборки.
- Запрет ложной надежды (в промпте и скриптах): никаких «я вызову скорую»,
  «позвоню близким», «передам родным». Только «я записала», «близкие это
  увидят»; можно спросить «нужна ли скорая?». Действия делают близкие через
  приложение.
- Безопасность: вердикты решает детерминированный `core/safety_engine.py`
  (0 ложных GREEN на регрессионном корпусе); в `safety_confirm`/`safety_active`
  реплики — точные скрипты, LLM не участвует.

## Диагностика и тесты

```bash
make test-fast   # офлайн-сьют в прод-образе (169 тестов)
make test-live   # сьют + HTTP-интеграция с живым voice-демоном
make test-db     # data-core и incident drill'ы с реальным Postgres

curl -s http://127.0.0.1:9600/health   # TTS/STT (ready, stt_ready)
curl -s http://127.0.0.1:9500/health   # llama.cpp {"status":"ok"}
curl -s http://127.0.0.1:9400/health   # telephony (tts, pg, redis)
```

## Латентность (замеры 2026-08-21, CPU 10 ядер)

| Стадия | Было | Стало |
|---|---|---|
| Пауза тишины после фразы (FS record) | 10 с | 2 с |
| STT (faster-whisper int8, beam 1) | 8–18 с | 1.2–3 с |
| LLM первая фраза (Qwen3-4B Q4, 8 потоков, thinking off) | 6–14 с | 1.5–3 с |
| TTS первое предложение (Silero) | — | 0.1–0.3 с |
| **Ход целиком (11 с речи → готовый ответ)** | ~25–30 с | **~6 с** |
| **Первый звук в трубке** | ~25 с | **~4–7 с** (2 с тишина + STT + первое предложение) |

Следующий рубеж (2–3 с) — Этап D: стриминг аудио из FreeSWITCH в агент
(распознавание во время речи, barge-in), см. `ENGINEERING_PLAN.md` §14–15.

## Data-core (Postgres/Redis/MinIO)

Состояние звонков живёт в Postgres (единственный источник истины), Redis —
только кэш/locks с явной DEGRADED-семантикой, аудио — в MinIO с SHA-256.
Outbox (`FOR UPDATE SKIP LOCKED`) для уведомлений, webhook-инбокс
идемпотентен. Drill'ы в `telephony/tests/test_data_core.py`.

## Инциденты и эскалация

RED-вердикт открывает durable-инцидент (`open → ack → checking → resolved |
false_alarm`); эскалация telegram → sms → call с fallback, dedup-ключи,
таймеры от PG `now()`, каждый переход в `audit_log`. Drill'ы в
`telephony/tests/test_incidents.py`.

## Состав

```text
runtime/scripts/    tts_server, tts_common (faster-whisper адаптер),
                    moss_runtime/silero_tts_backend.py (голос)
telephony/          call_agent, core/ (диалог, оркестратор, safety),
                    adapters/ (llm, moss_tts, stt), moss_agent.lua,
                    vera_scenarios.txt, moss_dialplan.xml, тесты
docker/             Dockerfile + compose (6 сервисов + tg-профиль)
scripts/            llama_entrypoint.sh (скачивание GGUF при старте)
voice-lab/          текстовый полигон: REPL, корпус 100 сценариев, Gate-отчёты
refs/               эталонные голосовые образцы (для legacy MOSS-бэкенда)
```

## Лицензии

Интерфейсный код — MIT. Silero TTS — GNU AGPL / CC BY-NC (ознакомиться с
условиями перед коммерческим использованием). Qwen3 (Apache-2.0), Whisper
(MIT), llama.cpp (MIT), faster-whisper (MIT) — на условиях их лицензий.
MOSS-TTS-Nano (Apache-2.0) остался как legacy-бэкенд `--model moss-tts-nano`.

## Безопасность голоса

Клонируйте только собственный голос или голос человека, давшего явное
разрешение.
