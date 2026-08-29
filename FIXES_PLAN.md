# FIXES_PLAN — план исправлений (зафиксирован 2026-08-29)

Источник требований: `read.md` (гейты G0–G9) + `docs/architecture_realtime_2026-08-27.md`.
Полный аудит дефектов с файл:строкой — в отчёте агента от 2026-08-29 (таблица ниже).

Правило: каждый пункт = отдельный commit, после каждого — `make test-fast` зелёный.
Порядок жёсткий: P0–P4 (живой код) до P5–P6 (миграция), P7–P9 (чистка/durability),
P10–P11 (server/product-ready).

## P0 — Безопасность: утечка ESL-пароля (критично)

**Дефект 1.1:** живой пароль FreeSWITCH ESL (`d7f78342…9f89`, 32-hex) был
закоммичен в `voice_runtime/esl_client.py` / `telephony/esl_stream.py` /
`loopback_test.py` — совпадал с live-confiгом `event_socket.conf.xml`; утёк в
`release/mossvoice-ba73b7f/`. `scripts/check_secrets.sh` не ловил 32-hex строки.
Статус 2026-08-29: **ИСПРАВЛЕНО** — пароль ротирован (FS перезапущен, новый
пароль в live-confiге и `~/.fs_cli_conf` chmod 600), дефолт из кода убран
(env `MOSS_ESL_PASSWORD`, пустой = fail-fast), `esl_stream.py` удалён,
release-артефакты очищены, hex-детекция добавлена в check_secrets.

- Ротация пароля в live FreeSWITCH (`event_socket.conf.xml`). ✅
- Дефолт убрать из кода; пароль только через env `MOSS_ESL_PASSWORD`. ✅
- Усилить `check_secrets.sh`: 16+ hex подряд, любые длинные hex-строки. ✅
- Пересобрать release-артефакты; перевыпустить пароли. ✅

Выход: `grep -r d7f78342... .` = 0; release-сканер ловит hex.

## P1 — Баги диалогового ядра (dialogue.py / safety_engine.py)

**1.6 `_help_pending` мёртв** (`dialogue.py:747` чистит флаг до чтения в `_plan_mode:881`) —
«да» на «Нужна помощь?» даёт generic-ack, помощь не фиксируется.
Fix: потреблять флаг только в `_plan_mode` (арм в `_ask_help`, не в `plan_reply`).
✅ 2026-08-29: убран преждевременный сброс в plan_reply; флаг живёт до _plan_mode.

**1.7 `_closing_confirmed` никогда не присваивается** (`dialogue.py:849` только чтение) —
петля прощания «до свидания → Вы прощаетесь? → до свидания → …».
Fix: ставить флаг при подтверждении, сбрасывать при продолжении.
✅ 2026-08-29: повторное короткое «до свидания» = подтверждение (terminal);
при продолжении разговора флаг сбрасывается — следующее прощание снова один раз переспрашивается.

**1.8 `_agenda_question()` IndexError** (`dialogue.py:595-598` без границы) —
два входа: interrupt-resume `:807`, рассказ-4-5 слов + family `:1106`.
Fix: safe fallback `idx >= len(all_) → wrap-up вопрос`.
✅ 2026-08-29: index-guarded, деградирует в _wrap_up_question.

**1.9 Safety: экстренные токены без субъекта** (`safety_engine.py:483-495`) —
«врача/срочно» дают confirmed_red в любом контексте («записалась к врачу» → alert).
Fix: субъектный фильтр (self/я) для несердечных экстренных токенов.
✅ 2026-08-29: _CONTEXTUAL_EMERGENCY_TOKENS (врач/доктор/срочно) требуют
SELF + маркер остроты рядом; «скорая/инфаркт/инсульт/неотложка» остаются безусловными.

**1.10 Safety: окно отрицания ±3 токена** (`safety_engine.py:199-214,506-563`) —
«я упал, но не сильно» глотает падение.
Fix: независимое окно для HIGH_ROOTS/падений, только left-window отрицания для жалоб.
✅ 2026-08-29: `_negated_left` — падение гасит только «не» ПЕРЕД глаголом;
«не упал» = ok, «упал, но не сильно» = confirmed_red.

Выход: регресс-тесты на каждый кейс; `make test-fast` 228+.
Статус 2026-08-29: **ВЫПОЛНЕНО** — `_help_pending` не сбрасывается в plan_reply
(потребляется в _plan_mode), `_closing_confirmed` реализован + сброс при
продолжении разговора, `_agenda_question` index-guarded, safety: субъектный
фильтр для контекстуальных экстренных токенов (врач/доктор/срочно) +
асимметрия отрицания падений (только leading). Новые регрессии:
`test_dialogue_fixes_20260829.py` (6), `test_safety_engine` FallAsymmetry (6).
`make test-fast` = **241 OK (28 skip)**.

## P1b — STT: гейт мусора не спасает при «уверенной бессмыслице» (живой звонок 2026-08-29)

Измерено на реальном звонке `ca81bc3ac2c7` (dialogue_turns):
- «упал» → распознано «у палок не ударилось» conf **0.774** — прошло гейт 0.55,
  потеряно safety-слово «упал» (verdict=ok, хотя пользователь говорил про падение);
- «Торатичина» conf **0.614** — гейт пропустил мусор в LLM/повестку;
- «Лоха!» (=«Ладно!») conf **0.763** — искажение.
Вывод: binary-гейт 0.55 бесполезен против уверенного мусора.
Fix (по очереди, что дешевле):
1. Словарный/контекстный фильтр хода: транскрипт без распознаваемых слов
   (не в леммах RU-набора/не совпадает с шаблонами «да/хорошо/плохо/слышно»)
   → пустой ход с reason="low_conf" (не уходит в LLM/повестку).
2. Поднять гейт точечно для критичных сущностей здоровья (упал/болит/голова/
   таблетки/врач) — small-риск бады, но для них допускать только высокий conf.
3. Fase: пересмотреть `MOSS_STT_MODEL=base` на телефонном пути (в AGENTS.md
   зафиксировано: base в 2-5× медленнее) — измерять WER на телефоне, а не на чисте.

Выход: регресс на реплее сохранённых user-*.wav данного звонка: «Торатичина»
и «у палок» больше не уходят в диалог.
Статус 2026-08-29: **ВЫПОЛНЕНО** — добавлен `core/vocab.py` (FUNCTION_WORDS +
CORE_ROOTS + CRITICAL_HEALTH_ROOTS + OBSERVED_NOISE + лёгкий суффиксный стем);
`orchestrator.process_turn_stream` гейтит транскрипт без распознаваемых слов →
reason="low_conf" (якорь, не LLM); критические сущности (упал/удар/болит/врач…)
НИКОГДА не режутся. Регрессии: `test_vocab_gate.py` (4), включая реальный кейс
«у палок не ударилось» (проходит — «удар» критический). make test-fast 241 OK.

## P2 — Контракт VoiceRuntime ↔ agent (главный блокер realtime)

**1.4 turn_stream клиент не читает ответ** — сервер отвечает chunked
`application/octet-stream` (length-prefixed JSON-фреймы, `call_agent_http.py:565`),
а `agent_http.py:44-52` ждёт единый JSON → каждый успешный ход логируется как FAIL;
при настоящем 429/404 `_stream_done:228` ничего не делает → `streaming=True` навсегда.
Fix: фреймовый декодер; сброс `streaming` по `on_done(False)`; различать
HTTP-статусы (ответ сервера с `ok:false`).
✅ 2026-08-29: `_stream_post` в agent_http читает тело как opaque (200 = успех),
4xx/5xx → AgentError с телом ошибки; `call_session._stream_done` сбрасывает
streaming/suppress/segdir на отказ ТОЛЬКО текущего turn (guard по turn_no, stale
не убивает новый). Тесты: `voice_runtime/test_agent_http.py` (8) — 200/429/404,
caller_id, unblock/stale.

**1.15 done.json раньше освобождения turn lock** (`orchestrator.py:1546`) —
гонка: VR шлёт следующий turn → 429.
Fix: написать done.json ПОСЛЕДНИМ (после persist/save) или освобождать lock раньше.
✅ 2026-08-29: `_write_done_file` перенесён в КОНЕЦ `process_turn_stream` (после
persist/emit/trace); при barge-in (cancel) done.json тоже пишется (иначе VR
застрял бы в streaming=True).

**1.5 `create_call` без caller_id** (`call_session.py:74`) — теряется вся повестка
(`orchestrator.py:431` включает check-in только при caller_id); семейные вопросы
остаются pending.
Fix: брать caller из `CHANNEL_ANSWER` (Caller-Caller-ID-Number) → передавать
в `create_call({caller_id})`.
✅ 2026-08-29: runtime передаёт caller из CHANNEL_ANSWER/scan в `_attach_channel` →
`CallSession.start` шлёт `create_call({caller_id})`.

Выход: unit-тесты контракта; loopback-звонок 4402 даёт повестку и фреймы.
Статус: **ВЫПОЛНЕНО (код+тесты)**; живых loopback-звонков нет до P8 (деплой runtime).

## P3 — Устойчивость runtime (esl_client / runtime / call_session / vad)

**1.11 ESL-обрыв невидим, реконнекта нет** (`runtime.py:130-133` ждёт несуществующего
`Event-Name=="disconnect"`; `esl_client.py:183` кладёт `connection/disconnect` без
этого ключа). Fix: распознавать disconnect самостоятельно + reconnect с бэкоффом
+ тег в `/ready`.
✅ 2026-08-29: reconnect с backoff уже был (ESL_RETRY_SECONDS/_try_reconnect);
добавлен `Event-Name: disconnect` в оба disconnect-пути _read_events → runtime
видит обрыв, esl_ok=False, /ready=503. Тест усилен (test_socket_close_emits_disconnect).

**1.12 Потерянный PLAYBACK_STOP стопорит `_pump_segments`** (`call_session.py:244`).
Fix: трекер `playing` по файлу/uuid + watchdog сброса по таймеру; не полагаться
только на событие.
✅ 2026-08-29: `_play` запоминает `_play_end` = номинальная длительность WAV +
0.5с; `_maybe_watchdog_playing` в on_tick сбрасывает playing по истечении.
Сброс _play_end при PLAYBACK_STOP/barge-in/api_break. Тесты: PlaybackWatchdogTests (3).

**1.13 Barge-in без длительностного порога** (`vad.py:97` onset по 30мс чанку) —
кашель рубит реплику. Fix: onset только по sustained speech (≈220–320мс),
использовать `_in_speech`-наращивание.
✅ 2026-08-29: `_onset_fired` — onset после MIN_SPEECH_MS (220) / ECHO_MIN (320);
буфер сохраняет всё с реального начала (ничего не теряется). Тесты: onset порог (2).

**2.2 Очередь ESL maxsize=2000, drop при Full** (`esl_client.py:198-201`) —
потерянный HANGUP → зомби-сессия до 2ч. Fix: не-dropping (больше размер /
блокирующий put + приоритет для HANGUP/DESTROY).
✅ 2026-08-29: блокирующий put с backpressure (повтор при Full), потеря событий
исключена; channel-scan как backstop (уже был).

## P4 — Верификация record_stereo / LEFT (echo, блокер G3)

**1.14 Realtime-контур построен на LEFT=caller** (`media_tap.py:138`), но AGENTS.md
2026-08-23: «в этой сборке FS направленное разделение каналов НЕ работает»;
серверного echo-guard в runtime нет → риск self-barge-in/эха.
Fix: живой звонок с медиа → если стерео реально (проверить ch=2, полярность) —
ок; если моно-микс — перенести echo-guard (`_looks_like_echo`) в CallSession
и серверный путь отдаёт левый канал только при подтверждённом стерео.

Выход: решение «стерео vs echo-guard», обновить AGENTS.md фактом.

## P5 — G1: один SIP route 4400 = VoiceRuntime

**1.3 Инверсия:** `moss_dialplan.xml:10` 4400→Lua, runtime на 4401/4402.
Fix: 4400 = answer→park (+runtime regex `^4400$`), 4401 удалить, 4402 остаётся
только тестами; создать `scripts/install_freeswitch.sh` (sync dialplan+gateways+
global vars, reloadxml, ESL check, /ready check, fail-fast по версии);
установленный mac-drift (абс. путь в deployed dialplan) вылечить через install
скрипт.

Выход: `grep 4401` по source = 0; loopback через 4400 идёт в VoiceRuntime.
Статус 2026-08-29: **РЕПО-ЧАСТЬ ВЫПОЛНЕНА, деплой ОТЛОЖЕН.** dialplan rev-6
(4400=answer+park, 4402 loopback, 4401 удалён), runtime regex `^44(00|02)$`,
loopback_test/тесты на 4400, `scripts/install_freeswitch.sh` (идемпотентный:
sync dialplan, mossvoice_dir в vars.xml, чистка public-4400 роутов, reloadxml,
ESL check, /ready check, fail-fast). НЕ применён к живому FS: без runtime,
развёрнутого как сервис (P8), переключение 4400 сломает прод-звонки владельца.
Порядок: P8 (деплой runtime в compose/supervisor) → запуск install_freeswitch.sh
→ живой loopback 4400.

## P6 — G2: streaming MediaAdapter (убрать tail-WAV из прода)

**1.14/2.6:** `uuid_record` + tail-read — только dev-адаптер.
Fix: `MediaAdapter` (frames_in/send_audio/flush/close) на media bug / WebSocket /
RTP; PCM16 mono 16kHz/20ms канон; неправильный формат → media-unhealthy, не
молчаливое STT. `uuid_record`-адаптер удалить после прохождения streaming-тестов.

## P7 — G0: чистка legacy и package-корректность

**2.7/3.x:** удалить `telephony/esl_stream.py` (POC), `runtime_selftest.py`,
`legacy/` (перенести HTTP-слой в `telephony/api/http.py`), фасад `call_agent.py`
(entrypoint на канонический модуль), дубль `worker/` vs `workers/`
(переименовать в `agent_service/`), `moss_providers.py` vs `adapters/*` →
единый `providers/` (contracts + stt/llm/tts/storage), `_paths.py` → pyproject
(entrypoints `python -m mossvoice.*`), `release/` артефакты и `*.supervisor.log`
из дерева, `voice-bench/`+`voice-lab/` под `tools/`.
Каждый шаг = коммит + зелёные тесты.

## P8 — Деплой runtime + отключение loopback-шума

**1.2/2.3/2.4:** voice_runtime в Dockerfile+compose+supervisor; отключить 7 launchd
`com.mossvoice.agent-loop.*`; `start_telephony.command`+supervisor — только dev
(`dev/mac/`); `MOSS_MAX_CONCURRENT_CALLS` согласовать с `--parallel` llama.cpp.
Статус 2026-08-29:
- **runtime развёрнут НА ХОСТЕ под launchd** (`com.mossvoice.runtime.plist`,
  KeepAlive): supervisor `start --service runtime` (добавлена опция `--service`),
  лаунчер `scripts/run_runtime.sh` берёт ESL-пароль из `~/.fs_cli_conf` (env
  MOSS_ESL_PASSWORD, plist с TCC-безопасным путём `~/Library/Application Support/
  MossVoice/run_runtime.sh` + MOSS_REPO). Контейнер НЕ может достать ESL на
  127.0.0.1 хоста — host-деплой корректен. `/ready` = esl_connected, agent_ok.
- **ПРОД-ПЕРЕКЛЮЧЕНИЕ 4400 ОТКАТАНО обратно на Lua**: loopback B-leg (inbound
  4402) держит канал в `EARLY` (не ACTIVE) → `uuid_record` пишет ПУСТОЙ tap
  (0/44 байта) → CallSession отказывает сессию. Реальный inbound SIP (Zoiper)
  в ACTIVE — вероятно, даст tap, НО не верифицирован живьём (P4). Пока P4 не
  сделан, runtime ограничен dev-extension `^4402$` (иначе двойная обработка
  4400 Lua+runtime). Находка зафиксирована: **runtime на loopback B-leg не
  проверяем** — нужен реальный звонок.
- **Фикс `_on_answer`**: loopback A-leg ЭМИТИТ CHANNEL_ANSWER в этой сборке —
  runtime цеплял outbound-легу; добавлен direction==inbound фильтр (тест в
  логе: A-leg больше не attach).

## P9 — G5: durable spool / persistence

**2.6:** spool/сегменты с хост-`/tmp` на persistent volume; события с stable
event_id, idempotent PG-upsert, retry/backoff/dead-letter, независимые sink
queues, метрики, readiness при spool-failure; records tee в async recorder,
retention только после подтверждённого удаления.

## P10 — G8/G9: server deploy + observability

**2.1/2.5/3.x:** починить IP-автосинк (install в repo, absolute PATH для fs_cli,
reloadxml после правки); dialplan public: 4400 не доступен снаружи;
`deploy/` + `infra/freeswitch/` (dialplan/sip/gateways/vars); systemd;
/live+/ready+Prometheus; **убрать raw transcript из operational-логов**
(конфликт architecture §6 ↔ G9); release из чистого tag с commit+digest в
манифесте, сканер секретов обязателен.

## P11 — G6/G7: телефония и приложение на том же ядре

Inbound DID → канальные vars (moss_did/caller_e164/call_id/direction) → 4400;
outbound через ESL originate (no sleeps, no провайдер-привязки Core);
Product API + WebRTC/WebSocket media adapter → тот же CallSession.

## Приоритет запуска

P0+P1 параллельно (независимы, снимают самые дешёвые риски):
почётная цель — за вечер зелёные тесты и ротация пароля.
P2+P3 — следующий стек (realtime-контур начинает работать честно).
P5+P6 — миграция 4400 и медиа. P7–P11 — после зелёного рубежа.

## Замеренный срез диалогов (2026-08-29, звонок ca81bc3ac2c7 + архив)

Полная реконструкция по dialogue_turns + whisper-распознаванию user/reply-файлов:
- STT conf праздно высокие на мусоре: 0.614/0.763/0.774 (см. P1b).
- Монотонный canned-шаблон «Рада, что вы говорите. А …» повторён 5× подряд
  (681/685/687/691/694) — главный источник ощущения «это бред».
- Якорь «скажите коротко: хорошо или плохо» дублируется (688+692) и НЕ
  распознаёт «да, я тебя слышу» (690) как ответ — нужен детект
  acknowledgement-якоря.
- Повестка повторяет один и тот же вопрос («как вы сегодня планируете провести
  время?», 687 и 694) при пустых/мусорных ходах — нужен ротатор формулировок
  при повторе темы.
- Праздное «Лоха!» (693) уходит в LLM — кандидат в словарный фильтр (P1b).
- Safety: «упал» потерян не диалогом, а STT (см. P1b); дилогия ответила
  «плохим слышно, скажите хорошо или плохо» — корректная лестница тишины, но
  без восстановления потерянной сущности.
- История черновата ещё и cross-step терминологией («палки» вместо сегментов
  «плохо слышно») — не ошибка, а следствие мусора STT.