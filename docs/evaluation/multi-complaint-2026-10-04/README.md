# Несколько жалоб, разговор и измеренная нагрузка — 2026-10-04 UTC

Целевая ветка **feature/voice-zoiper-m5**. Baseline
`ad5aad75037ac7b2df048b8cd190cafbd5c754bc`; изменения применяются к нему,
main не изменяется. Verified source **c11674ef97382570f1e5ef544f2380b8c612b3de**:
[CI37244559679](https://github.com/Belvist/imvera/actions/runs/37244559679), **all11 PASS;
3392 PASS/0 FAIL/3 SKIP/208.77s**, genuine LFS checkout/model readiness подтверждены.
[Команды и provenance](checks.json). Follow-up меняет только reports/provenance;
implementation/test/config/workflow bytes идентичны этому exact-CI source.

## Что воспроизведено

Изучены `docs/live-calls/fs-fd317c1c-multi-complaint.md`,
`fs-9de2dab3-borscht-thread.md`, `docs/ops-log-review-2026-10-05.md`.
В Git находятся отчёты, **исходных записей/JSONL этих двух звонков здесь нет**.
Actual deployed SHA, flags/profile/providers и hardware working-set не установлены.
Поэтому доказан SDK-контрпример текущему исходному дереву, а не причина ошибок
акустического STT, конкретного deployment или произвольного живого звонка.

На baseline, в default legacy/coverage1, после
`Рука болит опухла, что-то давление ещё, и этот сахар поднялся` создаются три
эпизода. После двух нераспознанных ответов о времени первой жалобы движок
выдаёт summary, оставляя другие жалобы неуточнёнными. При этом строка concern
содержит все три: сохранённый список не доказывает завершённое уточнение.
Отчёт fs-fd317c1c утверждает, что третий ответ принят; baseline SDK этого не
подтверждает: onset отсутствует после обоих опубликованных clock-ответов.
Сопоставить с фактическим deployed trace без исходного JSONL нельзя.

## Причины и владельцы

| Причина | Старый / текущий владелец | Изменение |
|---|---|---|
| Clock ownership отвергал грамматический hedge | issue_memory.extract_grounded_onset_value | Учитываются existing UNCERTAINTY/ISSUE/BODY_SITE spans; остаточный предикат обязан относиться к симптому. Покупка сахара/таблетки/дочь/альтернативное время не закрывают onset. |
| Ack исключал site-less жалобы при наличии anatomical site | conversation_policy._grounded_ack_for_mentions → questions.episode_ack | Primary выбирается среди site-bearing mentions, но остальные grounded labels сохраняются. Одна семантическая потребность/вопрос. |
| Три разных temporal probes считались повтором | Reducer._note_temporal_emit / EngineState.last_temporal_probe | Identity существующего счётчика включает canonical episode_id. Snapshot roundtrip проверен; старые unscoped values читаются. |
| Исчерпанный probe повторно выбирался в loop8 | существующий legacy scheduler внутри Reducer | Если ещё есть очередь speaker complaints, исчерпанная потребность отмечается unanswered фактической цитатой. Это не известный onset и не медицинский факт. Существующий product planner пропускает этот need и продолжает. Single-episode frozen bail не изменён. |
| Следующий звонок терял третью жалобу | check_path.episode_digest | Existing bounded string digest до6 вместо2; формат прежний, чужие жалобы исключаются. Доказательный текущий mention остаётся необходимым для reopening. |

Нет нового brain/FSM/scheduler/provider/generator или flag, no global ActionPolicy
medical cutover. Safety/control/explicit stop остаются deterministic. Локальный
scope — исправление очереди и ownership, не новая медицинская диагностика.
Текущее административное `episode.status=resolved` по завершению pack **не значит**,
что человек выздоровел. Swelling «опухла» в этой реплике сохраняется в исходной
цитате, но отдельный структурный признак swelling этими проверками не доказан.

## До / после: реальный source-bound SDK replay

[Cases](cases.json), [before](before.json), [after](after.json): семь сценариев,
10 повторов,260 текстовых turns на сторону; hearing моделируется ScenarioRunner.
Флаги и SHA/dirty source прямо в артефактах. No SIP/STT/TTS/human acceptance.

После опубликованного списка раньше:

> Жаль, что рука болит. Когда появилась эта боль — сегодня или раньше?
> «Понятно. В12 вроде.» → повтор вопроса о времени.
> Второй непонятый ответ → summary без уточнения давления/сахара.

Теперь:

> Слышу вас: рука болит, давление и сахар. Давайте по порядку.
> Когда появилась эта боль — сегодня или раньше?
> «В12 вроде.» → Сейчас боль сильнее или уже становится легче?
> «Терпимо.» → Давление — давайте уточним. Когда это началось — сегодня или раньше?
> «Со вчера.» → Сахар — давайте уточним. Когда это началось — сегодня или раньше?
> «Сегодня после обеда.» → А кроме этого — по самочувствию ничего не тревожит?

Это цитаты SDK, **не запись нового телефонного звонка**. Открытый рассказ остаётся
входом; не нужно спрашивать три независимых вещи одновременно. Уже сообщённое
должно закрывать свои grounded needs; неизвестное остаётся неизвестным.
Не удалось вспомнить onset первой жалобы → следующий нужный question первой
или следующей жалобы, а не потеря очереди.
SDK p50 2.412→2.500ms; p95 5.338→4.588ms. Это не ускорение живой речи.
Нет добавленных model stages; фактические neural invocation counts здесь не измерены.

## Сколько памяти и какую нагрузку измерили

[stt-load.json](stt-load.json) — **настоящая GigaAM**, официальный checksum/SHA256
checkpoint+tokenizer проверены. Immutable STT image/source
`2e78b543d3ccd5854d44eb681f1f07b8d016b06c`, профиль и image ID в артефакте.
Current STT inference/executor logic совпадает с этим image; startup checksum
теперь использует bounded stream, общий readiness helper изменён для dependencies, не считать весь current bridge испытанным image.
Isolated Linux host3CPU/~9.735GiB; worker quota2CPU/4GiB, single inference lane,
queue4 = один running + три waiting. Репозиторный WAV4.088s,24 запроса/уровень.

| Clients | HTTP200 | HTTP429 | p50/p95 successful HTTP | successes/s |
|---|---:|---:|---:|---:|
| 1 | 24 | 0 | 640/683ms | 1.573 |
| 2 | 24 | 0 | 1005/1267ms | 1.889 |
| 4 | 24 | 0 | 2099/2356ms | 1.876 |
| 8 | 4 | 20 | 1726/2462ms | 1.616 |

HTTP latency включает создание клиента/HTTP/очередь/inference, не чистый model
compute. Clients работают без think time: burst/stress, а не число телефонных
собеседников. p95 при8 рассчитан только по4 успешным, отказы рядом явно показаны.
Working-set Docker после warmup1.455GiB, после нагрузки1.461GiB; **peak RSS/CPU
не измерены**. Четыре коротких отдельные WAV: p50 274ms/p95 315ms (n4).
Checkpoint на диске428.13MiB; размер файла не равен RAM.

Первая попытка isolated probe не выполнена: при VFS container свободный диск
workspace исчерпан, также получен HTTP500. Причина этого HTTP500 отдельно не
подтверждена worker traceback. Удалён только созданный нами container. Повтор с tmpfs
для container scratch и output в host tmpfs завершился успешно; после сохранения
артефакта собственный контейнер удалён. Чужие images/volumes, БД и live M5 не тронуты.
Один container snapshot временно занял оставшийся диск; production sizing должен
учитывать disk/runtime layers отдельно от memory. Исходный model path read-only.

### Что известно о всей системе

| Компонент | Доказательство |
|---|---|
| STT worker | Working-set1.46GiB после этой нагрузки; cap4GiB/2CPU |
| Bridge + NLP | В compose cap4GiB/2CPU; реальный working-set current models NOT_MEASURED |
| TTS HTTP adapter | cap1GiB/1CPU; это **не** Qwen resident backend |
| Qwen resident voice/GPU | Текущая RAM/VRAM/throughput NOT_MEASURED; один Metal RTF0.362 из отчёта не capacity gate |
| FreeSWITCH/Postgres/OS | NOT_MEASURED; добавляются к бюджету |

Subtotal compose defaults **5vCPU/9GiB лимитов**, не фактическое потребление и
не полный сервер. Production profile admission **1 active call** остаётся1;
lab configuration/running flags на M5 нужно установить отдельно. Два HTTP voice
адаптера над одним backend не умножают вычислительную мощность. Логи114+ STT429
и voice busy поддерживают необходимость проверки очередей/compute ownership.

### Какие серверы проверять

- **8vCPU/16GiB Linux** — начальный стенд для bridge+одной CPU GigaAM+adapters+
  телефонии/БД с запасом. **Qwen resident endpoint нужен отдельно**. Это стартовый
  бюджет и кандидаты на замер, не гарантия concurrent calls или latency.
- **8–16CPU/32GiB + GPU24GB класса L4/A10/4090** — кандидат для резидентного
  голоса/возможно ASR после проверки поддерживаемого Qwen backend, лицензии,
  driver/model footprint. Мы не измеряли этот GPU и не обещаем100 звонков.
- Дальше отдельные model-owning replicas и session-sticky bridge processes.
  Миллион зарегистрированных пользователей ≠ миллион одновременных звонков.
  Нужна measured arrival rate, speech duty cycle и latency/error SLO.

Планировочный минимум при throughput S req/s на replica и целевой загрузке u:
`replicas >= ceil(total request arrival rate / (S*u))`. Для оценки arrival rate
нужны реальные turns/minute и previews/turn. u<1 — запас, выбранный по bursts/SLO,
не универсальная гарантия. Делать отдельные оценки STT/TTS/bridge и взять bottleneck;
после этого принять реальным нагрузочным CallActor/SIP gate.

## Как сделать легче и быстрее

1. Сохранять models resident; масштабировать STT отдельными lanes, Qwen отдельными
   реальными backends. Не увеличивать Python threads/queue вместо вычислений.
2. Изолировать optional batch previews от финального STT: idle-only уже существует;
   измерять calls/turn, не запускать repeated full-prefix inference без бюджета.
3. Сохранять thread caps2 как текущий измеренный CPU профиль; другие значения
   benchmark на конкретном server, без oversubscription.
4. Использовать pilot/prod async observation tier; full forensic только для
   выделенного диагностического звонка. Не делать PG/network IO hot-path barrier.
5. Проверить raw trace сегментами: engine p954165/5721ms в reports несопоставим
   с SDK5ms и остаётся **необъяснённым** без model-stage/queue/lock durations.
6. Настоящие phone WAV + исправленный `capacity_probe.py` проверяют actual
   STT.text/asr_quality → canonical SDK → actual validated TTS, без consent hacks.
   FirstPCM/completePCM разделены; errors и missing measurements не скрыты.
   Controlled provider tests доказывают plumbing, не производительность.
`stt_calls`/`tts_calls` полного probe — logical adapter invocations, не количество
HTTP retries/физических model executions; для последних нужен worker trace.
7. Принять worker-level firstPCM/service/RSS, затем полный звонок, затем soak с
   mix медленных длинных историй/перебиваний/clinical urgency. До этого caps1.

## Выполненная экономия startup памяти

`services/stt/gigaam_engine._verify_checksum` теперь использует bounded
`hashlib.file_digest`, вместо checkpoint.read_bytes. На настоящем официальном
448929252-byte checkpoint оба способа дают тот же checksum. [Измерение](checksum-memory.json):
Python traced peak **448934176→267377 bytes** (428.14MiB→261.11KiB).
Это уменьшение временного Python buffer при startup, **не экономия428MiB
постоянного model working-set** и не worker RSS/latency capacity benchmark.
Elapsed0.744/0.621s, по одному чтению в фиксированном порядке; кеш влияет,
ускорение startup этим не принято. Test проверяет корректный checksum и реальную
порчу последнего байта при запрещённом whole-file read. Проверка не ослаблена.

## Приёмка и остаток

CHANGED: пять причин выше, тип snapshot identity, truthful capacity probe,
измерительный STT probe и устаревшие scaling claims. Состояние/поведение медицинских
порогов не отдаётся генератору. [Gates](checks.json).

NOT VERIFIED: реальные STT ошибки этих записей, deployed current SHA, full speech
latency/warmth/interruption, Qwen throughput/RSS, вся система под нагрузкой.
REMAINING RISKS: детерминированная формулировка/ordered product minima остаются;
pack имеет общий лимит вопросов и bounded memory6; clinical attribute completeness
давления/глюкозы beyond существующий pack здесь не расширена. Это исправление
многожалобного пути, не обещание безграничной человеческой беседы.
NEXT GATE: **реальный повтор fs-fd317c1c через CallActor/FreeSWITCH** на проверенной
revision с записью+raw trace и health/profile/provider IDs. После него длинная речь,
несколько фактов в одной реплике, unknown/other-person/stop/safety/перебивание;
stage p50/p95 и real hardware working-set, затем capacity soak обоих compute tiers.
