# M5 dialogue reliability: запуск и приёмка

## Conversation floor integration — 2026-10-04

[Evidence and complete replays](evaluation/conversation-floor-2026-10-04/README.md).
Verified source `a15dc36096485fb47eecbd7f099eb2dafb800681`,
[CI37167925199](https://github.com/Belvist/imvera/actions/runs/37167925199):
all11 PASS,3259 PASS/0 FAIL/3 SKIP,176.67s. Deploy this source or a later reviewed
revision, then verify actual bridge SHA; report fs-145617fc used old `2d8315c`.
STT may omit punctuation: bounded navigation is recognized in shared
prepare_kernel before post-STT admission, not patched after the fragment gate.
Do not bypass admission or call the kernel twice.
Fetch/fast-forward the m5 branch; do not copy templates into CallActor or TTS.
The existing producer/discourse distinguish feedback, substantive continuation
and explicit handoff. Call navigation resolves through the existing service-answer
owner and the same selector; renderer composes the answer plus selected semantic
need before delivery. No new flag, model or global ActionPolicy cutover.
Keep the active `scripts/prerender_opening.py`: startup commands still invoke it.

For live acceptance repeat `Нормально вроде бы → Нормально говорю → Да →
Правильно, говорю, всё → И что дальше?`, plus a real story with `Да`, a further
substantive continuation and `Я всё сказала`. Capture exact SHA, audio/raw trace,
heard questions and stage timing; specifically investigate the reported 4165ms
engine turn. No claim of free human conversation or capacity follows from SDK tests.

## SDK follow-up — 2026-10-04

Verified source `03c8e26f4d174e18675a2d52c37eb08fe332290c` on m5:
[CI37164021083](https://github.com/Belvist/imvera/actions/runs/37164021083),
all11 jobs PASS,3206 passed/0 failed/3 skipped.
[Evidence](evaluation/single-need-questions-2026-10-04/README.md).
Coverage mood now delegates to the existing slot renderer; one move asks mood,
without an appended negated anxiety/health question. Preserve this one-need
boundary when integrating; no changes to safety/consent/state ownership.

The canonical replay now imports the SDK from its own checkout. For service
launches, confirm the selected Python, working directory and actual module path;
an editable installation from main/another checkout is not the m5 runtime.
Use the source SHA, profile/model IDs and module location together. Real
CallActor/FreeSWITCH audio+trace, accepted neural voice, latency/interruption,
Core and capacity still need target access and remain NOT VERIFIED.

Общий Mac/Linux worker contract и серверный запуск: [portable production handoff](production-server-handoff.md).

Текущий dialogue cut (2026-10-02): [user-led conversation handoff](user-led-conversation-integration.md).
Общий SDK/Actor producer, ActionPolicy personal-thread moves и реальное ожидание
после ACK; точный опубликованный SHA и ворота — в `current-task.md`.


2026-10-02. Ветка `feature/voice-zoiper-m5`, база `933c52b` после обновлений
агента (`a246bd1`, `933c52b`); reliability slice начат на `c896aee`. Это исправления
существующего SDK/CallActor/STT/startup, без второго движка и без генеративного
LLM в живом разговоре. Приёмка в прод ещё не выполнена. Точные результаты
общих проверок и опубликованный SHA — в `current-task.md` и release report.

## Что агенту учитывать при интеграции

- Подключать существующий CallSession/DialogueEngine. Его канонический текст
  передавать в TTS без переписывания; Renderer композирует grounded ответ один
  раз, в том числе при повторной сборке ResponsePlan.
- Даже при прощании сохраняется принятая жалоба с доказательной цитатой.
  Подтверждённый адресованный отказ от текущего звонка сохраняется отдельно от
  обычного goodbye. Это не автоматический отзыв согласия на будущие звонки.
  Core остаётся владельцем публичного статуса; локальный candidate — не Core ACK.
- Время относится к своему действию: «таблетки принимаю в 12 часов вечера»
  не задаёт начало боли; «12 часов вечера» задаёт час начала, а не двенадцать
  часов продолжительности. Настоящая длительность рядом с часом сохраняется
  отдельно. Обновления агента по hedge, repair и dedup сохранены.
- CallActor владеет задачами и deadlines STT/TTS. Disconnect инвалидирует их;
  поздний результат не изменяет завершённую сессию или новую generation.
  Уже выполняющуюся синхронную запись нельзя прервать как coroutine: её fence
  удерживается до завершения, чтобы finalize не обогнал запись.
- STT принимает один активный request ID, ограниченный PCM и конечные числовые
  поля. Невалидный ответ — ошибка; отсутствие asr_quality — UNUSABLE. Нельзя
  подставлять GOOD или превращать объект/число в распознанную речь.
- HTTP timeout возвращает управление, но не останавливает зависшее вычисление
  Python/PyTorch. Worker сохраняет WAV до конца работы и отбрасывает результат.
  Если очередь не освобождается, снимать диагностику и перезапускать выделенный
  worker по runbook; не перенаправлять на незаявленную модель.
- Выбранный TTS engine должен совпадать с readiness/model_revision. Ошибка
  выбранного MLX больше не вызывает переключение на Silero. Лабораторный выбор
  LAB_FAST остаётся отдельным явным режимом до старта; `silero_lab` имеет NC
  ограничение и не является принятым прод-голосом.
- Prefix STT остаётся `IMVERA_STT_PREVIEW=0` по умолчанию. Это ограниченная
  повторная batch-транскрипция, не stateful streaming; не включать в прод до
  парного измерения нагрузки и final latency. Протокол — в
  [realtime-conversation-v1.md](realtime-conversation-v1.md).

## Перед запуском на M5

1. Зафиксировать текущие SHA/конфиг/endpoint/model_revision, статус БД и доступный
   путь отката. Не удалять БД и записи. Проверить чистоту рабочего дерева,
   fetch и fast-forward только m5; при чужих изменениях сначала сохранить их.
2. Установить runtime-зависимости тем же Python, которым работают процессы:
   `python -m pip install -e '.[dev,test,api,voice-runtime,semantic-nlp,mlx,gigaam-stt]'`.
   Linux CPU image/CI отдельно устанавливают CPU torch 2.14.1; на M5 не подставлять
   Linux wheel. Наличие torch не означает наличие обученных heads.
3. Сохранить и проверить действующие `models/semantic_nlp/` из вашего живого
   контура. Runtime требует `v2/{head.pt,labels.json}`,
   `polarity_v1/{head.pt,labels.json}`, `xenc_v3/{heads.pt,labels.json}` и его
   локальный `encoder/`, если он был обучен. Полная батарея также проверяет v3.
   Сравнить SHA256 с сохранённой рабочей копией; не создавать фиктивные веса,
   не переобучать взамен утраченных. Установочные extras их не скачивают.
4. Записать engine и URLs явно: GigaAM из `config/voice-m5.yaml`, выбранный
   MLX TTS, `IMVERA_MEDIA_BRIDGE_MODE=callactor`, единственный DialogueEngine.
   Для выбранного MLX установить `IMVERA_LAB_FAST_TTS=0` и
   `IMVERA_TTS_ENGINE=mlx_customvoice` (либо ваш уже принятый clone engine).
   Не включать generative composer/interpretation и не подменять голос.
5. Перезапустить только изменённые Python bridge/workers установленным
   supervisor, прогреть реальные модели. FreeSWITCH-образ и данные БД не
   пересобирать ради изменения SDK. Пройти `/health/ready` каждой реплики и
   `python scripts/dialogue_product_smoke.py`; bridge должен быть callactor,
   single_writer, NLP all_hot. 503 — запрет приёмки, не косметическая ошибка.

## Linux image: воспроизводимая сборка

Bridge image содержит Python runtime, config и клиентов отдельных STT/TTS
workers. Он не содержит MLX (Apple Silicon), обученных NLP-весов, записей или
тайного CA из сессии сборки. Артефакты монтируются read-only в `/app/models`,
HF cache — отдельно. Без них readiness должен отказать.

```bash
REVISION=$(git rev-parse HEAD)
docker build --build-arg IMVERA_GIT_SHA="$REVISION" \
  -f infra/freeswitch/Dockerfile.bridge -t "imvera-bridge:$REVISION" .
docker image inspect "imvera-bridge:$REVISION" \
  --format '{{.Id}} {{index .Config.Labels "org.opencontainers.image.revision"}}'
```

В среде с доверенным TLS proxy использовать BuildKit
`--secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt`; секрет применяется
только в install layer, не копируется в образ. Не отключать проверку TLS.
`IMVERA_GIT_SHA` попадает в label и runtime truth, git внутри образа не нужен.
При сборке через Compose передать `IMVERA_GIT_SHA=$(git rev-parse HEAD)` в его
окружение; оба Compose build передают значение в Dockerfile. Значение `unknown`
допустимо для dev, но не является доказательством версии при прод-приёмке.
Image проверяется с действительными worker URLs/volume mounts; localhost внутри
контейнера не является M5/соседним worker.

## Обязательные живые проверки

| Проверка | Принимается только при |
| --- | --- |
| Реальный звонок 7000 | Двустороннее аудио + JSONL, SHA/config/model truth известны |
| Паузы и медленная речь | Нет обрезания реплики, двойного вопроса и потерянной жалобы |
| Перебивание | Старые PCM не возобновляются, SDK question освобождён, слышимая остановка p95 <250 мс |
| Задержка ответа | Конец пользовательской речи → реальный первый downlink: p50 <1 с, p95 ≤2 с на целевом железе |
| STT/TTS down, timeout, disconnect | TECHNICAL/неизвестность видна, нет фиктивного успешного результата, поздний ответ отвергнут |
| Отказ и безопасность | Цитаты сохранены, опасность не скрыта отказом, согласие семьи не заменяет согласие подопечного |
| Core | Подтверждён приём события/результата и правильный публичный статус |
| Нагрузка/100 полных звонков | Измерены память, очередь, capacity, нет потерянных задач/записей |
| Человечность | Прослушивание записи, темп/паузы/интонация; текстовые тесты не заменяют оценку |

Живой отказный сценарий проводить на отдельном стенде с тем же конфигом:
останавливать тестовую реплику, а не общую прод-реплику. Mock-provider tests
проверяют runtime-контракт, а не реальную модель или SIP.

## Откат

Сохранить предыдущие source SHA/image digest, flags, конфиг и model hashes до
обновления. При fail gate остановить новые звонки, дать текущим завершиться,
вернуть предыдущий код/image с теми же данными/артефактами и повторно проверить
readiness. Для этого изменения миграции БД не добавлены. База разработки
`c896aee` не обязательно является предыдущим принятым образом вашего стенда:
оператор записывает фактический digest, не угадывает его по ветке.

GitHub Actions artifacts, releases/tags и LFS проверены: комплекта trained
heads там нет; в истории тоже нет файлов весов. Это действительная зависимость
живого контура, а не проблема установки Python-пакета.

Текущий блокирующий gate: действительные NLP-артефакты + запуск на вашем M5
и запись полного звонка. Из этой среды они недоступны; локальный HTTP/image
smoke и unit-тесты не доказывают готовность прода.
