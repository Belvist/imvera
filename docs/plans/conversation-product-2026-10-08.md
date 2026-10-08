# IMVERA: путь до приёмки диалогового продукта

Дата: 2026-10-08. Целевая ветка `feature/voice-zoiper-m5`, исходная база
`2c7cc19147aba178350b6ef9614d9eb61c3b3666`. Это план работ и критерии
приёмки, а не утверждение о готовности production.

Этап1 source cut опубликован на cdb3e7c; CI37856818078:11/11 SUCCESS,
3549 PASS/0 FAIL/3 SKIP. Этапы2–7 OPEN; обнаруженные текущие blockers
и actual captures ниже. Target deployment/audio не выполнялись.

## Что строим

Пожилой человек говорит в своём темпе, может рассказать историю, сообщить
несколько жалоб, задать вопрос, отказаться от одного уточнения и продолжить
разговор. Вера отвечает на содержание, сохраняет тему и спрашивает только
недостающую информацию, которая влияет на следующий полезный шаг. Число
вопросов само по себе не является результатом заботы.

Остаются один EngineState, один Reducer, один выбор следующего хода и
канонический ResponsePlan → renderer → CallActor → TTS. Safety/consent/stop,
доказательные факты и разрешение действий остаются за кодом. Новой FSM,
второго планировщика и набора сценариев рядом с существующим не будет.
ADR-025/026 продолжают действовать: live generative renderer не включается.
Его возможный benchmark — отдельное решение, не скрытая часть этого cut.

## Текущий фундамент и оставшиеся владельцы

Уже проверены исходниками/CI: канонический Understand, многожалобные эпизоды,
grounded routine coverage, вежливое завершение темы, продолжение услышанного
приглашения, отмена/ledger, ограничения inference и PCM-кэша. Личные темы
выбирает ActionPolicy v10; обычный check-in всё ещё преимущественно legacy.
Счётчик check-slot элементов независимо от покрытых тем удерживает optional
coverage. Глобальный medical cutover, живой turn-taking, Core delivery и
100 полных звонков ещё не приняты.

## Этапы и критерии выхода

| Этап | Работа в существующем владельце | Доказательство выхода |
| --- | --- | --- |
| 1 — убрать лишнее условие опроса | `coverage.coverage_met`: accepted domains вместо требования количества check-slot ответов; удалить старый closing predicate | Одни и те же 3 факта одним/несколькими ходами дают одинаковый остаток needs; mood/sleep не навязываются без mission; story после раннего приглашения не закрывается |
| 2 — единый выбор уместного хода | Existing ActionPolicy/DecisionRouter: различить required/optional needs, заменить оставшуюся обязательную квоту доменов реальными mission needs, расширить authority через shadow → объяснённый diff → soft; legacy владельца удалить после приёмки замены | Ноль необъяснённых critical divergences; user question прежде необязательного опроса; required clinical needs не потеряны; selector latency измерена |
| 3 — содержательная реакция и тема | Existing discourse + ResponsePlan/realization: grounded response, meaningful follow-up, continuation/resume и короткий ACK без обязательного вопроса | 15 типов диалогов из ADR-028; no fact invention, no repeated known/declined need; несколько тематических ходов, смена/возврат темы и исправление |
| 4 — слышимый realtime | Existing VAD/STT/turn pipeline/CallActor: endpointing для медленной речи, ограниченные previews, слышимое cancel/барge-in, TTS/prosody | Реальные WAV/trace через FreeSWITCH на точном SHA; proposed targets end-of-speech→first audible PCM p95≤1.5s, audible interruption stop p95≤250ms; не срезать медленные фразы |
| 5 — надёжный продуктовый результат | Existing persistence/outbox → тестовый Core → получатель; idempotency/retry/ack | Реальный ID события, ack Core и receipt каждого тестового получателя; outage/replay не теряет и не дублирует тревогу; текст Веры соответствует реально доступному действию |
| 6 — ёмкость и стоимость | Existing workers/admission/replicas: real STT+TTS service curves, очереди/deadlines, распределение нагрузки | 10→25→50→100 полных SIP/RTP разговоров и burst, минимум 60 минут soak; p95 не выходит за принятые SLO, нет потерянных turns/cancel, peak RAM/VRAM и CPU/GPU измерены |
| 7 — человеческая приёмка и rollout | Тот же путь звонка, versioned config, малый cohort, rollback одним revert/deploy | 100 последовательных полных звонков; blind listening ≥30 записей/≥3 оценщиков, предложенный median warmth≥4/5; 0 ложных обещаний/ложных safety в acceptance pack; мониторинг и rollback проверены |

Пороговые времена и human score выше — целевые критерии, не измеренные
достижения и не медицинская гарантия. Сначала фиксируем baseline и условия
телефонной полосы, затем принимаем или корректируем SLO на основании данных.
Один успешный звонок не заменяет пакет и soak.

## Первый cut: достаточность фактов вместо количества ответов

В full check-in `coverage_met` требует одновременно 3 известных домена и
3 check-slot/episode элемента. Питание и лекарства находятся в accepted
coverage_records, но не входят во второй счётчик. Поэтому фраза
«Мне хорошо. Сегодня поела, таблетки уже приняла» закрывает wellbeing,
nutrition, medication и всё равно получает вопрос о настроении.

Удаляем второй барьер в **существующем** coverage owner. Сохраняем target
3 evidence-backed domains для явно включённого full check-in: это ещё не
полное снятие протокольной квоты. Short preset/default flags не меняются.
Unknown/refusal/чужое/прошлое не становятся ответами. Required background
goals, клинический planner, safety и delivery ownership не меняются.
`content_exchanges` остаётся исторической диагностикой старых capture,
но больше не решает, сколько вопросов человек обязан выслушать.

Этот cut прежде был отложен из-за invitation/summary ownership. Эти дефекты
исправлены в 4d3ad19/f7b748ca; теперь повторяем прежний multi-fact→story
контрпример и длинные продолжения, включая cancelled/unheard invitation.
Rollback — revert этого cut, не новый флаг/параллельный policy.

## Стоимость и масштабирование

Миллион зарегистрированных пользователей не равен миллиону одновременных
звонков. Ёмкость рассчитываем по concurrent calls, частоте turns и burst.
Для C звонков и T финальных реплик/минуту STT arrival rate = C×T/60;
preview adds отдельную измеренную нагрузку. Сервисные кривые STT/TTS и
target utilization определяют число реплик. Current historical CPU STT
benchmark не определяет размер GPU/TTS сервера и не подтверждает100 calls.

Fast path не вызывает генератор: Understand → evidence → существующий
selector → renderer. Резидентные STT/TTS workers и ограниченные очереди
отделены от лёгких call actors. Масштабируем inference по service curves,
bridge по измеренной duplex нагрузке; не увеличиваем один admission limit
вместо добавления вычислений. Новые model calls, p50/p95, peak memory и
429/503 измеряются отдельно, включая неуспешные запросы.

## Сравнение с конкурентами

[Официальные источники и применимые выводы](../research/voice-dialogue-competitors-2026-10-08.md).
Newo — evidence/control и реальные actions; Fish Agents — realtime SDK и
published versions; Retell — пользователь может заранее дать сведения,
поэтому node boundaries не должны навязывать анкету; Vapi — отдельные
start/stop speaking планы; PolyAI — user-led dialogue + интеграции;
ElliQ — elder companionship, иной аппаратный формат.
Ничьи опубликованные проценты/миллисекунды не являются нашим benchmark.

## Следующий cut: подтверждённые блокеры authority

После публикации первого cut на cdb3e7c повторены 15 одинаковых SDK сценариев
в isolated legacy/shadow/policy, short preset, simulated delivery и semantic ML
off; service flags не менялись. [Captured replies/state](../evaluation/information-sufficiency-2026-10-08/authority-followup.json).
Legacy/shadow speech совпала; policy меняет7 sequences и4 outcomes. Это не
автоматическая оценка качества и не принятие global cutover.

1. **Unknown disposition → legal needs.** EpisodeSnapshot/need-value отличают
   известное значение от отсутствующего, но не переносят unanswered/temporal
   disposition из EngineState. Policy повторяет onset после «Не помню».
   Следующий versioned cut должен проецировать disposition, исключать такой ASK
   из единого legal set через aliases duration/onset/temporal и НЕ объявлять
   неизвестное известным. Frozen v10 manifest не перепинывается ради зелёного CI.
2. **Correction + additional detail.** «Нет, я перепутала, спала плохо» приходит
   без correction, одновременно как wellness negative и sleep fact. Legacy
   сохраняет старый filled sleep, затем «Часто просыпалась» после summary
   достигает goodbye. Нужны единый смысл correction/domain attribution и
   reducer-owned acceptance подробности; не просто убрать goodbye или добавить
   phrase template. Проверять чужое/прошлое/отрицание/прямой stop отдельно.
3. **Clinical optional need realization.** Policy выбирает functional impact
   после уже volunteered onset/current/severity и получает generic fallback
   «про головная боль». Нужны согласование meaningful need с product sufficiency
   и существующим semantic realizer, а не ещё один обязательный вопрос.

Все три OPEN; source CI первого cut не проверяет исправление этих находок.
Промышленное включение общего policy заблокировано до их source regressions,
объяснённого differential и последующей живой приёмки.

## Внешние зависимости приёмки

Запрошенные доступы к M5 и тестовому Core пока не предоставлены. Источники,
локальные regression gates и CI проверяются здесь; фактический target SHA,
модели/flags, оригинальные WAV и receipts получаем на целевом контуре.
Никакого production rollout, «как человек» или превосходства над конкурентами
не объявляем по текстовому replay. Продолжаем независимые cuts, сохраняя
NOT VERIFIED для этих внешних gate.
