# Dialogue 3.0 — проверка и статус (2026-09-03)

> **Статус:** Фаза 0 + Фаза 1 **закрыты в коде**. Track A (hybrid LLM pilot) **в коде**, default **off**. Owner gate: живой Zoiper после `make up telephony`.

## Модель речи (честно)

**Не «LLM every turn».** Прод-путь — **hybrid**:

| Путь | По умолчанию | С флагами |
|------|--------------|-----------|
| Check-in agenda | Rotated pools (`allow_llm=False`) | `MOSS_DIALOGUE_LLM_CHECKIN=1` → guarded LLM на «самочувствие» и «сон»; pools = fallback |
| Side-question | GENERIC_ACKS pools | `MOSS_DIALOGUE_LLM_SIDE_QUESTIONS=1` (или зеркалит check-in) |
| Narrative off-topic | Guarded LLM | без изменений |
| Safety / symptom yes-no | Скрипт / pools | без изменений |

Guards на всех LLM-ветках: `sanitize_segment`, `reply_too_similar`, max 1 `?`, promise/medical блок.

## Структура

```
telephony/core/conversation/
  compose.py    — intents + rotated fallback pools
  flags.py      — MOSS_DIALOGUE_LLM_* feature flags
  guards.py     — broken/mirror/promise + reply_too_similar (loop detector)
  goals.py      — AGENDA + TOPIC_KEYS
  pools.py      — GREETING, TOPIC, WRAP, SYMPTOM, MINIMAL pools (5–6 variants each)
  danger.py     — alert-terminal copy
  engine.py     — ConversationEngine.prepare_plan()
  reply.py      — resolve_spoken_reply (pools fallback when LLM fails guards)
```

`telephony/core/dialogue/` — пакет: `fsm.py` (DialogueFSM), `agent.py` (Agent),
`classifiers.py`, `prompts.py`, `cleaners.py`, `skill_state.py`; `_pick_not_repeated`,
`_dedupe_reply`, rotated greeting via `/calls` → Lua. LLM context: SkillState + последние 3–4 хода `llm_history`.

## Закрыто (2026-09-03)

| Пункт | Статус |
|-------|--------|
| Guard на **все** сегменты TTS (`sanitize_segment`) | ✅ orchestrator.py |
| Rotated fallbacks (не один скрипт на тему) | ✅ pools.py + Agent._topic_fallback |
| Rotated greeting (6 вариантов, sync Lua) | ✅ start_check_in + `/calls` `{greeting}` |
| LLM/скрипт dedupe (`reply_too_similar`) | ✅ guards.py + `_dedupe_reply` перед commit |
| STT confirm cap (1× «Я правильно услышала?») | ✅ `_stt_confirm_used` |
| Symptom clearing loop («отпустило» → resume) | ✅ `_symptom_resolved` + `_clearing_reasks` |
| Narrative не закрывает тему длинным «хорошо» | ✅ `_maybe_narrative_off_topic` word-count guard |
| Hybrid LLM pilot (Track A) | ✅ flags + guarded allow_llm (default off) |
| `dialog_quality --strict` | ✅ **23/23 PASS** |
| `make test-fast` | ✅ **434 OK** (29 skip) |

## Feature flags (docker/.env)

```bash
# Pilot: LLM перефразирует вопросы только на «самочувствие» и «сон»
MOSS_DIALOGUE_LLM_CHECKIN=1

# Side-questions: ответ по сути (default = как check-in, если не задано)
MOSS_DIALOGUE_LLM_SIDE_QUESTIONS=1
```

Без флагов поведение как Dialogue 3.0 — только pools.

## Owner gate (не автоматизируется)

1. `make up telephony` — пересборка образа
2. **1 живой Zoiper-звонок** — проверить: нет 5× одинаковой фразы, greeting меняется между звонками
3. **1 danger-звонок** («упал» / «мне плохо») — нет «вызову скорую», есть запись для близких
4. **С флагом check-in:** 1 звонок на pilot-темах — LLM-формулировка, но тот же topic keyword и guards

## До Newo-class UX (ROADMAP Э1, не этот PR)

- ESL media cutover 4400 (P4 live)
- Barge-in на живом канале
- p50 first_audio &lt; 1.5 s на реальном SIP
- **Latency baseline (F8):** [`docs/LATENCY_BASELINE.md`](LATENCY_BASELINE.md) + `voice-lab/latency_baseline.py`
- **STT streaming spike (B1):** [`docs/STT_STREAMING_SPIKE.md`](STT_STREAMING_SPIKE.md)

## Команды

```bash
make test-fast
python3 voice-lab/dialog_quality.py --strict
make up telephony
```
