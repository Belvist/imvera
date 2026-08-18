# FAST mode — первый запуск на облачных моделях (Этап 5)

Диалоговый движок MossVoice умеет работать с тремя наборами моделей без
изменения кода: выбор делается переменными окружения, отсутствие ключа —
автоматический откат на локальные модели (circuit breaker + fallback).

| Компонент | Локально (по умолчанию) | FAST mode (облако)     |
|-----------|-------------------------|------------------------|
| STT       | Whisper large-v3-turbo (MLX/CPU) | `openai` — whisper-1 |
| LLM       | Qwen3-1.7B (mlx_lm / :9500)      | `openai` — gpt-4o-mini |
| TTS       | MOSS-TTS-Nano (48 кГц, клон)     | `elevenlabs` — eleven_multilingual_v2 |

## Включение

```bash
export OPENAI_API_KEY=sk-...
export ELEVENLABS_API_KEY=...
export MOSS_TTS_ELEVEN_VOICE=<elevenlabs voice id>
docker compose -f docker/docker-compose.fast.yml up -d --build
```

или по одному компоненту (остальные остаются локальными):

```bash
MOSS_STT_PROVIDER=openai   # только STT через OpenAI
MOSS_LLM_PROVIDER=openai   # только LLM через OpenAI
MOSS_TTS_PROVIDER=elevenlabs
```

Дополнительные настройки:

```
MOSS_STT_OPENAI_MODEL=whisper-1
MOSS_LLM_OPENAI_MODEL=gpt-4o-mini
MOSS_TTS_ELEVEN_MODEL=eleven_multilingual_v2
```

## Отказоустойчивость (Этап 9)

Каждый облачный провайдер завёрнут в `moss_providers.py`:

* явный таймаут на каждый запрос;
* один повтор безопасного запроса;
* circuit breaker: 3 последовательные ошибки → провайдер считается
  недоступным на 60 с (полупробный запрос по истечении);
* ошибка провайдера не роняет звонок: STT вернёт None → «Повторите,
  пожалуйста»; LLM вернёт None → консервная фраза; TTS упал → локальный
  MOSS-TTS-Nano всё ещё поднят в voice-контейнере как резерв.

При `ready() == False` (нет ключа) фабрика логирует и сразу выдаёт локальный
бэкенд — FAST mode не «ломает» обычный запуск без ключей.

## Что остаётся локальным всегда

* голосовой демон `voice` (MOSS-TTS-Nano + Whisper) — резервный TTS/STT и
  источник клонированного голоса для будущей линии moss-voice-vN;
* детерминированная логика диалога (`DialogueEngine` в call_agent): LLM
  только формулирует фразу, действия сценария решаются без модели.

## Проверка без ключей

```bash
cd telephony && python -m unittest discover -s tests -p test_providers.py -v
```

Тесты покрывают контракты, fallback-фабрики, circuit breaker и обёртки
PCM→WAV для стриминга — сеть не используется.
