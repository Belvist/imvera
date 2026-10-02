# IMVERA: от сбора полей к выбору conversational move

Дата: 2026-10-02. Аудируемый HEAD: `09cff20133fcf77b32bf9b32357ee0dd1922daa2`,
`feature/voice-zoiper-m5`, 137 коммитов впереди origin/main. Дерево до аудита
чистое; main не менялся. Отчёт создан **до реализации cut**. Статус: аудит
исходников и SDK; реальный M5/телефон/модели/прослушивание NOT VERIFIED.

## Решение до изменений

Переход нужен внутри существующих owners. Простое `MODE=policy` сейчас
запрещено как promotion: воспроизведено, что выбранный вопрос не связывается
с клиническим pending need, ответы не закрывают его и вопросы повторяются.
Кроме того, frozen v9 вообще не представляет личную тему. Это два разных
блокера: исполнение разрешённого действия и полнота разрешённых действий.

Первый минимальный cut — **Cut 0, измерения в существующем comparison tool**:
SDK snapshots, фактически выбранные действия, question IDs/needs, simulated
delivery и сравнение legacy/shadow/policy на одинаковых входах. Он не меняет
production поведение. Следующий production cut — выделить reducer-owned commit
выбранного плана; только затем расширять существующий ActionPolicy. Нельзя
выдавать этот первый cut за улучшение речи.

Вариант A остаётся действующим. Вариант B разрешён к исследованию этим заданием,
но не к включению: измерений локального генератора на M5 нет. ADR-025/026/027
не отменяются молча. Вариант C отвергается: safety/state/actions не становятся
полномочиями модели. Предложение зафиксировано в ADR-028.

## A. CURRENT SYSTEM

### Реальный CallActor путь по исходникам

```text
FreeSWITCH public.xml: answer + uuid_audio_stream mono16k
 → services/imvera_media_bridge/main.py:fs_pcm_stream
 → callactor.py:handle_callactor_ws → CallActor.push_pcm
 → VAD / UtteranceBuilder / TurnManager → _handle_utterance_inner
 → HttpSTTProvider.transcribe_final
 → kernel.interpret(answer_slot=...) → post-STT echo/fragment admission
 → kernel_to_rich_turn + deterministic mission understanding
 → semantic_nlp act candidate → TurnUnderstandingV2.apply_act_candidate
 → TurnUnderstandingV2.adjudicate_final
 → ordered outcome → CallSession.handle_user_text / _apply_user_turn
 → DialogueEngine.on_user_turn / _apply → reducer.reduce
 → atomic_semantic_apply / issue memory / goals / discourse
 → _schedule_advance → schedule_next_action → DecisionRouter
 → ONE selected scheduler → ResponsePlan → render_response_plan
 → reducer._emit_speak → SpeakEffect / outbox / generation + question identity
 → CallActor._deliver_session_turn → exact canonical text → TTS
 → resampler / PlaybackQueue / _playback_pump → FreeSWITCH
 → actual playout callback → Session.mark_spoken_action → PlayoutCompleted
```

Ссылки: actor `1188–1232`, `1967`, `2017`, `2150`, `2230`, `2309–2321`,
`2451`, `2631`, `2694–2703`, `3021`, `3210`, `3313`; session `952–978`,
`1162`; engine `72`, `473`; reducer `99`, `551`, `944`, `981`, `1021`.
Номера относятся к указанному HEAD, имена функций остаются основным ориентиром.

**SDK и CallActor пока не идентичны в производстве смысла.** SDK
`DialogueEngine.build_rich_turn → TurnUnderstandingV2.resolve → builder`
вызывает kernel без того же answer_slot и добавляет contextual harvesters
(`turn_understanding.py:464–539`). Actor строит rich turn непосредственно
из kernel и использует apply/adjudicate (`call_actor.py:2150,2230,2314,2451`).
Session передаёт готовый rich turn без SDK resolve. Общий Reducer обеспечивает
часть общей защиты; SDK replay не доказывает parity с CallActor.

### Владельцы: ответы на 12 вопросов аудита

| Вопрос | Фактический owner / место |
|---|---|
| Кто понимает смысл | Kernel + mission provider + act adjudication; SDK и actor producers отличаются, описано выше |
| Кто меняет state | `reduce` — единый атомарный mutation funnel; `atomic_semantic_apply` и вызываемые helpers пишут в тот же EngineState |
| Кто решает следующий ход | reducer guards, затем `schedule_next_action → route_schedule_next_action`; default `_schedule_next_action_legacy` |
| Кто выбирает вопрос | `product.next_product_need:204` для эпизода; `_next_background_goal:368`; `mission_flow.next_askable_goal:54` для custom goal |
| Кто формулирует | `response_plan.render_response_plan:54`; questions/product spoken/coverage renderer functions и planner-supplied строки |
| Hardcoded сценарии | `product/issue_plans.FAMILY_PLANS:40`; ordered symptom steps, reducer guard/repair paths, mission sequencing |
| Phrase banks | questions `11–99,454–471`; product/spoken `_FAMILY_SPOKEN:17`, `_GENERIC:84`; coverage.domain_question:222 |
| Фиксированные очереди | protocol/pilot_checkin.yaml; coverage tie-break; `_next_background_goal`; `next_product_need` явно plan order |
| Возврат к миссии | `resume_after_user_thread:995`; suspended obligation `1258`; mission_flow custom suspend/resume |
| Обрезание свободной темы | `conversation_policy:1056`, count>=2; любые открытые clinical episodes блокируют thread `1051,1080` |
| Live / experimental | conditional router authority реально вызывается; TinyRanker/paraphrase helpers не имеют callers в packages/services; retired composer отсутствует |
| Устаревшие ADR | конкретные исторические claims и поправки перечислены ниже; статус proposed не означает внедрение |

«Reducer sole writer» сейчас означает logical event funnel, **не** отсутствие
записей вне reducer.py: legacy `_episode_plan:400,408–410`, scheduler thread
counter `1055–1058`, renderer `questions.rotate_pool:129–133` и
`Engine.begin_interpret:134` меняют состояние. Нельзя переключить pure choose,
оставив необходимые commits только в legacy selector.

### Runtime flags: конфигурация не равна наблюдению M5

* Media bridge default `uplink_only` (`main.py:31`); данный call graph включается
  для `callactor|voice|duplex`. Базовый FS compose не устанавливает этот mode.
* Engine activation требует `IMVERA_DIALOGUE_ENGINE` и direct wellness flag,
  оба source default ON (`runtime.py:90`). Lab opening shortcut не доказывает
  продуктовый consent.
* `IMVERA_ACTION_POLICY_MODE=off` означает **legacy scheduler внутри нового
  DialogueEngine**, а не запуск старого packages/dialogue/Planner. Soft/policy
  требуют companion cutover flag; soft cohort default 0. Custom missions всегда
  bypass frozen policy (`decision_router:285–291`).
* Coverage ladder default OFF; Zoiper env helper включает его. STT prefix preview
  и barge-in source defaults OFF. Prefix preview — batch recomputation, не
  stateful realtime ASR. Реальные значения на текущем M5 неизвестны.
* Engine actor branch не вызывает `/v1/interpret` даже при LLM flags
  (`2365–2375`), canonical speech обходит `/v1/render` (`2694–2703`). URL9103
  в health не доказывает model invocation.
* Act head вызывается model-first на engine turns; relation xenc shadow также
  может выполнять вычисления, хотя не выбирает speech. Polarity/relation fallback
  имеют отдельные условия. Tier1 нельзя объявить бесплатным.
* Здесь Linux, нет M5 credential/VPN, актуальных FS traces и реальных NLP/GGUF
  артефактов. Журнал агента с отметкой live не является независимой записью.

## B. WHY IT FEELS LIKE A QUESTIONNAIRE

1. **Понимание не равно conversation policy.** Существуют episodes/evidence,
   multi-goal answers и unknown, но следующие действия в основном извлекают
   дополнительный health need или обязательный background goal.
2. **Coverage частично уже адаптивна.** `scored_next_domain:197` реально
   вызывается (`conversation_policy:1802`): information=1 + lexical topic bonus2
   − position penalty. FILLER_ORDER — tie-break из protocol data, не единственный
   алгоритм. Всё ещё есть минимум exchanges/domains и узкий collection legal set.
3. **Episode question order действительно жёсткий.**
   `information_gain.best_question_need:61` делегирует product owner; функция
   heuristic gain не означает live authority. Product skip-known/resolved/refused
   работает, но current/associated steps иногда специально спрашиваются once
   несмотря на clues (`product/planner:124–159`). Эти необходимости требуют
   доказательного пересмотра, а не удаления полей.
4. **Thread не определяет исчерпанность темы.** Hook + lexical overlap
   (`discourse:317`) и decay после трёх unrelated turns (`298`) — слабая память.
   Новый count2 защищает от повторного invitation, но теперь обрывает вовлечённый
   рассказ без semantic reason. Это product restriction, не safety requirement.
5. **Ответы на вопросы узкие.** `_IDENTITY_ANSWER` для generic question
   (`conversation_policy:1244` и `action_policy/bridge:46`); arbitrary QA owner нет.
   Mission attachment может добавить user_question без снятия answers_pending,
   из-за чего вопрос вообще не получает ответа.
6. **План уже частично семантический, но речь всё ещё задаётся заранее.**
   ResponsePlan содержит QuestionNeed/allowed facts/prohibited inferences,
   одновременно mandatory_question и готовый answer_user_question string.
   Подмена этих строк генератором сама по себе не исправит выбранный move.

### Реальные offline SDK контрпримеры на HEAD

| Вход / последовательность | Наблюдение |
|---|---|
| Самочувствие хорошее, настроение спокойное, спала хорошо, сегодня пойду гулять | Все4 slots FILLED: база multi-fact уже есть; sleep/plans могут хранить всю фразу |
| Голова болит со вчера, сейчас сильная боль | onset=вчера, current=improving, severity отсутствует; Vera повторно спрашивает current |
| А вы любите музыку? | user_question присутствует, act=answer, answers_pending=true; вместо ответа переход к ITS |
| Зачем вы звоните? | canonical question, корректный identity answer |
| Story → чай → вспоминали поездки → хочу рассказать про дачу | count2 возвращает wellness; продолжение теряет conversational ownership |
| Policy: голова болит → с утра → терпимо | onset/severity снова спрашиваются: pending_episode_attribute остаётся None |
| Policy: хорошо → нет после ITS | ITS задаётся повторно: asked/resolved lifecycle не committed |
| Спасибо, не хочу больше разговаривать | act=answer/control=none; legacy продолжает ITS, policy даёт ACK; завершение распознаётся только на следующем «До свидания» |

Причина неверного current/severity лежит до selector: comma clause split,
узкая ellipsis relation (`relation_parser:148–173`), yesterday→not-current
projection (`observation_memory:80–86,1004–1017`) и приоритет improving
(`issue_memory:415`). Это не лечится банком вопросов. QA inconsistency:
`turn_understanding.attach_mission_understanding:420` добавляет user_question,
но reducer `1270` и scheduler `1244` требуют !answers_pending.
Последний случай — существующий gap распознавания global stop; сохранность
frozen control implementation не означает полноту его языкового покрытия.
Он не исправлен и не засчитан как успешная acceptance.

### Почему ActionPolicy пока не authority по умолчанию

Frozen v9 pure selector unit/shadow/router: **115 passed**,0.87s. Но в actual
SDK multi-turn policy mode с cutover=1 pending need не committed:
`bridge.to_response_plan:54` возвращает план; renderer `180` и reducer
`_emit_from_plan:944` не заменяют записи из legacy `_episode_plan`.
Аналогично ordinary ITS asked/resolved живёт в legacy helpers. Green choose tests
не проверяли эту lifecycle integration. Default fence сейчас имеет основание.

Кроме этого, PolicySnapshot `95–122` не содержит thread/engagement/reluctance;
ActionKind не содержит FOLLOW_THREAD/WAIT/resume target. BACKGROUND_GOAL mandatory
class (`mandatory:91,128`) исключает ACK, когда eligible обязательная цель
остаётся открытой. «Обязательно узнать» фактически становится «спросить сейчас».
ANSWER_USER всегда identity. Snapshot risk_level="none"; outer safety guards
нельзя заменить этим snapshot.

## C. KEEP / CHANGE / REMOVE

| Component | Решение |
|---|---|
| EngineState / Reducer / delivery outbox | KEEP; один authority; общие explicit plan commits вместо side effects legacy выбора |
| Understand/kernel/mission provider | KEEP evidence/subject guards; CHANGE producer parity, lost QA and current+severity binding |
| Episodes / QuestionNeed / observation memory | KEEP; sufficient evidence и допустимый unknown; не закрывать слот по акту/длине текста |
| DecisionRouter / ActionPolicy | CHANGE existing owners; сначала lifecycle, затем versioned legal-set extension; без второго scheduler |
| Discourse | CHANGE existing state: grounded entity refs, unresolved intent, willing continuation, suspend reason/return point |
| Product/protocol | KEEP required safety/consent/facts; CHANGE обязательность времени вопроса на constraints+utility |
| ResponsePlan / Renderer | CHANGE existing contract к meaning-only для migrated moves; REMOVE displaced ordinary string-plan producers |
| Banks | KEEP deterministic safety/control/fallback; постепенно REMOVE ordinary complete-question policy sources, а не размножать их |
| CallerMemory | KEEP как phrase-resolution cache, не autobiographical facts store |
| Cross-call memory | KEEP scoped Core snapshot; CHANGE ContextPack provenance: source/time/consent/validity per fact |
| TinyRanker/neuro helpers | Offline contracts/bench only; не рекламировать как live brain; подключать только после completeness/calibration |
| Retired composer | KEEP retired; B должен заменить renderer boundary после benchmark, не воскресить unsafe legacy speech path |

## D. TARGET ARCHITECTURE

```text
Understand → canonical accepted meaning → Reducer updates EngineState
 → existing ActionPolicy: generate candidates → hard constraints → LEGAL SET
 → existing scorer chooses ONE move → ResponsePlan (meaning + refs + obligation)
 → Reducer commits chosen obligation/target/identity, reserves delivery
 → ONE Renderer: deterministic realization OR eligible constrained surface
 → validate whole candidate → freeze canonical text → existing TTS/playout
```

Используем существующие ACK_ONLY, CLARIFY, ANSWER_USER, ASK_EPISODE,
BACKGROUND_GOAL, SUMMARY_CLOSE, GOODBYE_FINAL, SAFETY. FOLLOW_USER_THREAD уже
существует в ConversationObligation; ActionKind потребуется расширить этой
семантикой, не создать параллельный enum. WAIT — существующее action=none +
TimerEffect/listening obligation. Transition — параметры move, не ещё одна FSM.

Safety/consent/explicit stop/urgent и wrong subject — hard constraints.
Незаполненная неэкстренная required цель — utility debt и return point, не
автоматический запрет ACK/thread. До deferral нужна классификация critical need.
Unknown допустим. Уточнение выбирается, если его ответ меняет безопасное следующее
действие, с penalty repetition/burden и benefit accepted information.

Один utterance может удовлетворить несколько needs через existing observations
и QuestionNeed equivalence. Сначала canonicalize смысл, потом выбрать самый
полезный remaining need; нельзя объявлять факт из candidate confidence.

Thread обновляется существующим discourse внутри Reducer. Пользовательская
вовлечённость, вопрос, смена/исчерпанность темы и доступный mission return point
управляют продолжением. Count остаётся telemetry/аварийной границей, не главным
режиссёром. ACK без question требует listening timer: actor отменяет старый
timer при speech, generic ACK completion не ставит новый (`actor:2640`,
`reducer:624–646`). Иначе «поговорим» превратится в тишину.

ContextPack — read-only bounded projection: relevant delivered turns, grounded
thread entities, unresolved obligations, actual delivered question, episodes,
evidenced facts и consent-scoped dated memory, prohibited inferences. Не transcript
каждого звонка; не caller phrase cache. Existing flat prior dict теряет provenance
(`session:119–137`); модель не должна восстанавливать его догадкой.

### A / B / C

| Критерий | A: без live generation | B: optional constrained local surface | C: LLM full brain |
|---|---|---|---|
| Качество | Улучшает coherence/moves/clarification; не arbitrary free conversation | Потенциально шире; Russian phone listening NOT_RUN | Не доказано на продукте |
| M5 p50/p95/RAM | NOT_RUN; текущие STT/TTS/classifiers тоже требуют замера | NOT_RUN; модель ещё не выбрана | NOT_RUN |
| Generative use | 0 | Только eligible низкорисковые moves; ordinary health=0 | Практически каждый turn |
| Hallucination surface | Узкое, но ошибочный parser всё ещё опасен | Entities/numbers/relations/promises/medical meaning: нужен semantic veto | Наиболее широкое, state/control authority недопустимы |
| Complexity | Lowest additional cost; расширение существующих owners | Eligibility, ContextPack, completion validator, bounded queue/fallback/cancel | Большой orchestration/state-validation слой |
| 100 calls / цена | Не доказано | Не доказано; low average eligibility не устраняет burst/queue | Не доказано; нет причины выбирать |

B пока **proposed**, не выбранный checkpoint. Нельзя считать имя Qwen3-4B-4bit
в YAML benchmark. Existing `/render` отдаёт токены в speech до complete grounding;
legacy Validator — blacklist/length, не semantic equivalence. Whole candidate
должен пройти проверку **до** canonical/TTS. Модель не получает write/action/Core
authority. Completion timeout/invalid candidate → explicit deterministic fallback.

## E. MIGRATION CUTS

1. **Cut0:** extend existing comparison capture/metrics; freeze15 requested
   scenario types; paired legacy/shadow/policy and semantic state. No production
   behavior changes. Audio/slow/barge types are NOT_RUN until actual recording.
2. **Cut1a lifecycle:** move displaced pending-target/counters/ITS commits
   from legacy scheduler into reducer-owned plan application. Pure selector.
   SDK AND actor parity; valid/unknown/refused replies, stale/cancelled delivery,
   timers, policy error→one legacy fallback. No default cutover.
3. **Cut1b vocabulary/authority:** version existing policy (v10 proposed), add
   grounded thread projection and legal ACK/follow/resume alternatives; retain
   hard vetoes. Shadow→explained divergence→soft cohort→policy only with live proof.
4. **Cut2 thread:** existing discourse manages engagement/topic/resume, replace
   fixed-count ownership; clinical symptom interrupt retains deterministic priority.
5. **Cut3 clarification:** fix canonical multi-clause and QA admission first;
   required ≠ immediate; sufficient-evidence stopping and true unknown.
6. **Cut4 realization:** migrate meaning-only ResponsePlan and one renderer;
   morphology/referent/transition/anti-repeat with explicit supported meanings.
   Delete displaced ordinary full-string producers per ADR023.
7. **Cut5 B benchmark:** extend existing model bench cold/warm/repeated loads,
   RAM/RSS/MLX peak, p50/p95, bounded admission/cancel, Russian adversarial
   grounding and phone listeners. B optional only if measured cost/quality wins.

Каждый cut фиксирует старого/нового owner, deletion diff, paired evidence,
state/safety tests, actual invocation counts и latency либо NOT_RUN. Frozen v9
manifest10 core files не repin ради зелёного теста; изменения ядра требуют
объявленной версии/differential. Старую authority удаляем только после gate,
rollback git revert, не два параллельных writers.

## F. COST MODEL

Current actor per accepted turn: STT final; act classifier model-first;
kernel/mission/optional semantic fallback; relation shadow where eligible;
deterministic scheduler/renderer; TTS. No generative engine call. Prefix previews
добавляют work и не уменьшают final ASR. 300ms NLP budget проверяется **после**
compute (`model:131`), native inference нельзя обещать отменить мгновенно.

Для N calls, r turns/s/call, generative eligibility g: arrivals λ=N*r*g.
При k replicas со средним service time s пропускная граница ниже k/s с запасом
на burst/p95; все переменные измерить. Per-call B inference ≈ turns*g плюс
explicit retries. Стоимость = token/inference time + STT/TTS + amortization,
не только parameter count. RAM = loaded artifacts + KV/activation + queues;
маленькая модель не доказывает100 calls на одном M5.

Existing workers имеют max_workers1/queue4. Existing capacity_probe игнорирует
recognized text, использует fixed Session turns и fixed TTS acknowledgment:
это worker-load recipe, не100 real calls. Existing model bench имеет один warm
sample/model, не RAM/percentiles/concurrency несмотря на docstring. ActionPolicy
microbenchmark можно использовать для selector CPU, не для phone latency.

## G. RISKS / ADR DRIFT

* Policy authority теряет pending/ITS lifecycle; немедленный flag flip BLOCKED.
* SDK/live producers различаются; shape/field confidence не доказательство parity.
* Explicit current/severity и open QA имеют reproduced admission defects.
* ACK без timer может зависнуть. Wrong-subject/consent/urgent нельзя размягчать.
* Cross-call flat values не ContextPack provenance; actor model sees only scoped
  explicitly authorized facts, no inferred relationships or symptoms.
* Old call timeline записывает first marks only; opening может дать отрицательный
  stt→decision. Это НЕ per-turn end-of-user-speech→firstPCM.
* Missing/debug-filtered/truncated trace events — unknown, не нулевая latency или
  нулевые model calls. Transport ACK != услышанный звук.
* ADR020 composer cuts/interfaces historical/amended by025; 021 proposed banks
  и strict severity claims не полное описание нынешнего v9. ADR023 replacement
  law действует вместо blanket100call freeze. ADR024 ranker/proof primitives
  существуют, но live legal_set completeness/ranker отсутствуют. ADR025 «нет torch»
  historical: torch здесь есть, genuine model weights нет. ADR026 accurately
  bounded thread; изменять её count надо новым cut. ADR027 natural renderer
  unimplemented — актуально. Rollout docs v8 при config/manifest v9 — stale.
* candidate.py «classifier only fallback», neuro docstrings «wired shadow»,
  action_policy.__init__ «offline only» не соответствуют actual conditional callers.

## H. ACCEPTANCE TEST

Frozen suite включает 15 типов из задания: multi-facts, daughter story, yesterday,
user question, topic switch, topic return, not recalled, ambiguity, correction,
barge-in, slow speech, symptom-in-story, single-question refusal, global end,
just conversation. Text projections последних transport типов не их acceptance.

На replay: accepted evidence/subject, emitted vs delivered question IDs/needs,
question-only runs, repeated presentations с repair отдельно, multi-fact closure,
pending/ITS progression, answered user intent, thread→mission reasons,
explicit owner/stats. Topic jump — annotated human expectation, не substring
matching. Mission completion — backed by evidence, не только lifecycle SATISFIED.

На CallActor/FreeSWITCH: same audio/script/loaded SHA/providers/flags, full audio
+ JSONL with complete IDs. Questions/minute по реально delivered вопросам.
Per-turn acoustic end→endpoint→STT→decision→firstPCM→transport и actual audible
events, p50/p95; barge stops, slow speaker completion, no phantom delivery.
Модели: requested/started/completed/rejected by exact revision; per-turn/call
count, warm/cold service, RAM и concurrency arrival mixture. Blinded listeners
оценят questionnaire-feel/warmth/accuracy; не unit-derived score.

Promotion: no unexplained critical divergence, original safety/state gates
unchanged, no new clinical false evidence, one writer/scheduler, canonical==TTS,
safe rollback. Перечисленные reproduced defects являются blockers, а не
«незначительными» failures, которые можно убрать из acceptance.

### Audit evidence / next gate

Source audit выполнен по всем перечисленным в задании trees/ADR и relevant
dialogue/caring/realtime tests. 115 policy/router/shadow tests PASS; 10 frozen
source hashes match. Offline SDK counterexamples собраны с state/RichUserTurn
и fingerprints. NOT VERIFIED: actual loaded M5 flags/model throughput/voice,
audio/phone/human perception/Core ACK/100 call capacity/competitor execution.
Следующий блокирующий gate — reducer-owned authority lifecycle и SDK/actor
canonical parity перед любым soft/policy promotion; live baseline собирает M5
агент по существующим recording/forensic/handoff procedures.

## Cut0: выполнено после отчёта

Изменён существующий `tools/voice_lab/dialogue_comparison.py`, новый runtime
owner отсутствует. `run --decision-metadata` записывает read-only state, реальные
SpeakEffect/question IDs/генерации и simulated delivery; `metrics` использует
их, не punctuation. Metadata consistency проверяет effect↔transcript,
strict question boolean, delivered qid/phase/generation и конечные числовые
SDK durations. External telephone capture не выдаётся за SDK delivery.

Все 15 новых cases используют explicit short preset
`mandatory_background_goals=false`, coverage flag 0. Старый comparison suite
сохраняет свой full preset; actual per-case configuration записана. Preset не
представляется как observed M5 config. Barge/slow cases — text projections,
их аудио приёмка NOT_RUN. Raw source fingerprints совпадают с финальным tool.

[Baseline и команды](evaluation/conversational-move-baseline-2026-10-02/README.md)
содержат три attributable captures, actual transcripts и machine-readable
summary. Сокращены только неиспользуемые per-decision state поля; все captured
turn states/effects/understanding сохранены, raw hashes записаны. До/после
projection metrics совпадают; CLI повторно проверяет сохранённые captures.

| Проверка | Фактический результат |
|---|---|
| Same 15 input sequences/preset, legacy vs shadow | 0/15 изменённых response sequences |
| Legacy vs diagnostic policy | 15/15 изменённых sequences; не все различия ошибки, promotion не принят |
| Budget-return proxy | legacy 4 /shadow 4 /policy 0; это observed transitions, не human appropriateness score |
| Delivered episode question without pending attribute proxy | legacy 0 /shadow 0 /policy 8; нужны obligation/lifecycle исправления |
| Comparison + metadata integrity tests | 23 passed,1.06s; reviewer independently 23 passed,0.92s |
| Full `python -m pytest -q --tb=short` | 2502 passed /8 inherited missing-model failures /9 skipped,114.67s |
| `make lint`, `git diff --check` | PASS |
| `policy_diff_v8_v9 --stdout-only` | 4 expected /0 unexplained PASS; 10 frozen hashes unchanged |
| Existing selector microbench, 10,000 iterations | Linux x86_64 p50=.832ms /p95=1.305ms /p99=5.018ms; not M5/phone |
| Production/config/scripts bytes vs 09cff201 | All 331 tracked files unchanged; no flags/provider/scheduler switched |

Полный набор не зелёный: реальные v2/v3/polarity/xenc trained artifacts здесь
отсутствуют. Старые skips/expectations не менялись. Model microbench's existing
five-turn pipeline diagnostic тоже зелёный, но не проверяет chosen-plan commit
и потребление delivered ответа; его green не отменяет reproduced SDK loops.
Current-task содержит команды, review scope и операторскую передачу. Cut0
улучшает измеримость; речь на живом звонке им не изменена.
