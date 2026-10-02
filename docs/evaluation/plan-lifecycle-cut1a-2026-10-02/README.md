# Cut 1a: общий исполнитель выбранного вопроса

База: `00b992d3901767bf678cd28ce2d7fb6461786632`,
`feature/voice-zoiper-m5`. Получены изменения агента, включая настоящие
обученные heads. Main и действующие сервисы не изменялись.

## Что изменено

Раньше legacy `_episode_plan` записывал pending attribute и плановый бюджет
эпизода при выборе вопроса. Pure ActionPolicy возвращал такой же смысловой
план без этих записей. В результате ответ не привязывался к вопросу.

Теперь смысл (`episode_id`, `QuestionNeed`) проходит через ResponsePlan и
compatibility adapter в существующий Question. Reducer `_emit_speak` вызывает
один `_commit_emitted_question` после успешного резервирования вопроса.
Записи из legacy selector удалены; оба scheduler используют одного исполнителя.
Тот же исполнитель записывает существующее ITS obligation; terminal reply
потребляется в общем Reducer, включая ранние и прерванные ответы.

Начальная попытка ждать PlayoutCompleted для pending была отвергнута ревью:
она теряла «С утра» во время озвучки и преждевременно завершала разговор.
Итоговый cut сохраняет исходный timing контекста ответа. Он **не меняет**
исторические `_product_asked` в доказательство услышанной речи: это плановый
бюджет pack. Факт доставки по-прежнему определяется Question.phase,
PlayoutCompleted и goal.delivered_attempts. Отмена/незавершённая озвучка
не увеличивает delivered_attempts и не создаёт клинических значений.

Cancellation дополнительно проверяет question_id: событие другого вопроса
с той же generation не очищает текущий playout. Пустой ID сохраняет прежний
compatibility contract.

Изменены только существующие state/conversation_policy/reducer и checkout
полного CI job (`lfs: true`). Ни второго scheduler, ни второго state/reducer,
ни новых phrase banks/моделей/provider, ни изменения default flags.
Frozen v9 core не переписан и не переприкреплён. Policy не включён в звонках.

## Воспроизводимые проверки

```bash
PYTHONPATH=. python -m pytest -q --tb=short tests/test_response_plan_lifecycle.py
PYTHONPATH=. python -m pytest -q --tb=short
PYTHONPATH=. python tools/voice_lab/policy_diff_v8_v9.py --stdout-only
make lint
git diff --check
```

26 новых lifecycle cases проверяют completed/early/cancelled ответы в
legacy/shadow/policy, identity/generation/revision, повторный completion,
grounded temporal/severity и доставленные попытки. Старые assertions/skips
не изменялись. Focused набор: **237 passed, 1.90 s**. Независимый review:
**55 passed, 0.49 s**, APPROVE только для узкого общего executor scope.
Frozen differential: **4 expected / 0 unexplained**, gate PASS.

Full-suite результат и paired captures записаны в соседнем summary.json.
Отдельно есть attributable transcripts, source fingerprints, states/effects
и фактические параметры replay. SDK timing исключает STT/TTS/аудио/очереди.
Отсутствующие показатели не подменяются нулями.

| Измерение | Результат |
|---|---|
| База с настоящими heads | 2508 passed / 2 failed / 9 skipped, 137.42 s |
| Итоговый полный прогон | 2534 passed / 2 failed / 9 skipped, 134.25 s |
| 15 одинаковых inputs, legacy до/после | 0 изменённых response sequences |
| Diagnostic policy до/после | 4 изменённых cases; не автоматическая оценка человечности |
| SDK legacy wall time p50/p95 | до 2.527/10.289 ms, после 2.435/38.516 ms |
| SDK policy wall time p50/p95 | до 2.445/13.286 ms, после 2.458/6.175 ms |

Timing — 42 samples в каждом replay, без контролируемого performance benchmark;
вариация p95 не доказывает ускорение или отсутствие замедления. Phone latency
и model invocation count NOT_RUN. Новых model calls в executor не добавлено.
[Транскрипты policy до/после](policy-before-after.md) показывают фактические
ответы; [summary.json](summary.json) содержит inputs/config equality и checks.
В частности, после «Нет, больше ничего» повтор ITS сменился summary; после
«Терпимо» accepted severity больше не спрашивается повторно. В обычном legacy
эти завершённые ответы уже работали — их речь этим cut не улучшена.

## Модели

Настоящие `v2`, `v3`, `polarity_v1` загружаются; шесть прежних ошибок закрылись.
`xenc_v3/heads.pt` также получен. Encoder в Git LFS имеет SHA256
`560fb3342f1d837ef68383982d963c4a8853594427dbdaf7260f0935abba62c7`,
596070136 байт. В этой среде `git lfs pull` вернул login-attempt error,
прямая authenticated batch — HTTP 403. Локально остался указатель, поэтому
два all_hot/readiness теста не проходят. Причина отказа LFS здесь не установлена.
Файлы агента/weights не заменялись, fallback encoder не подставлялся.

Полный CI job теперь запрашивает LFS при checkout: опубликованного pointer
недостаточно для safetensors loader. Успех скачивания CI проверяется отдельно.

## Передача агенту на M5

1. Получить итоговый m5 commit, сохранить действующий конфиг и модельные hashes.
   Проверить `git lfs pull` и **байты/SHA256**, затем all_hot/readiness. Не
   пересоздавать trained heads или заменять локальный encoder базовой моделью.
2. Bridge автоматически этим push не обновляется. Применить существующую
   процедуру [handoff](../../production-dialogue-handoff.md) для Python-кода;
   FreeSWITCH/БД не пересобирать ради этого изменения. Зафиксировать loaded SHA.
3. Сохранить действующий режим выбора хода. Не включать policy/soft cohort:
   sparse legal set, personal thread и SDK/Actor parity ещё не приняты.
4. Записать живые completed/early/interrupted clinical и ITS replies:
   одинаковый input, generation/question IDs, accepted quotes, pending need,
   actual playback ledger/audio и первый PCM. SDK cancellation не доказывает
   реальную акустическую обработку перебивания.
5. Следующий архитектурный cut — canonical producer parity и legal-set/thread
   evolution существующего ActionPolicy. Compound consumption, global-stop и
   открытые user questions остаются отдельными известными дефектами.

CHANGED: общий reducer executor и cancellation identity; CI LFS checkout.
VERIFIED: указанные SDK/state/gate проверки и paired captures.
NOT VERIFIED: actual M5/CallActor/FreeSWITCH/audio, human warmth, model/phone
latency, generative throughput/100 calls. Runtime модели на M5 неизвестны.
REMAINING RISKS: producer parity, legal-set completeness, compound needs,
семантические дефекты и неполученный здесь encoder. Generic policy ACK timing
и свободная тема этим cut не исправлены.
NEXT GATE: loaded M5 regression recording и canonical producer parity до
изменения authority. Этот cut исправляет lifecycle; анкета пока не устранена.
