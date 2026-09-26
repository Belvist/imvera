# ПОЛНЫЙ БРИФ ВЛАДЕЛЬЦА — что не так и что делать (читай целиком)

Сессия: та же. Репо: `/Users/earflow/Downloads/voiseup`. Ветка: `feature/voice-zoiper-m5`.
Закон: `docs/OPERATING_BRIEF.md` + ADR-014 + **ADR-021 CDK** + ADR-022.
HEAD сейчас ожидается около `372b8b7` (P0b step 0–1). Не откатывай P0a/P0b/88f172b.

Ты НЕ закрыл «динамическую детерминированную систему». Владелец спрашивает прямо —
ответ: **нет**. Ниже почему и что делать дальше без балванок.

---

## 0. Одна фраза правды

Вера должна быть **протоколом ухода**: одинаковый (state + act) → один ActionId → фраза из банка.
Сейчас у вас смесь: таблица слотов (хорошо) + ветвление на лексике/эвристиках (плохо) + раздутые банки фраз (шум).

P0b Step 1 (`dc988c4` / `372b8b7`) = **один YAML для списков**. Это фундамент, не CDK.
`88f172b` / nlu negation = **safety net**, не мозг.
Удвоение phrase banks (`4229a3f`) = **балванки**, не динамика.

---

## 1. В чём проблема (полностью)

### 1.1 Симптом для бабушки (live)
- `fs-6e3abff0`: «более-менее» / «ничего не беспокоит» / «ничего не болит» → pain-probe и/или urgent_close / ложный RED.
- `fs-e98331b8`: short check-in без mood/sleep/plans → ложный YELLOW (чинили `21c61be`, класс регрессий).
- Владелец слышит: «она не понимает» → агент чинит **фразы и regex**, система не появляется.

### 1.2 Архитектурная гниль (корень)
По ADR-021 целевой контур:

```text
STT → Understand(acts) → Reduce(EngineState)
   → NeedQueue(из Protocol) → Action(один id)
   → PhraseSelect(banks) → TTS → StatusEngine
```

Факт сегодня:

| Слой | Как должно | Как есть | Почему это проблема |
|---|---|---|---|
| Protocol | одна таблица = закон required/coverage/status/acts | YAML есть; **acts декларативные**; часть читателей ещё не все | списки едины, **ходы** всё ещё не из таблицы |
| Understand | закрытая решётка актов (WELLNESS_OK, DECLINE, ISSUE_SITE, …) | метки/answer-эвристики + lexical safety | одна и та же «answer» на разные смыслы → неверная очередь |
| Reduce | единственный writer state | ок по направлению | не трогать вторым мозгом |
| NeedQueue | MUST из Protocol + приоритеты SAFETY>issue>coverage>ITS | FILLER/mandatory из YAML, но **forbids acts не крутят очередь** | DECLINE в YAML не запрещает pain_site_probe в рантайме |
| Action | один ActionId на ход | if/policy/heuristic лестницы + phrase-driven ощущение | недетерминизм «под фразу» |
| PhraseSelect | банк на ActionId, anti-repeat | банки раздувают «чтобы звучало» | больше текста ≠ понимание |
| Status | из protocol status_impact + filled slots | раньше tri-truth; short-mode чинили отдельно | риск снова разъехаться |
| Safety | net поверх актов | net = основной фикс false RED | следующий баг снова regex |

### 1.3 Процессная гниль (как ты работаешь)
- На «система не понимает» отвечаешь **больше фраз / точечный regex**.
- DoD = pytest / «прогнал батарею» без нового live `call_id` после архитектурного PR.
- Объявляешь «готово систему», когда сделан **behavior-neutral refactor списков**.
- Параллельно трогаешь Character/banks в том же потоке, что протокол.

Это запрещено Operating Brief: один PR = одна тема; live proof для dialogue/safety; не LLM речь; не raise caps.

### 1.4 Что УЖЕ сделано правильно (не ломай)
- P0a OBS tiers / summary / health (`ef3bab7` и рядом)
- Safety negation net (`88f172b`) — ремень, оставить
- Short-mode false YELLOW (`21c61be`) — закон short
- P0b inventory + `pilot_checkin.yaml` + FILLER/BACKGROUND из YAML (`dc988c4`, `372b8b7`)
- Frozen path SIP→…→CDK→banks→TTS (не четвёртая система)

### 1.5 Что ещё открыто (не этот PR целиком)
SIDE_TOPIC шум, ABDOMINAL без severity, ADR-014 soak, PSTN, max_active_calls=1, TG≠Core StatusEngine, Silero NC lab-only.
**Не хватай в CDK Step 2.**

---

## 2. Что значит «динамическая детерминированная система» (DoD владельца)

Система = да, только если одновременно:

1. **Детерминизм:** одинаковые (EngineState + Act) → один и тот же ActionId (тест + replay).
2. **Динамика:** очередь Needs меняется от актов (DECLINE снимает probe; ISSUE_SITE ставит severity; WELLNESS_OK закрывает wellness) — не от новых if «если текст содержит…» в policy.
3. **Один закон:** Protocol YAML (или скомпилированная таблица) владеет required/coverage/status_impact **и** act→effects (clears/enqueues/forbids).
4. **Речь:** PhraseSelect только по ActionId; запрет чинить баг новой «правильной» фразой в policy.
5. **Доказательство:** live `call_id` после проводки acts (не только unit).

Пока acts в YAML не влияют на NeedQueue/Action — это **не система**, это конфиг списков.

---

## 3. Что сделать дальше (жёсткий план)

### СТОП прямо сейчас
- Не раздувать phrase banks.
- Не новый regex «под бабушку» как дизайн.
- Не PSTN / max_active_calls / Character / SIDE_TOPIC / ABDOMINAL в этом потоке.
- Не объявлять CDK done после docs/YAML без act-wiring.
- Не ждать «владельца придумать вариант» — варианты уже выбраны ниже.

### GATE L — Live (владелец звонит; ты готовишь приёмку)
Чеклист фраз:
1. «более-менее» / «нормально»
2. «ничего не беспокоит»
3. «ничего не болит, всё хорошо»

Ожидание: нет pain-site probe после DECLINE; нет urgent_close/ложного RED; ITS + одно goodbye.
Ты: снять `.run/traces/<call_id>.jsonl`, выписать acts/action_id/status. Если владелец ещё не звонил — **не блокируй Step 2 код**, но **не закрывай** CDK без live; в отчёте явно LIVE: pending.

### Step 2 — Acts → NeedQueue / Action (ОСНОВНАЯ РАБОТА СЕЙЧАС)
Цель: декларация `acts:` в `pilot_checkin.yaml` становится **исполняемой**.

Минимум в YAML (можно расширить поля, смысл зафиксирован):
```yaml
acts:
  WELLNESS_OK:
    clears: [wellness]
    forbids: []
    enqueues: []
  DECLINE:
    clears: [open_probe]
    forbids: [pain_site_probe, concern_probe]
    enqueues: []
  ISSUE_SITE:
    enqueues: [severity]
    forbids: []
```

Код (один мозг, без второго scheduler):
1. После Understand: нормализованный Act (enum/str из закрытой решётки ADR-021).
2. Reducer/NeedQueue применяет `clears` / `enqueues` / `forbids` из PROTOCOL["acts"].
3. Выбор следующего ActionId **не может** предложить forbidden, пока forbid активен.
4. Safety net (`complaint_without_negation`) остаётся belt-and-suspenders; **диалог ветвится по Act**, не по net.
5. `BACKGROUND_SLOTS` / required уже из YAML — не дублировать.

Тесты (обязательно, красные→зелёные):
- Act DECLINE → следующий ActionId ∉ pain_site_probe / concern_probe (класс fs-6e3abff0).
- Short mode + закрытый wellness без mood/sleep/plans → не YELLOW (класс fs-e98331b8) — не регрессировать.
- Golden/replay 2–3 сценария: wellness-ok+decline; pain+site→severity; short ok.
- Существующие corpus / policy_diff / protocol_table — green или явный reason в PR.

Коммит: одна тема `feat(protocol): execute act effects from YAML (CDK step 2)`.
В PR тексте 5 буллетов CDK: Understand / Reduce / NeedQueue / Action / PhraseSelect — что изменилось на каждом.

### Step 3 — Understand ужесточить (после Step 2 green+live или parallel только если не раздувает PR)
- Закрытая решётка; «более-менее» → WELLNESS_OK/NEUTRAL, не generic answer→concern.
- Новые формулировки = примеры→тот же Act, не новый if в conversation_policy.
- Отдельный PR, если Step 2 уже большой.

### Step 4 — PhraseSelect дисциплина
- Банки только под стабильные ActionId.
- Запрет PR «просто больше фраз» без нового ActionId/доказанного gap.
- Anti-repeat per call уже должен жить; не ломать.

### Step 5 — Live proof = закрытие CDK-среза
Мост на новом SHA. Новый call_id. Таблица: user line → act → action_id → status.
Без этого не писать «система готова».

---

## 4. Forbidden (ещё раз)
- LLM речь Веры / Composer hot path
- Четвёртая система / dual brain
- Raise max_active_calls без capacity probe
- Cloud STT/TTS silent fallback
- «Почини всё Vera»
- Откат OBS / protocol YAML / negation safety
- Балванки: regex-мозг, phrase-only фиксы, удвоение банков как ответ на «не понимает»

---

## 5. Формат ответа владельцу (каждый раз)
```
CHANGED: …
NOT TOUCHED: …
VERIFIED: команды + результаты (не «должно работать»)
LIVE: call_id | pending + чеклист
NEXT: один следующий шаг
CDK?: no | partial(step N) | yes — с критерием из §2
```

Сейчас честный статус для старта: **CDK?: partial (step 1 only)**.

---

## 6. Старт немедленно
1. Прочитай этот файл + `docs/plans/P0b-protocol-as-data.md` + `pilot_checkin.yaml`.
2. Начни **Step 2** (исполняемые act effects). Не начинай с фраз.
3. Если live ещё нет — коди Step 2 + unit/replay; LIVE оставь pending.
4. Не трогай banks в этом PR.

Конец брифа. Работай.
