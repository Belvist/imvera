# AUTO_TEST_REPORT — автономное тестирование без Zoiper

> Дата: **2026-09-03** (итерации 1–4)  
> Исполнитель: агент (без участия владельца / без живого Zoiper GUI)

## Резюме (iteration 4 — LIVE FS path)

| Проверка | Результат |
|----------|-----------|
| `scripts/live_vera_conversation.py` (3 сценария) | **3/3 PASS** (после фикса чекера bad_symptom) |
| Путь | ESL originate → loopback/4400 → **VoiceRuntime** → turn_stream → reply WAV → STT |
| `scripts/synthetic_caller.py --strict` | **30/30 PASS** (iteration 3) |
| `make test-fast` | см. прогон ниже |

**Честно:** это **реальный FS-звонок** (originate + park + runtime), но **не Zoiper RTP**. Речь абонента = `uuid_broadcast` на **A-leg** loopback (B-leg mute на loopback — известное ограничение). Lua на 4400 **не используется** (dialplan = answer+park); опционально ext **4403** = moss_agent.lua.

---

## LIVE FS conversation (2026-09-03 вечер)

Харнесс: `scripts/live_vera_conversation.py` · README: `scripts/LIVE_VERA_CONVERSATION.md`

### Прогон 3 сценариев (ext 4400, VoiceRuntime)

#### good_path — call_id=`62380d5dd39f` PASS

| Turn | USER (audio) | VERA (STT transcribed) |
|------|--------------|------------------------|
| 1 | хорошо себя чувствую | Как настроение сегодня? |
| 2 | настроение хорошее | Как спали ночью. |
| 3 | спала нормально | Чем планируете заняться сегодня? |
| 4 | пойду в магазин | Я записала, родные получат это в приложении. |

#### bad_symptom — call_id=`f1d7db1066cd` PASS (диалог ок)

| Turn | USER | VERA |
|------|------|------|
| 1 | плохо | Расскажите, что именно беспокоит. |
| 2 | болит голова | Сейчас легче или всё ещё? |
| 3 | сильно | Что вы сейчас чувствуете, тяжесть, слабость или что-то другое? |

#### greeting_back — call_id=`0a05a5b9abde` PASS

| Turn | USER | VERA |
|------|------|------|
| 1 | здравствуйте | Здравствуйте, рада вас слышать. Как вы сегодня? |
| 2 | хорошо | Как настроение сегодня? |
| 3 | нормально | Как спали ночью. |

### Что работает на этом Mac

| Метод | Результат |
|-------|-----------|
| `loopback/4400` + VoiceRuntime | ✅ greeting + multi-turn |
| `uuid_broadcast` на **A-leg** | ✅ user chunk 66–89 KB, STT ok |
| `uuid_broadcast` на B-leg | ❌ не слышит runtime VAD |
| Lua `4403` (test dialplan) | ⚠️ установлен, но call_id иногда не доходит до telephony при гонке |
| Zoiper `1000` зарегистрирован | ✅ `show registrations`; GUI не автоматизирован |

### Инфра-фиксы во время прогона

- Очистка stale loopback каналов перед originate
- `telephony_cleanup_stale_calls()` — снятие 4 zombie-сессий при `calls_active=calls_limit=4`
- `deploy/freeswitch/dialplan_moss_lua_test.xml` — ext 4403 для Lua-тестов

```bash
python3 scripts/live_vera_conversation.py --report /tmp/live_vera_report.json
```

---

## Резюме (iteration 3 — v1 gate)

| Проверка | Результат |
|----------|-----------|
| `scripts/synthetic_caller.py --strict` | **30/30 PASS** (iteration 3) |
| `make test-fast` | **381 OK** (29 skip) |
| `dialog_quality.py --strict` | **18/18 PASS** |
| `e2e_live_calls.py --strict` | **17/17 PASS** |
| `test_auto_call_scenarios.py` | **24/24 PASS** |
| `make up telephony` + rebuild | **задеплоено**, healthy @ :9400 |

**Честно не проверено:** живой Zoiper (RTP, микрофон AirPods, barge-in, paired loopback legs). HTTP `turn_stream` + macOS `say`/ffmpeg симулирует Lua upload, но STT variance остаётся (см. ограничения).

---

## Итерации autonomous loop

| Iter | synthetic_caller | Ключевые фиксы |
|------|------------------|----------------|
| 1 | 26/30 | baseline harness; `bad_symptom` HTTP «сильно» dead-end |
| 2 | 27/30 | narrative pool + «да» после narrative; TTS expand для STT |
| 3 | **30/30** | greeting-before-wellness в resolver; flaky greeting test |

---

## Synthetic caller (`scripts/synthetic_caller.py`)

**Путь A (канон):** `POST /calls` → `POST /calls/{id}/turn_stream` (audio_b64, chunked frames) → `POST /end`.

**Путь C (гибрид):** 14 сценариев `turn_text` + 16 с `turn_stream` / silent WAV (≥50% STT path).

```bash
# Полный прогон (нужны telephony + say + ffmpeg на macOS)
make build && docker compose -f docker/docker-compose.yml up -d --force-recreate telephony
python3 scripts/synthetic_caller.py --strict

# Только dialogue (без STT)
python3 scripts/synthetic_caller.py --strict --no-wav

# Один сценарий
python3 scripts/synthetic_caller.py --scenario 02_bad_symptom_http --strict

# JSON отчёт
python3 scripts/synthetic_caller.py --strict --iteration N --json-report /tmp/syn.json
```

### Покрытие PRODUCT_FLOW (30 сценариев)

| # | Сценарий | Режим | PRODUCT_FLOW |
|---|----------|-------|--------------|
| 01 | good_path_full | text | GOOD 3 probes → notify |
| 02 | bad_symptom_http | text | BAD depth, «сильно»/«утром» |
| 03 | critical_fall | text | CRITICAL → notify |
| 04 | silence_ladder | silent×3 + text | CLARIFY ladder |
| 05–06 | goodbye / refusal | text | CLOSING terminal |
| 07 | repair_repeat | text | REPAIR |
| 08 | hello_back | text | GREETING back |
| 09 | side_question | text | SIDE_ANSWER |
| 10 | negated_fall | text | safety negation |
| 11–12 | positive / safety_confirm | text | no false red |
| 13 | stt_uncertain_mood | text | mid-band (text path) |
| 14 | medium_wellness | text | MEDIUM → BAD path |
| 15–20 | closing, symptom, narrative, help… | text | assorted |
| 21–22 | echo / low_conf | silent + text | recovery |
| 23–29 | *_wav_stream | **stream** | STT + dialogue |
| 30 | time_closing_good | text | time-of-day probes |

---

## Исправленные баги (2026-09-03)

1. **HTTP `bad_symptom` — «сильно» / «утром» → `Услышала.`**  
   - Причина: `semantic_close` для `TOPIC_BAD_SYMPTOM` требовал `word_count≥2` или `mentions_symptom`.  
   - Фикс: `agenda/manager.py` — `_bad_symptom_probe_answered()` + словарь severity/timing short answers.

2. **Narrative story → dead-end ack без вопроса**  
   - Фикс: `NARRATIVE_ACK_POOL` (≥5 реплик с вопросом); `resolver` — «да» после wellness-вопроса → `E_WELLNESS_GOOD`.

3. **«здравствуйте» уходило в BAD_PATH**  
   - Причина: short-answer wellness shortcut срабатывал до `E_GREETING`.  
   - Фикс: `resolver` — `SpeechAct.GREETING` проверяется первым в блоке `LISTEN`.

4. **Flaky `test_new_call_returns_facade_greeting`**  
   - Фикс: assert «Вера»/«Имвэра» + wellness question (пул ротируется).

---

## Ранее закрытые (сохранены)

- Closing/refusal FSM (`E_CLOSING`, `E_REFUSAL`)
- Repair dedupe skip
- Hello-back composer branch
- Negated fall wellness
- Critical terminal + verdict merge

---

## Ограничения симуляции vs Zoiper

| Симулируется | Не симулируется |
|--------------|-----------------|
| HTTP `/calls` + `/turn_stream` как Lua | SIP/RTP/SDP/Zoiper GUI |
| STT на host (Qwen3-ASR) через audio_b64 | Реальный микрофон / AirPods routing |
| Chunked TTS frames + done semantics | Barge-in / uuid_break |
| FreeSWITCH loopback (`--fs-loopback`) smoke | Качество loopback (echo-leg) |
| turn_text для быстрой регрессии диалога | STT confidence mid-call без WAV |

**Owner gate (один раз):** живой Zoiper-звонок для P4 RTP + client audio chain.

---

## Команды воспроизведения

```bash
make test-fast
python3 voice-lab/dialog_quality.py --strict
python3 voice-lab/e2e_live_calls.py --strict
cd telephony && python3 -m unittest tests.test_auto_call_scenarios -v
python3 scripts/synthetic_caller.py --strict
```

---

## Файлы

| Файл | Назначение |
|------|------------|
| `scripts/synthetic_caller.py` | Synthetic Zoiper harness (30 scenarios) |
| `scripts/live_vera_conversation.py` | **Live FS** harness (ESL + runtime/Lua) |
| `scripts/LIVE_VERA_CONVERSATION.md` | Документация live FS tester |
| `telephony/conversation_system/agenda/manager.py` | bad_symptom semantic_close |
| `telephony/conversation_system/reply/pools.py` | `NARRATIVE_ACK_POOL` |
| `telephony/conversation_system/policy/resolver.py` | greeting / narrative «да» |
| `telephony/tests/test_auto_call_scenarios.py` | 24 facade scenarios |
| `voice-lab/e2e_live_calls.py` | 17 HTTP E2E scenarios |
