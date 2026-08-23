# MOSS-TTS-Nano backend (клонирование голоса на CPU)

> **Статус: legacy.** Дефолтный бэкенд голоса с 2026-08-20 — **Silero TTS
> ru v5** (`runtime/scripts/moss_runtime/silero_tts_backend.py`, запуск
> `tts_server.py --model silero`, голос через `MOSS_SILERO_SPEAKER`,
> дефолт `kseniya`). Silero выбран потому, что продукту нужен стандартный
> женский голос без артефактов; клонирование не требуется. Nano остался
> как `--model moss-tts-nano` (этот документ описывает его).

`runtime/scripts/moss_backend.py` — движок синтеза речи на базе
**MOSS-TTS-Nano** (OpenMOSS / MOSI.AI, лицензия apache-2.0):

- ~0.1B параметров, ONNX Runtime, **чистый CPU** (без torch при инференсе);
- 20 языков, включая русский; авто-ударения и нормализация;
- **zero-shot клонирование голоса** по референс-аудио (~8–15 сек записи);
- встроенные голоса без референса: Junhao, Zhiming, Weiguo, Xiaoyu,
  Yuewen, Lingyu, Ava (по умолчанию), Bella, Adam и др.;
- нативный вывод 48 kHz; стриминг покадровым декодированием;
- работает на 1 ядре CPU (проверено на MacBook Air M4 производителем).

Архитектура: Autoregressive Audio Tokenizer + LLM (5 ONNX-графов:
prefill / decode_step / local_decoder / local_cached_step /
local_fixed_sampled_frame + кодеки MOSS-Audio-Tokenizer-Nano, 48 кГц, 12.5 Гц).

## Подключение к серверу

Драйвер реализует тот же duck-typed интерфейс `tts_model`, что прежние
бэкенды (`build_prompt_cache` / `generate_with_prompt_cache` /
`_generate_with_prompt_cache`), поэтому `tts_server.py` (`/say`, `/generate`,
`/stream`), телефония и Docker работают без изменений.

## Веса

Каталог по умолчанию: `runtime/models/` (`MOSS_TTS_MODEL_DIR`)

```text
MOSS-TTS-Nano-100M-ONNX/         # TTS-графы + tokenizer (~640 МБ)
MOSS-Audio-Tokenizer-Nano-ONNX/  # кодеки encode/decode (~86 МБ)
```

Если каталог пуст (Docker-том), веса скачиваются автоматически при первом
запуске из HuggingFace:

- `OpenMOSS-Team/MOSS-TTS-Nano-100M-ONNX`
- `OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX`

## Переменные окружения

| переменная | по умолчанию | назначение |
|---|---|---|
| `MOSS_TTS_MODEL_DIR` | `runtime/models` | каталог ONNX-весов |
| `MOSS_TTS_VOICE` | `Ava` | встроенный голос, если референс не задан |
| `MOSS_TTS_THREADS` | число CPU | потоки onnxruntime |
| `MOSS_TTS_MODEL` (compose) | `moss-tts-nano` | `--model` для tts_server |

## Разметка текста

`[pause:400ms]` → пауза, `[sigh]`/`[whisper]` вырезаются при нормализации.
Текст автоматически нормализуется (робустный препроцессор) и режется на
фрагменты по токен-бюджету; между фрагментами клона вставляется короткая
пауза (как в официальном демо).

## Рантайм

Официальный ONNX CPU-рантайм OpenMOSS/MOSI.AI вендорен в
`runtime/scripts/moss_runtime/` с патчами: убраны `torch`/`torchaudio`
(референс читается через soundfile/librosa), относительные импорты.

## Производительность (M-серия, CPU)

- первая синхронная фраза ~1.5–2.5 с текста (3–4 с аудио);
- клонирование референса — один раз при старте сессии;
- `/health` → `sample_rate=48000`.
