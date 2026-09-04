# Phrase Quality Review — Owner Read

Profile: `vera_deterministic`

## Summary

- total=**50**
- full_pass=**50** (STRUCTURAL + LANGUAGE on FINAL)
- structural_ok=**50**
- language_ok=**50**
- raw_pass=**22**
- regen_count=**4**
- fallback_count=**28**
- deterministic_fallback=**24** (control actions — by design)
- validator_fallback=**4** (LLM rejected → typed fallback)
- auto_fail=**0**

### Validator-triggered fallback histogram

- extra_question: 4

### Spoken-quality violations on FINAL

- (none)

---

## ask_wellness_1

**CASE:** ASK_WELLNESS
**ACTION:** ASK_SLOT(mood)
**USER:** нормально
**RAW QWEN OUTPUT:** Какое у вас сегодня настроение?
**FINAL OUTPUT:** Какое у вас сегодня настроение?
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** no

## ask_wellness_2

**CASE:** ASK_WELLNESS
**ACTION:** ASK_SLOT(mood)
**USER:** терпимо
**RAW QWEN OUTPUT:** Какое у вас сегодня настроение?
**FINAL OUTPUT:** Какое у вас сегодня настроение?
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** no

## ask_wellness_3

**CASE:** ASK_WELLNESS
**ACTION:** ASK_SLOT(mood)
**USER:** ничего особенного
**RAW QWEN OUTPUT:** Какое у вас сегодня настроение?
**FINAL OUTPUT:** Какое у вас сегодня настроение?
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** no

## ask_mood_1

**CASE:** ASK_MOOD
**ACTION:** ASK_SLOT(sleep)
**USER:** настроение хорошее
**RAW QWEN OUTPUT:** Как вы спали этой ночью?
**FINAL OUTPUT:** Как вы спали этой ночью?
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** no

## ask_mood_2

**CASE:** ASK_MOOD
**ACTION:** ASK_SLOT(sleep)
**USER:** спокойное
**RAW QWEN OUTPUT:** Как вы спали этой ночью?
**FINAL OUTPUT:** Как вы спали этой ночью?
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** no

## ask_mood_3

**CASE:** ASK_MOOD
**ACTION:** ASK_SLOT(sleep)
**USER:** ровное
**RAW QWEN OUTPUT:** Как вы спали этой ночью?
**FINAL OUTPUT:** Как вы спали этой ночью?
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** no

## ask_sleep_1

**CASE:** ASK_SLEEP
**ACTION:** ASK_SLOT(plans)
**USER:** спал хорошо
**RAW QWEN OUTPUT:** Вы спали хорошо. Что планируете на сегодня?
**FINAL OUTPUT:** Вы спали хорошо. Что планируете на сегодня?
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** no

## ask_sleep_2

**CASE:** ASK_SLEEP
**ACTION:** ASK_SLOT(plans)
**USER:** проснулся отдохнувшим
**RAW QWEN OUTPUT:** Что планируете на сегодня?
**FINAL OUTPUT:** Что планируете на сегодня?
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** no

## ask_sleep_3

**CASE:** ASK_SLEEP
**ACTION:** ASK_SLOT(plans)
**USER:** средне
**RAW QWEN OUTPUT:** Что планируете на сегодня?
**FINAL OUTPUT:** Что планируете на сегодня?
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** no

## ask_plans_1

**CASE:** ASK_PLANS
**ACTION:** ASK_SLOT(plans)
**USER:** внуки приедут
**RAW QWEN OUTPUT:** Что планируете на сегодня?
**FINAL OUTPUT:** Что планируете на сегодня?
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** no

## ask_plans_2

**CASE:** ASK_PLANS
**ACTION:** ASK_SLOT(plans)
**USER:** ничего особенного
**RAW QWEN OUTPUT:** Что планируете на сегодня?
**FINAL OUTPUT:** Что планируете на сегодня?
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** no

## ask_plans_3

**CASE:** ASK_PLANS
**ACTION:** ASK_SLOT(plans)
**USER:** погуляю
**RAW QWEN OUTPUT:** Что планируете на сегодня?
**FINAL OUTPUT:** Что планируете на сегодня?
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** no

## ack_narrative_1

**CASE:** ACK_NARRATIVE
**ACTION:** ACK_ONLY
**USER:** внучка приезжала, мы чай пили и разговаривали
**RAW QWEN OUTPUT:** Понимаю. Берегите себя.
**FINAL OUTPUT:** Понимаю. Берегите себя.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** no

## ack_narrative_2

**CASE:** ACK_NARRATIVE
**ACTION:** ACK_ONLY
**USER:** соседка заходила, помогла с покупками
**RAW QWEN OUTPUT:** Понимаю. Спасибо.
**FINAL OUTPUT:** Понимаю. Спасибо.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** no

## ack_narrative_3

**CASE:** ACK_NARRATIVE
**ACTION:** ACK_ONLY
**USER:** утром гулял в парке, было приятно
**RAW QWEN OUTPUT:** Понимаю. Берегите себя.
**FINAL OUTPUT:** Понимаю. Берегите себя.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** no

## wait_1 **← FALLBACK**

**CASE:** WAIT
**ACTION:** WAIT
**USER:** секундочку
**RAW QWEN OUTPUT:** (deterministic / empty)
**FINAL OUTPUT:** Конечно, я подожду.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** yes

## wait_2 **← FALLBACK**

**CASE:** WAIT
**ACTION:** WAIT
**USER:** подождите
**RAW QWEN OUTPUT:** (deterministic / empty)
**FINAL OUTPUT:** Конечно, я подожду.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** yes

## wait_3 **← FALLBACK**

**CASE:** WAIT
**ACTION:** WAIT
**USER:** минутку, вспомню
**RAW QWEN OUTPUT:** (deterministic / empty)
**FINAL OUTPUT:** Конечно, я подожду.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** yes

## fatigue_1 **← FALLBACK**

**CASE:** FATIGUE
**ACTION:** HANDLE_FATIGUE
**USER:** я устал уже отвечать
**RAW QWEN OUTPUT:** (deterministic / empty)
**FINAL OUTPUT:** Понимаю. Можем на этом закончить.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** yes

## fatigue_2 **← FALLBACK**

**CASE:** FATIGUE
**ACTION:** HANDLE_FATIGUE
**USER:** хватит вопросов
**RAW QWEN OUTPUT:** (deterministic / empty)
**FINAL OUTPUT:** Понимаю. Можем на этом закончить.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** yes

## fatigue_3 **← FALLBACK**

**CASE:** FATIGUE
**ACTION:** HANDLE_FATIGUE
**USER:** не хочу больше отвечать
**RAW QWEN OUTPUT:** (deterministic / empty)
**FINAL OUTPUT:** Понимаю. Можем на этом закончить.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** yes

## refusal_1 **← FALLBACK**

**CASE:** REFUSAL
**ACTION:** HANDLE_REFUSAL
**USER:** не хочу про настроение
**RAW QWEN OUTPUT:** (deterministic / empty)
**FINAL OUTPUT:** Хорошо, не будем об этом.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** yes

## refusal_2 **← FALLBACK**

**CASE:** REFUSAL
**ACTION:** HANDLE_REFUSAL
**USER:** давайте не будем про сон
**RAW QWEN OUTPUT:** (deterministic / empty)
**FINAL OUTPUT:** Хорошо, не будем об этом.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** yes

## refusal_3 **← FALLBACK**

**CASE:** REFUSAL
**ACTION:** HANDLE_REFUSAL
**USER:** не буду говорить о планах
**RAW QWEN OUTPUT:** (deterministic / empty)
**FINAL OUTPUT:** Хорошо, не будем об этом.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** yes

## correction_1 **← FALLBACK**

**CASE:** CORRECTION
**ACTION:** HANDLE_CORRECTION
**USER:** нет, не голова, спина
**RAW QWEN OUTPUT:** (deterministic / empty)
**FINAL OUTPUT:** Поняла, спасибо за уточнение — речь о спине.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** yes

## correction_2 **← FALLBACK**

**CASE:** CORRECTION
**ACTION:** HANDLE_CORRECTION
**USER:** не нога, а колено
**RAW QWEN OUTPUT:** (deterministic / empty)
**FINAL OUTPUT:** Поняла, спасибо за уточнение — речь о колене.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** yes

## correction_3 **← FALLBACK**

**CASE:** CORRECTION
**ACTION:** HANDLE_CORRECTION
**USER:** я имел в виду давление
**RAW QWEN OUTPUT:** (deterministic / empty)
**FINAL OUTPUT:** Поняла, спасибо за уточнение — речь о колене.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** yes

## repair_1 **← FALLBACK**

**CASE:** REPAIR
**ACTION:** REPAIR
**USER:** что вы спросили?
**RAW QWEN OUTPUT:** (deterministic / empty)
**FINAL OUTPUT:** Как вы спали этой ночью?
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** yes

## repair_2 **← FALLBACK**

**CASE:** REPAIR
**ACTION:** REPAIR
**USER:** повторите
**RAW QWEN OUTPUT:** (deterministic / empty)
**FINAL OUTPUT:** Как вы спали этой ночью?
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** yes

## repair_3 **← FALLBACK**

**CASE:** REPAIR
**ACTION:** REPAIR
**USER:** не понял
**RAW QWEN OUTPUT:** (deterministic / empty)
**FINAL OUTPUT:** Как вы спали этой ночью?
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** yes

## why_1 **← FALLBACK**

**CASE:** WHY_CALLING
**ACTION:** ANSWER_USER(WHY_CALLING)
**USER:** зачем вы звоните?
**RAW QWEN OUTPUT:** Как вы спали этой ночью?
**FINAL OUTPUT:** Мы звоним, чтобы узнать, как вы себя чувствуете, и передать близким, если им будет важно.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=False violations=['question_on_answer_user']
**SPOKEN:** ok
**REGENERATED:** yes
**FALLBACK:** yes

## why_2

**CASE:** WHY_CALLING
**ACTION:** ANSWER_USER(WHY_CALLING)
**USER:** почему вы мне звоните?
**RAW QWEN OUTPUT:** Чтобы узнать, как вы спали этой ночью. Берегите себя.
**FINAL OUTPUT:** Чтобы узнать, как вы спали этой ночью. Берегите себя.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** no

## why_3 **← FALLBACK**

**CASE:** WHY_CALLING
**ACTION:** ANSWER_USER(WHY_CALLING)
**USER:** для чего этот звонок?
**RAW QWEN OUTPUT:** Как вы спали этой ночью?
**FINAL OUTPUT:** Мы звоним, чтобы узнать, как вы себя чувствуете, и передать близким, если им будет важно.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=False violations=['question_on_answer_user']
**SPOKEN:** ok
**REGENERATED:** yes
**FALLBACK:** yes

## identity_1 **← FALLBACK**

**CASE:** IDENTITY
**ACTION:** ANSWER_USER(IDENTITY)
**USER:** кто вы?
**RAW QWEN OUTPUT:** (deterministic / empty)
**FINAL OUTPUT:** Я Вера, голосовой помощник сервиса Имвера. Звоню, чтобы узнать, как вы себя чувствуете.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** yes

## identity_2 **← FALLBACK**

**CASE:** IDENTITY
**ACTION:** ANSWER_USER(IDENTITY)
**USER:** как вас зовут?
**RAW QWEN OUTPUT:** (deterministic / empty)
**FINAL OUTPUT:** Я Вера, голосовой помощник сервиса Имвера. Звоню, чтобы узнать, как вы себя чувствуете.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** yes

## identity_3 **← FALLBACK**

**CASE:** IDENTITY
**ACTION:** ANSWER_USER(IDENTITY)
**USER:** вы кто такая?
**RAW QWEN OUTPUT:** (deterministic / empty)
**FINAL OUTPUT:** Я Вера, голосовой помощник сервиса Имвера. Звоню, чтобы узнать, как вы себя чувствуете.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** yes

## privacy_1 **← FALLBACK**

**CASE:** PRIVACY
**ACTION:** ANSWER_USER(PRIVACY)
**USER:** кто увидит мои ответы?
**RAW QWEN OUTPUT:** (deterministic / empty)
**FINAL OUTPUT:** Ваши ответы видят только близкие, которых вы подключили к сервису. Я не спрашиваю паспорт, адрес и другие личные данные.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** yes

## privacy_2 **← FALLBACK**

**CASE:** PRIVACY
**ACTION:** ANSWER_USER(PRIVACY)
**USER:** кому вы передаёте информацию?
**RAW QWEN OUTPUT:** (deterministic / empty)
**FINAL OUTPUT:** Ваши ответы видят только близкие, которых вы подключили к сервису. Я не спрашиваю паспорт, адрес и другие личные данные.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** yes

## privacy_3 **← FALLBACK**

**CASE:** PRIVACY
**ACTION:** ANSWER_USER(PRIVACY)
**USER:** это конфиденциально?
**RAW QWEN OUTPUT:** (deterministic / empty)
**FINAL OUTPUT:** Ваши ответы видят только близкие, которых вы подключили к сервису. Я не спрашиваю паспорт, адрес и другие личные данные.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** yes

## side_q_1 **← FALLBACK**

**CASE:** SIDE_QUESTION_RESUME
**ACTION:** ANSWER_USER(WHY_CALLING)
**USER:** а зачем вы вообще звоните?
**RAW QWEN OUTPUT:** Как вы спали этой ночью?
**FINAL OUTPUT:** Мы звоним, чтобы узнать, как вы себя чувствуете, и передать близким, если им будет важно.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=False violations=['question_on_answer_user']
**SPOKEN:** ok
**REGENERATED:** yes
**FALLBACK:** yes

## side_q_2 **← FALLBACK**

**CASE:** SIDE_QUESTION_RESUME
**ACTION:** ANSWER_USER(IDENTITY)
**USER:** кстати, кто вы?
**RAW QWEN OUTPUT:** (deterministic / empty)
**FINAL OUTPUT:** Я Вера, голосовой помощник сервиса Имвера. Звоню, чтобы узнать, как вы себя чувствуете.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** yes

## side_q_3 **← FALLBACK**

**CASE:** SIDE_QUESTION_RESUME
**ACTION:** ANSWER_USER(WHY_CALLING)
**USER:** почему вы звоните мне?
**RAW QWEN OUTPUT:** Как вы спали этой ночью?
**FINAL OUTPUT:** Мы звоним, чтобы узнать, как вы себя чувствуете, и передать близким, если им будет важно.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=False violations=['question_on_answer_user']
**SPOKEN:** ok
**REGENERATED:** yes
**FALLBACK:** yes

## side_q_4 **← FALLBACK**

**CASE:** SIDE_QUESTION_RESUME
**ACTION:** ANSWER_USER(IDENTITY)
**USER:** что такое имвера?
**RAW QWEN OUTPUT:** (deterministic / empty)
**FINAL OUTPUT:** Я Вера, голосовой помощник сервиса Имвера. Звоню, чтобы узнать, как вы себя чувствуете.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** yes

## resolved_1

**CASE:** RESOLVED_SYMPTOM
**ACTION:** ASK_SLOT(mood)
**USER:** голове уже легче
**RAW QWEN OUTPUT:** Какое у вас сегодня настроение?
**FINAL OUTPUT:** Какое у вас сегодня настроение?
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** no

## resolved_2

**CASE:** RESOLVED_SYMPTOM
**ACTION:** ASK_SLOT(mood)
**USER:** таблетка помогла
**RAW QWEN OUTPUT:** Какое у вас сегодня настроение?
**FINAL OUTPUT:** Какое у вас сегодня настроение?
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** no

## resolved_3

**CASE:** RESOLVED_SYMPTOM
**ACTION:** ASK_SLOT(mood)
**USER:** стало лучше
**RAW QWEN OUTPUT:** Какое у вас сегодня настроение?
**FINAL OUTPUT:** Какое у вас сегодня настроение?
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** no

## long_1

**CASE:** LONG_STORY
**ACTION:** ACK_ONLY
**USER:** вчера внучка приезжала, картошки привезла, а вечером колено заболело
**RAW QWEN OUTPUT:** Понимаю, речь о колене. Берегите себя.
**FINAL OUTPUT:** Понимаю, речь о колене. Берегите себя.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** no

## long_2

**CASE:** LONG_STORY
**ACTION:** ACK_ONLY
**USER:** утром ходил в аптеку, потом отдыхал, к вечеру стало легче
**RAW QWEN OUTPUT:** Понимаю. Берегите себя.
**FINAL OUTPUT:** Понимаю. Берегите себя.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** no

## long_3

**CASE:** LONG_STORY
**ACTION:** ACK_ONLY
**USER:** дочь звонила, мы долго говорили, потом немного устал
**RAW QWEN OUTPUT:** Понимаю. Берегите себя.
**FINAL OUTPUT:** Понимаю. Берегите себя.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** no

## close_1 **← FALLBACK**

**CASE:** CLOSE
**ACTION:** CLOSE
**USER:** до свидания
**RAW QWEN OUTPUT:** (deterministic / empty)
**FINAL OUTPUT:** Хорошо. Берегите себя, до свидания.
**GATE:** structural=True language=True full_pass=True
**VALIDATOR:** ok=True violations=[]
**SPOKEN:** ok
**REGENERATED:** no
**FALLBACK:** yes

