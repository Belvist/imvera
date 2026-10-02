# Dialogue comparison — captured text

Suite: `conversational-moves-v1` / `0b79c38ca190e5a2d0de9bcc2d7a3535138296d122e6e2218b82af58d222808d`.

Comparable cases: **15/15**. Missing cases remain NOT_RUN.

This is a transcript comparison, not a measured superiority or warmth/MOS score.

A: cut1a-before-policy / `00b992d3901767bf678cd28ce2d7fb6461786632` / text / 2026-10-02T19:43:32.701331+00:00.
Runtime B: actual flags, platform and full source SHA256 fingerprints are in [after-policy.json](after-policy.json), field `runtime`.
B: cut1a-after-policy / `00b992d3901767bf678cd28ce2d7fb6461786632` / text / 2026-10-02T20:01:50.752168+00:00.
Runtime B: actual flags, platform and full source SHA256 fingerprints are in [after-policy.json](after-policy.json), field `runtime`.

## volunteered_four_facts

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Самочувствие хорошее, настроение спокойное, спала хорошо, сегодня пойду гулять.
A: Хорошо, поняла. А кроме этого — по самочувствию ничего не тревожит?
B: Хорошо, поняла. А кроме этого — по самочувствию ничего не тревожит?

Input 2: Нет, больше ничего.
A: Поняла вас. А кроме этого — по самочувствию ничего не тревожит?
B: Спасибо, Тамара Юрьевна. На сегодня всё. Берегите себя.

Input 3: До свидания.
A: До свидания, Тамара Юрьевна. Всего вам хорошего.
B: До свидания, Тамара Юрьевна. Всего вам хорошего.

A SDK observations: `{'call_outcome': 'COMPLETED', 'mission_status': 'COMPLETED', 'candidate_family_status': 'GREEN'}`; episodes: 0.
B SDK observations: `{'call_outcome': 'COMPLETED', 'mission_status': 'COMPLETED', 'candidate_family_status': 'GREEN'}`; episodes: 0.

## daughter_story

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Дочь вчера приехала, хорошо посидели.
A: Понимаю.
B: Понимаю.

Input 2: Чай пили и фотографии смотрели.
A: Понимаю.
B: Понимаю.

Input 3: А потом вспоминали наши поездки.
A: Понимаю.
B: Понимаю.

Input 4: Я еще хотела рассказать про дачу.
A: Понимаю.
B: Понимаю.

A SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'PARTIAL', 'candidate_family_status': 'UNSET'}`; episodes: 0.
B SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'PARTIAL', 'candidate_family_status': 'UNSET'}`; episodes: 0.

## yesterday_story

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Вчера ходила в парк и встретила подругу.
A: Понимаю.
B: Понимаю.

Input 2: Долго сидели на скамейке и разговаривали.
A: Понимаю.
B: Понимаю.

Input 3: Я рада была ее увидеть.
A: Понимаю.
B: Понимаю.

A SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'PARTIAL', 'candidate_family_status': 'UNSET'}`; episodes: 0.
B SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'PARTIAL', 'candidate_family_status': 'UNSET'}`; episodes: 0.

## open_user_question

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: А вы любите музыку?
A: Я Вера, голосовой помощник сервиса Амвера. Звоню, чтобы узнать, как вы себя чувствуете.
B: Я Вера, голосовой помощник сервиса Амвера. Звоню, чтобы узнать, как вы себя чувствуете.

Input 2: Я часто слушаю старые песни.
A: Часто — поняла вас, записала. Сейчас это сильно беспокоит или уже терпимо?
B: Часто — поняла вас, записала. Сейчас это сильно беспокоит или уже терпимо?

A SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'COMPLETED', 'candidate_family_status': 'UNSET'}`; episodes: 1.
B SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'COMPLETED', 'candidate_family_status': 'UNSET'}`; episodes: 1.

## topic_switch

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Дочь вчера приезжала.
A: Понимаю.
B: Понимаю.

Input 2: А лучше про огород расскажу.
A: Понимаю.
B: Понимаю.

Input 3: Помидоры уже собрала.
A: Понимаю.
B: Понимаю.

A SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'PARTIAL', 'candidate_family_status': 'UNSET'}`; episodes: 0.
B SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'PARTIAL', 'candidate_family_status': 'UNSET'}`; episodes: 0.

## return_to_topic

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Дочь вчера приезжала.
A: Понимаю.
B: Понимаю.

Input 2: Сегодня я гуляла в парке.
A: Понимаю.
B: Понимаю.

Input 3: Вернемся к дочери, она фотографии привезла.
A: Понимаю.
B: Понимаю.

A SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'PARTIAL', 'candidate_family_status': 'UNSET'}`; episodes: 0.
B SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'PARTIAL', 'candidate_family_status': 'UNSET'}`; episodes: 0.

## not_recalled

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Голова болит.
A: Жаль, что голова болит. Когда начала болеть голова — сегодня или раньше?
B: Жаль, что голова болит. Когда начала болеть голова — сегодня или раньше?

Input 2: Не помню.
A: Понимаю, не будем угадывать. Когда начала болеть голова — сегодня или раньше?
B: Понимаю, не будем угадывать. Когда начала болеть голова — сегодня или раньше?

Input 3: Терпимо.
A: Сейчас голова болит сильно или терпимо?
B: Поняла вас. Спасибо, что рассказали. Спасибо, Тамара Юрьевна. Я записала: головная боль. На сегодня всё. Берегите себя.

A SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'COMPLETED', 'candidate_family_status': 'UNSET'}`; episodes: 1.
B SDK observations: `{'call_outcome': 'COMPLETED', 'mission_status': 'COMPLETED', 'candidate_family_status': 'YELLOW'}`; episodes: 1.

## ambiguous_reply

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Как-то не очень.
A: Что именно беспокоит?
B: Что именно беспокоит?

Input 2: Не знаю, как объяснить.
A: Поняла вас. А кроме этого — по самочувствию ничего не тревожит?
B: Поняла вас. А кроме этого — по самочувствию ничего не тревожит?

Input 3: Ничего не болит, просто устала.
A: Понимаю. Устала — спасибо, что рассказали. Когда это началось — сегодня или раньше?
B: Понимаю. Устала — спасибо, что рассказали. Когда это началось — сегодня или раньше?

A SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'COMPLETED', 'candidate_family_status': 'UNSET'}`; episodes: 1.
B SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'COMPLETED', 'candidate_family_status': 'UNSET'}`; episodes: 1.

## self_correction

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Самочувствие хорошее, спала хорошо.
A: Поняла вас. А кроме этого — по самочувствию ничего не тревожит?
B: Поняла вас. А кроме этого — по самочувствию ничего не тревожит?

Input 2: Нет, я перепутала, спала плохо.
A: На что жалуетесь?
B: На что жалуетесь?

Input 3: Часто просыпалась.
A: Часто — спасибо, что рассказали. Сейчас это сильно беспокоит или уже терпимо?
B: Часто — спасибо, что рассказали. Сейчас это сильно беспокоит или уже терпимо?

A SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'COMPLETED', 'candidate_family_status': 'UNSET'}`; episodes: 1.
B SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'COMPLETED', 'candidate_family_status': 'UNSET'}`; episodes: 1.

## barge_in

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Подождите, я еще не закончила.
A: Понимаю.
B: Понимаю.

Input 2: Голова болит со вчера.
A: Слышу вас: головная боль. А кроме этого — по самочувствию ничего не тревожит?
B: Слышу вас: головная боль. А кроме этого — по самочувствию ничего не тревожит?

A SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'COMPLETED', 'candidate_family_status': 'UNSET'}`; episodes: 1.
B SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'COMPLETED', 'candidate_family_status': 'UNSET'}`; episodes: 1.

## slow_speech

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Самочувствие хорошее, но вчера долго не могла уснуть.
A: Поняла вас. А кроме этого — по самочувствию ничего не тревожит?
B: Поняла вас. А кроме этого — по самочувствию ничего не тревожит?

Input 2: Сегодня спала нормально.
A: Поняла вас. А кроме этого — по самочувствию ничего не тревожит?
B: Понимаю.

A SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'COMPLETED', 'candidate_family_status': 'UNSET'}`; episodes: 0.
B SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'COMPLETED', 'candidate_family_status': 'UNSET'}`; episodes: 0.

## symptom_inside_story

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Вчера с дочерью чай пили, а голова болит со вчера, сейчас сильная боль.
A: Жаль, что голова болит. Сейчас голова болит сильно или терпимо?
B: Жаль, что голова болит. Сейчас голова болит сильно или терпимо?

Input 2: Да, сейчас тоже беспокоит.
A: Расскажите, пожалуйста, чуть подробнее про головная боль.
B: Сейчас голова болит сильно или терпимо?

A SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'COMPLETED', 'candidate_family_status': 'UNSET'}`; episodes: 1.
B SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'COMPLETED', 'candidate_family_status': 'UNSET'}`; episodes: 1.

## refuse_one_question

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Не хочу отвечать про здоровье, давайте просто поговорим.
A: Понимаю.
B: Понимаю.

Input 2: Внучка вчера приезжала.
A: Понимаю.
B: Понимаю.

Input 3: Фотографии привезла.
A: Понимаю.
B: Понимаю.

A SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'DECLINED', 'candidate_family_status': 'UNSET'}`; episodes: 0.
B SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'DECLINED', 'candidate_family_status': 'UNSET'}`; episodes: 0.

## finish_entire_call

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Спасибо, не хочу больше разговаривать.
A: Понимаю.
B: Понимаю.

Input 2: До свидания.
A: До свидания, Тамара Юрьевна. Всего вам хорошего.
B: До свидания, Тамара Юрьевна. Всего вам хорошего.

A SDK observations: `{'call_outcome': 'COMPLETED', 'mission_status': 'DECLINED', 'candidate_family_status': 'YELLOW'}`; episodes: 0.
B SDK observations: `{'call_outcome': 'COMPLETED', 'mission_status': 'DECLINED', 'candidate_family_status': 'YELLOW'}`; episodes: 0.

## just_conversation

Input 0: [opening]
A: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
B: Доброе утро. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?

Input 1: Я просто поговорить хотела, жалоб нет.
A: Понимаю.
B: Понимаю.

Input 2: Мне нравится рассказывать про сад.
A: Понимаю.
B: Понимаю.

Input 3: Розы в этом году красивые.
A: Понимаю.
B: Понимаю.

Input 4: И про соседку хотела рассказать.
A: Понимаю.
B: Понимаю.

A SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'PARTIAL', 'candidate_family_status': 'UNSET'}`; episodes: 0.
B SDK observations: `{'call_outcome': 'TECHNICAL', 'mission_status': 'PARTIAL', 'candidate_family_status': 'UNSET'}`; episodes: 0.

Changed response sequences: 4/15 comparable cases.
Human review of warmth, respect, accuracy and rhythm remains required.
