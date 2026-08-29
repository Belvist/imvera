# Realtime-контур: целевая архитектура

Дата фиксации: 2026-08-27. Статус: **введён «мараторий» на новые функции телефонии** —
сначала зафиксирована архитектура realtime-контура, потом функции.

## 1. Границы (не пересекаются)

```
FreeSWITCH        = телефония и media edge   (SIP/RTP/codec/NAT/DTMF/call UUID)
Voice Runtime     = реальный разговор         (VAD/STT/Dialogue/LLM/TTS/playback)
IMVERA Core       = бизнес-логика и данные    (Postgres, SafetyEngine, memory, outbox)
```

- FreeSWITCH **не** управляет разговором: никакой бизнес-логики в Lua, диалога,
  VAD-политик, HTTP-клиента в роли state machine.
- Lua-контракт **ЗАМОРОЖЕН целиком** (решение от 2026-08-27). Изменений в
  `moss_agent.lua` больше не вносим; следующий шаг — перевод FreeSWITCH ↔ Voice
  Runtime с WAV-файлов на непрерывный bidirectional PCM stream.
- Orchestrator **никогда** не грузит тяжёлые модели (STT/LLM/TTS) в свой процесс.

## 2. CallSession — центральная сущность

Один звонок = один владелец состояния. Сейчас эту роль выполняет `CallContext`
(`telephony/core/state.py`); целевая модель — actor/task на звонок:

```python
call_id, fs_uuid
generation_id, turn_id
user_speaking, assistant_speaking
stt_task, llm_task, tts_task, playback_task
dialogue, short_memory
started_at, last_activity
```

Два звонка не могут случайно смешать состояние: у каждого свой `CallContext` +
`lock`/`turn_lock` под все мутации.

## 3. generation_id end-to-end (ВНЕДРЕНО)

Каждый принятый turn начинает новую генерацию:

- `CallContext.new_turn()` — монотонные `turn_id`/`generation_id` (общий счётчик,
  приращение под `_generation_lock`).
- `begin_turn()` инкрементирует при каждом принятом turn; перекрытие отвергается
  `CallBusyError` (429) без инкремента.
- `process_turn_stream()` тегирует **каждый** фрейм (`interim`, audio `wire`,
  `seg_file`, `done`) полями `turn_id`/`generation_id`.
- `process_turn()` и `process_text_turn()` возвращают `turn_id`/`generation_id`
  в ответе; текстовый turn тоже инкрементирует генерацию.

Идемпотентность устаревших результатов:

```python
if result.generation_id != session.generation_id:
    discard()  # старый LLM/TTS/playback не попадёт в новый turn
```

Соглашение: любой downstream-потребитель (WebApp, host dialplan, будущие STT/TTS
services) обязан игнорировать фреймы с `generation_id != current`.

## 4. Стандарт аудио

Внутри Voice Runtime ровно один формат:

```
PCM signed 16-bit · mono · 16000 Hz · 20 ms frames
```

Всё (PCMU/PCMA/Opus/G722/8k/48k) декодируется FreeSWITCH и ресемплируется ДО
входа в Voice Runtime. STT не знает ни про codec, ни про FreeSWITCH, ни про
Zoiper. WAV допускается только как запись/архив, не как realtime-транспорт.

## 5. Запрет in-process LLM/STT/TTS fallback (ВНЕДРЕНО)

`telephony/adapters/llm.py`:

- по умолчанию `_ensure_local()` возвращает `False`, модель НЕ грузится —
  каскад только `remote/cloud -> scripted fallback`;
- staging debug — только явный флаг `MOSS_LLM_ALLOW_IN_PROCESS=1`
  (никогда в production).

Пример scripted fallback: «Одну секунду, я немного задержалась. Повторите,
пожалуйста.»

## 6. Наблюдаемость (per-turn)

Каждый turn обязателен к появлению в логе как:

```
[call-agent] TURN {call_id} turn_id=.. generation_id=.. transcript=..
[call-agent] LATENCY {call_id}: turn=.. gen=.. stt=.. plan=.. gen+tts=..
              first_audio=.. usr=.. rep=..
```

Целевая метрика на turn (планируется Prometheus):

```
call_id, fs_uuid, turn_id, generation_id
audio_in_ms, vad_start_ms, vad_end_ms
stt_start, stt_final, stt_latency, stt_confidence
llm_start, llm_first_token, llm_done
tts_start, tts_first_audio
playback_start, playback_end
barge_in, cancel_reason
total_turn_latency
```

Плюс `/live` (process alive) и `/ready` (STT/LLM/TTS готовы) вместо одного `/health`.

## 7. Аварийный ответ сервиса (restart)

Активный звонок принадлежит одному Voice Worker (владельцу):

- Redis: `call_id -> worker_id` (lease, routing, locks).
- Postgres: durable turn/event history.
- Падение воркера -> `technical_failure`, а не магическая «миграция» живого RTP.

## 8. Вынос сервисов (план)

```
voice-runtime ──> STT service
              ──> LLM service
              ──> TTS service
```

Независимое масштабирование (2 Voice Runtime / 4 STT / 1 GPU LLM / 2 TTS) вместо
«каждая реплика телефонии таскает свой Whisper».

## 9. Dialogue Manager vs NLG

```
текст ─> Dialogue Manager ─> Action ─> LLM/NLG ─> фраза
```

LLM формулирует, но не управляет состоянием системы. ВАЖНО для продукта,
разговаривающего с пожилыми людьми.

## 10. Контрольный список (11 пунктов) и статус

| # | Пункт | Статус |
|---|-------|--------|
| 1 | Заморозить Lua-контракт FreeSWITCH | ✅ Сделано (дальше не менять) |
| 2 | CallSession/actor на звонок | 🟡 CallContext внедрён; async actor — план |
| 3 | WAV `/tmp` → постоянный PCM stream | ⏳ План |
| 4 | turn_id + generation_id end-to-end | ✅ Внедрено |
| 5 | Вынос STT из telephony | ⏳ План |
| 6 | Запрет in-process LLM/STT/TTS fallback | ✅ Внедрено |
| 7 | Объединение moss_providers.py + adapters/* | ⏳ План |
| 8 | ThreadingHTTPServer → единый async runtime | ⏳ План |
| 9 | /live + /ready + Prometheus + JSON-логи | 🟡 TURN/LATENCY внедрены; /live /ready — план |
| 10 | SIP/RTP/barge-in integration test | ⏳ План |
| 11 | Только потом функции (память, календарь, сценарии) | ⏳ |

## 11. Безопасность

- `docker/.env` с непустым API-ключом считать скомпрометированным,
  перевыпустить.
- Production — Docker secrets / Vault / cloud secret manager; `.env` не должен
  попадать в архив/Git.