# MossVoice Telephony

Прод — Docker-микросервисы (`make up` из корня). Локальный запуск под
супервизором — для разработки.

```
   Docker compose (docker/docker-compose.yml)
   ┌──────────────────────────────────────────────────────────────┐
   │ voice :9600          answers :9500         telephony :9400   │
   │ Silero TTS (48кГц)   llama.cpp llama-      call_agent.py     │
   │ + faster-whisper     server, Qwen3-4B      STT→LLM→TTS       │
   │ /generate /stream    GGUF, OpenAI API      /calls /say       │
   │ /transcribe          /v1/chat/completions  /turn_stream      │
   │        ▲                     ▲                    │         │
   │        └─────────────────────┴──── MOSS_LLM_PROTOCOL=openai│
   │ db :5432 (Postgres, истина) · cache :6379 · storage :9000   │
   └──────────────────────────────────────────────────────────────┘
              │ 127.0.0.1:9400/9500/9600
   FreeSWITCH (хост) ── ext 4400 → moss_agent.lua
     запись реплики → POST /calls/{id}/turn_stream (segment_dir)
     → играет /tmp/mossvoice/segs_*/seg-NNNN.wav по мере готовности
   Telegram WebApp ──WS──> tg_server 8600 (профиль telegram)
```

Контракт общих путей: FreeSWITCH (хост) и telephony (контейнер) видят
`/tmp/mossvoice` **одинаково** — там Lua держит записи реплик, агент кладёт
готовые предложения (seg-файлы 16 кГц) и приветствие.

| Компонент            | Порт                 | Назначение                |
|----------------------|----------------------|---------------------------|
| voice (TTS+STT)       | 127.0.0.1:9600        | Silero TTS + faster-whisper |
| answers (LLM)         | 127.0.0.1:9500        | Qwen3-4B GGUF, `/v1/chat/completions` |
| telephony (диалог)    | 127.0.0.1:9400        | /calls, /say, /turn, /turn_stream |
| tg_server (Telegram)  | 0.0.0.0:8600          | WS-мост + WebApp           |

## Отказоустойчивость

- каждый сервис — отдельный процесс; при падении супервизор перезапускает с
  backoff 1..60 с, счётчик сбрасывается после 2 мин стабильной работы;
- LLM-демон недоступен → call_agent деградирует на скриптовые фразы;
- TTS занят → 503 + Retry-After (SingleFlight, очередь до 8 на голос);
- LLM занят → 503 + Retry-After (SingleFlight, очередь до 4);
- Telegram: rate-limit WS по IP (1/с, burst 5), не более 4 одновременных звонков
  и 16 WS-сессий; бот-токен никогда не попадает в argv (`ps`), initData HMAC
  проверяется на /ws.

## Диагностика

```bash
python3 moss_supervisor.py status
curl -s http://127.0.0.1:9500/health   # LLM
curl -s http://127.0.0.1:9600/health   # TTS
curl -s http://127.0.0.1:8600/health   # Telegram gateway
```

## Docker

Прод-стек — `make up` из корня (6 сервисов + опциональный tg-профиль).
Модели живут в volume `models` (не в образе), первый старт скачивает их;
`make update` пересобирает образы без перекачивания весов. Docker Desktop
≥ 12 ГБ RAM (при 8 начинается swap).

Ключевые переменные (`docker/docker-compose.yml`): `MOSS_TTS_MODEL`
(дефолт `silero`), `MOSS_SILERO_SPEAKER` (дефолт `kseniya`),
`MOSS_STT_MODEL` (дефолт `openai/whisper-small`, faster-whisper берёт
хвост id), `MOSS_LLM_GGUF_URL` (Qwen3-4B Q4_K_M), `MOSS_LLM_THREADS` (8),
`MOSS_SCENARIOS_FILE` — сценарии монтируются из `telephony/vera_scenarios.txt`.

## FreeSWITCH (SIP)

Телефонный профиль поверх стека. Ext `4400` → `moss_agent.lua` (HTTP
127.0.0.1:9400).

Установка диалплана (FS под brew):

```bash
cp telephony/moss_dialplan.xml \
   /opt/homebrew/etc/freeswitch/dialplan/default/mossvoice.xml
fs_cli -x reloadxml
```

- `moss_dialplan.xml` — extension `^4400$` → `lua moss_agent.lua`
  (context default; путь до lua в правиле абсолютный, репозиторный).
- `moss_agent.lua` — приветствие (кэш агента), запись реплики (2 с тишины,
  макс 15 с), **стриминговый ход**: фоновый POST `/calls/{id}/turn_stream`
  с `segment_dir` → играет `seg-NNNN.wav` по мере синтеза → до
  `finished=true`; в конце `/calls/{id}/end` и чистка temp.
- Проверка: `fs_cli -x "originate loopback/4400/default 4400 XML default"`,
  играть/писать должно в логе FS (`playback .../seg-0001.wav`).

## Компоненты

- `moss_supervisor.py` — локальный (dev) менеджер сервисов: start/stop/status,
  перезапуск с backoff. В проде его заменяет compose `restart: unless-stopped`.
- `core/dialogue.py` — режимная машина Веры (companion/check_in/clarify/
  safety_confirm/safety_active/closing), история LLM, сценарии из
  `vera_scenarios.txt`, запрет обещаний («я вызову» и т.п. запрещены).
- `core/orchestrator.py` — звонки, ходы, стриминг: `/turn` (целиком) и
  `/turn_stream` (по предложениям; `segment_dir` → seg-файлы 16 кГц для FS).
- `adapters/llm.py` — LLMClient: `MOSS_LLM_PROTOCOL=openai` (llama.cpp,
  SSE-стрим, thinking off) или native `/chat`; фолбэк — скриптовые фразы.
- `adapters/stt.py` — STTEngine + confidence (energy-гейт + сегментные
  метрики whisper); бэкенд — faster-whisper int8 (beam 1).
- `tts_server.py` (в `runtime/scripts`) — голос: `/generate`, `/stream`,
  `/transcribe`, `/stream-cancel`; бэкенды: `silero` (дефолт) и
  `moss-tts-nano` (legacy).
- `call_agent.py` — фасад: `GET /health`, `POST /say|/calls|/turn|
  /turn_stream`, `/calls/{id}/end|stream-cancel`.
- `tg/tg_server.py` — Telegram-шлюз: WS `/ws` (initData HMAC, rate-limit,
  лимит звонков), `/health` с метриками нагрузки.