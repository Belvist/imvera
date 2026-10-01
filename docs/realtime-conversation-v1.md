# IMVERA Realtime Conversation v1 — передача агенту

Дата: 2026-10-01. Ветка: feature/voice-zoiper-m5. Первый этап: база d9e24f6, опубликованные исправления 98e1a7c/fbff72c. Продолжение: ограниченные STT prefix previews поверх fbff72c. Живое принятие ещё не выполнено.

## Что означает «как у Newo»

В [публичном описании Newo](https://newo.ai/platform/newo-zero-hallucination-architecture) модель занимается языком, отдельный слой — подтверждёнными данными, следующим шагом и разрешёнными действиями. Newo описывает Observer/Supervisor и прямо говорит, что ошибки не исключены. Проценты готовности IMVERA и конкретные настройки чужого realtime из этой статьи не следуют.

У нас остаются один DialogueEngine, доказательные факты, Renderer и управляемая доставка. Это похожее разделение ответственности, но одинаковое звучание пока не измерено. Для записи конкурента анализировать язык, темп, длину пауз, перебивания и характер ответа; не клонировать голос по умолчанию.

## Фактическое состояние компонентов

| Компонент | Состояние в этой m5 | Следующая проверка |
| --- | --- | --- |
| Endpointing | Исправлен повторный hold; сохранён post-roll и возобновление речи | Запись медленной речи и пауз 300/500/700 мс через 7000 |
| Barge-in | Исправлены порядок остановки, политики и фазы; существующий флаг по умолчанию 0 | Echo + break ACK + слышимая остановка на стенде |
| STT partial | Реальный opt-in prefix_batch через тот же backend; default OFF, native_streaming=false | Сравнить нагрузку и final latency на M5; для stateful streaming нужен отдельный benchmark checkpoint |
| TTS streaming | Существующий streaming PCM сохранён; первый chunk измеряется до transport send | Фактический TTFT, RTF и прослушивание |
| Естественный Renderer | Канонический детерминированный Renderer; генеративный composer не восстановлен | Отдельное решение владельца о generative LLM и проверка её границ |
| Prosody | Уже есть warm instruct, speed=0.95, streaming_interval=0.16 в конфиге | A/B одной фразы на одном железе, минимум 3 слушателя |
| Control | Без смены владельца фактов, safety/consent/действий | Имеющиеся safety/consent/canonical gates + live trace |

## Первый этап: что заменено и почему

VAD уже наблюдает 500–650 мс тишины. Раньше сборщик после этого ждал ещё свой hold=500 мс и post-roll=150 мс. Теперь накопленная тишина передаётся в тот же сборщик и считается один раз. Фреймы по 20 мс округляют post-roll до 140 мс. Порог самого VAD не уменьшен. При возобновлении внутри хвоста уже собираемый сегмент сразу принимает акустическую речь, пока VAD подтверждает новый onset.

При перебивании сначала инвалидируется generation, отменяется локальная очередь и запрашивается остановка транспорта. Отмена запроса LLM и фиксация outbox идут после этого. Поздние PCM старой generation не проигрываются заново; одна уже переданная сокету race-frame может остаться, это отдельная граница транспорта. Защищённые opening/identity/consent политики не обходятся флагом. Эхо не считается голосом пользователя.

bargein_detected идёт до stop, пользовательская фаза восстанавливается после отмены. Команды cancel/stop ограничены по 250 мс каждая, сбой записывается. ESL +OK не является доказательством тишины в трубке; audible_stop_verified=false. Первый PCM TTS и первая успешная отправка в транспорт теперь измеряются отдельно. Публичный histogram читает настоящий stage.timing/timeline формат; он остаётся отчётом первого звука звонка, а не p95 всех ответов.

## Сравнение одинакового PCM

Инструмент: tools/voice_lab/realtime_pcm_probe.py. EnergyVad, CPU Python, 16 кГц PCM16, фреймы 20 мс, два тона и тишина. ASR, neural VAD, TTS, FreeSWITCH и конкуренты не запускались. Время — число входных фреймов, не wall-clock inference.

| VAD silence | Пауза внутри фразы | До: последний voiced frame → STT submission | После | Изменение | Фраза сохранена |
| --- | --- | --- | --- | --- | --- |
| 500 мс | 0 мс | 1120 мс | 640 мс | -480 мс | да, один сегмент |
| 500 мс | 100 мс | 1120 мс | 640 мс | -480 мс | да, один сегмент |
| 500 мс | 300 мс | 1120 мс | 640 мс | -480 мс | да, один сегмент |
| 500 мс | 500 мс | 1120 мс | 640 мс | -480 мс | да, один сегмент |
| 650 мс | 0 мс | 1280 мс | 800 мс | -480 мс | да, один сегмент |
| 650 мс | 100 мс | 1280 мс | 800 мс | -480 мс | да, один сегмент |
| 650 мс | 300 мс | 1280 мс | 800 мс | -480 мс | да, один сегмент |
| 650 мс | 500 мс | 1280 мс | 800 мс | -480 мс | да, один сегмент |

Восемь input_sha256 совпадают. Сокращение 480 мс доказано на этом PCM, а не обещано для SIP/нейромоделей.

| Файл | Before SHA256 | After SHA256 |
| --- | --- | --- |
| packages/voice_runtime/call_actor.py | `148eb06ecd21d33984d373ec16589a9948b58fe430fce2f72e139bde5ca6899f` | `36afda694eb70ef035b7b64fff231b80d3ee4298655f5c05f6792471aa42f64f` |
| packages/voice_runtime/utterance_builder.py | `005aa8068f1941fd1395a811ba3da8b7448dbf75900b64bb805acd4c6ae5d1d1` | `74a9ff8a9314fba8f14dc701d3f5edd24d01659a1967ccb97d4cfeed9f228fec` |
| packages/voice_runtime/vad.py | `c84e1d940a2c13ca8031abb0ff2964b510c321557b7fff6970821ebf25f0feb1` | `a080743939f4675a57b968c4bb2b7d1e380a2471011d34bdaeaba28dd204e05d` |
| packages/voice_runtime/silero_vad.py | `f3dc7a420f6e37aeed2d963da2b8862601c24aa8bec0d1377925de68e91707f8` | `36a0038f54f188579aa59e0026f3426fe2c6adf507bf1bc93b53b007e1a00164` |
| services/stt/http_provider.py | `a2547a9c0ff10e4f680b975f2975d6d4ed3dc526809440d303e132401060e762` | `afaee571e0e43665965852dcfa44ea3c1d68ac45a13565259c5c505131eaf0b2` |
| tools/voice_lab/latency_histogram.py | `c39ca7875e6bda57c221b555064785f5380a0a5e6c0be05e2a36ffc9e83c8510` | `a45fc1d46a30d512536fb6d95eec304fcaa47063332afb4a60b436128bf54a14` |

Повтор:

```bash
PYTHONPATH=. python tools/voice_lab/realtime_pcm_probe.py --output /tmp/realtime-pcm.json
make test-dialogue-runtime test-dialogue-rich test-semantic-kernel lint
python scripts/dialogue_corpus_gate.py
python scripts/hard1000_gate.py
python scripts/hard_battery.py
python scripts/agent_dialogue_gate.py
python tools/voice_lab/policy_diff_v8_v9.py --stdout-only
```

## Следующий gate: настоящий разговор на Mac/7000

1. Fetch m5, проверить SHA дерева/процессов, STT/TTS endpoint и model_revision, warmup/readiness, codec, реальные feature flags. Отсутствующий LLM worker допустим при нынешнем режиме без generation.
2. На тестовом стенде использовать существующие IMVERA_LAB_HALF_DUPLEX=0, IMVERA_ECHO_REF_GATE=1, IMVERA_LAB_BARGE_IN=1 и IMVERA_OBS_MODE=debug. Сначала снять baseline с barge_in=0, затем включить 1 для того же набора звонков. Это не изменение production по умолчанию.
3. После обычного вопроса перебить в середине ответа полноценной фразой; отдельно проверить эхо, короткое «угу», шум, ранний ответ, поправку и продолжение после паузы. Opening/identity/consent остаются защищены. Проверить late chunks, следующий generation, один вопрос и правильного владельца атрибута.
4. Снять JSONL и двустороннее аудио. Сопоставить generation, bargein_detected, transport.cancel, local purge и настоящий последний downlink sample. Измерить слышимую остановку, не только ESL ACK: целевой p95 <250 мс. Ошибка/timeout означает gate fail, а не обещание успеха.
5. Для каждого ответа измерить конец пользовательской речи → endpoint → stt.final → решение/канонический текст → первый PCM → реальный первый downlink. Полные turn p50 <1с / p95 ≤2с — целевой gate, здесь не проверен. Opening histogram не заменяет этот замер.
6. Одни и те же фразы прослушать с минимум 3 слушателями: ясность, спокойствие, паузы, темп, вопросительная интонация. Запись конкурента должна иметь источник и одинаковый сценарий для измеренного сравнения.

## Проводка отмены до единственного SDK

Дополнительная правка поверх первого опубликованного коммита 98e1a7c:
CallActor передаёт отмену в существующий CallSession.cancel_playout_action
после остановки аудио, очищает pending delivery для этой generation.
Иначе SDK effect оставался STARTED, playing/planned question — открытым,
несмотря на остановку PCM. Никакого нового владельца состояния нет:
событие PlayoutCancelled обрабатывает существующий reducer.

Session сохраняет адрес терминального CANCELLED effect в существующем
outbox-индексе. Позднее событие completion находит этот статус и не может
выдать отменённый вопрос за доставленный. Повторная отмена идемпотентна.
При уже отправленных семплах persistence остаётся DELIVERY_UNKNOWN;
при нулевых — CANCELLED. Отмена не удаляет прежнюю delivered question.
Два SDK/runtime теста падают на 98e1a7c и проходят на конечном коде;
проверяют следующий содержательный ход и новую generation, а не только флаг.
Runtime CI включает их, STT preview-срез и HTTP/WAV probe; всего 137 runtime-проверок.

## Второй этап: промежуточное распознавание без ложной финальности

Текущий GigaAM v3_e2e_rnnt принимает полный WAV. Исследован публичный
[model.py](https://github.com/salute-developers/GigaAM/blob/7447938d791c4f3e643386ee22c33777004293a5/gigaam/model.py),
[encoder.py](https://github.com/salute-developers/GigaAM/blob/7447938d791c4f3e643386ee22c33777004293a5/gigaam/encoder.py)
и decoder.py той же ревизии: полноконтекстный encoder, нет корректного
интерфейса продолжения. Сохранение только RNNT decoder state не превращает
его в streaming. Установленную на Mac ревизию библиотеки дополнительно сверить.

Добавлен существующий контракт transcribe_partial → POST /v1/preview.
Тот же выбранный backend действительно распознаёт накопленные PCM-префиксы
1/2/4/8 секунд. Это **prefix_batch, не stateful streaming**: максимум четыре
попытки / 15 секунд суммарного дополнительного аудио на utterance. Одна
задача preview в CallActor; занятые checkpoints пропускаются, не копятся.
Воркер атомарно принимает preview только при пустом executor; HTTP 429
не вызывает retry на другом replica. Внешний endpoint ограничивает размер
префикса; лимит четырёх попыток обеспечивает CallActor, это не rate limiter
для произвольного внешнего клиента.

GET /v1/capabilities сообщает partial_mode, native_streaming=false,
revisable=true, final_required=true, checkpoints и model_revision.
STT_PARTIAL содержит utterance_id, segment_seq, preview_epoch, partial_id,
model_revision, duration_ms и время запроса. Получатель заменяет прежний
preview; после final/отмены старого сегмента его не использует. Это только
наблюдение для трассы. Не передавать partial в SemanticKernel, State,
question ledger, согласие, клинические факты, Core verdict или TTS.

Endpoint/reset/disconnect/начало озвучки сначала инвалидируют epoch и
отменяют preview. Итоговый запрос не ждёт его HTTP cancellation. Даже
провайдер, игнорирующий отмену, не может поздним результатом изменить
состояние или породить STT_PARTIAL старого сегмента. Проверяются identity,
mode, finality и двухсекундный бюджет. Итоговый запрос всегда распознаёт
полный сегмент; non-final результат с final endpoint отклоняется.

Исправлена отдельная ошибка STT cancellation: WAV создаётся и удаляется
внутри синхронной inference-задачи. HTTP отмена больше не удаляет файл,
который модель ещё читает. Отменённая/просроченная задача в очереди не
открывает WAV и не запускает модель; результат отменённой работающей
задачи отбрасывается. Провайдер отправляет адресную best-effort отмену и
относительный timeout_s: monotonic часы разных хостов не сравниваются.
/health/ready теперь показывает настоящую очередь executor.

**Включение только на стенде:** IMVERA_STT_PREVIEW=1 должно быть явно
задано и воркеру STT, и bridge. Default 0 сохраняет прежний final-only путь.
Сначала получить /health/ready и /v1/capabilities с фактического STT URL.
При выключенном воркере capabilities=unsupported, preview — явный 503;
итоговый запрос продолжает работать. Новый флаг не включает barge-in.

Prefix previews не сокращают работу final ASR. Уже работающий PyTorch
не останавливается отменой HTTP и может задержать итоговый запрос.
Поэтому не включать режим для живых пользователей на основании этих
тестов. На M5 сравнить 0/1 на одинаковых записях: RTF каждого prefix,
STT final и whole-turn p50/p95, CPU/RAM, очередь и поздние результаты.
Сравнить отрицание «болит… нет, не болит», паузы, длинную речь, эхо,
согласие/отказ и перебивание. До этого latency/capacity/warmth NOT VERIFIED.

Офлайн: 28 новых контрактов; пять cancellation/deadline/WAV/health случаев
падают на неизменённом fbff72c. HTTP ASGI provider → worker выполняет WAV
путь с тестовым backend; реальный SDK не меняется от preview с жалобой,
согласием и отказом, а итоговое прощание закрывает звонок. Это проверка
протокола/владения, не качества GigaAM или физического звука.

Парный инструмент для того же backend:

```bash
python tools/voice_lab/stt_preview_probe.py /absolute/path/elder.wav \
  --stt-url http://127.0.0.1:9101 \
  --worker-hardware 'M5, actual CPU/RAM and PyTorch device' \
  --worker-revision 'verified active Git/image SHA' \
  --runs 30 --output /absolute/path/stt-preview-paired.json
```

Подставить фактический URL и проверенные данные воркера. STT worker должен
рекламировать prefix_batch; bridge для этого probe не вызывается. WAV —
mono PCM16, 16кГц, 1–20 секунд, одна и та же запись на обеих сторонах.
Скрипт чередует порядок 0/1, подаёт checkpoints во время реального времени
исходной WAV и запускает одинаковый final на её конце. JSON содержит
input/source hashes, модельную ревизию, количество/ошибки preview,
final_request p50/p95, source-end latency и хеши итоговых транскриптов.
Меньше 20 samples помечаются diagnostic_only. Шесть отдельных HTTP/WAV
проверок инструмента прошли без реальной модели.

Граница этого измерения — source_wav_end, **не конец речи в трубке**.
Время final request включает очередь/транспорт/ASR, а не только inference.
CPU/RAM и точный RTF модели записать отдельно; hardware/revision в JSON —
сведения оператора, не удалённая проверка. Это не whole-turn, TTS, VAD,
barge-in, warmth или сравнение с конкурентом. Отрицательный результат по
final latency означает оставить IMVERA_STT_PREVIEW=0; он не доказывает
плохое качество или хороший streaming другого checkpoint.

## После live gate — следующие отдельные замены

Нативный incremental STT: bounded prefix-путь выше уже реализован, но не устраняет полную повторную работу модели. Stateful adapter/checkpoint выбирать по elderly-phone audio, включая шум/отрицание/исправление, качество и RTF на целевом железе. Существующий batch encoder нельзя объявить streaming переименованием. Final-only commit остаётся обязательным.

Языковой Renderer при изменённом решении владельца: вход — принятые факты и конкретный ResponsePlan, один обязательный вопрос, разрешённые речевые действия. Модель не меняет State и не вызывает tools; кандидат проверяется до канонического text_commit и TTS. Safety/control/consent сохраняют канонические детерминированные реплики. Нельзя проверить свободную фразу несколькими regex и объявить нулевые галлюцинации. Старый transport composer не возвращать.

Просодия: сначала запись пользователя и A/B текущего голоса на реальном Mac. Не менять голос/температуру по чужому маркетинговому описанию. Синтез речи модели уже существующий, её естественность и задержка должны быть измерены.

Stateful STT, свободный LLM Renderer и изменение просодии этим срезом не реализованы; следующий шаг выбирается по живому gate и решению о LLM. Инструкция для Mac-агента передана через этот документ; внешних сообщений не отправлялось.
