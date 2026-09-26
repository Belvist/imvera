# P0b GO — с балванок фраз → детерминированная система (CDK)

Читай целиком. Закон: `docs/OPERATING_BRIEF.md` + ADR-014 + **ADR-021** + ADR-022.
Ветка: `feature/voice-zoiper-m5`. Рабочая папка: `/Users/earflow/Downloads/voiseup`.

## Зачем этот бриф (нельзя игнорировать)

Владелец злой правильно: коммит `88f172b` (`complaint_without_negation`) — это
**safety-патч на строках**, не система. Так дальше нельзя.
Цель этапа — **Pilot-ready на frozen path**, не «ещё один if под бабушкину фразу».

`88f172b` **не откатывать** (ложный RED опаснее дыры в архитектуре).
Но **запрещено** делать следующий PR в том же стиле (новые regex/фразы «чтобы
стало лучше»). Следующий PR = **Protocol as data + проводка NeedQueue**.

---

## Северная звезда (ADR-021 CDK) — заучить

```text
STT → Understand (acts only) → Reduce (EngineState)
   → NeedQueue (что MUST спросить) → Action (один ход)
   → PhraseSelect (банки по action_id) → TTS
   → (после звонка) StatusEngine
```

| Слой | Что производит | Что ЗАПРЕЩЕНО |
|---|---|---|
| Understand | closed acts: WELLNESS_OK, DECLINE, ISSUE_SITE, … | Vera text, «угадай по подстроке и смени тему» |
| Reduce | единственный writer EngineState | второй scheduler в transport |
| NeedQueue | очередь needs из **таблицы протокола** | tri-truth: mission + FILLER_ORDER + StatusEngine порознь |
| Action | один ActionId на ход | if-лестницы под конкретные русские фразы |
| PhraseSelect | банк 5–12 фраз на ActionId | LLM речь; хардкод одной «правильной» реплики в policy |

**Детерминизм** = (EngineState + last Act) → один ActionId.
**Динамика** = NeedQueue + события (safety / issue / decline / coverage), не «новые болванки».

---

## Диагноз: где сейчас балванки, а не система

1. **Tri-truth протокола**
   - `PILOT_MANDATORY_CHECKS` / mission required
   - `FILLER_ORDER` в `packages/dialogue_engine/coverage.py`
   - StatusEngine / CareState (GREEN/YELLOW/RED)
   - short-mode bypass из `21c61be`
   → четыре источника «что обязательно» вместо одной таблицы.

2. **Safety/policy на лексике**
   - `_looks_like_complaint` / `complaint_without_negation` решают эскалацию
     по маркерам строк, а не по акту `DECLINE` / `WELLNESS_OK`.
   - Это допустимо как **временный safety net**, не как мозг диалога.

3. **Фразы**
   - Если Action выбирается эвристикой, а потом подставляется одна фраза —
     это болванка. Нужен ActionId → PhraseSelect(banks).

4. **DoD = pytest без live** — нарушает Operating Brief. Live `call_id` обязателен
   для dialogue/safety поведения.

---

## Миграция: 5 ступеней (не прыгать)

### Ступень 0 — Инвентарь (этот PR, день 1, без смены поведения)
Сделай файл `docs/plans/P0b-protocol-as-data.md` (если нет — создай) и таблицу:

| Сейчас в коде (путь:символ) | Роль | Куда переезжает в Protocol YAML |
|---|---|---|
| PILOT_MANDATORY_CHECKS | … | modes.*.required_slots |
| FILLER_ORDER | … | modes.*.coverage_order |
| short-mode / checkin rules (21c61be) | … | modes.short.* |
| StatusEngine inputs для YELLOW/RED | … | status_impact.* |
| complaint/decline safety nets | … | acts + safety_overrides (не удалять net в P0b) |

Выпиши 1 живой контрпример на каждый конфликт (уже есть: `fs-e98331b8` false YELLOW;
`fs-6e3abff0` false RED через negation).

**Стоп:** пока таблица неполная — код Protocol не пиши.

### Ступень 1 — Protocol YAML как единственный закон слотов (код + тесты)
Создай **один** файл данных, например:
`packages/dialogue_engine/protocol/pilot_checkin.yaml` (или `.json` если в репо уже так принято — не плоди форматы).

Минимальный shape (можно уточнить имена, смысл зафиксирован):

```yaml
version: 1
modes:
  short:          # check-in / already covered
    required_slots: []          # или явный whitelist
    coverage_order: []
    may_its_without: [mood, sleep, plans]   # закон 21c61be
  full:
    required_slots: [wellness, ...]         # из текущих mandatory
    coverage_order: [nutrition, medication, mood, sleep]
  complaint:
    required_slots: [site, severity]        # pain без severity ≠ ITS
    coverage_order: []
status_impact:
  missing_required_after_close: YELLOW      # объясняет fs-e98331b8
  urgent_unnegated_complaint: RED
acts:                                         # закрытая решётка Understand
  WELLNESS_OK: { clears: [wellness], enqueues: [] }
  DECLINE:     { clears: [open_probe], forbids: [pain_site_probe] }
  ISSUE_SITE:  { enqueues: [severity] }
```

**Проводка (минимальная, один мозг):**
- NeedQueue / coverage / mission-required читают **только** этот файл (или
  скомпилированный dict при импорте).
- Старые константы `FILLER_ORDER` / `PILOT_MANDATORY_CHECKS` либо
  **генерируются из YAML**, либо становятся thin wrappers с deprecation
  comment — не оставляй два источника правды.
- StatusEngine для pilot-checkin берёт `status_impact` из того же файла
  (или явный adapter). Не третий hardcoded set.

**Тесты = источник правды (обязательно):**
1. Unit: short-mode не требует mood/sleep/plans → не YELLOW (`fs-e98331b8` класс).
2. Unit: `DECLINE` / negated complaint → не `urgent_close` / не RED (`fs-6e3abff0` класс) **через акт/протокол**, safety net может остаться belt-and-suspenders.
3. Replay/golden: 2–3 эталонных сценария (wellness-ok decline; short ok; pain+severity).
4. Gate: существующие dialogue corpus / policy_diff не краснеют без явной причины в PR.

### Ступень 2 — Understand → acts (не расширять regex-мозг)
- Закрытая решётка актов из ADR-021.
- Новые русские формулировки = **новые примеры/классификатор → тот же акт**,
  не новый `if "ничего не" in text` в conversation_policy.
- `complaint_without_negation` оставить как safety net; **не** строить на нём
  ветвление диалога. Диалог ветвится по Act + NeedQueue.

### Ступень 3 — ActionId → PhraseSelect
- Один ход = один ActionId из таблицы.
- Фразы только из banks; anti-repeat per call.
- Запрет: хардкод «правильной» реплики в policy «потому что live баг».

### Ступень 4 — Live proof (DoD P0b)
Не «тесты зелёные». Нужно:
1. Мост на новом SHA (`dialogue.engine.version`).
2. Live Zoiper: сценарий wellness + «ничего не беспокоит» + «ничего не болит»
   → нет pain-site probe после DECLINE, нет ложного RED/urgent семье.
3. Live или replay: short check-in без mood/sleep/plans → GREEN (класс `fs-5b509b4f`).
4. В ответе: `call_id` + 5–10 строк из trace (acts / action_id / status).

Если сам не можешь дозвониться — подготовь чеклист фраз для владельца и
**остановись** на live-gate; не объявляй P0b closed.

---

## Scope этого захода (P0b PR)

### Делай
1. Ступень 0 документ `docs/plans/P0b-protocol-as-data.md` (полная инвентаризация).
2. Ступень 1: YAML + проводка NeedQueue/coverage/mandatory из одного источника.
3. Тесты классов `fs-e98331b8` и `fs-6e3abff0` (протокол/acts, не только regex).
4. Коммит(ы) на `feature/voice-zoiper-m5`, одна тема: protocol-as-data.
5. Отчёт: CHANGED / NOT TOUCHED / VERIFIED / NEXT GATE (live).

### Не делай (forbidden)
- Новые phrase-regex фиксы «под бабушку» как основной дизайн
- LLM речь Веры / Composer в hot path
- PSTN, raise `max_active_calls`, Character/copy polish
- SIDE_TOPIC / ABDOMINAL как отдельные фичи в этом PR
- Четвёртая система / второй dialogue brain
- «Почини всю Vera» / рефактор ради рефактора
- Откат `88f172b` или P0a OBS

### Порядок внутри PR
Сначала plan-файл + failing tests (красные на старом поведении где надо) →
YAML → wiring → green tests → (live). Не наоборот.

---

## Definition of Done

- [ ] Один файл протокола = единственный закон required/coverage/status_impact для pilot check-in
- [ ] Tri-truth убран или сведён к thin wrappers от этого файла
- [ ] Тесты: false-YELLOW short + false-RED decline — зелёные через протокол/acts
- [ ] Corpus / policy_diff / ruff на тронутом — ок
- [ ] Live `call_id` ИЛИ явный stop на live-gate с чеклистом для владельца
- [ ] В PR тексте: «как это не балванка» = 5 буллетов (Understand/Reduce/NeedQueue/Action/PhraseSelect)

Начни со Ступени 0 (инвентарь в `docs/plans/P0b-protocol-as-data.md`), потом Ступень 1.
Не пиши «готово систему» без YAML+проводки+тестов.
