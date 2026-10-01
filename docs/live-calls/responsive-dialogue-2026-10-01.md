# Responsive dialogue: paired text replay (2026-10-01)

Base: `996bad869ad82d7ee8a6715a7b49e3f262e2d706` (merged m5). After: tested working tree; product SHA256 below identifies its bytes independently of the later docs commit.

Text simulation with ScenarioRunner, call_id=conversation-proof, elder=Тамара Юрьевна. Identical ordered inputs, Python 3.12, PYTHONPATH=cwd. Audio, heavy-model accuracy, latency, listener warmth and competitor runs: NOT_RUN. Baseline product is unchanged; its untracked file is the identical new regression test only.

## Root causes and existing owners

- Scheduler computed a complaint acknowledgment but discarded it when no clinical question remained. Accepted speaker reports now receive a reaction on ordinary question or first summary paths, after routing. Evidence must belong to the current turn and matching episode. No new question or interview budget.
- Multi-report copy inferred headache from head anatomy. It now checks the symptom concept; dizziness/numbness retain their literal labels.
- Strong-pain handoff lost the next subject; it now retains the pain reaction and names the next episode. Severity acknowledgment comparison tolerates trailing punctuation without changing stored quotes.
- Summary bypassed structured Renderer acknowledgments; public composition could duplicate the acknowledgment. Renderer and actual emission now share acknowledgment/body components. Gratitude appears once.
- Personal thread uses its existing consumed hook for an optional invitation. Relief requires a confirmed, current-turn, speaker current=resolved observation matching the episode; administrative completion, past symptoms and topic preferences cannot trigger it.

## Source fingerprints

| Product file | Before SHA256 | After SHA256 |
| --- | --- | --- |
| conversation_policy.py | `326781b0d5e61ecf07482c0d3ed824e2cdaefea2132a34523c557cbef461d871` | `8f9f8833fc6e2eb8cceede8db6ab16cbb9e3154a1351fdeae024ebd5ba64b9ad` |
| questions.py | `11ae1b82e867a6bfa5c980962a49774d0b1ec98616d7a08194fa35aaefc5d8b5` | `fe61b5e69a3abcbad13716bb0cbcf200ee0488ce58e2b2d0a9b5f896f41fa252` |
| reducer.py | `d3c4c24efe914eea60efd67b8a6dcd8432f9cf86c70f9584a050517ea8150793` | `2cb62fcca83cb58bb730dcf2a85f071b8da977e0bc3e8f5b227b28394d2966dd` |
| response_plan.py | `4239f75ddd122bb349b62894e408d70bb6904fecd242c6ed21f70319f7e7f8e9` | `72b12db33edda4d8316529e1b31e9ce21660c060cd176c00603245072fb5c9a0` |

## Full output for identical inputs

Each list includes the initial greeting and all emitted replies, including unchanged controls.

### complete_answer

Inputs: ["Голова болит уже две недели, но терпимо.", "Нет.", "До свидания."]

Before:

- Здравствуйте. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
- Хорошо. Что-то ещё хотите сказать?
- Спасибо, Тамара Юрьевна. Я записала: головная боль. На сегодня всё. Берегите себя.
- До свидания, Тамара Юрьевна. Всего вам хорошего.

Closed: True; closing_reason: `goodbye`.
After:

- Здравствуйте. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
- Жаль, что голова болит. Что-то ещё хотите сказать?
- Спасибо, Тамара Юрьевна. Я записала: головная боль. На сегодня всё. Берегите себя.
- До свидания, Тамара Юрьевна. Всего вам хорошего.

Closed: True; closing_reason: `goodbye`.

### complete_multi

Inputs: ["Голова болит с утра терпимо, руки ноют сейчас.", "Нет."]

Before:

- Здравствуйте. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
- Хорошо. Что-то ещё хотите сказать?
- Спасибо, Тамара Юрьевна. Я записала: головная боль и руки ноют. На сегодня всё. Берегите себя.

Closed: False; closing_reason: `None`.
After:

- Здравствуйте. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
- Понимаю, голова болит и руки ноют. Что-то ещё хотите сказать?
- Спасибо, Тамара Юрьевна. Я записала: головная боль и руки ноют. На сегодня всё. Берегите себя.

Closed: False; closing_reason: `None`.

### late_complaint

Inputs: ["Руки болят уже две недели.", "Руки трясутся со вчера сильно."]

Before:

- Здравствуйте. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
- Хорошо. Что-то ещё хотите сказать?
- Спасибо, Тамара Юрьевна. Я записала: руки болят и руки трясутся. На сегодня всё. Берегите себя.

Closed: False; closing_reason: `None`.
After:

- Здравствуйте. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
- Жаль, что руки болят. Что-то ещё хотите сказать?
- Слышу вас: руки трясутся. Спасибо, Тамара Юрьевна. Я записала: руки болят и руки трясутся. На сегодня всё. Берегите себя.

Closed: False; closing_reason: `None`.

### named_handoff

Inputs: ["Голова болит и руки ноют.", "Сегодня.", "Сильно."]

Before:

- Здравствуйте. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
- Понимаю, голова болит и руки ноют. Давайте по порядку. Когда начала болеть голова — сегодня или раньше?
- Сейчас голова болит сильно или терпимо?
- Понимаю, сильная боль — это тяжело. Когда появилась эта боль — сегодня или раньше?

Closed: False; closing_reason: `None`.
After:

- Здравствуйте. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
- Понимаю, голова болит и руки ноют. Давайте по порядку. Когда начала болеть голова — сегодня или раньше?
- Сейчас голова болит сильно или терпимо?
- Понимаю, сильная боль — это тяжело. Теперь про руки. Когда появилась эта боль — сегодня или раньше?

Closed: False; closing_reason: `None`.

### dizziness

Inputs: ["Голова кружится и живот болит."]

Before:

- Здравствуйте. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
- Поняла вас. Головная боль и боль в животе — это неприятно, давайте уточним по порядку. Когда кружится голова, вы можете уверенно стоять и ходить?

Closed: False; closing_reason: `None`.
After:

- Здравствуйте. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
- Слышу вас: голова кружится и живот болит. Давайте по порядку. Когда кружится голова, вы можете уверенно стоять и ходить?

Closed: False; closing_reason: `None`.

### personal_story

Inputs: ["Мне одиноко, скучаю по дочери.", "Нет."]

Before:

- Здравствуйте. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
- Вы говорили — мне одиноко, скучаю по дочери. А что там самое главное?
- Хорошо. Что-то ещё хотите сказать?

Closed: False; closing_reason: `None`.
After:

- Здравствуйте. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
- Вы говорили: «мне одиноко, скучаю по дочери». Я вас слушаю. Хотите рассказать чуть подробнее?
- Хорошо. Что-то ещё хотите сказать?

Closed: False; closing_reason: `None`.

### relief

Inputs: ["Голова болит.", "Уже не болит."]

Before:

- Здравствуйте. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
- Жаль, что голова болит. Когда начала болеть голова — сегодня или раньше?
- Хорошо. Что-то ещё хотите сказать?

Closed: False; closing_reason: `None`.
After:

- Здравствуйте. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
- Жаль, что голова болит. Когда начала болеть голова — сегодня или раньше?
- Рада, что сейчас вам легче. Что-то ещё хотите сказать?

Closed: False; closing_reason: `None`.

### unknown_degree

Inputs: ["Голова болит.", "Не помню.", "Терпимо."]

Before:

- Здравствуйте. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
- Жаль, что голова болит. Когда начала болеть голова — сегодня или раньше?
- Понимаю, не будем угадывать. Сейчас голова болит сильно или терпимо?
- Хорошо. Что-то ещё хотите сказать?

Closed: False; closing_reason: `None`.
After:

- Здравствуйте. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
- Жаль, что голова болит. Когда начала болеть голова — сегодня или раньше?
- Понимаю, не будем угадывать. Сейчас голова болит сильно или терпимо?
- Поняла, сейчас терпимо. Что-то ещё хотите сказать?

Closed: False; closing_reason: `None`.

### urgent

Inputs: ["Не могу дышать, руки болят."]

Before:

- Здравствуйте. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
- Понимаю, это важно. Я передам информацию близким. Спасибо за разговор. До свидания.

Closed: True; closing_reason: `urgent`.
After:

- Здравствуйте. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
- Понимаю, это важно. Я передам информацию близким. Спасибо за разговор. До свидания.

Closed: True; closing_reason: `urgent`.

### refusal

Inputs: ["Не хочу разговаривать, голова болит."]

Before:

- Здравствуйте. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
- Поняла, больше не буду звонить без вашего согласия. До свидания.

Closed: True; closing_reason: `revoke_consent`.
After:

- Здравствуйте. Это сервис Амвера. Тамара Юрьевна, как вы себя чувствуете?
- Поняла, больше не буду звонить без вашего согласия. До свидания.

Closed: True; closing_reason: `revoke_consent`.

## Integration handoff

Keep canonical SpeakEffect.text as the single TTS input, including summary. bridge_text + question_text describes that same utterance; do not prepend the bridge again. Forward real playout callbacks. Keep controls/urgent/repair and mission resumption in their existing owners. Do not use a model ANSWER vote as proof of a clinical value.

Run make test-dialogue-rich test-semantic-kernel and the existing corpus/hard/agent/policy gates. Then on the Mac stand verify published SHA, actual model readiness and call 7000 with complete report, late tremor, handoff, dizziness, personal story, relief, unknown severity, refusal and urgent inputs. Save JSONL + audio; inspect per-episode facts, one question, canonical==TTS==delivered and one farewell. Listener warmth, latency and interruption handling require that gate.
