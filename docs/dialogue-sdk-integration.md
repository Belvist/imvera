# Интеграция Dialogue SDK — руководство следующему агенту

Дата: 2026-10-01. Рабочая ветка: `feature/voice-zoiper-m5`.
Контракт: [ADR-025](adr/025-grounded-dialogue-sdk.md), границы обучения:
[ADR-024](adr/024-bounded-neuro-learning.md).

Тёплая манера: [ADR-026](adr/026-grounded-warm-dialogue.md).
`ResponsePlan.acknowledgement_kind` задаёт смысл реакции, а Renderer — текст.
`not_recalled` выставляется только после реального снятия вопроса как неизвестного;
`resume_mission` — при реальном возврате к приостановленной цели. Не добавляй
случайные «понимаю» в TTS/CallActor и не обещай выздоровление. При завершении
по control жалоба из той же реплики сохраняется через atomic apply, а вопрос
и ответы миссии из этого control-turn не добавляются.
Протокол сравнения и загрузки настоящих чужих транскриптов:
[elder-care comparison](research/elder-care-dialogue-comparison-2026-10-01.md).

## Связный разговор: интегрировать смысл, а не приставку к TTS

[Разбор и реальные текстовые ответы движка](live-calls/fs-2baf87ec-conversational.md).

- `temporal_answer` получает `acknowledgement_value` только из количества,
  которое принято в onset/duration этого эпизода. Чужие лекарства, планы и
  «не помню» не дают права произнести «это продолжается уже две недели».
- `strong_answer` / `tolerable_answer` отражают принятую severity, не общий
  model vote `answer`. Сильная боль не получает позитивного поздравления.
- Несколько активных жалоб соединяются из grounded labels. `body_site` не
  даёт права придумать симптом: головокружение не становится головной болью.
- На «не расслышала» сохраняется услышанный текст вопроса; на «уточните»
  объясняется тот же смысл. Не стирай delivered question обычным advancement,
  не заполняй clinical value/mission goal просьбой уточнить. Custom mission
  использует тот же reducer repair owner; question identity сохраняется.
- `bridge_text` и `question_text` — компоненты одной канонической реплики.
  Их разделение для журналирования не даёт TTS права заменять или дописывать
  текст. Не вставляй «понимаю» после urgent/control и не повторяй старые acks
  при объяснении нового вопроса.

`make test-dialogue-rich` включает проверки `test_dialogue_warmth.py` и
`test_conversational_continuity.py`; полагаемся на специализированный CI job
даже когда общий job не может собрать модельное окружение.

## Обычный ответ, понятное пояснение и выбор порядка

[Причины, исправление и ограничения](live-calls/fs-2baf87ec-adaptive.md).
Kernel распознаёт ограниченные endurance-ответы и связывает degree-only
продолжение только с единственным доказанным владельцем. Не переносить это
на «терпеть соседей» или неопределённость. Repair объясняет степень простыми
словами, сохраняя delivered question_id/need и не заполняя ответ.

Явная просьба «давайте сначала про руки» получает question-act и REFERS_TO
на одну известную открытую жалобу говорящего. Это не observation о здоровье
и не ответ на прежний вопрос. Scheduler проверяет цель, кладёт прежний эпизод
в существующую очередь, сохраняет факты и custom suspended_obligation.
Неизвестная/неоднозначная тема не создаёт симптом. Не трактовать сравнительное
«лучше про...» как улучшение состояния. Safety/control и бюджет вопросов
имеют прежний приоритет; административное завершение не означает выздоровления.

Совпадения body_site недостаточно для владельца атрибутов: боль и дрожь
хранятся отдельными эпизодами. Ingest, observation binding и recap используют
тот же clinical_issue_concept, сохраняют цитаты и отделяют другого человека.
Синонимы боли не создают дубликат; «ещё болит» без места не наследует старую
локализацию. Legacy fallback не должен превращать першение/дрожь в «болит».
Kernel repair не переопределяется голосованием модели ANSWER; applied=false
и deterministic_repair_wins должны остаться в трассе.

## Реакция на полный ответ и завершение

[Все реплики до/после и передача на стенд](live-calls/responsive-dialogue-2026-10-01.md).
Полный ответ и новый симптом перед summary получают реакцию по принятому
speaker-эпизоду с evidence текущего хода. Для этого не создаётся новый вопрос.
«Давайте по порядку» допустимо, когда действительно запланировано уточнение.
Сравнение severity допускает конечную пунктуацию; сохранённая цитата не меняется.
`current_relief` разрешён только для confirmed observation текущего хода:
subject=speaker, attribute=current, value=resolved, совпадающий episode_id
и принятое current=resolved. Статус завершения опроса или «лучше про работу»
не доказывают улучшение. Чужие симптомы не дают реакции об улучшении собеседника.
Summary проходит Renderer; bridge_text и question_text уже составляют text.
Не добавляй ACK повторно в озвучку и не создавай второе прощание.
Личная история использует существующий open_hook один раз и приглашает
рассказать подробнее без принуждения. Safety/control/repair имеют прежний приоритет.
`make test-dialogue-rich` теперь включает test_responsive_dialogue.py и
три проверки тёплых реплик вашего агента из test_speech_warmth_live.py.

## Живой clarification-loop: обязательные границы

Разбор и повтор звонка `fs-2baf87ec`:
[исправление](live-calls/fs-2baf87ec-fix.md). Проверки включены в
`make test-semantic-kernel`, а не только в полный suite.

- `body_site` — ключ памяти; не ставь единственное число леммы перед
  множественным глаголом при формировании spoken label.
- Слова «нормально/лучше» принадлежат своей части фразы. Еда и сон не
  закрывают жалобу из следующего предложения.
- Пустые `issue_mentions`/`goal_facts` не означают «нет ответа»: consumer
  pending-attribute читает `raw_text`, observations и реальную цитату.
- «Это» — ссылка на эпизод, а не временное значение. Количество «две недели»
  сохраняй как duration даже при другом вопросе, без выдуманной severity.
- Slot classifier и personal phrase memory дают кандидат `answer`, а не
  clinical value. Quote/raw_text нельзя записывать в onset/duration/severity
  без проверки смыслового типа и владельца. Отвергнутый кандидат не учит
  память. Reference fallback не должен обходить эту проверку.
- Новый симптом снимает старый pending coverage filler до раннего return.
  Длительность боли не может заполнить предыдущий вопрос о еде.
- Завершение опроса эпизода не стирает жалобу и не означает выздоровление.
  Уже записанная жалоба останавливает общий повторный concern probe;
  новое неопределённое ухудшение и safety сохраняют право на уточнение.
- Одинаковая локализация не делает боль и дрожь одним симптомом. Сохраняй
  обе цитаты. Не исправляй неясное «кровят» в диагноз: исходная фраза
  сохраняется в evidence, значение требует исходного аудио/уточнения.

После обновления кода агент на стенде проверяет SHA, readiness и горячие
модели, затем повторяет звонок через 7000. Новый trace должен подтвердить
смысловые данные, одну реплику за ход, canonical == TTS и завершение звонка.
Текстовый replay не заменяет эту проверку.

## Что пользователь разрешил и чего требует

В живом разговоре **нет генеративной LLM**. Модели выделяют смысл и предлагают
типизированные кандидаты. Движок принимает факты, выбирает следующий шаг,
составляет каноническую реплику и отдаёт её TTS. Примеры разговоров служат
проверками и обучающими данными, а не таблицей «запрос → готовый ответ».

Старый `IMVERA_COMPOSER_BRIDGE` больше не включает генерацию: runtime composer
удалён. SDK доставляет проверенный текст движка непосредственно в TTS.
`bridge_llm_allowed` оставлен только для чтения старых сериализованных эффектов;
он не даёт разрешения на переписывание. Offline surface validator находится
в `tools/voice_lab/bridge_gate.py`, а не в production voice_runtime.

CI differential требует полной Git-истории: `policy-diff` читает v8 из
`c0fa158b`, поэтому checkout этого job должен использовать `fetch-depth: 0`.
Не исправляй отсутствие исторических объектов изменением ожидаемых policy deltas.

Один звонок → один DialogueEngine/EngineState. Владельцы:

```text
STT → SemanticKernel + MissionUnderstandingProvider + act/polarity candidates
    → TurnUnderstandingV2 → RichUserTurn
    → reducer / atomic_semantic_apply → EngineState
    → conversation_policy / mission_flow → ResponsePlan
    → render_response_plan / validator → SpeakEffect
    → CallActor / playout → completed/cancelled event
    → persistence projection → Core
```

Не создавай второй обработчик диалога в приложении, SIP, webhook или SDK-адаптере.
Core владеет публичным вердиктом; `candidate_family_status` не является его ack.

## Задача приложения — данные CallMission

```python
from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.mission import CallMission, GoalDefinition

mission = CallMission(mission_id="shopping", goals=(
    GoalDefinition(
        goal_id="items",
        description="Узнать, какие продукты нужно купить",
        prompt_hint="Какие продукты вам купить?",
        answer_type="free_text",
        allowed_values=(),
        semantic_scope="general",
        priority=10,
        max_attempts=2,
    ),
))
engine = DialogueEngine(call_id="call-1", mission=mission)
```

`description`, aliases, semantic_hints и allowed_values описывают требуемый
смысл/схему ответа. Они не выбирают реплики по совпадению примера. Для вопроса
о симптомах явно укажи `semantic_scope="speaker_health"`. Для enum/bool
используй проверяемые категории и allowed_values. Free text — буквальный
фрагмент цитаты, а не медицинский вывод или пересказ модели.

По умолчанию используется действующий детерминированный провайдер. Новый
семантический классификатор подключается через уже существующий
`MissionUnderstandingProvider.understand(MissionUnderstandingRequest)` и
constructor DI `mission_understanding_provider=provider`. Провайдер получает
снимок миссии/доставленного вопроса/контекста и возвращает
`StructuredMissionResult`, без доступа к изменению EngineState. Каждому ответу
нужны реальный goal_id, разрешённое значение, confidence и цитата текущего хода.
`mission_grounding` проверяет кандидатов перед изменением состояния.

## Модельный act должен попасть в канонический ход

Для адаптера, который выполняет распознавание act без генерации текста:

```python
candidate, confident, proposal_trace = nlp_candidate_turn(
    engine.pending_question_text() or "", text, engine.answer_context_slot(),
)
turn = engine.build_rich_turn(
    text, utterance_id=utterance_id,
    act_candidate=candidate, candidate_confident=confident,
)
engine.on_user_turn(utterance_id, text, rich_turn=turn)
```

Импорт `nlp_candidate_turn`:
`packages.dialogue_engine.semantic_nlp.candidate`. В production CallActor
уже выполняет inference и `apply_act_candidate`; не вызывай модель второй раз.
Для подробного trace используй `TurnUnderstandingV2.resolve`, возвращающий
ResolvedTurn. `apply_act_candidate` возвращает `(turn, applied, reason)`.
Логируй proposal и фактическое применение раздельно. В CallActor это
`interpret.nlp_candidate: proposed / used / resolution_reason`.

Предложение модели не может убрать факт о боли, отменить детерминированный
отказ/согласие/опасность, придумать значение слота или самостоятельно
попрощаться. `ANSWER` — тип хода, а не доказательство ответа именно на
доставленный вопрос. На yes/no вопрос «ага» остаётся ответом.

## Голосовой runtime и Realtime v1

[Передача на стенд, сравнение PCM и следующие этапы](realtime-conversation-v1.md).
Barge-in принадлежит CallActor/PerceptionSession, не Renderer. Generation
инвалидируется и останавливается до медленных внешних отмен/хранилища.
Не повторять ACK и не считать отменённый вопрос доставленным. Не выдавать
ESL +OK за слышимую остановку. Защищённые opening/identity/consent политики
сохраняются. Current STT final-only; transcribe_partial даёт явную ошибку,
а не фиктивный пустой partial. Partial будущего ASR — кандидат, не State fact.
Тёплая инструкция TTS уже есть; изменение её текста не доказывает качество
интонации. Генеративный live Renderer этим этапом не восстановлен.

## События доставки обязательны

После `start()` и каждого `on_user_turn()` забирай эффекты из outbox. SpeakEffect
содержит единственный текст для TTS, generation и question_id. Вызывай
`on_playout_started`, `on_playout_completed`, `on_playout_cancelled` по реальным
событиям. Не считай создание текста его доставкой. Не устанавливай
DELIVERED в момент запуска TTS и не подтверждай отменённую генерацию.
CallSession/CallActor уже реализуют эту проводку; приложение обычно
интегрируется через них, а не заменяет их собственной очередью.

Жалоба может прервать любую миссию. Работает общий планировщик эпизодов;
после уточнений возобновляется незавершённая цель. Ответ на время боли не
становится ответом на приостановленный вопрос о продуктах. Полный ответ,
данный сразу вместе с жалобой, сохраняется и не спрашивается заново.

«Не помню» означает недостающую информацию. Episode.unanswered_attributes
хранит цитату отдельно от known_attributes, а вопрос повторно не задаётся.
Это не отрицание боли и не разрешение поставить GREEN. Новые реальные
данные имеют приоритет над записью о прежнем незнании.
Если enum-схема явно разрешает значение `unknown`, оно сохраняется как
типизированный ответ с цитатой; act-модель не превращает его в пропуск цели.

## Проверки перед следующим изменением

```bash
python -m pytest tests/test_dialogue_sdk_grounded_progress.py tests/test_dialogue_sdk_act_resolution.py -q
python -m pytest tests/ -q
python scripts/dialogue_corpus_gate.py
python scripts/hard_battery.py
python scripts/agent_dialogue_gate.py
python tools/voice_lab/policy_diff_v8_v9.py
python -m ruff check packages services tests scripts tools
python scripts/dialogue_sdk_demo.py --json
```

Сопоставляй те же входы до/после и описывай каждое изменение. Не ослабляй старые
тесты. `dialogue_sdk_demo` печатает фактические реплики движка на синтетических
входах; это текстовая симуляция без качества моделей и телефонного аудио.

## Рост качества и масштаба

Следующая модель нужна для отношения «клауза → цель/атрибут/субъект», с
abstention на постороннем ответе. Act classifier эту задачу не решает.
Нынешний guard свободного текста распознаёт health interruptions; универсальная
релевантность произвольным задачам ещё не доказана. Сначала собери ошибки и
разметку на новых формулировках, раздели train/eval по людям/звонкам, проверь
precision ложного закрытия, recall, ложные safety/consent решения и p95 на
целевом железе. Не поднимай текущий shadow cross-encoder в authority по
маркетинговым обещаниям или порогу без такой проверки.

ADR-024 допускает будущий нейроранкер только внутри полного легального набора
действий. Он не пишет State и не владеет безопасностью. Proof chain должен
связывать decision → utterance → response → delayed outcome. Сейчас не
публикуй incomplete monitor с `legal_set_complete=False` как обучение с
подтверждённым улучшением.

Для масштаба сохраняй изоляцию EngineState и порядок событий одного звонка.
Модели прогреваются до readiness; нагрузка ограничивается очередями и admission,
а ресурсы inference масштабируются отдельно от звонков. Не клонируй encoder
для каждой сессии и не добавляй загрузку весов/HTTP/БД в новый шаг SDK.
Нынешний synchronous inference на event loop и лимиты voice-m5 требуют
отдельного измерения. Эта правка не доказывает 100 или 100000 аудиозвонков.

## Перед демонстрацией по телефону

Нужны реальные веса `semantic_nlp/v2`, `xenc_v3`, `polarity_v1`, PyTorch,
успешный warmup и точное совпадение SHA в мосте. Прогонять 5 сценариев из
`dialogue_sdk_demo` и safety/barge-in через SIP; проверить canonical == played,
единственное прощание и end-to-end p50/p95. Linux review workspace этих
артефактов и подключённого Mac/Zoiper не имеет: live acceptance NOT VERIFIED.

Отдельный открытый контракт: daily snapshot `partial` и candidate status
используют разные admission предпосылки. Подключи настоящие доказательства
identity/согласия самого человека/can_talk из Core; не исправляй расхождение
записью выдуманного согласия из факта завершения звонка.
