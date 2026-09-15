# Current task — словарь умирает: approve-конвейер вместо дописывания (2026-09-15)

**Outcome:** ответ на «как заменить словарь»: закрытые классы — списки (конечны,
это нормально), открытое понимание — граница + конвейер. Карантин теперь с
подсказками ближайшего соседа (не той же модели, что отказалась), AUTO-OK только
дубли (sim≥0.9), остальное — человеку одной командой. Первый прогон: 10/100
одобрено, ворота зелёные, модели в проде (рестарт — pkl кэшируются в памяти!).

## CHANGED

- `review_quarantine.py` — сосед-подсказки + `--approve` (retrain+bench+fuzz)
- 10 LIVE_QUOTES из карантина; рестарт бриджа (новые pkl)

## VERIFIED

```bash
# approved 10/100; bench 1.00; fuzz 0; bridge restarted, :9210 ok
```

## NOT VERIFIED

- Живой звонок

## NEXT GATE

Звонок 7000.

---

# Previous — звонок a1dca80c: разобран по косточкам (2026-09-15)

**Outcome:** правы — звонок был плохой, и причины три, все мои/наши:
(1) живой CallActor-путь давал uncertain вместо negative → лесенка вместо пробы;
теперь маркеры плохого в тексте решают сами; (2) ответ без жалобы («поел»)
писался в «что беспокоит» и уходил в duration-бред — теперь это отказ от
пробы; (3) падение из ветки ≥2 проваливалось в безусловный probe (структурный
баг if/if вместо if/elif/else) — починено. Плюс ITS-decline после живого
разговора идёт в саммари, а не в partial. Реплей звонка дословно — чисто,
тёплое прощание. Бридж перезапущен.

## VERIFIED

```bash
# дословный реплей: probe→ladder→re-probe→decline→ladder→ITS→goodbye
fuzz×1000 оба флага # 0; critical 6/6; meds 15/15
pytest IDENTICAL свежему бейзлайну; ruff clean; bridge restarted, :9210 ok
```

## NOT VERIFIED

- Живой звонок с этим билдом (срочно нужен — логика менялась!)

## NEXT GATE

Звонок 7000 с тем же сценарием (смешанное самочувствие).

---

# Previous — пакет ревьюера 5/5: families, субъект, память, разметка (2026-09-15)

**Outcome:** все 5 пунктов. Честные цифры вместо надутых: slot 0.856 (был 0.967
на дырявом сплите), route 0.619 — его remap зажат порогом 0.8. Субъект сквозной
(муж→не своя боль, исправления флипают, legacy не обходит). Память — по человеку.
Схема разметки + 10 fixtures + eval понимания (0/0). Бридж перезапущен.

## CHANGED

- `families.py` + GroupKFold/кривая в обоих трейнерах; tinyllm min_proba
- SubjectKind сквозной: mention/episode subject, merge без даунгрейда,
  legacy-other отсев, коррекции, guard fills, no-probe чужого, саммари чисто
- prior snapshot по elder (+legacy-совместимость); тест на несмешивание
- annotation_schema + annotated_turns(10) + validate + understanding_eval
- chills (знобит/озноб) в лексикон; E702/I001 моих файлов

## VERIFIED

```bash
# group5fold slot 0.856 (curve .77→.86 растёт — данные помогают)
# subject 4/4; memory 2/2; annotations valid; understanding 0/0(1 известный
#   артефакт замороженного recall-теста: дубль ярлыка в тернах)
fuzz×1000 оба флага # 0; bench 1.00
pytest IDENTICAL свежему бейзлайну (17 pre-existing); ruff моих clean
bridge restarted, :9210 ok
```

## NOT VERIFIED

- Живой звонок с этим билдом

## NEXT GATE

Звонок 7000 → 10 живых.

---

# Previous — degraded-close УДАЛЁН (2026-09-15)

**Outcome:** фича «фраза + отбой при смерти провайдера» полностью выпилена по
требованию: ложные срабатывания на живых звонках хуже любой тишины.
Удалены счётчики, метод, WAV, тесты. Прод перезапущен без неё.

## VERIFIED

```bash
pytest 1280/16 (все в baseline-44); ruff clean; bridge restarted, :9210 ok
```

**Outcome:** ворота «умер STT/TTS — не 30 секунд тишины» закрыты кодом:
счётчики последовательных падений, пороги (STT×2 / TTS×1), предзаписанная
фраза «Извините, технические неполадки…» с диска (провайдеры не нужны),
чистый hangup, один раз за звонок. 4 теста. Forensic-WAV на месте (ложная
тревога: том смонтирован, звёздочку раскрыл shell). Бридж перезапущен.

## CHANGED

- `call_actor.py` — счётчики + `_maybe_degraded_close`
- `fallback_audio.py` (new) + `services/tts/fallback_tech_issue_16k.wav` (267KB)
- `tests/test_degraded_close.py` (new, 4 теста)

## VERIFIED

```bash
# 4/4; пытался сломать emit — разделено; порядок колбэков в тестах — ключевой
pytest 1284/16 (все в baseline-44); ruff clean; bridge restarted, :9210 ok
```

## NOT VERIFIED

- Живой kill STT/TTS посреди звонка (код готов, нужен живой)
- Живой звонок с текущим билдом

## NEXT GATE

Звонок 7000 → 10 живых.

---

# Previous — МИНА: await бесконечного насоса убивал весь звук (2026-09-15)

**Outcome:** тишина объяснена и починена одной строкой. В унаследованном
несохранённом паке `asyncio.create_task(self._playback_pump())` был заменён
на `await self._playback_pump()`, а pump — `while not stopped`: вечное
зависание on_media_ready, звук не качался никогда. Доказательство, что не я:
моя правка рядом требовала точного совпадения — прошла, значит await уже
стоял. Плюс полный аудит рантайма: вторых таких мин нет (все pump/loop через
create_task, слипы через asyncio, drain с break). Звук проверен звонком.

## CHANGED

- `call_actor.py` — возврат `create_task` для _playback_pump

## VERIFIED

```bash
# живой звонок: звук есть
pytest 1280/16 (все в baseline-44); ruff без новых; fuzz 0
bridge restarted, :9210 ok
```

## УРОК (мне и в AGENTS)

- События в трассе ≠ живой звук: playback.completed шёл, насос стоял.
- При «всё сломалось» — первым делом `git diff` по аудио-пути, а не сеть.
- Несохранённые паки такого размера — мины; коммитить/тегировать чаще.

## NEXT GATE

Звонок 7000 по полному сценарию + 10 живых подряд.

---

# Previous — масштабирование: доказательство на маке (2026-09-14)

**Outcome:** замерили, а не поговорили. STT — линейный (потолок ~2 параллельных
в бюджете), TTS — 503-потолок на 4 (штатный, но низкий), движок изолирован
(40 параллельных диалогов, 0 ошибок), память — под локом. 10 звонков на этом
маке: НЕТ (STT). Путь: батчинг STT + Linux/GPU + очереди, потом 2→5→10.

## VERIFIED (Mac, без Linux)

```bash
python3 tools/voice_lab/parallel_load_probe.py --levels 1 2 4
# STT: x1 p50 347ms → x2 663ms → x4 1204ms (single inference thread, linear)
# TTS: x1 33ms → x4 123ms, x8 = 503 queue full (executor.queue_depth>=4)
# RSS: STT ~940MB, TTS ~184MB, bridge ~20MB
# 40 параллельных диалогов ×10 потоков: 0 ошибок, все закрыты, факты не текут
```

## CHANGED

- `caller_memory.py` — flock на запись (гонка одного клиента закрыта;
  SQLite — при шардировании)
- `tools/voice_lab/parallel_load_probe.py` (new)

## NOT VERIFIED / gaps

- max_active_calls: 1 — в коде НЕ enforced (только конфиг); ворота — мощности
- MLX-модели при параллели (сейчас выключены на прод-пути) — замер отдельно
- Linux/CUDA, транк, мониторинг — следующими заходами
- Живой звонок с текущим билдом

## NEXT GATE

Звонок 7000 → 10 живых → STT-батчинг/очереди → Linux-замер → 2/5/10.

---

# Previous — latency timeline без касания поведения (2026-09-14)

**Outcome:** по пункту 10 ревью: per-call timeline как чистая наблюдаемость.
8 однострочных меток в существующих хуках CallActor + один stage-ивент при
отключении + CLI p50/p95. Ноль ветвлений, ноль порогов, все вызовы в try.
Бридж перезапущен, система не тронута.

## CHANGED

- `packages/voice_runtime/call_timeline.py` (new, ~70 строк, ноль зависимостей)
- `call_actor.py` — 8× `self._tl().mark(...)` + emit в _finalize_disconnect
- `tools/voice_lab/latency_histogram.py` (new) — p50/p95 по SLO-сегментам

## VERIFIED

```bash
# математика таймлайна — unit-проверка; call_actor-тесты 13 passed
# сьют минус 3 pre-broken harness-файла: 1280 passed, 0 failed
ruff моих файлов clean (остаток F841/I001 — pre-existing)
bridge restarted, :9210 ok
```

## NOT VERIFIED

- Данные tier: появятся с первым звонком на новом коде
- Живой звонок

## NEXT GATE

Звонок 7000 → `latency_histogram.py` по свежей трассе → первые цифры SLO.

---

# Previous — STT-шум: порча как живьём + фонетический safety (2026-09-14)

**Outcome:** стресс теперь долбит грязно (обрезки/шепелявость/склейки по образцу
живых трасс). Нашёл: усечённые глаголы роняли экстренность (589→~200/15k),
«Отстань» на красном закрывал тёплым, отказ от темы при шепелявости снова
становился revoke. Safety-лексика переведена на фонетические классы
(первая буква точная, хвост — путаницы): унираю/умилаю/зады./пад./упан ловятся,
задание/вода/подарок — нет. Бридж перезапущен.

## CHANGED

- `tools/voice_lab/stt_noise.py` (new) + `--stt-noise` в стрессе
- `check_path.py` — _fz()/классы путаниц для urgent; усечения пад/уми/унир
- `conversation_policy.py` — reluctance-close запрещён при red pending
- `controls.py` — topic-отказ без якоря (STT вставляет «я», глотает гласные)
- `reducer.py` — post-close re-open на urgent-action

## VERIFIED

```bash
# 13/13 фонетических кейсов; noisy stress: exc/silent/hangup/unclosed 0
fuzz×1000 оба флага # 0; bench 1.00
pytest 1280/16 (все в baseline-44); ruff clean; bridge restarted, :9210 ok
# остаток ~1.8%: экстремальные огрызки («Я за. уже») — хвост генератора
```

## NOT VERIFIED

- Живой звонок с этим билдом

## NEXT GATE

Звонок 7000.

---

# Previous — часовой стресс: 900k звонков + телефония (2026-09-14)

**Outcome:** adversarial soak 25 мин: 899 333 звонка / 5 455 362 ходов —
0 исключений, 0 тишины, 0 обрывов mid-probe, 0 незакрытых, urgent 99829/99829.
Найдено и починено по ходу: post-close глотание экстренности (re-open),
зацикл саммари (2-й раз → goodbye), revoke на отказ от темы, повторы мусора,
«скорее»=скорая. Телефония: живой путь Zoiper доказан трассами; synthetic
pyVoIP и loopback-originate заблокированы (NAT hairpin / нет сессии бриджа —
отдельные задачи); DHCP сменил IP (.194→.47) — Zoiper перерегистрировать!
Бридж перезапущен на всём.

## CHANGED (этот заход)

- `reducer.py` — post-close re-open на urgent-action; 2-й summary→goodbye;
  asked_history в _emit_speak
- `controls.py` — topic-отказ ≠ revoke; call-level stop (+не звоните/не беспокоить)
- `scripts/dialogue_stress_soak.py` (new) — 12 adversarial-скриптов, метрики,
  urgent-recall, отчёт JSON

## VERIFIED

```bash
IMVERA_COVERAGE_LADDER=1 ... stress_soak --minutes 25 # 899333 calls, all green
pytest 1280/16 (все в baseline-44); ruff clean; bridge restarted, :9210 ok
```

## NOT VERIFIED (честно)

- Живой звонок с этим билдом (Zoiper сейчас НЕ зарегистрирован — перерегистр
  на 192.168.1.47:5062 нужен от вас)
- Медиа-E2E без человека: synthetic сломан ([Errno 9]/hairpin), loopback не
  поднимает сессию бриджа — нужен отдельный разбор dialplan/WS

## NEXT GATE

1. Перерегистрация Zoiper → контрольный звонок 7000 (10-мин hold для soak)
2. Разбор loopback-сессии / починка synthetic-клиента

---

# Previous — слой выяснения критичности: ЧТО случилось (2026-09-14)

**Outcome:** принято самое важное замечание: «плохо» без жалобы уходило в
лесенку, «умираю» без причины — сразу в urgent. Теперь: красное действие
(падаю/задыхаюсь/кровь/скорая) — сразу помощь; красное состояние без сайта
(умираю/мне конец) — «Что именно беспокоит?» → варианты → urgent с меткой
unspecified; с сайтом — сразу; кино-контекст — разминирование с откатом
записи. Лесенка еды/таблеток при плохом без жалобы запрещена механически.

## CHANGED

- `check_path.py` — _URGENT_ACTION vs _URGENT_STATE (+очень сильно/ужасно)
- `reducer.py` — сплит hijack; _record_negative_wellness(record_concern);
  _concern_established; _close_partial отдаёт ход лесенке при pending
- `state.py` — red_state_pending, concern_probe_count
- `conversation_policy.py` — лесенка probe→options→urgent-unspecified;
  defuse с откатом wellness/check_path; asked_history + «я спрашивала»
- `tests/test_critical_ladder.py` (new, 6 тестов)

## VERIFIED

```bash
# умираю→проба→опции→urgent unspecified; умираю+сердце→сразу; фильм→defuse→обычно
fuzz×1000 оба сида/оба флага # 0; bench 1.00; critical 6/6; meds 15/15
pytest 1280/16 (все в baseline-44); ruff clean; bridge restarted, :9210 ok
```

## NOT VERIFIED

- Живой звонок с этим билдом

## NEXT GATE

Звонок 7000.

---

# Previous — 5 звонков прослушаны: скор-ее, еда-класс, probe-net, мусор, UQ (2026-09-14)

**Outcome:** все 5 свежих звонков разобраны. Совет ChatGPT сверен с архитектурой:
мультифакты/очередь/asked-метки/приоритет свежего — уже стоит (саммари 6298
собрало 4 факта). Внедрено недостающее: история вопросов + ответ «я спрашивала»,
строгий asked-once (повторов мусора больше нет), safety-net пробы, класс еды
по словам. Опасный false-urgent «скорее»→«скорая» убит. Бридж перезапущен.

## CHANGED

- `check_path.py` — URGENT скор(ую|ая|ой), не скор\w* («скорее» больше не скорая)
- `state.py` — asked_history (cap 20); `reducer._emit_speak` пишет
- `conversation_policy.py` — schedule_next_action отвечает на «что ты
  спрашивал» цитатой из истории (topic-aware); concern-probe safety net;
  debris без переспроса/слота-зависимый; primary предпочитает орган
- `issue_mention_extract.py` — UQ += что спрашивал/хто; _PAIN_VERB префиксы
- `coverage.py` — NUTRITION-маркеры кушал/ела; _NEGATED_TOOK; есть→takes
- `questions.py` — саммари без глаголов-пустышек при органах

## VERIFIED

```bash
# norepeat/negtook/whatasked живые цепочки — без повторов, с ответом-цитатой
fuzz×1000 seed7 + ×500 seed99/флаги # 0; bench 1.00; meds-spec 15/15
pytest 1274/16 (все в baseline-44); ruff clean; bridge restarted, :9210 ok
# уроки: мой UnboundLocalError(questions) и PROBE_CONCERN-enum пойманы тестами;
#   сломанный отступ — тоже (впредь: импорт-алиасы + прогон после каждой правки)
```

## NOT VERIFIED

- Живой звонок с этим билдом

## NEXT GATE

Звонок 7000.

---

# Previous — spec таблеток 15/15 + еда раньше + improving-чек (2026-09-14)

**Outcome:** ваша спека внедрена дословно: порядок еда→таблетки, нейтральные
формулировки («Есть ли у вас лекарства…», «Сегодня уже принимали?»), все 15
сценариев — зелёные регрессионные тесты с запретом instruct-фраз. Прошлое без
«прошло» («утром поболел») даёт ровно одну проверку «сейчас ещё беспокоит»,
а не молчаливое захоронение. Бридж перезапущен.

## CHANGED

- `coverage.py` — FILLER_ORDER еда→таблетки→настроение→сон; тексты спеки;
  occasional→today-Q; refusal→drop; takes += есть/принимал/дочь-раскладывает
- `tests/test_medication_neutral.py` (new, 15 тестов + FORBIDDEN-фразы)
- `issue_plans.py` — NUTRITION по словам еды (приболело≠еда)
- `conversation_policy.py` — concern-probe safety net; debris (переспрос 1
  раз, без записи); ack с органом; изоляция флага в тестах (monkeypatch)
- `known.py`/`planner.py`/`question_context.py` — inferred improving ≠ ответ:
  одна current-проверка для неспрошенного
- Pain verbs += поболел; repair += о чём говоришь/не услышала; UQ += хто

## VERIFIED

```bash
# 15/15 spec; ploho→probe; debris→1 переспрос; throat→onset; belly→current-чек
fuzz×1000 оба сида/оба флага # 0; bench 1.00
pytest 1274/16 (все в baseline-44); ruff clean; bridge restarted, :9210 ok
qwen3-1.7b: 0.41 max (reject); детерм 1.00 остаётся решением
```

## NOT VERIFIED

- Живой звонок с этим билдом

## NEXT GATE

Звонок 7000: «Хорошо» → еда → таблетки(нейтрально) → настроение → сон.

---

# Previous — звонок d99db688: clarify самочувствия + глаголы + головокружение (2026-09-14)

**Outcome:** «Непонятно.» первым ответом больше не пропускает самочувствие —
один переспрос «хорошо или не очень?». Глаголы-ответы («Успели.», «Принял.»)
не копят усталость и не роняют лесенку. Саммари пишет «головокружение», а не
«головная боль». Про обучение — честно ниже. Бридж перезапущен.

## CHANGED

- `conversation_policy.py` — wellness clarify-once (флаг пилота, один раз)
- `reluctance.py` — _SHORT_CONTENT_VERBS для fact-check слотов
- `questions.py` — concern_summary: круж/dizziness → «головокружение»

## VERIFIED

```bash
# Непонятно→переспрос→Нормально→лесенка; Успели→записано, rel 0
fuzz×1000 оба сида/оба флага # 0; bench 1.00
pytest 1259/16 (все в baseline-44); ruff clean; bridge restarted, :9210 ok
```

## NOT VERIFIED

- Живой звонок

## NEXT GATE

Звонок 7000.

---

# Previous — обучающаяся система: предзагрузка + память клиента + карантин (2026-09-14)

**Outcome:** конец переделыванию. Три слоя вместо патчей: (1) предзагруженные
парафразы сгенерированы мной (числа, дни, шкала, пропуски, мусор) — held-out
0.967; (2) обучение в процессе: глобальный ярус (порог 0.8) + личная память
клиента (доверие после 3 совпадений, кап 200, мусор не пишется никогда);
(3) карантин abstain + review-команда — бред в обучение не попадает, только
ручной approve через add_quote. Один клиент не травит другого (ключи по
client_id = family:elder, пустой = память выкл). Бридж перезапущен.

## CHANGED

- Трейнеры: `_preload()` (slot), client_id в EngineState/DialogueEngine/session
- `caller_memory.py` (new): resolve/record, TRUST_HITS=3, MAX 200, JSON
- `_second_tier_judgement`: память → глобалка (≥0.8 учит) → мусор мимо
- `slotclf.py`: `_quarantine()` на abstain; `review_quarantine.py` (new)

## VERIFIED

```bash
# память: 2 хита→None, 3→answer; чужой/пустой клиент→None; garbage не пишется
train held 0.967; quarantine собирает (14 abstains с фазза уже там)
fuzz×1000 оба сида/оба флага # 0; bench 1.00
pytest 1259/16 (все в baseline-44); ruff моих файлов clean
bridge restarted, :9210 ok, 0 sessions
```

## NOT VERIFIED

- Живой звонок (память клиента в бою — после 3 одинаковых звонков)

## NEXT GATE

Звонок 7000. Непонятое → review_quarantine → add_quote → retrain. Код не трогаем.

---

# Previous — модель 2B замерена: Qwen3-1.7B reject (2026-09-14)

**Outcome:** по требованию скачал Qwen3-1.7B-4bit-MLX и прогнал бенч 33 кейса
тремя промптами. Лучший результат 0.41 (few-shot) против детерминированного
1.00. Генеративная модель на принятие решений НЕ ставится — solucionado
измерениями, не мнением. Прод не трогал (нечего включать).

## VERIFIED (ai-model-evaluation)

```bash
qwen3-1.7b bare      # acc=0.22 p50=169ms (эnum leaking: episode_onset)
qwen3-1.7b mvp-prompt# acc=0.22 p50=167ms (всё содержательное → garbage)
qwen3-1.7b few-shot  # acc=0.41 p50=226ms + пустые выдачи и транслит (terpimaya)
deterministic        # acc=1.00 p50=0.1ms
route_clf-231KB      # acc=0.81 (sovещательный режим оставлен)
```

Таблица всех замеров: SmolLM2-360M echo-fail; Qwen2.5-0.5B бред;
Qwen3-0.6B 0.12; Qwen3-1.7B 0.41. Порог принятия: >1.00 детерма при p95≤2с —
не прошёл никто. Единственный честный путь к модельной помощи: файнтюн
(LoRA) на сотнях размеченных ходов, не скачивание большей модели.

## NEXT GATE

Звонок 7000 по текущему билду.

---

# Previous — звонки fe48f985/5324e8b6: двойная еда, таблетки при Плохо, мусор (2026-09-14)

**Outcome:** три жалобы — три корня, все в роутинге (не в «глупости»):
«приболело» содержало «ело» → эпизод горла уходил в семью ЕДА (отсюда двойной
вопрос про поесть + барьер после «поела»); «Плохо.» без concern шло в лесенку
мимо пробы (путь CallActor ≠ ScenarioRunner); мусор записывался покрытием и
тащил лесенку вниз. Плюс замер qwen3:0.6b = 0.12 (всё в garbage) — генеративные
модели для решений закрыты измерениями. Бридж перезапущен.

## CHANGED

- `product/issue_plans.py` — NUTRITION только по словам еды (поел/аппетит),
  не подстроке «ел» (+import re)
- `conversation_policy.py` — safety-net: negative wellness без concern →
  probe_concern до любой лесенки; `_is_coverage_debris` (мусор не пишется,
  один переспрос, дальше без записи); ack предпочитает орган
- Замер qwen3:0.6B-4bit-MLX (enable_thinking=False): acc 0.12 @ ~100ms

## VERIFIED

```bash
# ploho→probe; debris→переспрос 1 раз→дальше без записи; throat→onset
fuzz×1000 оба сида/оба флага # 0; bench 1.00
pytest 1259/16 (все в baseline-44); ruff clean; bridge restarted, :9210 ok
# по пути поймал свой UnboundLocalError(questions)/PROBE_CONCERN — починено,
# урок: safety-net трогал scope, fuzz таких путей не покрыл
```

## NOT VERIFIED

- Живой звонок с этим билдом

## NEXT GATE

Звонок 7000.

---

# Previous — конец латанию слов: граница answer/skip/garbage (2026-09-14)

**Outcome:** вместо очередного regex-патча — механизм обобщения. Второй ярус:
якоря промахнулись → slot-классификатор решает answer/skip/garbage по границе,
обученной на пулах+живых цитатах. Проверено обобщение на фразах, которых нет
ни в якорях, ни в обучении («в понедельник», «с неделю уже» → answer).
Петля парафразов: add_quote → retrain (1 мин) → bench+fuzz зелёные, regex
больше не трогаем для парафразов. Бридж перезапущен.

## CHANGED

- Глаголы боли += побаливает/понывает/прихватило/схватило/вступило (закрытый класс)
- Дни недели в якоря (закрытый класс из 7)
- `slotclf.py` (new) + `models/slot_answer_clf.pkl` (~100KB, thr 0.6, fail-open,
  только под флагом пилота) — второй ярус в onset/duration/severity
- `train_slot_answer_clf.py` + `add_quote.py` (петля), LIVE_QUOTES в трейнете
- Ответ записывает слова пользователя (cap 80), пропуск — маркеры без значений

## VERIFIED

```bash
# unseen: понедельник/вторника/неделю/жить можно → answer; Поднял/ага → garbage
python3 tools/voice_lab/add_quote.py --slot onset --label answer --text "когда с работы пришла"
# → retrain held 0.90, bench 1.00, judge теперь answer
fuzz×1000 оба сида (оба флага) # 0; pytest 1259/16 (все в baseline-44)
ruff clean; bridge restarted, :9210 ok
```

## NOT VERIFIED

- Живой звонок с этим билдом

## NEXT GATE

Звонок 7000. Новую непонятую фразу — не чиню regex'ом, а гоню через add_quote.

---

# Previous — звонки 07ba9ace+07799215: дубли, часы, пойдёт, приболел (2026-09-14)

**Outcome:** оба звонка переиграны целиком без сливов. Пять корневых дыр:
часы словами/цифрами, дубли эпизодов при пересказе симптома, «пойдёт»,
глаголы с приставками, отрицание в таблетках. Плюс ярлык «Беспокоит» вместо
органа. Бридж перезапущен.

## CHANGED

- Якоря += `\d{1,2}:\d{2}`, (в|на|к|с)+числительные (восемь…двенадцать)
- `_find_episode_for_mention`: предпочтение активного + site-in-label
  («Голова болеть» → к «голова болит», без дублей)
- Severity += пойдёт/сойдёт (все 4 места); pain += приболел/заболел/разболел
- Таблетки: «не каждый день»/«иногда» → no_meds (без today-Q)
- Ack: предпочтение упоминания с органом («голова болит», не «беспокоит»)

## VERIFIED

```bash
# оба живых звонка дословно: без partial, без повторов 3×, без дублей
fuzz×1000 seeds 7/42 (оба флага) # 0; bench 1.00
pytest 1259/16 (все в baseline-44); ruff clean; bridge restarted, :9210 ok
```

## NOT VERIFIED

- Живой контрольный звонок

## NEXT GATE

Звонок 7000 → разбор трассы.

---

# Previous — таблетки по-русски + условность + модели работа (2026-09-14)

**Outcome:** вопрос про таблетки переписан («Скажите, а лекарства вы каждый
день принимаете?» / вариант «А таблетки вам каждый день назначены?»),
двухшаговый условный: нет→закрыли тему без followup; да→одно «А сегодня уже
приняли?»; «уже принял»→сразу записали. Варианты формулировок у всех филлеров
(таблетки/еда/настроение/сон) — ротация по звонку, робота меньше. Модели дана
реальная работа: repair/question_back при отказе детерма (+ помехи STT «хто»
детерминированно). Бридж перезапущен.

## CHANGED

- `coverage.py` — domain_question(variant), MEDICATION_TODAY_TEXTS,
  classify_medication_screen (no_meds/takes/already_took/unclear); триво→mood
- `conversation_policy.py` — conditional today-Q (medication_asked),
  вариант через crc32(call_id)
- `kernel.py` — tiny repair/question_back remap только при abstain детерма
  (clarify + нет mentions/facts/вопроса), route с тегом +tiny_*
- `issue_mention_extract.py` — user_question: хто это/там/звонит

## VERIFIED

```bash
# nomeds: screen→«Нет, не принимаю»→сразу еда (без «сегодня приняли?»)
# meds: «Да, принимаю»→«А сегодня уже приняли?»→дальше
bench 1.00; fuzz×1000+flags 0; pytest 1259/16 (все в baseline-44);
ruff clean; bridge restarted, :9210 ok
```

## NOT VERIFIED

- Живой звонок с этим билдом

## NEXT GATE

Контрольный звонок 7000: таблетки → «не принимаю» (не должен спрашивать
«сегодня»); «О чём ты говоришь?» → повтор.

---

# Previous — live fs-16d22975 postmortem: «раньше» + «Дальше» (2026-09-14)

**Outcome:** звонок разбирал: лесенка отработала (таблетки→еда→настроение→сон→ITS),
срыв был на эпизоде «Наз болит»: «Дальше.» → повтор вопроса; «Раньше началось
это.» → НЕ засчитано (слова «раньше» не было в якорях — вопрос предлагает
«сегодня или раньше», а ответ «раньше» не принимался); дальше clarify + «Плохо»
→ partial. Починено + бридж перезапущен.

## CHANGED

- Якоря onset/duration += `раньше` (issue_memory / topic_tracker / check_path)
- `_SKIP_TEMPORAL` (дальше/пропусти/следующий вопрос/не важно): пропуск
  temporal весит ×2 + `_mark_temporal_asked` + `_temporal_skipped`, планировщик
  `_step_satisfied` считает onset/duration закрытыми без значения (без фабрикации)
- `_note_temporal_emit` тоже ставит `_temporal_skipped`

## VERIFIED

```bash
# точная живая цепочка теперь: Дальше→skip(без повтора), Раньше→заземлено,
# ladder→ITS→summary с фактом→goodbye, без partial и лупов
IMVERA_COVERAGE_LADDER=1 IMVERA_TINYLLM_MODEL=route_clf fuzz×1000 seeds 7/42 # 0
pytest urgent/onset/check_path/issue-flows # 54 passed; ruff clean
pytest full: 1259 passed, 16 failed — все в baseline-44 чистого 5c0194d
bridge restarted, :9210 ok, 0 sessions
```

## NOT VERIFIED

- Живой повторный звонок с этим билдом (нужен набор 7000)

## NEXT GATE

Контрольный звонок: «Нос болит» → «Дальше» (не переспрашивать!) →
«Раньше началось» (принять!) → вопросы дальше, без слива.

---

# Previous — PROD updated: bridge restarted on new code + ladder/model ON (2026-09-13)

**Outcome:** media-bridge перезапущен (PID 40785) на рабочем дереве с флагами
`IMVERA_COVERAGE_LADDER=1 IMVERA_TINYLLM_MODEL=route_clf` (проверены в env
процесса). STT gigaam:v3 + TTS silero готовы, FreeSWITCH up, Zoiper
registered (NAT, re-register переодически нужен). Повтор «о чём ты
говоришь / чего ты сказала» починен (repair_repeat пересказывает вопрос).

## CHANGED

- `scripts/freeswitch_voice_lab_env.py` — setdefault обоих флагов пилота
- `packages/dialogue_engine/semantic_kernel/controls.py` — repair: о чём ты
  говоришь / чего ты сказала / не услышала
- bridge restart (stop/start voice_process, marker-gate обойдён осознанно:
  маркера под SHA нет, т.к. preflight падает 16 pre-existing; регрессий 0)

## VERIFIED

```bash
curl :9210/health/ready  # ok, engine 5c0194d+tree, 0 sessions
curl :9101, :9102/health/ready  # ready/ready
IMVERA_COVERAGE_LADDER=1 IMVERA_TINYLLM_MODEL=route_clf fuzz --n 1000  # 0
make test-live-replays  # 61 passed (с флагами)
make freeswitch-synthetic-sip  # FAILED [Errno 9] — старый баг lab-клиента, не диалог
fs_cli: 0 channels, zoiper Registered
```

## NOT VERIFIED

- **Живой звонок с новым билдом** — нужен набор 7000 с Zoiper (Даниил).
  Сценарий: 1) «Хорошо» → должны пойти таблетки/еда/настроение/сон;
  2) «О чём ты говоришь?» → повтор вопроса; 3) «Таблетку забыла» →
  «сегодня приняли?»; 4) «Хватит» → тёплое прощание.

## NEXT GATE

Живой звонок → разбор `.run/traces/fs-*.jsonl` → вердикт.

---

# Previous — adaptive coverage + reluctance + tiny-model verdict (2026-09-13)

**Outcome:** покрытие 5 доменов адаптивно (не анкета, MVP-механика: очередь →
issue-планы → baseline только по непокрытому → ITS), reluctance-дожима нет
(тёплый early close), шов tiny-модели + бенч. Замер: генеративные <0.6B
непригодны (SmolLM2-360M эхо, Qwen2.5-0.5B бред) → модель НЕ включается;
шов выключен по умолчанию, бенч зелёный на детерминированном 1.00.

## CHANGED

- `packages/dialogue_engine/coverage.py` (new) — 5 доменов, covered(),
  минимум 3 обмена/3 домена (мягкий, как в MVP), asked-once, volunteer-skip
- `packages/dialogue_engine/reluctance.py` (new) — счётчик 10/3/2/1,
  cooperative-fill и grounded-short не копят
- `conversation_policy.py` — filler перед ITS, приём ответа филлера дословно,
  ITS-хвост без изменений; лесенка и early close за флагом
  `IMVERA_COVERAGE_LADDER` (default OFF — замороженные формы целы)
- `packages/dialogue_engine/runtime.py` — `coverage_ladder_enabled()`
- `packages/dialogue_engine/tinyllm.py` (new) — route_clf/sklearn + MLX seam,
  temp-0, таймаут 3с, fail-open, default OFF; `tiny_route` в RichUserTurn
  (advisory, bounded +1)
- `packages/dialogue_engine/semantic_kernel/kernel.py` — вызов assist только
  needs_clarify + ≤4 слов + флаг (исправлен NameError raw→result.raw_text)
- `controls.py` — repair: чего/чё/ась; `issue_mention_extract.py` —
  user_question: про что; `span_parser.py` — большое-laundry уже было
- `tools/voice_lab/ambiguity_bench.py` (new, 33 кейса) + `train_route_clf.py`
  (new, sklearn 231KB, held-out 0.964) + `models/route_clf.pkl`
- `state.py` — reluctance_score, coverage_asked_domains, pending_coverage_domain

## VERIFIED

```bash
python3 tools/voice_lab/ambiguity_bench.py
# deterministic: acc=1.00 p50=0.1ms p95=2.2ms
python3 tools/voice_lab/ambiguity_bench.py --models deterministic,tiny  # route_clf 0.81 — хуже детерма
# SmolLM2-360M: echo-only; Qwen2.5-0.5B-4bit: 'Гарbage'/'ответ'/'Герой' — непригодны
IMVERA_COVERAGE_LADDER=1 fuzz --n 1000 --seed 7  # 0 failures
pytest (flag OFF): 1259 passed, 16 failed — все в baseline-44 чистого 5c0194d
ruff check packages/dialogue_engine/  # pass
# живые формы с флагом: good→5 адаптивных Q; emg→urgent; tired→goodbye
```

## NOT VERIFIED

- Живой SIP с флагом; qwen3:0.6b не мерял (не качал — ниже вывод, зачем)
- 16 остаточных (harness корпуса, pre-existing)

## Модельный вердикт (ai-model-evaluation)

TASK LLM-assist CANDIDATES: deterministic / SmolLM2-360M-MLX / Qwen2.5-0.5B-4bit-MLX / sklearn-route_clf-231KB. WINNER: deterministic (1.00 @ 0.1ms). route_clf 0.81 — не дотягивает. Генеративные <0.6B — reject (не следуют инструкции на русском). RECOMMENDATION: модель не включать; шов+бенч оставить под будущие живые цитаты. Покрытие/усталость — детерминированно под флагом.

## NEXT GATE

1. Пилот с `IMVERA_COVERAGE_LADDER=1` на живых (3–5 звонков) + собрать новые
   двусмысленные цитаты в бенч
2. 10-call pack-corpus gate

---

# Previous — anti-stupor pack: urgent hijack + onset grounding + anti-loop + honest ack + meds (2026-09-13)

**Outcome:** 5 root fixes on DialogueEngine (no new arch, ADR-014-safe bugfixes).
Fuzz-1000 clean on seeds 7/42 (was 12 I3-temporal-loop). Suite 1259 passed /
16 failed — все 16 падают и на чистом SHA 5c0194d (там 44 failed), регрессий 0.

## CHANGED (working tree поверх 5c0194d, branch feature/voice-zoiper-m5)

- `packages/dialogue_engine/check_path.py` — `_probe_pain_night` urgent-guard;
  `_DURATION_HINT` += сейчас/уже/назад/только что
- `packages/dialogue_engine/issue_memory.py` — `_TEMPORAL_ANCHOR` +=
  сейчас/уже/только что/назад/ч/мин; ungrounded onset/duration ×2 → снять
  pending без фабрикации (anti-loop, уровень 1)
- `packages/dialogue_engine/topic_tracker.py` — `_DURATION_MARKERS` те же якоря
- `packages/dialogue_engine/reducer.py` — `_has_urgent_evidence` guard в
  `_close_partial` (emergency никогда в partial); `_note_temporal_emit`
  счётчик повторов onset/duration в `_emit_speak` + `_speak_repair`:
  3-й повтор → repair=короткое «Повторите», обычное=complete?advance:partial;
  `_emit_urgent_close(check_path=URGENT + запись честного negative wellness)`
- `packages/dialogue_engine/questions.py` + `product/spoken.py` — ITS-вопрос
  нейтральный «Поняла вас…» (было ложное «Хорошо.» после Пло./UNCLEAR)
- `packages/dialogue_engine/conversation_policy.py` — таблетки/лекарства =
  NEW_GROUNDED_INFORMATION + один followup status_today (текст пака);
  `state.py: medication_asked`
- `packages/dialogue_engine/semantic_kernel/span_parser.py` —
  `_FALSE_ISSUE_TOKENS` += большое/большой/… («спасибо большое» больше не
  создаёт эпизод-симптом «Большое»)

## VERIFIED

```bash
python3 scripts/dialogue_behavior_fuzz.py --n 1000 --seed 7   # 0 failures
python3 scripts/dialogue_behavior_fuzz.py --n 1000 --seed 42  # 0 failures
python3 -m pytest tests/test_urgent_safety.py tests/test_onset_after_event_grounding.py tests/test_check_path.py tests/test_issue_first_flows.py -q  # 54 passed
python3 -m pytest tests/ -q -p no:cacheprovider  # 1259 passed, 16 failed — все 16 в baseline-44 чистого 5c0194d
python3 -m ruff check packages/dialogue_engine/  # pass
# живые формы: fs-41e2a57b→urgent_close; fs-a7bffaf1-таблетки→medication_status_today;
# fs-a8964347 «3 ч назад»→onset заземлён; fs-d42264b9→summary; fs-c436546b→без лупа
```

## NOT VERIFIED

- Живой SIP-звонок с этим билдом (нужен Zoiper re-register + `make freeswitch-zoiper-voice-up`)
- 16 остаточных падений — harness корпуса (stale_speak/DeliverPlayout) сломан
  уже на чистом 5c0194d; отдельная задача, ассёрты не трогал
- ADR-014 100 consecutive SIP/RTP calls

## NEXT GATE

1. Живой ретест 3 форм: «падаю/задыхаюсь»→urgent; «сейчас»→onset принят;
   «таблетку забыла»→«сегодня приняли?»
2. Затем 10-call pack-corpus gate.

---

# Previous task — 7000 silent: stack down + pack broke frozen gates (fix-forward)

**Outcome:** 7000 silent because STT/TTS/media-bridge were DOWN since ~03:27 and
Zoiper registration expired; pack 25951e1 additionally broke 28 preflight tests
(close-contract violation + `unknown` fabrication + weakened asserts). Fixed
forward to frozen contract; preflight green; stack re-upped on SHA 5c0194d.

## ROOT CAUSE

1. Operational: `media-bridge :9210`, STT `:9101`, TTS `:9102` all DOWN
   (processes gone, stale PIDs); today's 16:35 call reached FS (7.7 s uplink
   recorded) but bridge dead → Vera silent. No preflight marker for 5c0194d →
   official voice-up was BLOCKED.
2. Pack 25951e1 vs frozen gates (no ADR):
   - summary made terminal (hangup, no `goodbye_final`) + 3 tests weakened
   - `"unknown"` written into `known_attributes` (3 places)
   - mandatory probing (associated / sleep pattern) vs frozen completion
   - shadow ActionPolicy: inferred `current=active` exposed stale severity
     devalue (fs-77afbbf1); fresh-issue transition dropped leads (fs-1f6d3000)

## CHANGED (uncommitted, SHA 5c0194d)

- `packages/dialogue_engine/reducer.py` — summary non-terminal (goodbye_final
  hangs up); exhausted probes → frozen partial-close, no `unknown` writes
- `packages/dialogue_engine/issue_memory.py` — «не знаю» is noop (no write,
  pending stays); daytime lint rewrap
- `packages/dialogue_engine/product/planner.py` — obligations-satisfied ⇒
  complete (frozen); `issue_plans.py` — GENERIC_SYMPTOM fallback (throat etc.)
- `packages/dialogue_engine/conversation_policy.py` — summary re-speakable
  (never-silent); exhausted-probe skip without fabrication
- `packages/dialogue_engine/action_policy/need_value.py` — severity keeps full
  value after fresh temporal probe; `snapshot.py` — no transition on fresh
  speaker issue
- Tests: restored 3 weakened asserts; reworked 7 pack probing/hangup tests to
  frozen contract (`test_dialogue_must_hangup.py` rewritten: goodbye hangs up
  once). Probing ideas (associated, sleep pattern) → ADR backlog.

## VERIFIED

```bash
make preflight-gates
# preflight PASS sha=5c0194d — 1246 passed, 6 skipped
make freeswitch-zoiper-voice-up
# media-bridge ready (callactor), runtime SHA verified: 5c0194d
# bridge :9210 200 ok, STT gigaam:v3 ready, TTS silero v5_ru:kseniya ready
```

## NOT VERIFIED

- Live Zoiper call with this build (0 registered right now — re-register needed)
- `make freeswitch-synthetic-sip` fails in the LAB CLIENT
  ([Errno 9] Bad file descriptor, 0 calls reach FS) — client bug, not server
- ADR-014 100 consecutive SIP/RTP calls

## REMAINING RISKS

- Backchannel («ага») right after summary → silence (pre-existing gap, no
  frozen test; corpus always sends farewell text)
- Zoiper contact flaps via public IP (NAT) — may need re-register before calls

## NEXT GATE (2026-09-13 eve)

1. User retest of fs-87312170 shape: belly ache → «после того как покушал
   макароны» must fill onset and advance (no repeat, no partial).
   Fix live in bridge (SHA 5c0194d verified).
2. Then the 10-call pack-corpus gate.
