# IMVERA Architecture v1.0 (ADR)

> Заморожено 2026-09-02 (ROADMAP Э0). Источник: `read.md` §«Что я прямо
> принимаю». Менять только явным решением владельца + запись в
> `AGENTS.md` «Ключевые решения».

## 18 замороженных решений

1. **FreeSWITCH остаётся** телефонией (SIP/RTP control plane).
2. **Lua phone brain удаляется** после подтверждённого cutover на VoiceRuntime
   (сейчас прод ещё на Lua — cutover = гейт Э1).
3. **Один VoiceRuntime** на ноду; один процесс владеет живыми звонками.
4. **Один CallSession-actor на звонок** до hangup (single ownership).
5. **ESL = только управление** (originate, break, setvar, events) — не media pipeline.
6. **MediaAdapter abstraction** — continuous PCM16 mono 16 kHz / 20 ms frames.
7. **Внутри канон PCM16 mono 16k/20ms**; неправильный формат → media-unhealthy.
8. **STT / Agent / LLM / TTS** — отдельные contracts (логически; не обязательно
   отдельные микросервисы на пилоте).
9. **Agent не знает про SIP/RTP/WAV** — только текст/события/аудио-кадры.
10. **Persistence не стоит в latency path** — durable spool / async worker.
11. **`generation_id` — hard safety boundary** для barge-in / flush / cancel.
12. **Inbound и outbound используют один VoiceRuntime**.
13. **Приложение (iOS) использует тот же conversation core** через Product API,
    не отдельный brain.
14. **Active call принадлежит одному cell** до hangup (нет seamless RTP failover).
15. **Capacity = concurrent calls**, не users.
16. **Масштаб = pools/cells**, не переписывание бизнес-логики.
17. **Real SIP E2E обязателен** в release gate (не только loopback).
18. **Legacy удаляется после подтверждённого cutover** (не раньше).

## Дополнительные инварианты

- Вердикт безопасности — детерминированный `SafetyEngine`, не LLM.
- Техническая ошибка **никогда** не маскируется под GREEN или NO_CONTACT.
- Вера никогда не обещает «я вызову / позвоню / отправлю» — только «я записала».
- Согласие на регулярные звонки даёт **сам подопечный** (voice/DTMF); семья
  не может согласиться за него; молчание ≠ согласие.
- Postgres = источник истины; Redis = кэш/locks с DEGRADED-семантикой.
- Уведомления только через transactional outbox (идемпотентность + retry).

## Границы процессов (пилот)

```text
Product API (:9480)     — auth, households, schedules, history, incidents
telephony (:9400)       — dialogue Serve (Agent + Safety + orchestrator)
VoiceRuntime (:9700)    — CallSession + MediaAdapter + ESL control
voice (:9600)           — Silero TTS (и опционально local STT)
answers (:9500)         — llama.cpp LLM (profile local-llm)
host STT/TTS            — 9705/9710/9711 (MLX на Mac; Linux — отдельно)
workflow / retention    — outbox + TTL purge
FreeSWITCH              — SIP; dialplan park → VoiceRuntime (после Э1)
```
