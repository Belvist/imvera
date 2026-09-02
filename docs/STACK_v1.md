# IMVERA Stack v1 (заморозка моделей)

> Дата: 2026-09-02 (ROADMAP Э0). Менять только после бенчмарка на реальных
> телефонных записях + запись в `AGENTS.md` / `docs/CHRONICLE.md`.

## Зафиксированный прод-стек (dev/pilot на Mac)

| Роль | Выбор | Почему | Порт / env |
|------|-------|--------|------------|
| **TTS** | Silero ru v5 `kseniya` | RTF 0.015, понятность, уже в compose | `:9600`, `MOSS_TTS_PROVIDER` пусто / local |
| **STT (primary)** | Qwen3-ASR-0.6B-4bit (MLX host) | Лучший RU на живых записях (WER ~6% vs ~26 whisper-small) | `:9705`, `MOSS_STT_HOST` |
| **STT (fallback)** | faster-whisper **base** fp32 | В контейнере без MLX; small OOMs на 16GB | `MOSS_STT_MODEL=openai/whisper-base` |
| **LLM** | llama.cpp Qwen3-4B Q4_K_M | Локально, thinking off, OpenAI protocol | `:9500`, `MOSS_LLM_PROTOCOL=openai` |
| **VAD** | Silero VAD v5 (RLock на инференс) | Endpointing + /has_speech | in-process |

## Кандидаты (арена, не прод без гейта)

| Роль | Кандидат | Условие переключения |
|------|----------|----------------------|
| TTS | Qwen3-TTS 0.6B (`:9711`) | Blind test > Silero + RTF ≤ 0.5 на target CPU/GPU |
| TTS | Piper | Fallback при падении Silero |
| STT | Nemotron 3.5 (`:9710`) | A/B WER ≤ Qwen3-ASR на SIP-записях |
| LLM | Cloud (OpenRouter/DeepSeek) | Только если локальный Qwen3 не тянет качество; ПДн — юрист |

## Лицензии (коммерческий пилот)

| Компонент | Лицензия | Действие |
|-----------|----------|----------|
| Silero TTS | AGPL / CC BY-NC (проверить актуальный пакет) | **Блокер коммерции** — подтвердить у юриста или заменить на Piper/Qwen3-TTS (Apache-2.0) до платного запуска |
| Qwen3 / llama.cpp / Whisper / faster-whisper | Apache-2.0 / MIT | OK |
| Qwen3-ASR (mlx_audio) | Apache-2.0 | OK |
| Piper | MIT | OK |

## Переносимость на Linux

- Silero + faster-whisper + llama.cpp — переносятся.
- Qwen3-ASR / Qwen3-TTS host на **MLX** — **не** переносятся на Linux.
  Для Linux-пилота: либо faster-whisper (+ опционально GPU), либо облачный STT
  с договором ПДн, либо отдельный CUDA-порт моделей.

## Переменные compose (канон)

```bash
MOSS_LLM_PROTOCOL=openai
MOSS_LLM_PROVIDER=local          # или openai при облаке
MOSS_STT_HOST=http://host.docker.internal:9705
MOSS_STT_MODEL=openai/whisper-base   # fallback внутри voice/telephony
# MOSS_STT_PROVIDER=nemotron         # только после A/B
# MOSS_TTS_PROVIDER=qwen3            # только после blind test
MOSS_SILERO_SPEAKER=kseniya
```

## Бенчмарк-протокол (повторять при смене)

1. 50 реальных `user-*.wav` из `/tmp/mossvoice` или MinIO.
2. STT: WER vs ручная разметка + latency p50/p95.
3. TTS: RTF + round-trip WER (TTS→STT) + уши владельца.
4. LLM: 20 ходов `turn_text` — promise-rate 0, double-question 0, связность.
5. Результат пишется в `docs/CHRONICLE.md` с датой.

**Статус Э0:** стек зафиксирован по уже проведённым замерам (2026-08-21…
2026-09-02). Полный повторный A/B Nemotron vs Qwen3-ASR и Silero vs Qwen3-TTS
на свежих SIP-записях — перед Э9 (перенос на сервер).
