# MossVoice Telephony

Прод-архитектура: три независимых модульных сервиса под единым супервизором.

```
                    [ moss_supervisor.py ]  (перезапуск при падении, backoff)
                    /          |          \
       1. Голос     |   2. Ответы    3. Телефония
   tts_server.py    |  llm_server.py  call_agent.py
   127.0.0.1:9600   |  127.0.0.1:9500 127.0.0.1:9400
   TTS-клон MOSS    |  Qwen3 LLM      STT+диалог
   + Whisper STT    |  /chat /health  /calls /turn /turn_stream
                    |                  │  HTTP→9500 (fallback: скрипт)
                    └──────────────────┘

   Telegram WebApp ──WS(4401/4429/4503)──> tg_server 8600 ──HTTP──> call_agent 9400
                          (initData HMAC + rate-limit + max_calls)
```

## Запуск

```bash
# Три основных сервиса (voice+answers+telephony)
./start_telephony.command

# Telegram-шлюз (поднимает ядро, если его нет): tg_server + cloudflared + bot
./tg/start_tg.sh          # env MOSSVOICE_BOT_TOKEN или tg/bot.token
```

| Компонент            | Порт                 | Назначение                |
|----------------------|----------------------|---------------------------|
| superвизор            | pidfile moss_supervisor.pid | управление, рестарт, статус |
| voice (TTS+STT)       | 127.0.0.1:9600        | MOSS-TTS-Nano клон + Whisper |
| answers (LLM)         | 127.0.0.1:9500        | Qwen3-1.7B, /chat          |
| telephony (диалог)    | 127.0.0.1:9400        | /calls, /turn, /turn_stream|
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

Те же три сервиса (+опционально Telegram-шлюз) как контейнеры — `docker/`
корня репозитория. Metal/MLX доступен только хосту, поэтому в контейнере
модели работают на CPU: TTS через ONNX-ветку MOSS-TTS-Nano, STT через
transformers-Whisper (адаптер декодирует WAV без ffmpeg, но в образ он тоже
добавлен), LLM через transformers (`MOSS_LLM_BACKEND=transformers`).

ВАЖНО про ресурсы: Docker-образ с CPU-моделями тяжёлый. При 8 ГБ VM RAM
сервис голос занимает ~6 ГБ, и LLM 1.7B начинает свопиться — генерация
деградирует до ~0.5 ток/с, реплика отвечает за 2-3 минуты. На хосте 16 ГБ
выделите Docker Desktop >= 12 ГБ RAM (Settings > Resources). E2E-проверка
проходила с дефолтом 8 ГБ: работает, но медленно.

```bash
# 1) сборка образа (CPU-torch уже скачан в wheels/, сборку не нужно ждать)
docker build -f docker/Dockerfile -t mossvoice/backend:latest .

# 2) три сервиса (порты: 9400 снаружи; voice/answers — только внутри сети compose)
docker compose -f docker/docker-compose.yml up -d

# здоровье
docker compose -f docker/docker-compose.yml ps
curl -s http://127.0.0.1:9400/health

# остановить
docker compose -f docker/docker-compose.yml down

# 3) Telegram-профиль: туннель + WebApp-страница + бот
./docker/tg_up.sh          # сам ждёт URL trycloudflare и передаёт его боту
```

Модели — через переменные (`docker/.env.example`): `MOSS_LLM_MODEL`
(дефолт `Qwen/Qwen3-1.7B`), `MOSS_STT_MODEL` (дефолт `openai/whisper-small`).
Веса кэшируются в volume `models`, записи звонков — в volume `calls`.

## FreeSWITCH (SIP, опционально)

Телефонный профиль подключается поверх трёх сервисов (не требуется для
Telegram-звонков). Ext `4400` -> `moss_agent.lua` (HTTP 127.0.0.1:9400).

- `moss_dialplan.xml` — extension `^4400$` -> `lua moss_agent.lua` (context default).
- `moss_agent.lua` — проигрывает greeting, записывает реплику, POST
  `/calls/{id}/turn`, проигрывает ответ (с barge-in), до `finished=true`.
- Проверка SIP: `fs_cli -x "originate loopback/4400/default &echo"`, записи
  в `telephony/calls/`.

## Компоненты

- `moss_supervisor.py` — прод-менеджер трёх сервисов: start/stop/status/restart,
  перезапуск с backoff, статус в `moss_supervisor.json`.
- `llm_server.py` — сервис генерации ответов: `GET /health`, `POST /chat`
  `{messages, max_tokens}` -> `{ok, text}`; очередь + 503.
- `tts_server.py` (в `runtime/scripts`) — голос: `/generate`, `/stream`,
  `/transcribe`, `/stream-cancel`; кэш prompt'а референса на всё время работы.
- `call_agent.py` — диалог: `GET /health`, `POST /say|/calls|/turn|/turn_stream`,
  `/calls/{id}/end|stream-cancel`; STT -> LLM (HTTP 9500, fallback скрипт) -> TTS.
- `tg/tg_server.py` — Telegram-шлюз: WS `/ws` (initData HMAC, rate-limit,
  лимит звонков), `/health` с метриками нагрузки.