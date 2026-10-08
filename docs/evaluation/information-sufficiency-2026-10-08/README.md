# Information sufficiency: убрать лишние вопросы

Target `feature/voice-zoiper-m5`, baseline `2c7cc19147aba178350b6ef9614d9eb61c3b3666`.
[Product completion plan](../../plans/conversation-product-2026-10-08.md),
[official competitor research](../../research/voice-dialogue-competitors-2026-10-08.md).

## Причина и замена владельца

`coverage.coverage_met` требовал 3 evidence-backed domains **и** 3 check-slot
элемента. Accepted food/medication не являются check slots. Эти факты закрывали
свои темы, но не освобождали человека от дополнительных mood/sleep вопросов.

Удалён второй predicate и `MIN_CONTENT_QUESTIONS` в том же coverage owner.
`covered_domains`/Reducer по-прежнему определяют факты, существующий scheduler
выбирает ход, renderer говорит. Historical `content_exchanges` остаётся только
диагностикой предыдущих captures; его значение больше не требует вопроса.
Трёхдоменный target full opt-in сохранён: это исправление конкретной причины
анкетности, не объявление всей системы свободной беседой.

## Actual paired SDK replies

Те же входы, flags и harness, 14 scenarios/260 turns с каждой стороны:
[before](before.json), [after](after.json). Playback completion simulated,
не STT/TTS/FreeSWITCH. Capture включает SHA, dirty marker и source hashes:
в before production bytes ещё совпадают с baseline, новые тесты/docs untracked;
в after coverage predicate изменён, HEAD ещё baseline до commit.

```text
USER: Мне хорошо. Сегодня поела, таблетки уже приняла.
BEFORE: Хорошо, что поели. А какое у вас сегодня настроение?
AFTER: Понимаю. Спасибо, что сказали. А кроме этого — по самочувствию ничего не тревожит?
USER: Нет, больше ничего.
BEFORE: Спасибо, что сказали про настроение. А спалось сегодня нормально?
AFTER: Спасибо, Тамара Юрьевна. На сегодня всё. Берегите себя.
```

Отдельная пара с историей:

```text
USER: Мне хорошо. Сегодня поела, таблетки уже приняла.
AFTER: Понимаю. Спасибо, что сказали. Что-то ещё важное есть?
USER: Вчера дочь приехала, мы смотрели фотографии.
AFTER: Про дочь поняла. Расскажите, я слушаю.
USER: Долго сидели и вспоминали дачу.
AFTER: Поняла про дачу.
USER: А потом пили чай и смеялись.
AFTER: Я вас слушаю.
```

Изменены 8 captured turns в 6 сценариях: volunteer/negative/heard routine,
первый ход story и первый положительный ход перед urgent/goodbye. Последующие
urgent/stop replies не изменились. Остальные captured responses совпадают.
Eight-story regression отдельно проверяет продолжение после раннего приглашения.

SDK elapsed before p50=2.7274ms/p95=5.6440ms, after p50=2.4547ms/p95=4.8223ms.
Это небольшая synthetic sample и полный текстовый SDK, не доказанный speedup
и не phone latency. End-of-speech→PCM NOT_RUN; total model calls NOT_MEASURED.
Нового генератора/provider вызова/модели cut не добавляет.

## Verification

Identical13 new regressions on baseline:5 FAIL/8 PASS/0.58s. After: new and
existing coverage/listening/summary/status133 PASS/1.81s. Required sleep goal
остаётся unresolved и затем спрашивается; foreign/past/uncertain/unknown/refusal
не становятся покрытием. Safety/stop сохраняют приоритет.

28 первых падений в continuation gate были в setup: он продолжал отвечать на
больше не заданные mood/sleep вопросы после уже достигнутого invitation.
Мигрированы только три пути подготовки к actual invitation (runner, unheard,
CallActor PCM). Все исходные assert выражения и cancellation/summary/content
проверки сохранены. Короткий путь и existing background-goal semantics не
подменены. First full3539 PASS/4 FAIL/9 SKIP/169.11s: four conversation-corpus
expectations still demanded the old optional mood/sleep ladder. Their exact
routine input/intent data now follow the earlier invitation. The correction
test keeps its genuine mood question via explicit required goal, yields ITS
first and then tests the same bare negative reply/source quote at u-7.
Generic source/slot/unknown/clinical/control/closure assertions are retained;
no test is skipped or made less strict. Corpus plus new/continuation recheck:
89 PASS/11.16s. Final full3543 PASS/0 FAIL/9 SKIP/165.23s; rich964/13.37s,
runtime338/21.37s, kernel294/1.65s; corpus500/500/5.46s plus8 tests/29.61s.
Policy diff12 expected/0 unexplained; lint/contracts/whitespace PASS.
[Exact commands/checks](checks.json). Source CI pending publication; no target deploy.

## Integration / next acceptance

Full coverage opt-in flag/default не менялся; не восстанавливайте старое
количество вопросов искусственным required mood/sleep. Mission задаёт реальные
needs, а не продолжительность анкеты. Не добавлен второй policy/brain/state,
regex/phrase bank, глобальное medical cutover или live generative renderer.
Rollback — один revert этого cut.

NOT VERIFIED: actual M5 loaded revision/providers/flags, real speech/interruptions,
human warmth, Core→family receipts и100 одновременных SIP calls. Запрошенный
target/Core доступ отсутствует. Remaining: full target3 domains, ordinary legacy
selection, bounded content/free language и realtime acceptance. Следующий
source cut по плану — существующий selector; следующий live gate — записанный
звонок с trace на точном tested SHA и проверенным actual runtime.
