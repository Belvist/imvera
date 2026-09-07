# IMVERA — сверка голосового диалога

**Дата отчёта:** 2026-09-07  
**Владелец продукта:** Даниил  
**Основание:** `IMVERA_Dialogue_System.md` редакция 2 (чеклист доказательств)  
**Предыдущая проверенная база:** `4d6913076041121a4f5127ee7af894590a3ac6d9` (цикл 21× wellness на BACKCHANNEL — воспроизведён на той базе, **не** переносится на новый SHA без повторной проверки)

---

## REPOSITORY / BRANCH / COMMIT / RUNTIME SHA

| Поле | Значение |
|------|----------|
| **REPOSITORY** | `https://github.com/Belvist/imvera.git` |
| **BRANCH** | `feature/voice-zoiper-m5` |
| **COMMIT (HEAD)** | `e0e86b042067f1860d26f681152c036795c501a4` |
| **RUNTIME SHA (проверки в этой сессии)** | `e0e86b042067f1860d26f681152c036795c501a4` |
| **Сравнение с базой** | `git diff --name-status 4d69130..HEAD` — **выполнено**, 24 файла (диалог Stage 1) |

### Доступ к GitHub

В **этой** среде `gh api repos/Belvist/imvera/commits/e0e86b0` вернул SHA успешно. Если в другой сессии был 404 — причина доступа **не установлена** (возможны: другой токен, приватность, другой org). Локальный клон и `origin` указывают на `Belvist/imvera`.

### Незакоммиченные изменения (не входят в HEAD)

```
 M scripts/voice_sip_e2e.py
 M services/asterisk_app/main.py
 M services/voice_gateway/main.py
 M tests/test_voice_stack.py
```

Результаты тестов ниже относятся к **чистому** `e0e86b0`, не к этим правкам.

### Runtime truth (рабочий стек, не live SIP)

| Параметр | Значение |
|----------|----------|
| Routing path | `CallActor` → `CallSession` → Planner / Validator / transition_store |
| Dialogue engine | Planner + QuestionLedger + FSM (`packages/dialogue/`) |
| STT (profile) | `mlx-community/Qwen3-ASR-0.6B-8bit` @ `:9101` |
| LLM (profile) | `mlx-community/Qwen3-4B-4bit` @ `:9103` |
| TTS (profile) | `mlx_customvoice` / `Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit` @ `:9102` |
| Dialogue timing | `answer_wait_ms=7000`, `backchannel_extra_ms=2000`, `pause_wait_ms=30000` (`config/voice-m5.yaml`) |
| Policy / ADR | ADR-009 (`docs/adr/009-llm-understanding-state-policy.md`) |
| Live call trace | **не снимался** в этой сессии |

---

## Таблица требований

Уровни **VERIFIED**: `policy` = заданный смысл / unit+session; `model` = реальный LLM; `audio` = размеченное аудио; `SIP` = Zoiper/телефония.

| REQUIREMENT | STATUS | IMPLEMENTATION | COMMAND | RESULT | ARTIFACT |
|-------------|--------|----------------|---------|--------|----------|
| **P0 — отсутствие цикла вопросов** (20×«ага») | **VERIFIED** (policy) | `question_ledger.py`, `planner.py`, `transition_store.py` | `python3 -m pytest tests/test_planner_question_ledger.py::test_twenty_backchannels_no_invented_facts_and_limited_attempts -q` | PASSED | — |
| **P0 — отсутствие цикла** (§23 script) | **VERIFIED** (policy) | `planner.py` | `python3 -m pytest tests/test_planner_question_ledger.py::test_planner_direct_twenty_backchannels_spec_script -q` | PASSED; 1× исходный wellness, не 21 | — |
| **P0 — смесь «ага/не знаю/кто вы/алло»** | **VERIFIED** (policy) | `answer_policy.py`, `test_mixed_nonanswer_sequence.py` | `python3 -m pytest tests/test_mixed_nonanswer_sequence.py -q` | PASSED | — |
| **P0 — перефразирование wellness (3-я попытка блокируется)** | **VERIFIED** (policy) | `QuestionGoal.max_automatic_attempts=2` | `python3 -m pytest tests/test_planner_question_ledger.py::test_backchannel_wait_then_clarify_then_unresolved -q` | PASSED | — |
| **P0 — WAIT** (7s окно, одно +2s, нет пустого TTS) | **VERIFIED** (policy) | `wait_state.py`, `call_actor.py`, `profile.dialogue_timing_settings` | `python3 -m pytest tests/test_wait_contract.py tests/test_call_actor_backchannel_ledger.py -q` | 4 PASSED | — |
| **P0 — WAIT** (реальные 7s таймеры CallActor) | **UNVERIFIED** | То же | — | Fake clock / короткий профиль в тестах; live timer не измерен | — |
| **P0 — смесь через CallActor** | **VERIFIED** (policy) | `test_mixed_nonanswer_sequence_callactor.py` | `make test-dialogue-gates` | PASSED | — |
| **P0 — жалоба через CallActor** | **VERIFIED** (policy) | `test_complaint_voice_path.py` | `make test-dialogue-gates` | PASSED | — |
| **P0 — PAUSE CallActor** | **VERIFIED** (policy) | `test_call_actor_pause_ack_starts_pause_wait` | `make test-dialogue-gates` | PASSED | live timer NOT VERIFIED |
| **P0 — старый таймер после ответа** | **VERIFIED** (policy) | `control_epoch` + `_on_wait_deadline` | `python3 -m pytest tests/test_wait_contract.py::test_stale_wait_id_ignored_after_control_epoch_bump -q` | PASSED | — |
| **P0 — «ага» не создаёт wellness/consent** | **VERIFIED** (policy) | `semantic_bridge`, `planner._handle_backchannel_on_active_goal` | `python3 -m pytest tests/test_planner_question_ledger.py tests/test_dialogue_acceptance_gaps.py::test_control_backchannel_does_not_fill_slot -q` | PASSED | — |
| **P0 — «да» при can_talk vs consent** | **VERIFIED** (policy, частично) | `semantic_bridge`, `interpretation.py` | `python3 -m pytest tests/test_voice_stack.py::test_semantic_can_talk_with_pending_answer tests/test_dialogue_acceptance_gaps.py::test_no_to_can_talk_does_not_repeat_same_question -q` | PASSED | — |
| **P0 — «нет» при can_talk → CLOSE без анкеты** | **VERIFIED** (policy) | `planner._handle_can_talk_decline` | `python3 -m pytest tests/test_dialogue_acceptance_gaps.py::test_no_to_can_talk_does_not_repeat_same_question -q` | PASSED | — |
| **P0 — прерванный вопрос + «да»** | **VERIFIED** (policy) | `test_dialogue_acceptance_gaps` | `python3 -m pytest tests/test_dialogue_acceptance_gaps.py::test_question_without_delivery_evidence_is_not_complete -q` | PASSED | — |
| **P0 — жалоба «голова болит»** (полная цепочка LLM) | **VERIFIED** (policy, заданный JSON) | `semantic_validator`, `planner.reflect_report` | `python3 -m pytest tests/test_semantic_pipeline.py::test_complaint_reflects_without_praise -q` | PASSED; **реальный LLM NOT VERIFIED** | — |
| **P0 — «с утра голова болит»** (без повтора времени) | **VERIFIED** (policy) | `semantic_validator` temporal guard | `python3 -m pytest tests/test_semantic_pipeline.py -q` | PASSED (span/temporal) | — |
| **P0 — «спала плохо, а вы кто?»** (смешанный смысл) | **VERIFIED** (policy, заданный JSON) | `semantic_bridge`, `session` | `python3 -m pytest tests/test_dialogue_acceptance_gaps.py::test_fact_and_question_in_same_utterance_preserve_fact -q` | PASSED (wellness+question, не полный сценарий «кто вы») | — |
| **P0 — тихая речь / фон / телевизор** | **UNVERIFIED** | STT worker всё ещё `asr_quality="GOOD"` константой (`services/stt/worker.py`) | — | Нет корпуса 40 записей | — |
| **P0 — STOP при медленном LLM** | **UNVERIFIED** | `control_epoch` при barge-in | `python3 -m pytest tests/test_inference_stop_epoch.py -q` | PASSED только epoch+wait; не LLM+STOP | — |
| **P0 — u1 отменён, u2 применён** | **VERIFIED** (policy) | `call_actor._drain_utterance_outcomes` | `python3 -m pytest tests/test_dialogue_acceptance_gaps.py::test_real_second_utterance_is_not_lost_on_state_version_change -q` | PASSED | — |
| **P0 — доставка голоса** (FIFO, FLUSH, downlink) | **UNVERIFIED** | `playback.py`, `call_actor.py` | — | Нет SIP-прогона на `e0e86b0` | — |
| **P0 — outbox / DELIVERY_UNKNOWN** | **VERIFIED** (policy) | `outbox.py`, `transition_store.py`, `test_dispatch_failure_matrix.py` | `python3 -m pytest tests/test_dispatch_failure_matrix.py -q` | 5 PASSED; CallActor finalize wired, **PG table NOT VERIFIED** | — |
| **P0 — сохранение целей при рестарте** | **VERIFIED** (policy) | `transition_store`, metadata snapshot | `python3 -m pytest tests/test_planner_question_ledger.py::test_restart_preserves_unresolved_goal -q` | PASSED | — |
| **P0 — исправление времени / память между звонками** | **UNVERIFIED** | Observations schema — Stage 4 | — | — | — |
| **P0 — изоляция двух людей** | **UNVERIFIED** | `family_id` в session | — | Нет теста двух person | — |
| **P0 — конечность ошибок** (STT/LLM/тишина) | **UNVERIFIED** | Частично `partial_unresolved_close`, disconnect handling | — | Нет fault-injection матрицы | — |
| **Приёмка — корпус 120** | **UNVERIFIED** | — | — | — | — |
| **Приёмка — 100 ходов** | **UNVERIFIED** | — | — | — | — |
| **Приёмка — Zoiper 10 звонков / 100 ходов** | **UNVERIFIED** | `scripts/voice_sip_e2e.py` (есть незакоммиченные правки) | — | Не запускалось на `e0e86b0` | — |
| **Приёмка — latency p50/p95** | **UNVERIFIED** | Stage timings в CallActor | — | Нет `docs/latency-baseline-*.md` | — |

### Сводный прогон unit-тестов (policy)

```bash
python3 -m pytest tests/ -q
# 170 passed, 4 skipped (working tree, Stage 2 uncommitted)
```

---

## CHANGED (e0e86b0 относительно 4d69130)

Диалог Stage 1 — **24 файла**, ключевое:

- `packages/dialogue/question_ledger.py` — QuestionGoal, лимит 2 попытки
- `packages/dialogue/planner.py` — BACKCHANNEL → WAIT, UNRESOLVED, reserve/delivery
- `packages/dialogue/transition_store.py` — commit до TTS, mid-call metadata
- `packages/voice_runtime/wait_state.py` — §6.1 answer-wait
- `packages/voice_runtime/call_actor.py` — event-driven wait, `control_epoch`
- `config/voice-m5.yaml` — `dialogue_timing`
- Тесты: `test_planner_question_ledger.py`, `test_wait_contract.py`, `test_inference_stop_epoch.py`, `test_call_actor_backchannel_ledger.py`
- `docs/adr/009-llm-understanding-state-policy.md`, `migrations/002_dialogue_transition.sql`

**Не в коммите e0e86b0:** SIP uplink правки (`voice_sip_e2e.py`, `asterisk_app`, `voice_gateway`).

---

## VERIFIED (эта сессия)

| Команда | Результат |
|---------|-----------|
| `git rev-parse HEAD` | `e0e86b042067f1860d26f681152c036795c501a4` |
| `git diff --name-status 4d69130..HEAD` | 24 файла (см. выше) |
| `python3 -m pytest tests/test_planner_question_ledger.py tests/test_wait_contract.py tests/test_inference_stop_epoch.py tests/test_call_actor_backchannel_ledger.py -q` | 9 passed |
| `python3 -m pytest tests/test_dialogue_acceptance_gaps.py -q` | 13 passed |
| `python3 -m pytest tests/ -q` | 157 passed, 2 skipped |

**На `e0e86b0` цикл 21× wellness при 20 BACKCHANNEL:** **не воспроизводится** на уровне policy (тесты §23 / 20×«ага» зелёные). Это **не** доказывает живой SIP.

---

## NOT VERIFIED

- Смешанная последовательность «ага / не знаю / кто вы / алло» через CallActor с реальными таймерами
- PAUSE end-to-end
- Полная цепочка жалобы с **реальным** LLM (Interpreter → Renderer)
- Аудиокорпус, admission, честный STT quality
- Outbox §15 policy matrix — **VERIFIED** locally; PG wire и live interrupt — NOT VERIFIED
- Cross-call memory, исправления времени, изоляция двух людей
- Корпус 120, 100 ходов, Zoiper 10×, latency p50/p95
- Live `call_id` и двусторонние записи

---

## REMAINING RISKS

1. **Policy ≠ модель:** зелёные unit-тесты с подставленным `SemanticPayload` не доказывают понимание живой речи.
2. **STT:** `services/stt/worker.py` возвращает `asr_quality="GOOD"` константой — D01/D03 на аудио не закрыты.
3. **Stage 2 в working tree (не в HEAD):** SemanticAdapter/reducer/outbox — policy-тесты зелёные; live voice path **NOT VERIFIED**.
4. **PG outbox:** metadata-only; `migrations/002` не применена к `pg_store`.

---

## NEXT GATE

**Один блокер:** смешанный P0-сценарий + реальная модель на voice path для жалобы.

| | |
|--|--|
| **Задача** | Добавить `test_mixed_nonanswer_sequence_callactor.py` (ага/не знаю/кто вы/алло) + прогон «голова болит» через HttpLLM на M5 |
| **Команда** | `python3 -m pytest tests/test_mixed_nonanswer_sequence_callactor.py tests/test_complaint_voice_path.py -q` (после реализации) |
| **Артефакт** | JSONL trace с `call_id`, intent по целям, отсутствие 3+ wellness attempts |

---

## Примечание о статусе дефекта 4d69130

На базе `4d69130` цикл (1 вопрос + 20 BACKCHANNEL → 21 одинаковая фраза) был **воспроизведён ранее**.  
На `e0e86b0` при policy-тестах цикл **не воспроизводится**.  
**SIP/live** на новом SHA — **UNVERIFIED**.
