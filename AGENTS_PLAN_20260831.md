# MossVoice / IMVERA — Comprehensive Plan (2026-08-31)

> Два главных модуля системы разбраны от и до: **диалоги** (ядро
> продукта) и **SIP-телефония** (канал доставки). Для каждого —
> гипотезы, как проверить, как решить, что может пойти не так.
>
> **Примечание по IP.** Текущий IP Mac (`ipconfig getifaddr en0`)
> и `local_ip_v4` в vars.xml **совпадают** — оба .194 (AGENTS.md
> §718). DHCP реально прыгал между .194 и .120 ранее; сейчас
> стабильно .194. План ссылается на актуальное состояние, а не
> на устаревшие .26/.5. DHCP-резервация на роутере — долгосрочно
> на случай следующего lease-renewal.
>
> **Примечание по приоритетам.** D1–D7 можно **писать код**
> параллельно с SIP-фазой, но **верифицировать** (живой звонок)
> — только после закрытия S1. Если агент работает автономно —
> фаза 2 без фазы 1 это только код+юнит-тесты, без энд-to-энд.

---

## I. ДИАЛОГИ (dialogue.py + safety_engine.py + fsm.py)

### Что это

Говорящий агент Веры, который ведёт телефонный разговор с пожилым
человеком: приветствие → вопросы самочувствия/настроения/сна/планов/
передача родным → завершение с вердиктом для семьи.

### Как тестировать диалоги БЕЗ SIP (Mac → telephony напрямую)

**Проблема.** SIP-путь (Zoiper → FreeSWITCH → dialplan →
VoiceRuntime) не работает, пока не починён S1. Но **весь
диалоговый движок** (clean_transcript → plan_reply → reply_stream →
commit_reply → safety_engine) доступен через HTTP API на порту
9400 — без FreeSWITCH, без WAV-файлов, без звука.

**Ключевой эндпоинт — `turn_text`** — POST с произвольным текстом,
ответ — текстовый reply Веры. Это полный цикл: STT-гейт пропускает
текст, safety_engine вёрдикт, FSM меняет состояние, LLM (DeepSeek)
генерирует ответ. Проверка живого диалога — одна команда curl.

**Как использовать (3 команды):**

```bash
# 1. Создать звонок (сессия)
CID=$(curl -s -X POST http://127.0.0.1:9400/calls \
  -d '{"caller_id":"test_mac"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['call_id'])")
echo "Call: $CID"

# 2. Отправить текстовый ход — получить ответ Веры
curl -s -X POST http://127.0.0.1:9400/calls/$CID/turn_text \
  -H 'Content-Type: application/json' \
  -d '{"text": "здравствуйте"}' | python3 -m json.tool

# 3. Продолжить диалог — каждый ход возвращает reply + finished
curl -s -X POST http://127.0.0.1:9400/calls/$CID/turn_text \
  -H 'Content-Type: application/json' \
  -d '{"text": "всё хорошо"}' | python3 -c "import sys,json; r=json.load(sys.stdin); print('Vera:', r['reply']); print('Finished:', r['finished'])"

# Проверить состояние звонка
curl -s http://127.0.0.1:9400/calls/$CID | python3 -m json.tool

# Завершить звонок
curl -s -X POST http://127.0.0.1:9400/calls/$CID/end | python3 -m json.tool
```

**Что покрывает `turn_text`:**
- `clean_transcript` (хотя текст идёт напрямую, STT-гейт не нужен — confidence=1.0)
- `plan_reply()` → DialogueFSM.dispatch() → безопасный вёрдикт
- LLM-генерация (DeepSeek через OpenRouter, или скрипт если LLM недоступен)
- `commit_reply` → история ходов
- `outcome` (status: ok/attention/alert) — вердикт для семьи

**Что НЕ покрывает:**
- STT (whisper/Qwen3-ASR) — текст подаётся готовый
- TTS (Silero/Qwen3-TTS) — ответ текстовый, не аудио
- FreeSWITCH/ESL/uuid_record/uuid_broadcast
- Энд-ту-энд аудио-путь

**Для audio-теста** (если нужен полный цикл с WAV):
1. `POST /say` — получить TTS-аудио Веры (WAV)
2. Сохранить файл
3. `POST /calls/$CID/turn` — отправить этот WAV как "вход абонента"
4. Получить reply WAV + JSON

**Чтобы закрыть Zоиper-зависимость полностью:**
- Тестирование диалогов, safety, variety, agenda — всё через `turn_text`
- SIP/Zoiper нужен ТОЛЬКО для проверки реального аудио-пути (запись/воспроизведение)
- Живой звонок с Zoiper — финальная верификация после S1

---

### Архитектура (от верхнего уровня к низшему)

```
┌─────────────────────────────────────────────────────────┐
│  Agent (dialogue.py:1319+)                              │
│  ├─ AGENDA (5 тем + family_questions)                   │
│  ├─ _a_ok() — основной ответ на подтверждение             │
│  ├─ _a_symptom() — ветка жалобы                          │
│  ├─ _a_refuse() — вежливый отказ (P-ACK)                │
│  ├─ _a_close() / _a_goodbye() — прощание                │
│  └─ reply_stream() → LLM (DeepSeek через OpenRouter)     │
├─────────────────────────────────────────────────────────┤
│  DialogueFSM (dialogue.py:220+)                          │
│  ├─ 11 состояний: IDLE/CHECKIN/SIDE_QUESTION/CLARIFY/    │
│  │  SAFETY_CONFIRM/SAFETY_ACTIVE/HELP/WORRY/             │
│  │  GOODBYE_CONFIRM/CLOSING/DONE                        │
│  ├─ ~25 событий: E_OK/E_UNKNOWN/E_SYMPTOM/E_EMPTY/...  │
│  └─ Таблица переходов ~60 строк (_build_transitions)     │
├─────────────────────────────────────────────────────────┤
│  SafetyEngine (safety_engine.py)                         │
│  ├─ NONE → POSSIBLE_RED → CONFIRMED_RED/UNCERTAIN/OK    │
│  ├─ Токенизация + НЕГ_WINDOW + SUBJECT_AWARE             │
│  └─ Латчинг CONFIRMED_RED; UNCERTAIN не латчится         │
├─────────────────────────────────────────────────────────┤
│  StateMachine (fsm.py)                                   │
│  └─ Generic RTC dispatch; guard = pure predicate         │
└─────────────────────────────────────────────────────────┘
```

### Ключевые проблемы и гипотезы

#### D1. `_a_ok()` — хеширование интента вместо LLM (ГЛАВНАЯ)

**Проблема.** Когда пользователь подтверждает тему ("хорошо", "да"),
`_a_ok()` решает, КУДА продвинуть повестку, через:
- `_answers_wellness()` (словарь OK_WORDS/BAD_WORDS + `_matches_topic`)
- `_agenda_advance()` (детерминированный счётчик тем)
- `_extract_facts()` (regex-извлечение фактов)
- Потом вызывает LLM с `last_intent` в системном промпте

**Гипотеза.** LLM получает готовый интент в виде строки
("порадоваться и задать один вопрос про сон") — это буквально
запись в системный промпт ("Цель ответа: ..."). LLM по сути
просто выполняет шаблон, а не думает. Это делает диалог
предсказуемым и повторяющимся — отсюда ощущение "как будто
программированный бот".

**Как проверить:**
1. Запустить живой звонок и записать 10 реплик Вера — посчитать,
   сколько раз ответ совпадает с `last_intent` дословно или почти
   дословно
2. Посмотреть на `_build_history()` — `last_intent` в скобках
   после цели ответа. LLM буквально читает инструкцию и
   генерирует именно это

**Решение — LLM-driven `_a_ok`:**
1. Убрать `last_intent` из `_build_history()` (или сделать его
   опциональным фоном, а не жёсткой целью)
2. Передать в LLM ТЕКУЩУЮ ТЕМУ и ПРЕДЫДУЩИЙ ОТВЕТ как
   контекст, но НЕ жёсткий интент
3. Промпт: "Текущая тема: {topic}. Человек сказал: {text}.
   Предыдущий ваш ответ: {last_reply}. Отвечайте естественно,
   один вопрос по теме или прощайтесь."
4. `_agenda_advance()` остаётся детерминированным (это счётчик
   тем), но решение "что говорить" — за LLM
5. Guard: если LLM выдаёт нечто неприемлемое (обещание,
   двойной вопрос, англ.) — fall-back на старый `_a_ok`

**Тесты:**
- `tests/test_dialogue_modes.py` — расширить: сравнить LLM-ответ
  vs старый `_a_ok` на 20 типичных сценариях
- Новый тест: `test_llm_driven_ok` — верифицирует что при
  `MOCK_LLM` возвращается живой ответ, а не `last_intent`
- Харнесс `voice-lab/dialog_quality.py` — метрика
  `intent_repetition_rate` (доля реплик = last_intent дословно)

**Риски:**
- LLM может уйти от темы — guard `_matches_topic` + `_agenda_asked`
  должны оставаться
- LLM может забыть продвинуть тему — `_agenda_advance()` должен
  вызываться ОБЯЗАТЕЛЬНО по детерминированному правилу
  (тема закрыта → advance), а промпт только формулирует текст
- Задержка: +200-500мс на генерацию вместо instant canned phrase
  → решение: `reply_stream` уже стримит, первый фрагмент до
  конца предложения (EARLY-FIRST-SOUND)

#### D2. Повтор вопросов в разных формах (VARIETY exhaustion)

**Проблема.** `_pick_not_repeated` фильтрует и по
`_last_question`, и по `_RECENT_SPOKEN` (deque, maxlen=40).
Но `_RECENT_SPOKEN` — **процессный глобальный кольцевой буфер**,
общий на **ВСЕ** звонки контейнера сразу (не per-call). При
4 одновременных линиях пул вариантов может съедаться
чужими звонками быстрее, чем планится.

**Гипотеза.** Уточнение: механизм уже работает (проверяет
оба множества), но масштабируемость на concurrent calls
не проверена. На одном звонке варианты не повторяются
(хорошо), но при 4+ звонках общий pool исчерпывается.

**Как проверить:**
1. Симуляция 4 параллельных звонков с одинаковыми ответами
2. Подсчитать уникальность вопросов по темам на каждом звонке
3. Посмотреть, не исчерпывается ли pool на maxlen=40

**Решение:**
1. Перевести `_RECENT_SPOKEN` в per-call хранилище
   (на Agent/CallContext вместо глобального)
2. Добавить `_asked_questions` deque в Agent, куда складывать
   каждый `_last_question` при `_ask_task()`
3. `_pick_not_repeated` проверяет оба: `_last_question` +
   `_asked_questions` (пер-call, не глобальный)
4. Глобальный `_RECENT_SPOKEN` оставить как backup с
   увеличенным maxlen (60) для межзвонковой вариативности

#### D3. Safety false-positive: "отлично... не болела" → possible_red

**Проблема.** Симметричное окно негации (±3 токена) перечёркивает
позитивные фразы: "Я отлично чувствую себя, ничего не болела" →
"не болела" в окне негации к "отлично" → possible_red.

**Решение (уже сделано частично):** `POSITIVE_NEG_WINDOW=2`,
позитив отрицается только негатором НЕПОСРЕДСТВЕННО перед ним.

**Как проверить:**
1. Тест: `safety.observe("я отлично чувствую себя, ничего не болела")`
   → должен быть `kind="ok"`, не `possible_red`
2. Тест: "я плохо себя чувствую, но не так сильно" → `possible_red`

#### D4. `_a_symptom` wellness advance

**Проблема.** Когда пользователь подтверждает улучшение ("голове
стало легче"), agenda двигается дальше вместо повторного вопроса
о теле. Но "Отлично, но болела голова" остаётся в symptom mode
(нет cues улучшения).

**Гипотеза.** Логика правильная, но `_improves` список может быть
неполным. Пользователь может сказать "помогло", "ушло", "стало
легче" — все ли покрыты?

**Проверка:**
1. Добавить в `_SHORT_ANSWER_MAP` и `_improves` слова:
   "устранил", "дошло", "прошло", "куда-то", "легче стало"
2. Тест: `test_symptom_advance_variants` — 20 формулировок
   улучшения → agenda advance

#### D5. Family questions + dynamic agenda

**Проблема.** Семейные вопросы добавляются ДО стандартных тем,
но очерёдность может ломать повествование. Вопрос от родных
может прийти на "передать родным" но быть на 3-м ходу.

**Гипотеза.** Порядок: стандартные 5 тем → family questions →
wrap-up. Это работает, но family question может прервать
поток если человек говорит на другую тему.

**Как проверить:**
1. Живой звонок с family question в очереди
2. Проверить что family question появляется ОДИН раз
   (не повторяется на каждом ходу)

**Решение:**
1. `set_family_questions` ставит флаг — вопросы появляются
   ТОЛЬКО когда agenda доходит до точки их вставки
2. Тест: `test_family_question_once` — вопросы не повторяются

#### D6. LLM fallback chain

**Проблема.** При отсутствии ключа OpenRouter диалоги падают
на скриптовых фразах. `CloudLLMAdapter` → `NullLLM` (пусто) →
fallback `plan['fallback']`. Но `NullLLM` может не генерировать
ничего → пустой ответ → `_a_unknown` → generic ack.

**Гипотеза.** Нужен промежуточный fallback: если LLM не отвечает,
использовать `_a_ok`/`_a_unknown` детерминированный ответ
(как в старом `_answers_wellness`), а не `plan['fallback']`.

**Решение:**
1. `reply_stream` проверяет: если из LLM ничего не пришло
   (пустой stream) → вызвать `_a_ok` детерминированно
2. Тест: `test_null_llm_fallback` — с `MOCK_LLM` который
   возвращает `""` → Vera даёт скриптовый ответ, не молчит

#### D7. Память контекста LLM (history window)

**Проблема.** Сейчас `llm_history[-4:]` — последние 4 хода
(2 вопрос-ответ пары). При 10+ ходах LLM забывает начало
разговора (проще, чем планировалось в текущих [-4:], но
проблема есть).

**Гипотеза.** 4 хода = 2 вопрос-ответ пары. Для длинного
звонка (15+ ходов) LLM может не помнить что спрашивала на
ранних ходах — фактически хуже, чем кажется.

**Решение:**
1. Увеличить до 8 ходов (4 пары) — не сильно увеличит
   токены (~1–2K tokens дополнительно)
2. Добавить `_facts_note()` (уже есть) — компактная память
   "приняла лекарства; недомогание; сон" — это сохраняет
   ключевую информацию вне окна
3. Тест: `test_llm_remembers_facts` — симуляция 15 ходов,
   LLM вспоминает факт из 10-го хода

---

## II. SIP ТЕЛЕФОНИЯ (FreeSWITCH + Zoiper + dialplan)

### Что это

Телефонный канал: Zoiper (SIP-клиент) → FreeSWITCH (SIP-сервер)
→ dialplan → VoiceRuntime (ESL) → туда же STT/LLM/TTS → обратно
через ESL → FreeSWITCH → Zoiper.

### Архитектура (от клиента к серверу)

```
Zoiper (Mac, 127.0.0.1:5060)
    │ SIP REGISTER/INVITE/BYE
    ▼
FreeSWITCH (127.0.0.1:5060, port 8021 ESL)
    ├─ sip_profiles/zoiper.xml (bind 127.0.0.1)
    ├─ sip_profiles/internal.xml (bind 127.0.0.1)
    ├─ vars.xml (local_ip_v4=192.168.1.194)
    ├─ dialplan/default/mossvoice.xml (4400=answer+park)
    ├─ dialplan/default/1000.xml (user 1000)
    └─ event_socket.conf.xml (ESL auth)
        │ ESL (8021)
        ▼
VoiceRuntime (host, launchd com.mossvoice.runtime.plist)
    ├─ uuid_record (tap caller audio)
    ├─ uuid_broadcast (playback Vera's voice)
    ├─ uuid_break (barge-in)
    ├─ STT (Qwen3-ASR host:9705)
    ├─ LLM (DeepSeek via OpenRouter)
    └─ TTS (Silero host:9600 / Qwen3-TTS host:9711)
```

### Ключевые проблемы и гипотезы

#### S1. Zoiper не регистрируется — 403 Forbidden

**Корень (найден 2026-09-01).** Не `local_ip_v4`, а
`<alias name="127.0.0.1"/>` в zoiper.xml конфликтует с
алиасом того же IP в `internal` профиле. FreeSWITCH не может
добавить дублирующийся alias → отбрасывает `127.0.0.1` и биндит
на `$${local_ip_v4}` = `192.168.1.194`. Лог:
`Error Adding Alias [127.0.0.1] for profile [zoiper] (name in use)`.

**Фикс (уже применён).** Убран `<alias name="127.0.0.1"/>`,
`ext-rtp-ip`/`ext-sip-ip` → `127.0.0.1`, добавлен симлинк
zoiper.xml в `/opt/homebrew/etc/freeswitch/sip_profiles/`.
`sofia status` теперь показывает `sip:mod_sofia@127.0.0.1:5060 RUNNING`.

**Решение:**
1. В `vars.xml` установить `local_ip_v4=192.168.1.194`
   (текущий актуальный IP; DHCP-резервация на роутере
   пингует этот IP навсегда)
2. Симлинк zoiper.xml в `/opt/homebrew/etc/freeswitch/sip_profiles/`
3. `force-register-domain=127.0.0.1` — уже стоит

**Верификация (2026-09-01):**
- `sofia status` → `zoiper sip:mod_sofia@127.0.0.1:5060 RUNNING (0)` ✓
- Нет ошибок `Error Adding Alias [127.0.0.1]` в логах после рестарта ✓
- `originate loopback/4400/default 4400 XML default` → `+OK`, оба лега ACTIVE ✓
- Диалог через HTTP API (`POST /calls/$CID/turn_text`) — работает:
  Vera генерирует живые ответы через DeepSeek, agenda продвигается,
  goodbye подтверждение работает ✓
- `ext-rtp-ip=127.0.0.1`, `ext-sip-ip=127.0.0.1` — оба на localhost ✓

#### S2. `default_password=1234` → 10 секунд тишины

**Проблема.** Стоковый `default/global` extension в
`dialplan/default.xml:135` делает `sleep 10000` если
`${default_password}=1234`. КАЖДЫЙ звонок в default контекст
получал 10 секунд тишины.

**Статус:** `default_password` уже ротирован (не `1234`).
Значение хранится в `vars.xml` и **не должно коммититься
в открытую** — ссылаться на env/скрипт миграции, а не на
конкретный пароль в тексте.

**Как проверить:**
1. `fs_cli -x "eval \${default_password}"` → **НЕ** `1234`
   (точное значение — в vars.xml, не в этом плане)
2. Посмотреть лог звонка на `sleep` — grep в логах
3. `originate loopback/4400/default 4400 XML default` — проверить
   что нет sleep 10000 (вызов должен быть answered быстро)

**Решение:**
1. Убедиться что vars.xml содержит непустой `default_password`
   (не `1234`) — значение хранится в vars.xml и зашивается
   скриптом установки/миграции
2. Добавить в `install_freeswitch.sh` проверку:
   `grep default_password vars.xml | grep -v 1234`
3. Долгосрочно: убрать `default/global` extension вообще или
   заменить на `reject`

#### S3. DHCP скачки IP → FS бинд на мёртвый адрес

**Проблема.** Mac получает IP по DHCP нестабильно (ранее
прыгал .194 → .120 → .194). vars.xml содержит пин
`local_ip_v4=192.168.1.194`. Если IP улетит в другой
сегмент, FS биндит 5060 на мёртвый адрес → Zoiper не
может зарегистрироваться.

**Гипотеза A.** `local_ip_v4` пин в vars.xml → FS всегда
биндит на конкретный IP → при смене DHCP FS не переключается.

**Гипотеза B.** FS вычисляет `local_ip_v4` автоматически (если
не захардкожен), и `vars.xml` его переопределяет.

**Как проверить:**
1. `eval $${local_ip_v4}` — сравнить с `ipconfig getifaddr en0`
2. Если FS вычисляет сам — `local_ip_v4` в vars.xml может
    быть закомментирован или захардкожен
3. Проверить `ipconfig getifaddr en0` → `eval $${local_ip_v4}`

**Решение:**
1. **Немедленно:** DHCP-резервация на роутере для MAC
    `36:7f:b5:4c:85:cc` → `192.168.1.194`
    (фиксируем актуальный IP, чтобы никогда не меняться)
    Это ЕДИНСТВЕННОЕ НАДЕЖНОЕ РЕШЕНИЕ
2. **Вариант Б:** скрипт `scripts/ip-sync.sh` в launchd
    который проверяет `ipconfig getifaddr en0` каждые 60с и
    обновляет `local_ip_v4` в vars.xml + `reloadxml` если поменялся
3. **Вариант В:** заменить `local_ip_v4` на `$${local_ip_v4}`
    (без пина) — FS сам определяет IP, но нужно проверить
    что он совпадает с Zoiper

**Риски:**
- Задача 1.1 (DHCP-резервация на роутере) — **требует
  ручного действия человека** (зайти в админку роутера).
  Нельзя автоматизировать агентом — помечено как
  "требует вас".
- Если роутер не поддерживает DHCP reservation —
  fallback на скрипт `ip-sync.sh`

#### S4. `sofia profile zoiper restart` не применяет `force-register-domain`

**Проблема.** После изменения `force-register-domain` в zoiper.xml
или internal.xml `profile restart` НЕ перечитывает этот параметр.
Нужен полный restart FS.

**Как проверить (по порядку):**
1. `sofia profile zoiper restart` → `sofia status zoiper` —
   если `sip-ip` обновился на 127.0.0.1 — готово (радиус
   поражения минимальный, остальные профили не тронуты)
2. Если не помогло — полный restart:
   `fs_cli shutdown graceful; freeswitch -nc`
   (разорвёт все текущие звонки на ВСЕХ профилях)

**Решение:**
1. `install_freeswitch.sh` добавить шаг: если изменился
    `force-register-domain` или `sip-ip` → сначала
    `sofia profile zoiper restart`, и только при неудаче —
    полный shutdown+restart
2. Или: отдельный скрипт `scripts/restart-fs.sh` для
    безопасного рестарта с проверкой, что текущих звонков нет
3. Долгосрочно: при любых правах zoiper.xml делать
    `sofia profile zoiper restart` и логировать результат;
    alert если `sip-ip` не совпадает с ожидаемым

#### S5. ESL-пароль закоммичен в коде

**Проблема.** `esl_client.py` / `esl_stream.py` содержат live-пароль
`d7f78342…9f89` в коде (hex-шаблон). check_secrets не ловит hex.

**Статус:** Уже исправлено (P0). Пароль ротирован, `esl_stream.py`
(старый POC) удалён, voice_runtime/esl_client.py теперь берёт
пароль из env `MOSS_ESL_PASSWORD`.

#### S6. voice_runtime — статус деплоя

**Проблема.** `voice_runtime/` источников **есть в git**
(не "ls-files=0" — это было устаревшее наблюдение).
Проблема именно в деплое: процесс не запущен как
имениованный сервис, и 7 launchd `agent-loop.*` непрерывно
долбят 4400 → 0ea49711ae79 держит 673 пустых ходов.

**Гипотеза.** voice_runtime должен быть запущен как сервис
launchd (`com.mossvoice.runtime.plist`), но текущий launchd
не грузит plist (ошибка `bootstrap gui/$(id -u)` —
Input/output error, типичная для sandbox macOS).

**Как проверить:**
1. `launchctl list | grep mossvoice` — сколько сервисов
2. `ps aux | grep voice_runtime` — процессы
3. `cat ~/Library/LaunchAgents/com.mossvoice.runtime.plist`
4. `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.mossvoice.runtime.plist`

**Решение:**
1. Проблема launchd bootstrap — это sandbox/ограничение macOS.
   Попробовать: `launchctl load ~/Library/LaunchAgents/com.mossvoice.runtime.plist`
2. Или: запуск через `scripts/run_runtime.sh` напрямую
3. `scripts/run_runtime.sh` берёт ESL-пароль из `~/.fs_cli_conf`
4. Долгосрочно: runtime как compose service или launchd
   с корректным bootstrap

#### S7. Media path: RTP не приходит на Zoiper

**Проблема.** Даже если Zoiper зарегистрируется, медиа (RTP)
может идти на мёртвый IP. SDP в INVITE содержит `c=IN IP4 192.168.1.194`,
но Zoiper слушает на .194 (localhost — работает).

**Гипотеза.** `ext-rtp-ip` в zoiper.xml = `$${local_ip_v4}` = 192.168.1.194
→ FS отправляет RTP на .194 → Zoiper должен слышать
(проверить: Zoiper и FS на одном хосте — loopback работает).
Но если `ext-rtp-ip` попадает в NAT-правило — может сломать.

**Решение:**
1. `ext-rtp-ip=127.0.0.1` и `ext-sip-ip=127.0.0.1` в zoiper.xml
   — SIP и RTP на localhost (Zoiper и FS на одном хосте)
2. Если медиа не идёт — проверить `sofia status` на
   `rtp` пары и `rtp-ip` в загруженном профиле

---

## III. ЕДИНЫЙ МАРШРУТ РЕАБИЛИТАЦИИ

### Приоритет и зависимости

```
S1 (Zoiper reg) ← зависит от S3 (DHCP стабильность)
S2 (password) ← минорный, уже почти done
S4 (restart) ← нужен после S1 (перезапуск FS)
S6 (runtime) ← независимый, но влияет на звонки
D1–D7 (диалоги) ← КОД пишется параллельно с фазой 1,
  но ВЕРИФИКАЦИЯ (живой звонок) — только после S1.
  Юнит-тесты и фаззинг — можно без SIP.
```

### Фаза 1: SIP стабилизация (1 день)

**Задача 1.1 — DHCP-резервация на роутере** ⚠️ ТРЕБУЕТ ЧЕЛОВЕКА
- Зайти в админку роутера, настроить DHCP reservation:
  MAC `36:7f:b5:4c:85:cc` → IP `192.168.1.194`
- После этого `local_ip_v4` будет стабильно .194
- В `vars.xml` пин: `local_ip_v4=192.168.1.194`
- ⚠️ Если роутер не поддерживает DHCP reservation —
  fallback: скрипт `scripts/ip-sync.sh` каждые 60с

**Задача 1.2 — Исправить zoiper.xml**
- `ext-rtp-ip` и `ext-sip-ip` → `127.0.0.1` (не `$${local_ip_v4}`)
- Это гарантирует что и SIP, и RTP на localhost
- `sofia profile zoiper restart` (сперва, без полного shutdown;
  если не поможет — `fs_cli shutdown graceful; freeswitch -nc`)

**Задача 1.3 — Проверить регистрацию**
- `sofia status` → zoiper должен показывать `sip:mod_sofia@127.0.0.1:5060`
- Zoiper: Server=127.0.0.1, User=1000, Password=из vars.xml
  (не коммитить пароль в открытый текст)
- Если регистрация прошла → `sofia status` покажет `reg. 1`

**Задача 1.4 — Проверить default_password**
- `fs_cli -x "eval \${default_password}"` → **НЕ** `1234`
  (точное значение — в vars.xml, не в этом плане)
- `grep -r "1234" /opt/homebrew/Cellar/freeswitch/1.11.1/etc/freeswitch/vars.xml`
  → ничего не должно быть

**Задача 1.5 — Test call**
- Originate loopback: `fs_cli -x "originate loopback/4400/default 4400 XML default"`
- Или из Zoiper: набрать 4400
- Проверить что звонок уходит в Lua (answer+park) без sleep 10000

### Фаза 2: Диалоги — LLM-driven (2 дня)

> **Тестирование через HTTP API (`turn_text`)** — не ждать S1.
> `curl -X POST http://127.0.0.1:9400/calls/$CID/turn_text
> -d '{"text":"..."}'` — полный цикл диалога без SIP/WAV.
> Каждый вызов возвращает `{"reply":"...", "finished":bool}`.
> Это основной инструмент фазы 2.

**Задача 2.1 — Убрать `last_intent` из промпта**
- В `_build_history()`: заменить блок `last_intent` на мягкий
  контекст: `"Текущая тема разговора: {topic}. Предыдущий ваш ответ: {last_reply}."`
- Не менять `_agenda_advance()` — он детерминированный,
  продвигает тему; LLM только формулирует текст
- **Верификация через `turn_text`**: отправить "всё хорошо" →
  проверить что LLM формулирует живой ответ, а не
  дословно `last_intent`

**Задача 2.2 — Настроить промпт LLM**
- Текущий `VERA_SYSTEM_PROMPT` уже содержит правила
- Добавить: "Ты формулируешь свой ответ СВОБОДНО. Не следуй
  букве букве тому, что я написал в скобках выше. Твоя цель —
  быть тёплой, заботливой, задать один вопрос. Если тему можно
  закрыть — закрой. Если нужно уточнить — уточни."
- Убрать "Цель ответа:" как жёсткую цель
- **Верификация**: 20 разных подтверждений через `turn_text`,
  убедиться что ответы разнообразные и живые

**Задача 2.3 — Fallback chain**
- Если LLM не отвечает (null/timeout/error) →
  `_a_ok` детерминированно через `_agenda_advance()`
- `reply_stream`: если после stream нет ни одного delta →
  вызвать `_a_ok` и дать fallback
- **Верификация**: отключить LLM (закомментировать ключ),
  отправить через `turn_text` → Vera даёт скриптовый ответ,
  не молчит и не ошибится

**Задача 2.4 — Тесты**
- `test_llm_driven_ok_variety` — 20 вызовов `_a_ok` с одним и
  тем же подтверждением, проверка что LLM формулирует по-разному
  (верифицировать через `turn_text` с 20 одинаковыми "всё хорошо")
- `test_llm_remembers_topic` — LLM не забывает текущую тему
  при длинном разговоре (5+ ходов через `turn_text`)
- `test_null_llm_fallback` — с отключённым LLM, Vera даёт
  осмысленный ответ (тест через `turn_text`)
- `test_dialogue_via_http_api` — новый тест: полные сценарии
  через `POST /calls/$CID/turn_text` (приветствие → подтверждение →
  закрытие) — энд-ту-энд без SIP

### Фаза 3: Разнообразие и качество (1 день)

**Задача 3.1 — Расширить `_RECENT_SPOKEN`**
- Кладить туда ВСЕ вопросы (не только ответы)
- Maxlen 20 — покрывает ~2 полных звонка

**Задача 3.2 — Тесты variety**
- `test_variety_no_repeat` — 20 вопросов подряд, 0 повторов
- `test_variety_within_call` — 10 ходов в одном звонке,
  вопросы не повторяются

**Задача 3.3 — Харнесс диалога**
- Расширить `voice-lab/dialog_quality.py`
- Метрики: `intent_repetition_rate`, `question_per_reply_ratio`,
  `promise_count`, `topic_drift_rate`

### Фаза 4: Деплой и верификация (0.5 дня)

**Задача 4.1 — Деплой**
- `git push` → `make up telephony` (пересборка)
- `scripts/install_freeswitch.sh` (переустановить dialplan, vars)
- `scripts/restart-fs.sh` (restart FS, first `sofia profile zoiper restart`,
  при неудаче — полный shutdown+restart)

**Задача 4.2 — Верификация**
- Живой звонок через Zoiper на 4400
- Записать 5 ходов:
  1. Нет повторения вопросов
  2. LLM формулирует живые ответы (не canned)
  3. Закрытие темы работает
  4. Прощание с вердиктом
  5. Safety не даёт ложных тревог
- Записать 3 звонка подряд — стабильность

---

## IV. ГИПОТЕЗЫ — ЧТО МОЖЕТ ПОЙТИ НЕ ТАК

| # | Гипотеза | Проверка | Если не сработает |
|---|---------|---------|------------------|
| H1 | `ext-rtp-ip=127.0.0.1` починит Zoiper | `sofia status` + звонок | Пробовать `apply-nat-acl="none"` |
| H2 | LLM-промпт без last_intent даст живые ответы | 20 реплик подряд | Вернуть `last_intent` как мягкий hint |
| H3 | DHCP-резервация стабилизирует IP | `ipconfig getifaddr en0` после рестарта | Скрипт `ip-sync.sh` каждые 60с |
| H4 | `_a_ok` LLM-driven не уйдёт от темы | `_matches_topic` guard | Добавить жёсткий `_agenda_advance()` |
| H5 | Null LLM fallback работает | Отключить LLM, проверить | Кэшировать последнее известное good reply |
| H6 | voice_runtime запустится как launchd | `launchctl list \| grep mossvoice` | `run_runtime.sh` напрямую |
| H7 | Тема "передать родным" не конфликтует | Живой звонок с family question | Отдельный flow для family questions |

---

## V. ФАЙЛЫ КОТОРЫЕ НАДО ИЗМЕНИТЬ

### Диалоги
- `telephony/core/dialogue.py` — `_a_ok()`, `_build_history()`,
  `_pick_not_repeated()`
- `telephony/core/safety_engine.py` — возможно добавить
  `POSITIVE_NEG_WINDOW` корректировку (уже done)
- `telephony/tests/` — новые тесты
- `voice-lab/dialog_quality.py` — расширить метрики

### SIP/Телефония
- `/opt/homebrew/Cellar/freeswitch/1.11.1/etc/freeswitch/vars.xml`
  — `local_ip_v4=192.168.1.194` (текущий IP Mac, после
    DHCP-резервации на роутере)
- `/opt/homebrew/Cellar/freeswitch/1.11.1/etc/freeswitch/sip_profiles/zoiper.xml`
  — `ext-rtp-ip=127.0.0.1`, `ext-sip-ip=127.0.0.1`
- `/opt/homebrew/Cellar/freeswitch/1.11.1/etc/freeswitch/sip_profiles/internal.xml`
  — `force-register-domain=127.0.0.1` (уже done)
- `scripts/install_freeswitch.sh` — добавить проверку `sip-ip`,
  restart после changes
- `scripts/ip-sync.sh` — опционально, DHCP-автосинк

### Docker/Деплой
- `docker/docker-compose.yml` — без изменений
- `docker/.env` — без изменений

---

## VI. ТЕСТ-ЧЕКЛИСТ ПЕРЕД ДЕПЛОЕМ

1. ☐ `make test-fast` — все тесты зелёные (261+ OK)
2. ☐ `scripts/install_freeswitch.sh` — все проверки пройдены
3. ☐ `sofia status` — zoiper bound to 127.0.0.1:5060
 4. ☐ `eval $${local_ip_v4}` — 192.168.1.194 (актуальный IP Mac)
 5. ☐ `fs_cli -x "eval \${default_password}"` → НЕ `1234`
    (значение в vars.xml, не в этом документе)
 6. ☐ `fs_cli -x "originate loopback/4400/default 4400 XML default"` —
    call answered без sleep
 7. ☐ `curl -sf http://127.0.0.1:9705/ready` — STT host ready
 8. ☐ `curl -sf http://127.0.0.1:9600/health` — TTS ready
 9. ☐ `curl -sf http://127.0.0.1:9400/ready` — telephony ready
 10. ☐ Диалог через HTTP API (без SIP):
     `CID=$(curl -s -X POST http://127.0.0.1:9400/calls -d '{}' | python3 -c "import sys,json;print(json.load(sys.stdin)['call_id'])")`
     `curl -s -X POST http://127.0.0.1:9400/calls/$CID/turn_text -d '{"text":"здравствуйте"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['reply'])"`
     → ответ Веры не пустой, не крючок
  11. ☐ Живой звонок Zoiper → 4400 → 5 ходов → завершение (после S1)
  12. ☐ DHCP reservation на роутере для MAC `36:7f:b5:4c:85:cc`
      → IP `192.168.1.194` (ручное действие)

---

# MossVoice — Мост Mac ↔ сервер для реальных звонков (2026-09-01)

> Расширяет раздел III/IV и реализует `FIXES_PLAN.md` пункты
> **P10** (server deploy) и **P11** (Inbound DID → 4400).
> Не переписывает их — конкретизирует "как именно", пошагово.


## Зачем так, а не проще


STT (Qwen3-ASR) и TTS (Silero/Qwen3-TTS) сейчас крутятся ЛОКАЛЬНО на Mac
через MLX (ускорение Apple Silicon). На обычном Linux-VPS этого ускорения
нет — переносить туда весь стек означало бы либо сильно просевшую по
скорости CPU-инференцию, либо переход на платные облачные STT/TTS API
(доп. расходы + новая точка отказа). Поэтому: **компьютинг остаётся на
Mac, "сервак" — это только тонкий публичный шлюз**, который решает
ОДНУ проблему — у Mac дома нет стабильного публичного IP (тот же DHCP,
который уже ломал внутреннюю сеть, + вероятный CGNAT у провайдера —
входящие соединения на домашний IP скорее всего вообще не достучатся).


Схема: `Реальный телефон → SIP-транк провайдера → VPS (стабильный IP) →
WireGuard-туннель → Mac (FreeSWITCH + STT/TTS/LLM, как сейчас)`.


Дополнительный бонус: VPS с исходящим-only туннелем от Mac полностью
снимает DHCP-головную боль для ЭТОГО канала — Mac всегда сам
подключается НАРУЖУ к туннелю, ему не нужен статический домашний IP,
и роутер трогать не надо (в отличие от Фазы 1 плана S1-S4).


---

## Уровень 0 (общий для всего, ~30-40 мин) — VPS + WireGuard-хаб


**Задача 0.1 — Взять дешёвый VPS**
- Любой провайдер (Hetzner/DigitalOcean/Vultr), минимальная конфигурация
  (1 vCPU/1GB хватает — это только NAT-форвардинг, не инференс)
- Стоимость: ~4-6$/мес
- Нужен статический публичный IPv4


**Задача 0.2 — WireGuard на VPS (сервер туннеля)**
```bash
apt install wireguard
wg genkey | tee /etc/wireguard/server_private.key | wg pubkey > /etc/wireguard/server_public.key
```
`/etc/wireguard/wg0.conf` на VPS:
```ini
[Interface]
Address = 10.10.0.1/24
ListenPort = 51820
PrivateKey = <server_private.key>


[Peer]   # Mac
PublicKey = <mac_public.key>
AllowedIPs = 10.10.0.2/32
```


**Задача 0.3 — WireGuard-клиент на Mac**
```bash
brew install wireguard-tools
wg genkey | tee mac_private.key | wg pubkey > mac_public.key
```
`/opt/homebrew/etc/wireguard/wg0.conf` на Mac:
```ini
[Interface]
Address = 10.10.0.2/24
PrivateKey = <mac_private.key>


[Peer]   # VPS
PublicKey = <server_public.key>
Endpoint = <VPS_PUBLIC_IP>:51820
AllowedIPs = 10.10.0.0/24
PersistentKeepalive = 25   # критично — Mac за NAT/CGNAT, keepalive держит дырку живой
```
`wg-quick up wg0` на обеих сторонах. Проверка: `ping 10.10.0.2` с VPS
и `ping 10.10.0.1` с Mac — должно работать НЕЗАВИСИМО от того, что
происходит с домашним IP/DHCP.


**Как проверить уровень 0:** пинг туннеля стабилен даже после того, как
`ipconfig getifaddr en0` на Mac сменится (смоделировать переподключением
Wi-Fi) — если пинг не рвётся, туннель решает ту самую DHCP-проблему
из S3 для этого канала.


---

## Уровень 1 (быстрый тест, без денег за номер) — свой телефон через туннель


Для проверки "звонить не только с Zoiper на том же Mac" — БЕЗ SIP-транка
и реального номера:


1. Поставить WireGuard-приложение (официальное, App Store/Play Store) на
   свой телефон, добавить его вторым peer в `wg0.conf` на VPS
   (`AllowedIPs = 10.10.0.3/32`)
2. На телефоне — Zoiper/Linphone, сервер = `10.10.0.2` (Mac напрямую
   через туннель), порт 5060, те же креды что у тестового профиля
3. Звонок идёт: телефон → WireGuard → VPS → WireGuard → Mac напрямую,
   без публичного SIP вообще — минимальная поверхность атаки


**Это можно сделать прямо сейчас, без SIP-транка, и это даст первый
живой звонок НЕ с loopback того же Mac** — разумный шаг между "Zoiper на
Mac" и "настоящий телефонный номер".


---

## Уровень 2 (продакшн) — реальный номер (DID) через SIP-транк


**Задача 2.1 — SIP-транк провайдер**
Варианты: Telnyx, Flowroute, VoIP.ms, Twilio Elastic SIP Trunking —
у всех есть готовые гайды под FreeSWITCH. Даёт: DID (реальный номер) +
маршрутизацию входящих на ваш VPS по IP-аутентификации (без пароля,
просто провайдер знает ваш VPS IP и шлёт SIP туда) — так проще и
безопаснее чем регистрация с паролем наружу.
Стоимость: ~1-2$/мес за номер + ~0.005-0.01$/мин разговора (уточнить
у конкретного провайдера).


**Задача 2.2 — Форвардинг SIP+RTP через туннель (на VPS)**
Самый простой вариант — DNAT, без второго FreeSWITCH/Kamailio на VPS:
```bash
# на VPS, диапазон RTP-портов ДОЛЖЕН совпадать с тем, что реально
# в вашем sofia-профиле (rtp-start-port/rtp-end-port) — проверить
# в internal.xml/zoiper.xml, не полагаться на дефолт 16384-32768
iptables -t nat -A PREROUTING -p udp --dport 5060 -j DNAT --to-destination 10.10.0.2:5060
iptables -t nat -A PREROUTING -p udp --dport 16384:32768 -j DNAT --to-destination 10.10.0.2
iptables -t nat -A POSTROUTING -j MASQUERADE
```
Апгрейд на Kamailio/OpenSIPS/второй FreeSWITCH — только если понадобится
failover, несколько бэкендов или транскодинг. Для одного Mac и одного
номера DNAT достаточно и проще в обслуживании.


**Задача 2.3 — Dialplan: public-контекст → 4400**
Сейчас `4400 не доступен снаружи` (зафиксировано в P10) — это
осознанное ограничение, снимать ТОЛЬКО после Задачи 2.4 (см. ниже).
Реализация — P11 уже описывает верно: `Inbound DID → канальные vars
(moss_did/caller_e164/call_id/direction) → 4400`. Новый extension в
`dialplan/public/`, НЕ в `default/` (внутренний контекст трогать не надо).


**Задача 2.4 — Хардненинг ПЕРЕД тем как включать (обязательно, не опция)**


У этого проекта уже дважды была ровно эта категория ошибки — стоковый
`default_password=1234` и закоммиченный ESL-пароль. Публичный SIP —
третий шанс наступить на те же грабли, только теперь с реальными
деньгами на кону (toll fraud):


1. **VPS-файрвол**: входящий 5060/RTP — только с IP-диапазонов
   SIP-транк провайдера (публикуются в их доках), НЕ `0.0.0.0/0`
2. **Отдельный sofia-профиль на Mac** для туннельного трафика —
   не тот же `zoiper`/`internal`, что для локальных тестов; ACL —
   принимать только с `10.10.0.1` (VPS-конец туннеля)
3. **Уникальный пароль** для этого профиля — не переиспользовать
   `default_password` и не хардкодить в файлах, которые могут попасть
   в git (ровно та ошибка, что уже была дважды)
4. **Запретить/ограничить исходящие** на этом профиле — если его
   скомпрометируют, цель атаки почти всегда исходящие международные
   звонки за ваш счёт, а не что-то ещё
5. **fail2ban** (или аналог) на VPS по логам auth failures FreeSWITCH —
   боты сканируют весь IPv4 на открытый 5060 в течение МИНУТ после
   того, как порт становится достижим, это не гипотетический риск
6. Только после пп.1-5 подтверждены — снимать ограничение из P10
   (`4400 не доступен снаружи`), и то маршрутизировать ТОЛЬКО
   конкретный DID, не wildcard


**Как проверить:**
1. `sipvicious`/`svmap` с внешней машины по вашему VPS IP — до включения
   защит должен либо не отвечать, либо явно резать по ACL
2. Тестовый звонок с реального телефона на купленный DID → должен
   дойти до Веры через весь туннель
3. Проверить лог VPS/Mac на попытки REGISTER с чужих IP в первые
   сутки после включения — почти гарантированно будут, важно что
   они блокируются, а не проходят


## Чек-лист перед тем, как давать номер реальным пользователям

1. ☐ Уровень 0 — туннель стабилен независимо от DHCP на Mac
2. ☐ Уровень 1 — звонок с телефона через туннель прошёл и прозвучал нормально
3. ☐ VPS-файрвол ограничен IP-диапазонами транк-провайдера
4. ☐ Отдельный sofia-профиль + уникальный пароль + ACL на 10.10.0.1
5. ☐ Исходящие с публичного профиля запрещены или жёстко ограничены
6. ☐ fail2ban/анти-скан на VPS работает и залогирован тестовый бан
7. ☐ `public` dialplan маршрутизирует ТОЛЬКО купленный DID, не wildcard
8. ☐ 3 тестовых звонка подряд с реального телефона — стабильно

