# MossVoice Backend

Локальный голосовой клон на базе **MOSS-TTS-Nano** (OpenMOSS / MOSI.AI,
apache-2.0) с телефонным контуром. Лёгкая модель (~0.1B, ONNX, чистый CPU),
работает без GPU; клонирует голос по референс-аудио, а без него пользуется
встроенными голосами.

## Архитектура

Четыре независимых сервиса под единым супервизором:

| Сервис | Порт | Назначение |
|---|---|---|
| voice (`runtime/scripts/tts_server.py`) | 127.0.0.1:9600 | MOSS-TTS-Nano клон + Whisper STT |
| answers (`telephony/llm_server.py`) | 127.0.0.1:9500 | Qwen3-1.7B LLM, `/chat` |
| telephony (`telephony/call_agent.py`) | 127.0.0.1:9400 | STT → LLM → TTS диалог, SIP |
| tg-шлюз (`telephony/tg/tg_server.py`) | 0.0.0.0:8600 | Telegram WebApp WS-мост |

Супервизор `telephony/moss_supervisor.py` перезапускает упавшие сервисы с
backoff 1–60 с. Схема — в `telephony/README.md`, детали TTS — в
`docs/MOSS_TTS_BACKEND.md`.

## Запуск (локально)

```bash
./telephony/start_telephony.command        # голос + ответы + телефония
./telephony/tg/start_tg.sh                 # + Telegram-шлюз и туннель
```

Требования: Python 3.10+ (оптимально 3.12), ffmpeg, зависимости в
`runtime/qwen-venv`. Веса MOSS-TTS-Nano лежат в `runtime/models/`
(при пустом каталоге скачиваются из HuggingFace автоматически).

Локальный SIP-агент отвечает на номер **4400** (нужен установленный
FreeSWITCH).

## Запуск (Docker)

```bash
docker compose -f docker/docker-compose.yml up -d --build   # voice+answers+telephony
cd docker && ./tg_up.sh                                     # + Telegram-профиль
```

Всё работает на CPU; Docker Desktop нужно ≥ 8 ГБ RAM. Веса скачиваются в
volume при первом старте.

## Диагностика и тесты

```bash
python3 telephony/moss_supervisor.py status
curl -s http://127.0.0.1:9600/health        # TTS
curl -s http://127.0.0.1:9500/health        # LLM
bash telephony/tests/run_tests.sh
```

## Состав

```text
runtime/scripts/    moss_backend, вендоренный ONNX-рантайм, tts_common, tts_server
runtime/models/     ONNX-веса MOSS-TTS-Nano и MOSS-Audio-Tokenizer-Nano
telephony/          call_agent, llm_server, supervisor, tg-шлюз, тесты, FreeSWITCH
docker/             Dockerfile + compose (voice/answers/telephony/tg/tunnel/bot)
refs/               эталонные голосовые образцы (референс для клонирования)
```

## Лицензии

Интерфейсный код — MIT. MOSS-TTS-Nano и ONNX-рантайм — Apache-2.0
(OpenMOSS / MOSI.AI). Qwen3 (LLM) и Whisper распространяются на условиях
их собственных лицензий.

## Безопасность голоса

Клонируйте только собственный голос или голос человека, давшего явное разрешение.
