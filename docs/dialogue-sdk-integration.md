# Интеграция Dialogue SDK — руководство следующему агенту

Дата: 2026-09-30. Рабочая ветка: `feature/voice-zoiper-m5`.
Контракт: [ADR-025](adr/025-grounded-dialogue-sdk.md), границы обучения:
[ADR-024](adr/024-bounded-neuro-learning.md).

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
