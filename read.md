MossVoice — Production Consolidation & Server Deployment Spec

Задача агенту

Это НЕ задача «починить один звонок». Нужно привести репозиторий к единственной production-архитектуре, удалить конкурирующие legacy/POC пути и подготовить систему к серверному деплою с реальными входящими/исходящими телефонными номерами и будущим приложением.

Работать по gate'ам ниже. Каждый gate заканчивается тестами и отдельным commit. Не переходить к следующему gate, если текущий не зелёный. Не добавлять новые пользовательские функции, промпты или сценарии до завершения G0–G7.

Конечная архитектура — единственный источник истины

PSTN / мобильный номер / SIP trunk
                │
                ▼
        FreeSWITCH Media Edge
        - SIP/RTP/NAT/codecs
        - inbound DID / outbound gateway
        - answer/hangup/DTMF
        - media control
                │
        continuous bidirectional audio
                │
                ▼
             VoiceRuntime
        - 1 CallSession actor / call
        - PCM16 mono 16 kHz / 20 ms
        - VAD / endpointing
        - barge-in
        - turn_id / generation_id
        - playback queue + stale-frame drop
        - no business SQL/S3 in hot path
           │        │        │
           ▼        ▼        ▼
          STT      Agent     TTS
                    │
                    ▼
                   LLM
                    │
          Dialogue / Safety / Tools
                    │
                    └──── async CallEvents ────► persistence/workflow

Product API / Mobile App
        │
        ├── schedules/history/incidents/family/auth
        │
        └── WebRTC/WebSocket media adapter ───► SAME VoiceRuntime

Правило: FreeSWITCH = телефония/media edge. VoiceRuntime = живой голос. Agent = текстовый диалог и политика. STT/LLM/TTS = отдельные model failure domains. PostgreSQL/Redis/S3 = не стоят между speech_end и first_audio.

G0 — очистить репозиторий и запретить legacy в production

Удалить из репозитория/runtime artifact

Удалить (Git хранит историю, отдельный runtime legacy не нужен):

telephony/esl_stream.py — старый ESL POC; заменён voice_runtime/.

telephony/moss_agent.lua — после переключения 4400 на VoiceRuntime. Не оставлять production fallback.

telephony/tests/runtime_selftest.py — старый тест Lua/4400; заменить SIP VoiceRuntime E2E.

release/ и release/mossvoice-* — generated artifacts не хранятся в source tree.

telephony/calls/ — recordings/results/logs не принадлежат репозиторию.

telephony/*.supervisor.log, telephony/calls/*.log, *.pid, runtime json state.

__MACOSX/, .DS_Store, __pycache__/, *.pyc, .tmp_postfix_check.py.

docker/.env из любого release bundle; локально допустим только ignored secret file, в репо только .env.example.

voice-bench/ и voice-lab/ оставить как dev tooling, но перенести под tools/ или исключить из production image/release.

Убрать ложные legacy interfaces

telephony/legacy/call_agent_http.py не должен оставаться legacy, если он используется production agent API. Перенести его в канонический модуль (telephony/api/http.py или новый package), обновить imports, затем удалить telephony/legacy/.

telephony/call_agent.py сейчас compatibility facade. Production entrypoint должен быть один. Перевести supervisor/docker на canonical module entrypoint; после миграции тестов удалить facade.

telephony/worker/ и telephony/workers/ слишком легко спутать. Разделить именами:

agent_service/ — realtime/text Agent API;

workers/ — migrate/outbox/retention/background.

moss_providers.py и adapters/* не должны содержать параллельные реализации одного и того же provider stack. Оставить один contracts layer + один набор concrete adapters. Целевая структура:

providers/contracts.py — ABC/protocols/errors;

providers/stt.py, providers/llm.py, providers/tts.py, providers/storage.py — implementations/factories.
Удалить дубли после перевода imports/tests.

Package correctness

Добавить нормальный Python package/build (pyproject.toml или эквивалент). Production не должен зависеть от cwd и _paths.py hacks. Целевые entrypoints запускаются через modules, например:

python -m mossvoice.agent
python -m mossvoice.voice_runtime
python -m mossvoice.workers.migrate

Не обязательно делать массовый rename в одном commit: сначала canonicalize runtime paths, затем package move, с тестами между шагами.

G1 — один SIP route; 4400 = production VoiceRuntime

Текущая проблема: 4400 идёт в Lua, VoiceRuntime — 4401. Это удалить.

Dialplan

telephony/moss_dialplan.xml / будущий infra/freeswitch/dialplan/mossvoice.xml:

4400 — основной internal application extension: answer -> park, никаких Lua scripts.

4402 — loopback/E2E test only, недоступен из внешнего trunk.

4401 удалить полностью после миграции.

voice_runtime/runtime.py должен attach к 4400 и test 4402. Никаких references 4401 в production docs/tests.

После G1 grep по source (кроме migration notes) не должен находить production references на moss_agent.lua, esl_stream.py, 4401.

Установка FreeSWITCH конфигурации

Создать один idempotent installer/config deploy:

scripts/install_freeswitch.sh

Он обязан:

установить/sync dialplan + SIP gateway configs из repo;

установить глобальные variables/config, не абсолютные developer paths;

выполнить reloadxml;

проверить ESL connectivity;

проверить VoiceRuntime /ready;

вывести fail-fast, если production route не соответствует ожидаемому version/hash.

Mac helper start_telephony.command и custom supervisor — только dev tooling; перенести в dev/mac/, исключить из production image. На Linux production — systemd/container orchestrator.

G2 — заменить file-tail media на настоящий streaming MediaAdapter

voice_runtime/ использовать как основу CallSession/VAD/generation, но текущий uuid_record + growing WAV — только переходный dev adapter, не production media plane.

Создать интерфейс MediaAdapter:

AudioFrame {
  call_id,
  seq,
  timestamp_ms,
  pcm_s16le,
  sample_rate=16000,
  channels=1
}

async frames_in(call)
async send_audio(call, frame)
async flush(call)
async close(call)

Production FreeSWITCH adapter должен получать media непрерывно через проверенный streaming media mechanism (media bug/WebSocket/RTP adapter), а не tail-read WAV file. Конкретный FS module выбрать по установленной production сборке и закрепить version/test; сам VoiceRuntime не зависит от модуля.

Внутренний audio contract после FreeSWITCH adapter всегда:

PCM signed 16-bit little-endian
mono
16000 Hz
20 ms frames

Любой PCMU/PCMA/Opus/G722/etc. нормализуется на edge. Неправильный format → media-unhealthy, не молчаливое STT.

uuid_record adapter можно оставить только в dev/ до прохождения streaming adapter tests, затем удалить.

G3 — VoiceRuntime становится единственным владельцем live call

Один CallSession actor/task на один звонок:

call_id
fs_uuid / transport_id
turn_id
generation_id
user_speaking
assistant_speaking
active_stt
active_llm
active_tts
playback_queue
inbound_seq/outbound_seq
started_at/last_activity

Обязательные invariants:

speech_start:

generation_id += 1;

flush outbound playback;

cancel active LLM/TTS;

продолжать принимать caller audio без потери начала.

Каждый LLM/TTS/audio result несёт call_id + turn_id + generation_id.

Перед каждым outbound audio send:

if frame.generation_id != session.generation_id: DROP

Stale audio played = 0.

turn_id = user turn identity; generation_id может меняться отдельно при cancellation/retry.

Session state живёт у одного worker до hangup. Redis — routing/lease/summary, не попытка мигрировать live RTP call между workers.

G4 — разделить STT / Agent / LLM / TTS правильно

STT service

Вынести Whisper из Agent/telephony process. Agent не загружает speech model.

STT API — streaming PCM:

open_stream(call_id, turn_id)
push(AudioFrame)
partial(text)
final(text, confidence, timestamps)
cancel()

STT benchmark на русской телефонии обязателен; модель выбирается по WER/critical-entity error + latency, а не по названию.

Agent service

Agent принимает ТЕКСТ, а не WAV:

begin_call(context)
turn_text(call_id, turn_id, generation_id, text, confidence)
→ stream reply text/sentences
action/tool events
end_call()

Внутри Agent:

Dialogue Manager;

SafetyEngine;

memory/context policy;

tool selection;

LLM provider client.

Agent НЕ делает playback, media, RTP, VAD, STT, TTS.

LLM

Local answers или OpenRouter/OpenAI-compatible backend — interchangeable provider. Model never loads inside Agent as emergency fallback. Failure → secondary provider or bounded scripted fallback.

TTS

TTS service принимает text chunks/sentences и возвращает streaming PCM/audio frames. Не создавать seg-0001.wav как основной transport.

synthesize_stream(call_id, generation_id, text)
→ AudioFrame...
cancel(generation_id)

G5 — persistence и recordings не участвуют в latency

VoiceRuntime/Agent emit только local event into durable spool/queue.

CallEvent -> durable spool -> PG/S3/Redis workers

Никакой network PG/S3/Redis операции до first audio.

У persistence должны быть:

stable event_id;

idempotent PG writes (UNIQUE event_id / upsert);

S3/Redis errors must propagate to retry;

persistent spool volume, не /tmp container filesystem;

retry/backoff/dead-letter;

independent sink queues, без cross-sink starvation;

metrics queue_depth/retry/dead_letter/oldest_event_age;

readiness/admission rule при spool failure.

Recordings — tee из media pipeline в async recorder; не transport между сервисами.

Retention: PG metadata удаляется только после подтверждённого удаления external/local PII. Failure → retry, metadata остаётся.

Migrations: один migration job. Existing migrations привести к однозначной последовательности; до production можно переименовать duplicate numeric prefix и дальше использовать monotonic IDs.

G6 — реальные телефонные номера и SIP trunk

Внешнему пользователю никогда не показывать extension 4400. Это internal app route.

Inbound

DID (+7... / +31... / etc.)
   -> SIP provider/trunk
   -> FreeSWITCH external profile
   -> normalize E.164 + caller CLI
   -> set channel vars:
      moss_did
      moss_caller_e164
      moss_call_id
      moss_direction=inbound
   -> transfer/park to production app route 4400
   -> VoiceRuntime attaches

DID/user/tenant mapping хранится в Product Core/DB, а не hardcoded dialplan. Для первого сервера допустим статический mapping config, но API contract сразу должен быть provider-neutral.

Outbound / система сама звонит

Не реализовывать через sleeps и не привязывать Core к Exolve API.

Scheduler/Workflow
  -> validate consent + quiet hours
  -> reserve voice capacity
  -> create CallAttempt(idempotency key)
  -> CallController
  -> ESL originate via configured SIP gateway to E.164
  -> FreeSWITCH events: progress/ringing/answer/hangup
  -> on answer same VoiceRuntime CallSession
  -> release capacity + persist result

Например внутренний controller делает originate через конкретный FreeSWITCH gateway, а provider credentials/CLI принадлежат infra config. Provider-specific REST API — optional adapter only if SIP trunk provider requires it.

При no-answer/busy/failure retry policy живёт в durable workflow, не в VoiceRuntime.

G7 — приложение использует то же ядро

Не делать отдельный «AI для приложения».

Product API отдельно от VoiceRuntime:

Auth
Users / households / elders
Consents
Schedules
Calls/history/summaries
Incidents
Family questions
Notifications
Audit

Мобильный/web voice adapter (WebRTC/WebSocket) конвертирует media в тот же AudioFrame contract и создаёт тот же CallSession. Dialogue/Safety/LLM/TTS общие с PSTN.

Telegram/WebApp оставить как prototype client и постепенно перевести на Product API/media adapter; не давать frontend прямые STT/LLM/TTS endpoints.

G8 — серверный deployment

Один Linux server / pilot (правильная первая production форма)

Public edge:

FreeSWITCH: SIP TLS/TCP/UDP по необходимости, RTP UDP range; public IP/NAT корректно настроены.

HTTPS 443: Product API/app gateway.

Private only:

ESL 8021 — bind localhost/private network only, strong password/firewall.

VoiceRuntime.

STT.

Agent.

LLM.

TTS.

PostgreSQL/Redis/S3.

workers.

На Linux FreeSWITCH либо как systemd service на host, либо host-network container; SIP/RTP ports и NAT должны быть явными. Не использовать Mac start_telephony.command как production launcher.

Create deploy/:

deploy/
  compose.dev.yml
  compose.prod.yml
  env.example
  systemd/ (если FS на host)
  prometheus/
  grafana/
infra/freeswitch/
  dialplan/
  sip_profiles/
  gateways/
  vars/

Secrets — secret manager/Docker secrets/systemd credentials. Никогда в repo/release ZIP.

Public firewall

Открывать наружу только реально нужные SIP/RTP/HTTPS ports. ESL/model/data ports — private. По возможности SIP ограничить IP ranges provider trunk. Поддержать TLS/SRTP, если trunk/provider это позволяет.

Масштабирование после пилота

Не масштабировать по total users, масштабировать по concurrent calls и model throughput.

Production cell:

FreeSWITCH + local VoiceRuntime pool
        -> STT pool
        -> Agent/LLM pool
        -> TTS pool

Call не мигрирует между cells во время разговора. Global admission/scheduler выбирает cell ДО inbound/outbound attach.

G9 — observability / SLO / load certification

Все operational logs structured и без transcript/PII. Correlation fields:

call_id
transport_id/fs_uuid
turn_id
generation_id
service
stage
latency_ms
error_code

Обязательные metrics:

active_calls
admission_rejected
speech_to_stt_final_ms
stt_final_to_llm_first_token_ms
tts_first_audio_ms
speech_end_to_first_audio_ms
barge_in_to_playback_stop_ms
stale_frame_drop_total
stale_frame_played_total (=0)
stt_no_speech_total
provider_timeout_total
queue_depth / oldest_event_age

Начальные product gates:

barge-in → Vera stops: p95 <= 300 ms;

speech_end → final STT: p95 <= 700–1000 ms;

speech_end → first audible Vera: p95 <= 1.5 s (hard target <=2 s on pilot if model stack cannot initially meet 1.5);

stale audio played: 0;

lost audible user turns in clean call: 0;

raw transcript in operational logs: 0;

release containing secret/recording: 0.

Capacity is measured, not guessed. Run 1/2/4/8/16/... concurrent calls until p95/SLO breaks; production admission limit is below measured knee point.

Обязательные tests / release gates

Unit: core/dialogue/safety/providers/session/generation.

Data integration: Postgres/Redis/S3 + migrations + persistence crash/replay/idempotency + retention failure/retry.

Model integration: STT/LLM/TTS real daemon contracts.

Media integration: FreeSWITCH adapter gets continuous inbound frames while assistant is speaking.

Real SIP E2E:

inbound DID/SIP call;

speech after greeting;

speech during greeting;

barge-in <=300 ms;

first word not clipped;

old generation never played;

10+ turns;

hangup cleanup.

Outbound E2E:

reserve capacity;

originate to controlled test number;

ringing/answered/no-answer/busy;

same VoiceRuntime on answer;

idempotent retry.

App media E2E: WebRTC/WebSocket adapter into same VoiceRuntime.

Load: concurrent calls + soak 30–60 min; p50/p95/p99 and resource graphs.

Failure drills: LLM down, TTS down, STT down, PG/Redis/S3 down, FreeSWITCH reconnect, worker restart, WAL replay.

Release: clean tagged commit only; build one immutable image digest; test/scan/deploy exactly that digest.

make release must refuse dirty worktree, archive requested commit/tag (not blindly HEAD), include source commit in manifest, scan built artifact, create SHA256 after deterministic contents.

Definition of Done — только после этого система считается server/product ready

В source/runtime нет Lua phone path и старого ESL POC.

4400 — единственный production SIP application route и идёт в VoiceRuntime.

Реальный caller audio принимается непрерывно во время Vera playback.

Barge-in работает <=300 ms и не обрезает начало фразы.

VoiceRuntime не использует WAV/seg-dir как inter-service realtime transport.

STT/Agent/LLM/TTS разделены контрактами; Agent принимает text, VoiceRuntime владеет media.

Inbound DID работает через SIP trunk.

Outbound scheduler/controller реально делает call через тот же FreeSWITCH/VoiceRuntime.

Mobile/web media использует тот же CallSession core.

PG/Redis/S3 не блокируют first-audio hot path.

Persistence crash/replay idempotent, retention гарантирован.

/live//ready truthful, model/data/media degradation visible.

Реальный SIP E2E и load tests входят в release gate.

Release создаётся только из clean tagged commit, без recordings/logs/secrets.

Есть измеренный capacity per server/cell; MOSS_MAX_CONCURRENT_CALLS выставлен по benchmark.

Запрещено

не добавлять новые костыли в moss_agent.lua;

не создавать второй телефонный runtime;

не делать отдельный brain для app/Telegram;

не использовать DB/S3 calls в voice latency path;

не сохранять compatibility facade бесконечно «на всякий случай»;

не объявлять feature готовым только по unit tests без real SIP/media acceptance.
Да. Я перечитал весь `MOSSVOICE_PRODUCTION_REFACTOR_SPEC.md` именно с вопросом: **«Если сейчас пойти по этому плану, не придётся ли через два месяца снова переписывать архитектуру?»**

Мой вердикт: **основа правильная примерно на 85–90%. Полностью выбрасывать её или придумывать ещё одну архитектуру не надо.** Но я бы **до начала большого рефакторинга внёс несколько принципиальных поправок**. Они не меняют направление — они фиксируют границы, чтобы агент снова не построил «почти правильную» систему.

## Главная схема — правильная

Вот это оставляем как архитектурный закон:

```text
PSTN / SIP / приложение
        │
        ▼
   Media Edge
        │
        ▼
   VoiceRuntime
        │
 ┌──────┼──────┐
 ▼      ▼      ▼
STT   Agent   TTS
        │
       LLM
        │
 Dialogue / Safety / Tools
        │
        ▼
   async events
        │
 PG / Redis / S3 / Workflow
```

И особенно правильно:

```text
FreeSWITCH = SIP/RTP/телефония
VoiceRuntime = живой realtime-разговор
Agent = смысл диалога
STT/LLM/TTS = модельные компоненты
Product Core = данные и бизнес-функции
```

**Вот эту декомпозицию больше менять не надо.**

FreeSWITCH Event Socket действительно подходит для управления вызовами, подписки на события, originate, управления call legs и playback; я бы рассматривал ESL как **control plane**, а не пытался снова протащить через него сырой realtime PCM. Это соответствует назначению Event Socket в официальной документации FreeSWITCH. ([SignalWire][1])

---

# Но поправка №1 — не делать из проекта 15 микросервисов прямо сейчас

В текущем ТЗ написано:

```text
VoiceRuntime
STT service
Agent service
LLM service
TTS service
```

**Логические границы правильные.**

Но я бы изменил формулировку:

> Отдельный контракт ≠ обязательно отдельный контейнер/процесс на первом этапе.

Это важно.

Иначе агент сейчас построит:

```text
VoiceRuntime → HTTP → STT
             → HTTP → Agent
                    → HTTP → LLM
             → HTTP → TTS
```

и вы получите ещё четыре network hop в критическом voice path.

Правильное корпоративное правило:

```text
Контракты независимые.
Deployment независимый при необходимости.
```

Но на пилоте можно иметь:

```text
VoiceRuntime process
   ├─ STT client
   ├─ Agent client/library
   └─ TTS client
```

или colocated services на одной машине/Unix socket.

А когда нагрузка потребует:

```text
STT pool
LLM pool
TTS pool
```

мы масштабируем их отдельно **без изменения контрактов**.

### Поэтому изменить G4

Не:

> обязательно всё немедленно вынести в отдельные network services.

А:

> STT/Agent/LLM/TTS имеют независимые интерфейсы и lifecycle; deployment topology не является частью business-кода.

Это существенно уменьшит вероятность ещё одного рефакторинга.

---

# Поправка №2 — нужен ОДИН хозяин состояния звонка

Это критически важно.

В новой архитектуре нельзя снова получить:

```text
часть состояния в VoiceRuntime
часть в Agent
часть в Redis
часть в FreeSWITCH
```

Надо разделить владение.

### `VoiceRuntime / CallSession` владеет только realtime-состоянием

```text
call lifecycle
media state
turn_id
generation_id
user_speaking
assistant_spea
MossVoice — Production Consolidation & Server Deployment Spec

Задача агенту

Это НЕ задача «починить один звонок». Нужно привести репозиторий к единственной production-архитектуре, удалить конкурирующие legacy/POC пути и подготовить систему к серверному деплою с реальными входящими/исходящими телефонными номерами и будущим приложением.

Работать по gate'ам ниже. Каждый gate заканчивается тестами и отдельным commit. Не переходить к следующему gate, если текущий не зелёный. Не добавлять новые пользовательские функции, промпты или сценарии до завершения G0–G7.

Конечная архитектура — единственный источник истины

PSTN / мобильный номер / SIP trunk
                │
                ▼
        FreeSWITCH Media Edge
        - SIP/RTP/NAT/codecs
        - inbound DID / outbound gateway
        - answer/hangup/DTMF
        - media control
                │
        continuous bidirectional audio
                │
                ▼
             VoiceRuntime
        - 1 CallSession actor / call
        - PCM16 mono 16 kHz / 20 ms
        - VAD / endpointing
        - barge-in
        - turn_id / generation_id
        - playback queue + stale-frame drop
        - no business SQL/S3 in hot path
           │        │        │
           ▼        ▼        ▼
          STT      Agent     TTS
                    │
                    ▼
                   LLM
                    │
          Dialogue / Safety / Tools
                    │
                    └──── async CallEvents ────► persistence/workflow

Product API / Mobile App
        │
        ├── schedules/history/incidents/family/auth
        │
        └── WebRTC/WebSocket media adapter ───► SAME VoiceRuntime

Правило: FreeSWITCH = телефония/media edge. VoiceRuntime = живой голос. Agent = текстовый диалог и политика. STT/LLM/TTS = отдельные model failure domains. PostgreSQL/Redis/S3 = не стоят между speech_end и first_audio.

G0 — очистить репозиторий и запретить legacy в production

Удалить из репозитория/runtime artifact

Удалить (Git хранит историю, отдельный runtime legacy не нужен):

telephony/esl_stream.py — старый ESL POC; заменён voice_runtime/.

telephony/moss_agent.lua — после переключения 4400 на VoiceRuntime. Не оставлять production fallback.

telephony/tests/runtime_selftest.py — старый тест Lua/4400; заменить SIP VoiceRuntime E2E.

release/ и release/mossvoice-* — generated artifacts не хранятся в source tree.

telephony/calls/ — recordings/results/logs не принадлежат репозиторию.

telephony/*.supervisor.log, telephony/calls/*.log, *.pid, runtime json state.

__MACOSX/, .DS_Store, __pycache__/, *.pyc, .tmp_postfix_check.py.

docker/.env из любого release bundle; локально допустим только ignored secret file, в репо только .env.example.

voice-bench/ и voice-lab/ оставить как dev tooling, но перенести под tools/ или исключить из production image/release.

Убрать ложные legacy interfaces

telephony/legacy/call_agent_http.py не должен оставаться legacy, если он используется production agent API. Перенести его в канонический модуль (telephony/api/http.py или новый package), обновить imports, затем удалить telephony/legacy/.

telephony/call_agent.py сейчас compatibility facade. Production entrypoint должен быть один. Перевести supervisor/docker на canonical module entrypoint; после миграции тестов удалить facade.

telephony/worker/ и telephony/workers/ слишком легко спутать. Разделить именами:

agent_service/ — realtime/text Agent API;

workers/ — migrate/outbox/retention/background.

moss_providers.py и adapters/* не должны содержать параллельные реализации одного и того же provider stack. Оставить один contracts layer + один набор concrete adapters. Целевая структура:

providers/contracts.py — ABC/protocols/errors;

providers/stt.py, providers/llm.py, providers/tts.py, providers/storage.py — implementations/factories.
Удалить дубли после перевода imports/tests.

Package correctness

Добавить нормальный Python package/build (pyproject.toml или эквивалент). Production не должен зависеть от cwd и _paths.py hacks. Целевые entrypoints запускаются через modules, например:

python -m mossvoice.agent
python -m mossvoice.voice_runtime
python -m mossvoice.workers.migrate

Не обязательно делать массовый rename в одном commit: сначала canonicalize runtime paths, затем package move, с тестами между шагами.

G1 — один SIP route; 4400 = production VoiceRuntime

Текущая проблема: 4400 идёт в Lua, VoiceRuntime — 4401. Это удалить.

Dialplan

telephony/moss_dialplan.xml / будущий infra/freeswitch/dialplan/mossvoice.xml:

4400 — основной internal application extension: answer -> park, никаких Lua scripts.

4402 — loopback/E2E test only, недоступен из внешнего trunk.

4401 удалить полностью после миграции.

voice_runtime/runtime.py должен attach к 4400 и test 4402. Никаких references 4401 в production docs/tests.

После G1 grep по source (кроме migration notes) не должен находить production references на moss_agent.lua, esl_stream.py, 4401.

Установка FreeSWITCH конфигурации

Создать один idempotent installer/config deploy:

scripts/install_freeswitch.sh

Он обязан:

установить/sync dialplan + SIP gateway configs из repo;

установить глобальные variables/config, не абсолютные developer paths;

выполнить reloadxml;

проверить ESL connectivity;

проверить VoiceRuntime /ready;

вывести fail-fast, если production route не соответствует ожидаемому version/hash.

Mac helper start_telephony.command и custom supervisor — только dev tooling; перенести в dev/mac/, исключить из production image. На Linux production — systemd/container orchestrator.

G2 — заменить file-tail media на настоящий streaming MediaAdapter

voice_runtime/ использовать как основу CallSession/VAD/generation, но текущий uuid_record + growing WAV — только переходный dev adapter, не production media plane.

Создать интерфейс MediaAdapter:

AudioFrame {
  call_id,
  seq,
  timestamp_ms,
  pcm_s16le,
  sample_rate=16000,
  channels=1
}

async frames_in(call)
async send_audio(call, frame)
async flush(call)
async close(call)

Production FreeSWITCH adapter должен получать media непрерывно через проверенный streaming media mechanism (media bug/WebSocket/RTP adapter), а не tail-read WAV file. Конкретный FS module выбрать по установленной production сборке и закрепить version/test; сам VoiceRuntime не зависит от модуля.

Внутренний audio contract после FreeSWITCH adapter всегда:

PCM signed 16-bit little-endian
mono
16000 Hz
20 ms frames

Любой PCMU/PCMA/Opus/G722/etc. нормализуется на edge. Неправильный format → media-unhealthy, не молчаливое STT.

uuid_record adapter можно оставить только в dev/ до прохождения streaming adapter tests, затем удалить.

G3 — VoiceRuntime становится единственным владельцем live call

Один CallSession actor/task на один звонок:

call_id
fs_uuid / transport_id
turn_id
generation_id
user_speaking
assistant_speaking
active_stt
active_llm
active_tts
playback_queue
inbound_seq/outbound_seq
started_at/last_activity

Обязательные invariants:

speech_start:

generation_id += 1;

flush outbound playback;

cancel active LLM/TTS;

продолжать принимать caller audio без потери начала.

Каждый LLM/TTS/audio result несёт call_id + turn_id + generation_id.

Перед каждым outbound audio send:

if frame.generation_id != session.generation_id: DROP

Stale audio played = 0.

turn_id = user turn identity; generation_id может меняться отдельно при cancellation/retry.

Session state живёт у одного worker до hangup. Redis — routing/lease/summary, не попытка мигрировать live RTP call между workers.

G4 — разделить STT / Agent / LLM / TTS правильно

STT service

Вынести Whisper из Agent/telephony process. Agent не загружает speech model.

STT API — streaming PCM:

open_stream(call_id, turn_id)
push(AudioFrame)
partial(text)
final(text, confidence, timestamps)
cancel()

STT benchmark на русской телефонии обязателен; модель выбирается по WER/critical-entity error + latency, а не по названию.

Agent service

Agent принимает ТЕКСТ, а не WAV:

begin_call(context)
turn_text(call_id, turn_id, generation_id, text, confidence)
→ stream reply text/sentences
action/tool events
end_call()

Внутри Agent:

Dialogue Manager;

SafetyEngine;

memory/context policy;

tool selection;

LLM provider client.

Agent НЕ делает playback, media, RTP, VAD, STT, TTS.

LLM

Local answers или OpenRouter/OpenAI-compatible backend — interchangeable provider. Model never loads inside Agent as emergency fallback. Failure → secondary provider or bounded scripted fallback.

TTS

TTS service принимает text chunks/sentences и возвращает streaming PCM/audio frames. Не создавать seg-0001.wav как основной transport.

synthesize_stream(call_id, generation_id, text)
→ AudioFrame...
cancel(generation_id)

G5 — persistence и recordings не участвуют в latency

VoiceRuntime/Agent emit только local event into durable spool/queue.

CallEvent -> durable spool -> PG/S3/Redis workers

Никакой network PG/S3/Redis операции до first audio.

У persistence должны быть:

stable event_id;

idempotent PG writes (UNIQUE event_id / upsert);

S3/Redis errors must propagate to retry;

persistent spool volume, не /tmp container filesystem;

retry/backoff/dead-letter;

independent sink queues, без cross-sink starvation;

metrics queue_depth/retry/dead_letter/oldest_event_age;

readiness/admission rule при spool failure.

Recordings — tee из media pipeline в async recorder; не transport между сервисами.

Retention: PG metadata удаляется только после подтверждённого удаления external/local PII. Failure → retry, metadata остаётся.

Migrations: один migration job. Existing migrations привести к однозначной последовательности; до production можно переименовать duplicate numeric prefix и дальше использовать monotonic IDs.

G6 — реальные телефонные номера и SIP trunk

Внешнему пользователю никогда не показывать extension 4400. Это internal app route.

Inbound

DID (+7... / +31... / etc.)
   -> SIP provider/trunk
   -> FreeSWITCH external profile
   -> normalize E.164 + caller CLI
   -> set channel vars:
      moss_did
      moss_caller_e164
      moss_call_id
      moss_direction=inbound
   -> transfer/park to production app route 4400
   -> VoiceRuntime attaches

DID/user/tenant mapping хранится в Product Core/DB, а не hardcoded dialplan. Для первого сервера допустим статический mapping config, но API contract сразу должен быть provider-neutral.

Outbound / система сама звонит

Не реализовывать через sleeps и не привязывать Core к Exolve API.

Scheduler/Workflow
  -> validate consent + quiet hours
  -> reserve voice capacity
  -> create CallAttempt(idempotency key)
  -> CallController
  -> ESL originate via configured SIP gateway to E.164
  -> FreeSWITCH events: progress/ringing/answer/hangup
  -> on answer same VoiceRuntime CallSession
  -> release capacity + persist result

Например внутренний controller делает originate через конкретный FreeSWITCH gateway, а provider credentials/CLI принадлежат infra config. Provider-specific REST API — optional adapter only if SIP trunk provider requires it.

При no-answer/busy/failure retry policy живёт в durable workflow, не в VoiceRuntime.

G7 — приложение использует то же ядро

Не делать отдельный «AI для приложения».

Product API отдельно от VoiceRuntime:

Auth
Users / households / elders
Consents
Schedules
Calls/history/summaries
Incidents
Family questions
Notifications
Audit

Мобильный/web voice adapter (WebRTC/WebSocket) конвертирует media в тот же AudioFrame contract и создаёт тот же CallSession. Dialogue/Safety/LLM/TTS общие с PSTN.

Telegram/WebApp оставить как prototype client и постепенно перевести на Product API/media adapter; не давать frontend прямые STT/LLM/TTS endpoints.

G8 — серверный deployment

Один Linux server / pilot (правильная первая production форма)

Public edge:

FreeSWITCH: SIP TLS/TCP/UDP по необходимости, RTP UDP range; public IP/NAT корректно настроены.

HTTPS 443: Product API/app gateway.

Private only:

ESL 8021 — bind localhost/private network only, strong password/firewall.

VoiceRuntime.

STT.

Agent.

LLM.

TTS.

PostgreSQL/Redis/S3.

workers.

На Linux FreeSWITCH либо как systemd service на host, либо host-network container; SIP/RTP ports и NAT должны быть явными. Не использовать Mac start_telephony.command как production launcher.

Create deploy/:

deploy/
  compose.dev.yml
  compose.prod.yml
  env.example
  systemd/ (если FS на host)
  prometheus/
  grafana/
infra/freeswitch/
  dialplan/
  sip_profiles/
  gateways/
  vars/

Secrets — secret manager/Docker secrets/systemd credentials. Никогда в repo/release ZIP.

Public firewall

Открывать наружу только реально нужные SIP/RTP/HTTPS ports. ESL/model/data ports — private. По возможности SIP ограничить IP ranges provider trunk. Поддержать TLS/SRTP, если trunk/provider это позволяет.

Масштабирование после пилота

Не масштабировать по total users, масштабировать по concurrent calls и model throughput.

Production cell:

FreeSWITCH + local VoiceRuntime pool
        -> STT pool
        -> Agent/LLM pool
        -> TTS pool

Call не мигрирует между cells во время разговора. Global admission/scheduler выбирает cell ДО inbound/outbound attach.

G9 — observability / SLO / load certification

Все operational logs structured и без transcript/PII. Correlation fields:

call_id
transport_id/fs_uuid
turn_id
generation_id
service
stage
latency_ms
error_code

Обязательные metrics:

active_calls
admission_rejected
speech_to_stt_final_ms
stt_final_to_llm_first_token_ms
tts_first_audio_ms
speech_end_to_first_audio_ms
barge_in_to_playback_stop_ms
stale_frame_drop_total
stale_frame_played_total (=0)
stt_no_speech_total
provider_timeout_total
queue_depth / oldest_event_age

Начальные product gates:

barge-in → Vera stops: p95 <= 300 ms;

speech_end → final STT: p95 <= 700–1000 ms;

speech_end → first audible Vera: p95 <= 1.5 s (hard target <=2 s on pilot if model stack cannot initially meet 1.5);

stale audio played: 0;

lost audible user turns in clean call: 0;

raw transcript in operational logs: 0;

release containing secret/recording: 0.

Capacity is measured, not guessed. Run 1/2/4/8/16/... concurrent calls until p95/SLO breaks; production admission limit is below measured knee point.

Обязательные tests / release gates

Unit: core/dialogue/safety/providers/session/generation.

Data integration: Postgres/Redis/S3 + migrations + persistence crash/replay/idempotency + retention failure/retry.

Model integration: STT/LLM/TTS real daemon contracts.

Media integration: FreeSWITCH adapter gets continuous inbound frames while assistant is speaking.

Real SIP E2E:

inbound DID/SIP call;

speech after greeting;

speech during greeting;

barge-in <=300 ms;

first word not clipped;

old generation never played;

10+ turns;

hangup cleanup.

Outbound E2E:

reserve capacity;

originate to controlled test number;

ringing/answered/no-answer/busy;

same VoiceRuntime on answer;

idempotent retry.

App media E2E: WebRTC/WebSocket adapter into same VoiceRuntime.

Load: concurrent calls + soak 30–60 min; p50/p95/p99 and resource graphs.

Failure drills: LLM down, TTS down, STT down, PG/Redis/S3 down, FreeSWITCH reconnect, worker restart, WAL replay.

Release: clean tagged commit only; build one immutable image digest; test/scan/deploy exactly that digest.

make release must refuse dirty worktree, archive requested commit/tag (not blindly HEAD), include source commit in manifest, scan built artifact, create SHA256 after deterministic contents.

Definition of Done — только после этого система считается server/product ready

В source/runtime нет Lua phone path и старого ESL POC.

4400 — единственный production SIP application route и идёт в VoiceRuntime.

Реальный caller audio принимается непрерывно во время Vera playback.

Barge-in работает <=300 ms и не обрезает начало фразы.

VoiceRuntime не использует WAV/seg-dir как inter-service realtime transport.

STT/Agent/LLM/TTS разделены контрактами; Agent принимает text, VoiceRuntime владеет media.

Inbound DID работает через SIP trunk.

Outbound scheduler/controller реально делает call через тот же FreeSWITCH/VoiceRuntime.

Mobile/web media использует тот же CallSession core.

PG/Redis/S3 не блокируют first-audio hot path.

Persistence crash/replay idempotent, retention гарантирован.

/live//ready truthful, model/data/media degradation visible.

Реальный SIP E2E и load tests входят в release gate.

Release создаётся только из clean tagged commit, без recordings/logs/secrets.

Есть измеренный capacity per server/cell; MOSS_MAX_CONCURRENT_CALLS выставлен по benchmark.

Запрещено

не добавлять новые костыли в moss_agent.lua;

не создавать второй телефонный runtime;

не делать отдельный brain для app/Telegram;

не использовать DB/S3 calls в voice latency path;

не сохранять compatibility facade бесконечно «на всякий случай»;

не объявлять feature готовым только по unit tests без real SIP/media acceptance.
Да. Я перечитал весь `MOSSVOICE_PRODUCTION_REFACTOR_SPEC.md` именно с вопросом: **«Если сейчас пойти по этому плану, не придётся ли через два месяца снова переписывать архитектуру?»**

Мой вердикт: **основа правильная примерно на 85–90%. Полностью выбрасывать её или придумывать ещё одну архитектуру не надо.** Но я бы **до начала большого рефакторинга внёс несколько принципиальных поправок**. Они не меняют направление — они фиксируют границы, чтобы агент снова не построил «почти правильную» систему.

## Главная схема — правильная

Вот это оставляем как архитектурный закон:

```text
PSTN / SIP / приложение
        │
        ▼
   Media Edge
        │
        ▼
   VoiceRuntime
        │
 ┌──────┼──────┐
 ▼      ▼      ▼
STT   Agent   TTS
        │
       LLM
        │
 Dialogue / Safety / Tools
        │
        ▼
   async events
        │
 PG / Redis / S3 / Workflow
```

И особенно правильно:

```text
FreeSWITCH = SIP/RTP/телефония
VoiceRuntime = живой realtime-разговор
Agent = смысл диалога
STT/LLM/TTS = модельные компоненты
Product Core = данные и бизнес-функции
```

**Вот эту декомпозицию больше менять не надо.**

FreeSWITCH Event Socket действительно подходит для управления вызовами, подписки на события, originate, управления call legs и playback; я бы рассматривал ESL как **control plane**, а не пытался снова протащить через него сырой realtime PCM. Это соответствует назначению Event Socket в официальной документации FreeSWITCH. ([SignalWire][1])

---

# Но поправка №1 — не делать из проекта 15 микросервисов прямо сейчас

В текущем ТЗ написано:

```text
VoiceRuntime
STT service
Agent service
LLM service
TTS service
```

**Логические границы правильные.**

Но я бы изменил формулировку:

> Отдельный контракт ≠ обязательно отдельный контейнер/процесс на первом этапе.

Это важно.

Иначе агент сейчас построит:

```text
VoiceRuntime → HTTP → STT
             → HTTP → Agent
                    → HTTP → LLM
             → HTTP → TTS
```

и вы получите ещё четыре network hop в критическом voice path.

Правильное корпоративное правило:

```text
Контракты независимые.
Deployment независимый при необходимости.
```

Но на пилоте можно иметь:

```text
VoiceRuntime process
   ├─ STT client
   ├─ Agent client/library
   └─ TTS client
```

или colocated services на одной машине/Unix socket.

А когда нагрузка потребует:

```text
STT pool
LLM pool
TTS pool
```

мы масштабируем их отдельно **без изменения контрактов**.

### Поэтому изменить G4

Не:

> обязательно всё немедленно вынести в отдельные network services.

А:

> STT/Agent/LLM/TTS имеют независимые интерфейсы и lifecycle; deployment topology не является частью business-кода.

Это существенно уменьшит вероятность ещё одного рефакторинга.

---

# Поправка №2 — нужен ОДИН хозяин состояния звонка

Это критически важно.

В новой архитектуре нельзя снова получить:

```text
часть состояния в VoiceRuntime
часть в Agent
часть в Redis
часть в FreeSWITCH
```

Надо разделить владение.

### `VoiceRuntime / CallSession` владеет только realtime-состоянием

```text
call lifecycle
media state
turn_id
generation_id
user_speaking
assistant_speaДа. Я перечитал весь `MOSSVOICE_PRODUCTION_REFACTOR_SPEC.md` именно с вопросом: **«Если сейчас пойти по этому плану, не придётся ли через два месяца снова переписывать архитектуру?»**

Мой вердикт: **основа правильная примерно на 85–90%. Полностью выбрасывать её или придумывать ещё одну архитектуру не надо.** Но я бы **до начала большого рефакторинга внёс несколько принципиальных поправок**. Они не меняют направление — они фиксируют границы, чтобы агент снова не построил «почти правильную» систему.

## Главная схема — правильная

Вот это оставляем как архитектурный закон:

```text
PSTN / SIP / приложение
        │
        ▼
   Media Edge
        │
        ▼
   VoiceRuntime
        │
 ┌──────┼──────┐
 ▼      ▼      ▼
STT   Agent   TTS
        │
       LLM
        │
 Dialogue / Safety / Tools
        │
        ▼
   async events
        │
 PG / Redis / S3 / Workflow
```

И особенно правильно:

```text
FreeSWITCH = SIP/RTP/телефония
VoiceRuntime = живой realtime-разговор
Agent = смысл диалога
STT/LLM/TTS = модельные компоненты
Product Core = данные и бизнес-функции
```

**Вот эту декомпозицию больше менять не надо.**

FreeSWITCH Event Socket действительно подходит для управления вызовами, подписки на события, originate, управления call legs и playback; я бы рассматривал ESL как **control plane**, а не пытался снова протащить через него сырой realtime PCM. Это соответствует назначению Event Socket в официальной документации FreeSWITCH. ([SignalWire][1])

---

# Но поправка №1 — не делать из проекта 15 микросервисов прямо сейчас

В текущем ТЗ написано:

```text
VoiceRuntime
STT service
Agent service
LLM service
TTS service
```

**Логические границы правильные.**

Но я бы изменил формулировку:

> Отдельный контракт ≠ обязательно отдельный контейнер/процесс на первом этапе.

Это важно.

Иначе агент сейчас построит:

```text
VoiceRuntime → HTTP → STT
             → HTTP → Agent
                    → HTTP → LLM
             → HTTP → TTS
```

и вы получите ещё четыре network hop в критическом voice path.

Правильное корпоративное правило:

```text
Контракты независимые.
Deployment независимый при необходимости.
```

Но на пилоте можно иметь:

```text
VoiceRuntime process
   ├─ STT client
   ├─ Agent client/library
   └─ TTS client
```

или colocated services на одной машине/Unix socket.

А когда нагрузка потребует:

```text
STT pool
LLM pool
TTS pool
```

мы масштабируем их отдельно **без изменения контрактов**.

### Поэтому изменить G4

Не:

> обязательно всё немедленно вынести в отдельные network services.

А:

> STT/Agent/LLM/TTS имеют независимые интерфейсы и lifecycle; deployment topology не является частью business-кода.

Это существенно уменьшит вероятность ещё одного рефакторинга.

---

# Поправка №2 — нужен ОДИН хозяин состояния звонка

Это критически важно.

В новой архитектуре нельзя снова получить:

```text
часть состояния в VoiceRuntime
часть в Agent
часть в Redis
часть в FreeSWITCH
```

Надо разделить владение.

### `VoiceRuntime / CallSession` владеет только realtime-состоянием

```text
call lifecycle
media state
turn_id
generation_id
user_speaking
assistant_speaking
VAD
active STT
active LLM request
active TTS request
playback
cancellation
timeouts
```

### `Agent / DialogueSession` владеет смыслом разговора

```text
mode
agenda
check-in state
interrupt/resume
conversation history
safety state
memory context
tools
```

### Product Core владеет durable business data

```text
users
elder
family
schedule
consent
call history
incidents
memory records
```

Никогда:

```text
Redis = ещё один authoritative CallSession
```

Redis только:

```text
routing
lease
cache
capacity
ephemeral lookup
```

---

# Поправка №3 — формализовать две state machine

Это нужно сделать **до написания VoiceRuntime**.

Иначе снова появится 50 `if` вокруг barge-in.

## Call lifecycle

Например:

```text
NEW
 ↓
ADMITTED
 ↓
CONNECTING
 ↓
ANSWERED
 ↓
ACTIVE
 ↓
ENDING
 ↓
CLOSED
```

Для outbound:

```text
NEW
↓
ADMITTED
↓
DIALING
↓
RINGING
↓
ANSWERED
↓
ACTIVE
```

Дополнительно:

```text
FAILED
REJECTED
NO_ANSWER
BUSY
```

## Turn lifecycle

Отдельно:

```text
IDLE
 ↓
USER_SPEAKING
 ↓
ENDPOINTING
 ↓
PROCESSING
 ↓
ASSISTANT_SPEAKING
 ↓
IDLE
```

И barge-in:

```text
ASSISTANT_SPEAKING
        │
        │ user speech
        ▼
    INTERRUPTING
        ↓
 invalidate generation
        ↓
   USER_SPEAKING
```

Call lifecycle и turn lifecycle **не смешивать**.

Вот это сильно уменьшит количество будущих багов.

---

# Поправка №4 — уточнить `turn_id` и `generation_id`

В документе направление правильное, но семантика ещё недостаточно строгая.

Я бы зафиксировал окончательно:

### `call_id`

Не меняется весь звонок.

### `turn_id`

Новый осмысленный пользовательский turn.

Например:

```text
turn 15:
"Нет, подождите, я имела в виду завтра"
```

### `generation_id`

Версия assistant output, которая имеет право звучать.

Например:

```text
turn_id = 15
generation = 32
```

Вера начинает отвечать.

LLM/TTS пришлось retry:

```text
turn_id = 15
generation = 33
```

Или пользователь перебил:

```text
generation 33 INVALID
generation = 34
```

---

## Правило

На подтверждённом `speech_start`:

```text
turn_id++
generation_id++
```

Старый assistant output становится invalid.

Если делаем retry ответа на **тот же user turn**:

```text
turn_id stays
generation_id++
```

Таким образом они перестают быть двумя одинаковыми счётчиками.

---

# Поправка №5 — нужен pre-roll, иначе снова будет «она не слышит»

Вот этого в документе пока недостаточно.

VAD узнаёт о речи **после того**, как пользователь уже начал говорить.

Например:

```text
0 ms     человек: "Нет, подождите"
80 ms    VAD ещё думает
120 ms   VAD: SPEECH_START
```

Если STT начать собирать только с 120 ms:

```text
"Нет"
```

может отрезаться.

Нужен постоянно работающий circular buffer примерно:

```text
300–500 ms inbound PCM
```

Когда VAD подтвердил speech:

```text
STT получает:
pre-roll + current frames
```

Схема:

```text
inbound audio
████████████████████████

      VAD start
          ↑

buffer:
   ← 300 ms →

STT:
████████████████████████
↑
начинается ДО VAD onset
```

### Это обязательный production invariant

```text
first word clipped = 0
```

Без этого вы снова получите:

> «Вера постоянно не слышит первое слово».

---

# Поправка №6 — два разных VAD поведения

Тоже важно.

Нельзя использовать один и тот же VAD threshold для:

```text
перебить Веру
```

и:

```text
решить, что пользователь закончил предложение
```

Нужны:

### Fast onset detector

Для barge-in.

Пример:

```text
80–150 ms подтверждённой речи
```

→ stop Vera.

### Endpoint detector

Для конца фразы:

```text
400–800 ms тишины
```

в зависимости от речи.

Иначе:

> «Да... сегодня вроде нормально»

будет разрезано после `Да`.

---

# Поправка №7 — `flush()` должен иметь строгую гарантию

В документе уже есть:

```text
flush outbound playback
```

Но для вашего старого бага этого недостаточно.

Нужно определить контракт:

```python
await media.flush(generation_id)
```

означает:

> после завершения `flush()` ни один sample старой generation больше физически не может попасть пользователю.

Не просто:

```text
очистили Python queue
```

А:

```text
Python queue
FreeSWITCH playback buffer
media module buffer
```

всё старое отменено.

Иначе:

```text
generation_id правильный
```

но 500 ms старого TTS уже сидит в FreeSWITCH buffer и продолжит звучать.

### Главный invariant

```text
stale_audio_played_total = 0
```

---

# Поправка №8 — MediaAdapter должен включать backpressure

Сейчас контракт:

```text
frames_in
send_audio
flush
close
```

Хороший.

Добавить обязательно:

```text
bounded inbound buffer
bounded outbound buffer
sequence numbers
frame-loss detection
queue depth
```

Никаких:

```python
asyncio.Queue()
```

без `maxsize`.

20 ms audio — это 50 frames/sec.

Если STT завис на 10 секунд:

```text
500 frames
```

накопятся очень быстро.

Нужно определить policy.

Например inbound:

```text
buffer max 2 sec
```

Если больше:

```text
MEDIA_BACKPRESSURE
```

и session деградирует/заканчивается контролируемо.

Не бесконечно ест память.

---

# Поправка №9 — ESL оставить только control plane

Это надо написать прямо большими буквами.

```text
ESL
=
call events + commands
```

Например:

```text
CHANNEL_CREATE
CHANNEL_ANSWER
CHANNEL_HANGUP
originate
break
DTMF
variables
```

FreeSWITCH действительно предоставляет эти lifecycle/media events через event system/Event Socket. ([SignalWire][1])

Но:

```text
raw 20ms PCM
```

идёт по **отдельному MediaAdapter**.

Не через:

```text
ESL event loop
```

Это именно тот архитектурный тупик, в который уже попал старый `esl_stream.py`.

---

# Поправка №10 — не фиксировать конкретный FreeSWITCH media module в архитектуре

Вот здесь документ сейчас написан правильно:

> media bug/WebSocket/RTP adapter — выбрать по production build.

Так оставить.

Не надо сейчас писать:

> обязательно mod_X.

Потому что потом выяснится, что в вашей Linux сборке он:

```text
не пакетируется
устарел
односторонний
не умеет flush
```

Правильная зависимость:

```text
VoiceRuntime
      │
 MediaAdapter protocol
      │
 FreeSWITCH implementation
```

Конкретную implementation можно поменять без изменения VoiceRuntime.

FreeSWITCH сам по себе умеет разные media modes и работает как RTP/media edge, поэтому эта граница естественная. ([SignalWire][2])

---

# Поправка №11 — inbound admission должен быть ДО `answer`

Вот это я бы обязательно изменил в G1/G6.

Сейчас:

```text
INVITE
↓
answer
↓
park
↓
VoiceRuntime
```

Проблема:

VoiceRuntime capacity закончилась.

Но человек уже:

```text
поднял трубку
```

и слышит тишину.

---

## Правильно

```text
INVITE
↓
resolve DID
↓
check runtime ready
↓
reserve capacity
↓
attach CallSession
↓
только потом ANSWER
↓
immediately greeting
```

Если capacity нет:

```text
486 Busy
503
fallback route
```

в зависимости от продукта.

### То же правило уже есть у outbound

И должно быть симметрично для inbound.

---

# Поправка №12 — `4400` не должен стать архитектурным API

Для первого FreeSWITCH:

```text
4400
```

абсолютно нормально.

Но не надо хардкодить его по всему проекту.

Нужно:

```text
MOSS_APP_EXTENSION=4400
```

или конфиг:

```yaml
freeswitch:
  application_extension: 4400
```

Потому что 4400 — implementation detail FreeSWITCH.

Архитектура:

```text
MossVoice application route
```

а не:

```text
4400 навечно
```

---

# Поправка №13 — приложение использует тот же CORE, но не обязательно тот же серверный процесс

В документе:

> SAME VoiceRuntime

Идея правильная.

Но формулировка может заставить разработчика соединить всё с одним process.

Лучше:

> same VoiceRuntime implementation/session contract.

Например:

```text
PSTN cell:
FreeSWITCH → VoiceRuntime A

WebRTC:
Web Gateway → VoiceRuntime B
```

Но оба используют:

```text
одинаковый CallSession
одинаковый Agent
одинаковый generation contract
одинаковый STT/TTS contract
```

Это позволит независимо масштабировать PSTN и app traffic.

---

# Поправка №14 — versioning внутренних контрактов

Это одна из самых важных «корпоративных» вещей, которой пока нет в ТЗ.

Например `AudioFrame` сегодня:

```json
{
  "call_id": "...",
  "seq": 1,
  "pcm": "..."
}
```

Через 6 месяцев понадобится:

```text
codec metadata
clock timestamp
flags
trace_id
```

Если schema никак не versioned, снова массовый рефакторинг.

Нужно:

```text
protocol_version
```

для основных interfaces.

Например:

```text
MediaProtocol v1
AgentProtocol v1
STTProtocol v1
TTSProtocol v1
CallEvent v1
```

Не обязательно protobuf.

Можно JSON/msgpack/gRPC.

Но compatibility rules должны существовать.

Также `/ready`:

```json
{
  "service": "mossvoice-stt",
  "protocol": 1,
  "ready": true,
  "model_revision": "..."
}
```

Тогда несовместимая версия не подключится случайно.

---

# Поправка №15 — correlation/trace с первого дня

К текущим:

```text
call_id
turn_id
generation_id
```

добавить:

```text
trace_id
```

и при необходимости:

```text
span_id
```

Тогда один turn видно через:

```text
VoiceRuntime
STT
Agent
LLM
TTS
Persistence
```

Но transcript не нужен.

---

# Поправка №16 — отдельная critical-event lane

Это особенно важно для такого продукта.

Обычный event:

```text
"turn persisted"
```

может пережить retry несколько минут.

Но:

```text
safety incident
```

должен иметь отдельный приоритет.

Я бы определил:

```text
CallEvent.NORMAL
CallEvent.CRITICAL
```

Critical:

```text
local durable WAL
↓
high priority worker/outbox
↓
family notification/workflow
```

Voice hot path всё равно не ждёт внешнюю сеть.

Но событие не стоит за 20 тысячами S3 uploads.

---

# Поправка №17 — deploy должен уметь drain

Обычно про это вспоминают слишком поздно.

У вас 50 живых разговоров.

Вы выкатываете новую версию.

Нельзя:

```text
docker stop
```

и оборвать 50 звонков.

Нужно:

```text
ACTIVE
↓
DRAINING
```

В `DRAINING`:

```text
не принимать новые calls
существующие работают
```

Когда:

```text
active_calls == 0
```

→ процесс можно остановить.

Или timeout равный max call duration.

Это должно быть частью VoiceRuntime с первого production deployment.

---

# Поправка №18 — не пытаться делать seamless failover живого RTP call

Документ уже говорит:

> call не мигрирует между cells.

### Это абсолютно правильно.

Не менять.

Если worker/FreeSWITCH умер:

```text
call lost
```

Это допустимо для первой архитектуры.

HA означает:

```text
новые calls идут на другой cell
```

а не магическая миграция текущего звонка.

Так сильно проще и надёжнее.

---

# Поправка №19 — один pilot server ≠ production HA

G8 говорит:

> Один Linux server / pilot.

Это правильно.

Но надо явно писать:

```text
PILOT / limited production
```

а не «настоящий HA production».

Я бы данные даже на pilot по возможности вынес в:

```text
managed PostgreSQL
managed object storage
managed Redis
```

А сервер оставил:

```text
FreeSWITCH
VoiceRuntime
model workloads
```

Это уменьшает blast radius.

Но это уже deployment choice, архитектура от этого не меняется.

---

# Поправка №20 — release через immutable artifact — оставляем без изменений

Очень правильное решение:

```text
clean commit
↓
build once
↓
image digest
↓
tests
↓
security scan
↓
deploy same digest
```

Это не надо больше перерабатывать.

---

# Что в текущем документе я прямо принимаю и больше НЕ предлагаю пересматривать

Вот это можно считать **Architecture Decision Record** и заморозить:

1. **FreeSWITCH остаётся.**
2. **Lua phone brain удаляется.**
3. **Один VoiceRuntime.**
4. **Один CallSession actor на звонок.**
5. **ESL — управление, не media pipeline.**
6. **MediaAdapter abstraction.**
7. **Внутри PCM16 mono 16k/20ms.**
8. **STT/Agent/LLM/TTS имеют отдельные contracts.**
9. **Agent не знает про SIP/RTP/WAV.**
10. **Persistence не стоит в latency path.**
11. **`generation_id` является hard safety boundary.**
12. **Inbound и outbound используют один VoiceRuntime.**
13. **Приложение использует тот же conversation core.**
14. **Active call принадлежит одному cell до hangup.**
15. **Capacity измеряется concurrent calls, не users.**
16. **Система масштабируется pools/cells, не переписыванием.**
17. **Real SIP E2E обязателен в release gate.**
18. **Legacy удаляется после подтверждённого cutover.**

**Эти решения больше не надо заново обсуждать каждый раз.**

---

# Что я бы изменил в последовательности gate'ов

Текущие G0–G9 хорошие, но я бы окончательно сделал так:

```text
G0  Repo / contracts / package cleanup
 ↓
G1  CallSession state machines + protocol definitions
 ↓
G2  FreeSWITCH control plane + MediaAdapter spike
 ↓
G3  continuous inbound PCM + pre-roll + VAD
 ↓
G4  outbound streaming + hard generation flush
 ↓
G5  STT / Agent / TTS contracts
 ↓
G6  dialogue integration
 ↓
G7  persistence / safety events
 ↓
G8  inbound real DID
 ↓
G9  outbound calls/workflow
 ↓
G10 app media adapter/Product API
 ↓
G11 load/SLO/security/deployment
```

Почему так?

Потому что **сначала надо доказать media foundation**, а потом подключать весь остальной продукт.

---

# Самый важный technical milestone

До подключения LLM вообще сделать тест:

```text
Zoiper
 ↓
FreeSWITCH
 ↓
VoiceRuntime

Вера проигрывает тестовый tone/phrase
 ↓
я перебиваю:
"раз два три"
 ↓
<=300ms outbound stops
 ↓
STT не нужен
 ↓
сохраняем inbound PCM
 ↓
проверяем:
"раз два три" начинается с "раз"
```

Вот когда это стабильно работает **20/20 раз**, media architecture считается правильной.

Потом:

```text
+ STT
```

Потом:

```text
+ Agent
```

Потом:

```text
+ LLM/TTS
```

Не наоборот.

Это как раз спасёт от ещё одного цикла:

> «LLM классный, всё протестировали, а телефон опять не слышит».

---

## Мой окончательный вывод

**Да, этот Production Refactor Spec — правильная основа. Не выбрасывать и не создавать новый план.**

Но перед передачей агенту я бы внёс перечисленные поправки, особенно эти семь:

```text
1. logical service boundary != mandatory microservice
2. формальная Call/Turn state machine
3. точная turn_id/generation_id semantics
4. 300–500ms audio pre-roll
5. separate barge-in VAD / endpoint VAD
6. hard media flush contract
7. inbound capacity reservation BEFORE answer
```

И отдельно:

```text
ESL = control only
MediaAdapter = media only
```

Это соответствует роли Event Socket в FreeSWITCH: управление call legs, events, originate, DTMF и playback control идут через ESL; media path — отдельная ответственность. ([SignalWire][1])

Если эти правила сейчас вписать в главный документ и **после этого объявить его архитектурой v1.0/frozen**, я уже не вижу причины ещё раз фундаментально менять систему. Дальше будут меняться реализации — STT-модель, TTS, LLM, SIP provider, число серверов — **но границы системы останутся теми же**.

[Текущая версия Production Refactor Spec](sandbox:/mnt/data/MOSSVOICE_PRODUCTION_REFACTOR_SPEC.md)

Я бы именно этот документ теперь довёл до **Architecture v1.0**, зафиксировал решения выше и уже заставлял агента работать только по gate'ам, без самостоятельного изобретения четвёртой архитектуры.

[1]: https://developer.signalwire.com/freeswitch/integration/event-socket/?utm_source=chatgpt.com "Chapter 25: The Event Socket | FreeSWITCH Users Manual"
[2]: https://developer.signalwire.com/freeswitch/media-and-codecs/handling/?utm_source=chatgpt.com "Chapter 17: Media Handling | FreeSWITCH Users Manual"
