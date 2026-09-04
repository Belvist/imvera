# Система разговоров для звонка IMVERA

> **Статус:** архитектурный план и каркас пакета (2026-09-03).  
> **Решение:** текущий стек `telephony/core/dialogue/` + `telephony/core/conversation/` **не эволюционируем** — заменяем поэтапным cutover.  
> **Импорт в проде (целевой):** `telephony.conversation_system` (каталог `telephony/conversation_system/` создаётся на фазе 1).

---

## Почему текущая система продолжит ломаться

Анализ кода (~4000 строк dialogue + conversation, ~1700 orchestrator) и истории инцидентов в `AGENTS.md`:

| # | Симптом (живые звонки / owner) | Корень в архитектуре |
|---|--------------------------------|----------------------|
| 1 | «Она не слышит / ага / повтор» | Логика тишины, STT-reason и agenda перемешаны в `Agent.plan_reply` и `DialogueFSM._classify` |
| 2 | Один и тот же вопрос 5× | Повестка = индекс `_agenda_idx`, а не семантика «тема закрыта»; dedupe ловит текст, не намерение |
| 3 | Длинный рассказ → шаблон «Как сон?» | Narrative guard — патч поверх FSM; `SkillState.topics_covered` = пройденные индексы, не смысл |
| 4 | Side-question («Кто ты?») → снова agenda | FSM resume агрессивнее ответа; pools частично маскируют |
| 5 | `dialog_quality --strict` 23/23, UX «позорный» | Харнесс = regex-инварианты spoken path, не понимание и уместность |
| 6 | Каждый фикс = новый флаг на Agent | 30+ extended-state полей при «формальной» FSM (`_stt_confirm_used`, `_wellness_path`, …) |
| 7 | FSM actions делают всё сразу | `fsm.py` (~986 строк): classify + compose + pick pool + safety side effects |
| 8 | Два API ответа (`intent` / `fallback`) | Legacy fork; LLM path и pool path расходятся в orchestrator |
| 9 | `ConversationEngine` — заглушка | Только `sanitize_legacy_plan`; заявленный goal-FSM не существует |
| 10 | Три места правки | `dialogue/`, `conversation/`, `orchestrator.py` — нет единой границы «один ход» |

**Вывод:** нужна **новая система с чистыми слоями**, а не Dialogue 4.0 поверх DialogueFSM.  
`SafetyEngine` (детерминированный вердикт) **сохраняем**; всё остальное в dialogue path — **переписываем**.

---

## Цели и инварианты

### Продуктовые цели

1. **Звонок как задача, не чат:** greeting + wellness listen → адаптивная ветка (GOOD: 2–3 пробы | BAD: симптом | CRITICAL: fast close) → record+notify → closing по band и времени суток. См. `docs/PRODUCT_FLOW.md`.
2. **Живой, но предсказуемый голос:** pools + опциональный guarded LLM; без зеркалирования, двойных вопросов, обещаний действий.
3. **Устойчивость к плохому STT:** reason-aware ladder (echo / low_conf / silence), не слепое «Повторите».
4. **Семья видит смысл:** факты и `topics_discussed` по содержанию, не по `agenda_idx`.
5. **Один контракт для telephony, VoiceRuntime, Product API (Э8):** тот же `ConversationSession`, не три brain.

### Системные инварианты (никогда не нарушать)

| ID | Инвариант |
|----|-----------|
| I1 | Safety RED / UNCERTAIN — **только** `SafetyEngine` + confirm-gate; LLM не классифицирует опасность |
| I2 | Вера **никогда** не обещает «вызову / позвоню / отправлю» — promise-guard **до** TTS |
| I3 | Не более **одного** вопросительного предложения в реплике |
| I4 | Женский род от первого лица; без латиницы в ответе |
| I5 | FSM **тотальна**: необработанное событие → явный safe fallback + structured log, не молчание |
| I6 | Guards FSM **чистые** (read-only); мутации — только в actions |
| I7 | `TurnUnderstanding` строится **один раз** на ход, immutable до commit |
| I8 | Persistence / Observer **не в latency path** (ADR §10) |
| I9 | TECHNICAL / consent / DTMF-policy — отдельные режимы, не if внутри wellness FSM |
| I10 | Run-to-completion: один turn обрабатывается целиком под per-call lock |

### Preconditions / Postconditions одного хода

**Pre:** `CallSession` активна; `turn_no` монотонен; вход = `(transcript | empty, stt_reason, stt_confidence)`.

**Post (успех):** `TurnResult` с финальным `spoken_text`, `verdict`, `terminal`, `notes[]`; `ConversationMemory` обновлена; FSM в согласованном состоянии; Observer записал метаданные (fail-open).

**Post (отмена/barge-in):** generation boundary orchestrator; **новая** система не commit'ит partial state.

---

## Архитектура

### Слои (сверху вниз)

```text
┌─────────────────────────────────────────────────────────────┐
│  Integration: ConversationFacade (единая точка для оркестра) │
├─────────────────────────────────────────────────────────────┤
│  Runtime: ConversationSession + TurnPipeline (RTC, lock)   │
├──────────────┬──────────────┬──────────────┬────────────────┤
│ TurnAnalyzer │IntentResolver│ AgendaManager│  SafetyBridge  │
├──────────────┴──────────────┴──────────────┴────────────────┤
│  Policy FSM: CallPhaseMachine (declarative transitions)      │
├─────────────────────────────────────────────────────────────┤
│  ReplyComposer + VarietyEngine + DedupeGuard                 │
├─────────────────────────────────────────────────────────────┤
│  ConversationMemory (SkillState, facts, agenda semantic)     │
└─────────────────────────────────────────────────────────────┘
         │ read-only                    │ events
         ▼                              ▼
   SafetyEngine (existing)      vera_scenarios / pools / LLM
```

### Модули и ответственность

| Модуль | Файл (целевой) | Ответственность |
|--------|----------------|-----------------|
| **TurnAnalyzer** | `turn/analyzer.py` | Нормализация реплики → `TurnUnderstanding` (speech act, topic signals, symptom, confidence band). **Без** мутаций и **без** LLM в v1 |
| **IntentResolver** | `policy/resolver.py` | `(Memory, Understanding, SafetyVerdict)` → `PolicyDecision` (какой **тип** хода нужен). **Не** формулирует текст |
| **AgendaManager** | `agenda/manager.py` | Канон повестки, family questions, semantic close/advance/defer, wrap-up |
| **SafetyBridge** | `safety/bridge.py` | Адаптер к `SafetyEngine`: observe, map verdict → FSM events, confirm-gate policy |
| **CallPhaseMachine** | `policy/fsm.py` | Единственная таблица переходов фаз звонка |
| **ReplyComposer** | `reply/composer.py` | `ResponseGoal` → spoken text (pools → guarded LLM → guards) |
| **ConversationMemory** | `memory/state.py` | Extended state: facts, topics_discussed, last Q/A, flags **без** boolean soup на Agent |
| **VarietyEngine** | `variety/engine.py` | Per-call + cross-call rotation, `_pick_not_repeated` |
| **DedupeGuard** | `variety/dedupe.py` | `reply_too_similar`, same topic question, intent repetition |
| **ConversationFacade** | `integration/facade.py` | API для orchestrator: `begin_call`, `plan_turn`, `stream_reply`, `commit_turn`, `end_call` |
| **Observer** | `runtime/observer.py` | JSONL / `dialogue_turns.meta`; fail-open |

### Структура каталогов

**Дизайн-дом** (этот каталог):

```text
система разговоров для звонка/
  README.md                 ← этот документ
  docs/
    PRODUCT_FLOW.md         ← канонический поток (greeting→closing)
    LATENCY.md              ← бюджет задержки scripted vs LLM
    FSM.md                  ← таблица состояний (фаза 0)
    API_CONTRACT.md         ← контракт orchestrator ↔ facade
    MIGRATION.md            ← cutover по флагам
  src/                      ← эталон структуры; фаза 1 → telephony/conversation_system/
    domain/                 ← datatypes, enums, invariants
    turn/                   ← TurnAnalyzer
    policy/                 ← IntentResolver, CallPhaseMachine
    agenda/                 ← AgendaManager, goals, scenarios loader
    safety/                 ← SafetyBridge
    reply/                  ← ReplyComposer, pools, llm_adapter
    memory/                 ← ConversationMemory, SkillState export
    variety/                ← VarietyEngine, DedupeGuard
    runtime/                ← ConversationSession, TurnPipeline, Observer
    integration/            ← ConversationFacade
    tests/                  ← unit + scenario fixtures (не prod)
```

**Прод-пакет (фаза 1):** зеркало `src/` → `telephony/conversation_system/`.

---

## State machine design

### Состояния (CallPhase — качественная фаза)

| State | Смысл | Публичный mode (совместимость) |
|-------|-------|--------------------------------|
| `OPEN` | До первой содержательной реплики | companion |
| `WELLNESS_WALK` | Сервисный check-in по повестке | check_in |
| `CLARIFY` | Ladder тишины / low_conf / echo | clarify |
| `SIDE_ANSWER` | Ответ на вопрос абонента, повестка на паузе | companion |
| `SYMPTOM_FOLLOWUP` | Уточнение симптoma (не safety RED) | check_in |
| `SAFETY_CONFIRM` | possible_red → контрольный вопрос | safety_confirm |
| `SAFETY_ACTIVE` | confirmed/uncertain danger | safety_active |
| `HELP_WINDOW` | «Нужна помощь?» + подтверждение | check_in |
| `CLOSE_CONFIRM` | «Вы прощаетесь?» | check_in |
| `CLOSING` | Тёплое прощание | closing |
| `TERMINAL` | Ход после завершения (no-op safe) | closing |
| `CONSENT` | Режим согласия (E3) — **отдельная** под-машина | — |
| `TECHNICAL` | Жёсткий script при сбое | — |

Extended state (на `ConversationMemory`, **не** новые states): `agenda_cursor`, `topics_discussed[]`, `narrative_deferred_topic`, `empty_turn_count`, `stt_confirm_used`, `active_symptom`, `symptom_resolved`, family Q snapshot.

### События (вход FSM)

| Event | Источник |
|-------|----------|
| `E_SPEECH` | TurnAnalyzer: содержательная речь |
| `E_EMPTY` | Пустой transcript |
| `E_LOW_CONF` | STT gate / vocab |
| `E_ECHO` | Echo-guard orchestrator |
| `E_STT_CONFIRM` | Mid-confidence → один confirm |
| `E_GREETING` | Bare hello |
| `E_CLOSING` / `E_CLOSING_DIRECT` | Classifiers |
| `E_REFUSAL` | «Нет, спасибо» |
| `E_SIDE_QUESTION` | Вопрос абонента |
| `E_NARRATIVE` | Off-topic рассказ ≥ порога |
| `E_SYMPTOM` | possible_red (не confirmed) |
| `E_SAFETY_*` | SafetyBridge от SafetyEngine |
| `E_HELP` / `E_WORRY` | Help / third-party worry |
| `E_REPAIR` | «Повторите» |
| `E_DTMF` | ROADMAP E2 statuses (optional) |
| `E_TIMEOUT` | Max turns / duration |
| `E_HANGUP` | External |
| `E_*` catch-all | `E_UNHANDLED` → warm ack |

### Пример строк таблицы (фрагмент)

```text
(WELLNESS_WALK, E_NARRATIVE, guard=not_matches_current_topic, action=defer_agenda+ack_content, WELLNESS_WALK)
(WELLNESS_WALK, E_SIDE_QUESTION, guard=always, action=pause_agenda+goal_answer_side, SIDE_ANSWER)
(SIDE_ANSWER, E_SPEECH, guard=side_answered, action=resume_agenda, WELLNESS_WALK)
(*, E_SAFETY_CONFIRMED, guard=always, action=enter_danger_protocol, SAFETY_ACTIVE)
(CLARIFY, E_EMPTY, guard=empty_count_lt_5, action=silence_ladder, CLARIFY)
(*, E_UNHANDLED, guard=always, action=warm_ack+log, self)
```

Полная таблица — в `docs/FSM.md` (фаза 0, до кода actions).

### Guards и Actions (правила)

- **Guard:** `(memory: ConversationMemory, understanding: TurnUnderstanding, safety: Verdict) -> bool`
- **Action:** возвращает `ResponseGoal` + список `MemoryPatch` (explicit patches, не скрытые мутации)
- **Re-dispatch:** max depth 4; при превышении → `ResponseGoal(kind=ACKNOWLEDGE, pool=GENERIC)`

---

## Компоненты (детально)

### TurnAnalyzer

```python
# domain/understanding.py (концепт)
@dataclass(frozen=True)
class TurnUnderstanding:
    raw_text: str
    clean_text: str
    input_reason: str | None      # empty | low_conf | echo | stt_uncertain
    speech_act: SpeechAct
    topic_signals: tuple[str, ...]
    symptom_focus: str | None
    answers_last_control: bool | None
    confidence_band: Literal["high", "medium", "low"]
    is_narrative: bool
    word_count: int
```

Детерминированные источники: cleaners, classifiers (переносим **логику**, не файлы), TOPIC_KEYS, symptom extractors.

### IntentResolver

Превращает understanding + memory + safety в **PolicyDecision**:

```python
@dataclass(frozen=True)
class PolicyDecision:
    primary_goal: ResponseGoalKind   # ASK_TOPIC | ACK | CLARIFY | ...
    agenda_command: AgendaCommand | None  # ADVANCE | DEFER | PAUSE | NONE
    safety_command: SafetyCommand | None
    allow_llm: bool
    record_notes: tuple[str, ...]
```

Resolver **не** вызывает LLM и **не** меняет memory — только решение.

### AgendaManager

- Загружает канон из `vera_scenarios.txt` + `goals` constants
- `current_topic()`, `next_topic()`, `mark_discussed_semantic()`, `inject_family_questions()`
- **Semantic close:** тема закрыта если (a) содержательный ответ по ключам, (b) symptom cleared, (c) explicit refusal — **не** только «да»

### SafetyBridge

- Wrap `SafetyEngine.observe(Observation(...))`
- Mapping: `confirmed_red` → `E_SAFETY_CONFIRMED`, `possible_red` → `E_SYMPTOM` или `SAFETY_CONFIRM`
- Confirm-gate: «да» подтверждает только на yes/no control question
- **Не дублировать** regex danger из dialogue layer

### ReplyComposer

Вход: `ResponseGoal` + `ConversationMemory` + optional LLM stream  
Выход: `ComposedReply(segments[], source=pool|llm|script, guarded=True)`

Pipeline:

1. Select pool / build LLM messages from SkillState export  
2. `DedupeGuard` + promise/broken/medical/rescue guards  
3. `_clean_llm` / feminize / single-question trim  
4. Fallback chain: LLM fail → pool → MINIMAL_FALLBACK  

### Memory / SkillState

- `ConversationMemory` — единственный mutable extended state  
- `SkillState` — **read-only projection** для LLM (`to_context_lines()`), rebuild каждый ход  
- `topics_discussed` пополняется AgendaManager по семантике  
- Raw `turn_log[]` для persistence/audit (optional ring buffer)

### Variety / Dedupe

- **VarietyEngine:** per-call deque(20) + process-wide ring(60) для canned phrases  
- **DedupeGuard:** token overlap, same_topic_question, repeat intent regex  
- При исчерпании пула — controlled degradation (не silent fail)

---

## Интеграция

### API contract: `ConversationFacade`

Единственная точка для `orchestrator.py` и будущего `voice_runtime` agent HTTP.

```python
class ConversationFacade:
    def begin_call(self, *, call_id, caller_id, elder_context, mode, family_questions) -> SessionHandle: ...
    def plan_turn(self, handle, *, transcript, reason, stt_confidence) -> TurnPlanV2: ...
    def stream_reply(self, handle, plan: TurnPlanV2) -> Iterator[str]: ...
    def commit_turn(self, handle, plan, spoken_text) -> TurnCommit: ...
    def end_call(self, handle) -> CallSummary: ...
```

### `TurnPlanV2` (новый контракт — без intent/fallback fork)

```python
@dataclass
class TurnPlanV2:
    user_text: str
    spoken_reply: str              # финальный текст для TTS (pool/script) ИЛИ пусто если LLM stream
    stream: bool                   # True → orchestrator вызывает stream_reply
    terminal: bool
    verdict: str                   # ok | attention | alert | ...
    safety_status: str
    record_notes: list[str]
    dialogue_step: int             # совместимость events.py
    greeting: str | None           # только turn 0 / check_in start
    meta: dict                     # observer, scenario_version
```

### Orchestrator (минимальные изменения на фазе 3)

```text
# было
agent = Agent(llm=...)
plan = agent.plan_reply(text, reason)
for seg in agent.reply_stream(plan): ...

# станет (feature flag MOSS_CONVERSATION_V2=1)
facade = get_conversation_facade(llm=...)
handle = facade.begin_call(...)
plan = facade.plan_turn(handle, transcript=..., reason=...)
# guards остаются на boundary TTS (sanitize_segment) — дубль не нужен после ReplyComposer
```

### Lua / VoiceRuntime

- `/calls` POST → `begin_call` → `{greeting, call_id, dialogue_step}`  
- `/turn_stream` → `plan_turn` + `stream_reply` + `commit_turn`  
- Consent / DTMF → отдельные методы facade или `mode=consent` в begin_call  
- **Agent не знает про SIP/RTP** (ADR §9)

### Observer

После `commit_turn`:

```json
{"call_id","turn_no","phase_before","event","phase_after","goal_kind","reply_source","quality_flags":[]}
```

---

## Миграция (phased cutover)

| Фаз | Флаг | Поведение |
|-----|------|-----------|
| M0 | — | Только этот README + scaffold; prod = старый Agent |
| M1 | `MOSS_CONVERSATION_V2=0` | Пакет `telephony/conversation_system/`; unit tests; **не** в hot path |
| M2 | `MOSS_CONVERSATION_V2=shadow` | Новая система параллельно считает plan; лог diff; spoken = старый |
| M3 | `MOSS_CONVERSATION_V2=1` | Spoken path через facade; fallback на старый Agent при exception |
| M4 | — | Удалить `telephony/core/dialogue/`, `conversation/`; orchestrator slim |

**Не ломаем prod:**

- SafetyEngine, consent.py, family questions PG sync — **без изменений** на M1–M2  
- `dialogue_turns` schema — совместимость через adapter в commit  
- Feature flag per container in `docker/.env`

---

## Тестирование

### Unit

- `TurnAnalyzer` — таблица кейсов из реальных транскриптов (анонимизированные fixtures)  
- `AgendaManager.semantic_advance` — narrative / symptom / family Q  
- `CallPhaseMachine` — каждый `(state, event)` + totality  
- `ReplyComposer` — guards, dedupe, promise  
- `SafetyBridge` — confirm-gate, negation, fall metric vs person  

### Integration

- `tests/conversation_system/test_turn_pipeline.py` — full turn без LLM  
- Adapter tests: `TurnPlanV2` ↔ legacy events.py  

### dialog_quality harness v3

Расширить `voice-lab/dialog_quality.py`:

| Метрика | Порог |
|---------|-------|
| `ignored_side_question` | 0 |
| `topic_reask_after_narrative` | 0 |
| `semantic_topics_vs_cursor` | 0 mismatches |
| repeat_rate | ≤ 5% |
| promise_count | 0 |

Цель: **≥30 сценариев strict PASS** (vs 23 сегодня).

### Live gate (owner)

1. `make up telephony` + `MOSS_CONVERSATION_V2=1`  
2. Zoiper **один** канал (не loopback): check-in, side-question, symptom, прощание  
3. Запись `/tmp/mossvoice/<id>/` — user channel только абонент  
4. Sign-off в `docs/CHRONICLE.md`

---

## Этапы реализации

### Фаза 0 — Архитектура (этот коммит) ✅

**Deliverables:** README, docs/, scaffold `src/`  
**Acceptance:** план согласован; FSM.md черновик; API_CONTRACT.md

### Фаза 1 — Domain + TurnAnalyzer + Memory (1–2 PR)

**Deliverables:**

- `telephony/conversation_system/domain/*`  
- `TurnAnalyzer`, `ConversationMemory`, `AgendaManager` (без FSM)  
- ≥40 unit tests  

**Acceptance:** `make test-fast` green; `verify_no_stubs`; **нет** подключения к orchestrator

### Фаза 2 — CallPhaseMachine + SafetyBridge + IntentResolver (1 PR)

**Deliverables:**

- Полная transition table в `policy/fsm.py`  
- Resolver wiring  
- Port критичных сценариев из `dialogue_scenarios.py`  

**Acceptance:** FSM totality tests; safety regressions = старые `test_safety_engine` green

### Фаза 3 — ReplyComposer + Variety + Facade (1–2 PR)

**Deliverables:**

- Pools перенос (данные, не логика Agent)  
- `ConversationFacade` complete  
- Shadow mode M2  

**Acceptance:** `dialog_quality --strict` ≥28/30 на новом runner; shadow diff log <5% unexpected

### Фаза 4 — Orchestrator cutover (1 PR)

**Deliverables:**

- `MOSS_CONVERSATION_V2=1` hot path  
- Slim orchestrator (убрать прямые imports dialogue)  

**Acceptance:** `make test-fast`; dialog_quality strict; loopback LATENCY течёт

### Фаза 5 — Live + удаление legacy (owner gate)

**Deliverables:**

- Owner Zoiper sign-off  
- Delete `telephony/core/dialogue/`, `telephony/core/conversation/`  
- Update AGENTS.md  

**Acceptance:** 3 live scenarios OK; no rollback 48h

---

## Что НЕ переносим (kill list)

| Удалить / не копировать | Почему |
|-------------------------|--------|
| Монолитный `Agent` class (1261 строк) | God object |
| `DialogueFSM` actions с compose внутри | Смешение policy + rendering |
| Dual API `intent` + `fallback` | Заменяем `TurnPlanV2` + `ResponseGoal` |
| 30+ boolean flags на Agent | → `ConversationMemory` patches |
| `_classify` дублирующий TurnAnalyzer | Один parser |
| `ConversationEngine.prepare_plan` stub | Заменяем pipeline |
| LLM intent strings «Цель ответа: …» | Typed goals + SkillState context |
| DTMF «нажмите 1/2» в тишине | Удалено навсегда (Dialogue 3.0) |
| Regex danger в dialogue layer | Только SafetyEngine |
| Global `_RECENT_SPOKEN` без per-call | VarietyEngine unified |
| Patch-on-patch narrative guards в FSM actions | AgendaManager semantic |
| `docs/DIALOGUE_4_PLAN.md` evolution path | Заменён этим документом |
| Telegram как транспорт звонка | ROADMAP freeze |

### Что сохраняем (reuse)

- `core/safety_engine.py` — as-is, через SafetyBridge  
- `core/consent.py` — режим CONSENT в facade  
- `vera_scenarios.txt` — source of truth сценариев  
- `core/fsm.py` — generic StateMachine (reuse, не fork)  
- Pools **тексты** (перенос данных в `reply/pools/`)  
- `voice-lab/dialog_quality.py` — расширяем, не выбрасываем  

---

## Рекомендуемая первая фаза имплементации

**Начать с Фазы 1:** `domain/` + `TurnAnalyzer` + `ConversationMemory` + `AgendaManager` + unit tests.

Почему:

1. Не трогает prod hot path — безопасно параллельно текущему Agent.  
2. Закрывает главный продуктовый дефект: **семантика повестки ≠ индекс**.  
3. Даёт fixtures для harness v3 до написания FSM.  
4. Позволяет shadow-compare `TurnUnderstanding` vs старый `_classify` на логах.

**Первый PR:**

- Создать `telephony/conversation_system/` (копия структуры `src/`)  
- Реализовать `TurnAnalyzer.analyze(text, reason, confidence) -> TurnUnderstanding`  
- Реализовать `AgendaManager` с semantic `mark_discussed`  
- Tests: `tests/conversation_system/test_analyzer.py`, `test_agenda_semantic.py`  

---

## Команды проверки (будущие)

```bash
make test-fast
python3 -m unittest discover -s telephony/conversation_system/tests -p "test_*.py"
python3 voice-lab/dialog_quality.py --strict
make verify-stubs
```

---

## Связь с ROADMAP

- **Э2 статусы:** `TurnCommit.verdict` + meta для Status Engine  
- **Э3 согласие:** режим `CONSENT` в facade  
- **Э8 iOS:** `CallSummary` / `ConversationMemory` export через Product API  
- **Э1 медиа:** facade не блокирует VoiceRuntime cutover  

---

*Документ подготовлен на основе: `AGENTS.md`, `ROADMAP.md`, `docs/ARCHITECTURE_v1.md`, код `telephony/core/dialogue/`, `telephony/core/conversation/`, `orchestrator.py`, `voice-lab/dialog_quality.py`, тестов dialogue.*
