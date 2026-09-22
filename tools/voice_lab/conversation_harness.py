"""Offline conversation-quality harness v1 (Fish agent-tests style).

20 cases from real live shapes. Deterministic judge (free, honest):
thread continuation, bans, grounding, length. No LLM judge yet —
outputs are printed for human review alongside scores.
"""

from __future__ import annotations

import re
import time

from tools.voice_lab.conversation_prompt import build_messages

CASES: list[dict] = [
    {
        "id": "detective-thread",
        "history": [
            ("assistant", "Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?"),
            ("user", "Нормально, только спал плохо, до двух детектив читал."),
        ],
        "user": "Да, новый роман, не мог оторваться.",
        "known": "самочувствие хорошее, спал плохо",
        "objectives": "принимает ли лекарства",
        "must_hit": ["детектив", "роман", "интересн", "зачитал"],
        "banned_phrases": ["лекарства", "спокойной ночи"],
    },
    {
        "id": "daughter-thread",
        "history": [
            ("assistant", "Какие у вас планы на сегодня?"),
            ("user", "Да, дома буду, дочь вечером обещала заехать."),
        ],
        "user": "Ну да, одна не буду вечером.",
        "known": "планы — дома",
        "objectives": "принимает ли лекарства",
        "must_hit": ["дочь", "дочерью", "вечер", "одн"],
        "banned_phrases": ["лекарства"],
    },
    {
        "id": "strong-pain",
        "history": [
            ("assistant", "Боль сильная или терпимая?"),
            ("user", "Сильно."),
        ],
        "user": "Сильно, терпеть не могу уже.",
        "known": "головная боль",
        "objectives": "когда началось",
        "must_hit": ["сильн", "сочувств", "понимаю", "тяжело", "серьёзно"],
        "banned_phrases": ["хорошо", "лекарства"],
    },
    {
        "id": "onset-given",
        "history": [
            ("assistant", "Когда начала болеть голова — сегодня или раньше?"),
            ("user", "Не знаю, позавчера начала болеть."),
        ],
        "user": "Говорю же, позавчера.",
        "known": "головная боль началась позавчера",
        "objectives": "насколько сильная боль",
        "must_hit": ["позавчера", "поняла", "записала"],
        "banned_phrases": ["когда началось", "когда начала"],
    },
    {
        "id": "refusal",
        "history": [
            ("assistant", "Когда это началось — сегодня или раньше?"),
            ("user", "Не помню, во сколько начала болеть."),
        ],
        "user": "Да не помню я.",
        "known": "головная боль",
        "objectives": "насколько сильная боль",
        "must_hit": ["ничего страшного", "не страшно", "поняла", "ладно"],
        "banned_phrases": ["когда началось", "когда начала", "во сколько"],
    },
    {
        "id": "garbage",
        "history": [
            ("assistant", "Как вы себя чувствуете?"),
            ("user", "Белиберда какая-то."),
        ],
        "user": "Трамвай.",
        "known": "ничего",
        "objectives": "самочувствие",
        "must_hit": ["не расслышала", "повторите", "не поняла", "простите"],
        "banned_phrases": ["записала", "зафиксировала"],
    },
    {
        "id": "goodbye",
        "history": [
            ("assistant", "Спасибо, Даниил. Берегите себя. До свидания."),
            ("user", "До свидания."),
        ],
        "user": "До свидания.",
        "known": "разговор завершён",
        "objectives": "нет, попрощаться",
        "must_hit": ["свидания", "хорошего", "здоровья", "берегите"],
        "banned_phrases": ["самочувствие", "лекарства", "беспокоит"],
    },
    {
        "id": "side-question",
        "history": [
            ("assistant", "Как вы себя чувствуете?"),
            ("user", "А вы кто вообще такая?"),
        ],
        "user": "Нет, правда, кто вы?",
        "known": "ничего",
        "objectives": "самочувствие",
        "must_hit": ["вера", "амвера", "помощник", "сервис"],
        "banned_phrases": [],
    },
    {
        "id": "other-person",
        "history": [
            ("assistant", "Как вы себя чувствуете?"),
            ("user", "У мужа давление высокое, а я нормально."),
        ],
        "user": "Я-то нормально, это у него.",
        "known": "у самой самочувствие нормальное, у мужа давление",
        "objectives": "настроение",
        "must_hit": ["хорошо", "рада", "поняла", "муж"],
        "banned_phrases": ["ваше давление", "а у вас давление"],
    },
    {
        "id": "morning-plans",
        "history": [
            ("assistant", "Какие у вас планы на сегодня?"),
            ("user", "В магазин пойду и на работу потом."),
        ],
        "user": "Да, работать надо.",
        "known": "планы — магазин и работа",
        "objectives": "настроение",
        "must_hit": ["магазин", "работ"],
        "banned_phrases": ["лекарства"],
    },
    {
        "id": "sleep-bad",
        "history": [
            ("assistant", "Как вы спали?"),
            ("user", "Плохо спал, сосед сверлил.",
        )],
        "user": "Да всю ночь сверлил, гад.",
        "known": "спал плохо, мешал сосед",
        "objectives": "настроение",
        "must_hit": ["сосед", "сочувств", "понимаю", "шум"],
        "banned_phrases": ["лекарства"],
    },
    {
        "id": "meds-no",
        "history": [
            ("assistant", "Есть ли у вас лекарства, которые вы обычно принимаете?"),
            ("user", "Нет, ничего не пью."),
        ],
        "user": "Говорю, не пью ничего.",
        "known": "лекарств не принимает",
        "objectives": "настроение",
        "must_hit": ["поняла", "хорошо", "записала"],
        "banned_phrases": ["сегодня уже принимали", "лекарства утром"],
    },
    {
        "id": "correction",
        "history": [
            ("assistant", "Когда начала болеть голова — сегодня или раньше?"),
            ("user", "Да не голова, живот болит!"),
        ],
        "user": "Живот, говорю!",
        "known": "болит живот, не голова",
        "objectives": "когда начался боль в животе",
        "must_hit": ["живот", "поняла", "простите", "извините"],
        "banned_phrases": ["голова"],
    },
    {
        "id": "two-complaints",
        "history": [
            ("assistant", "Как вы себя чувствуете?"),
            ("user", "И голова болит, и живот крутит."),
        ],
        "user": "Всё сразу болит.",
        "known": "головная боль и боль в животе",
        "objectives": "когда началось",
        "must_hit": ["голова", "живот"],
        "banned_phrases": ["хорошо"],
    },
    {
        "id": "tired",
        "history": [
            ("assistant", "Как вы себя чувствуете?"),
            ("user", "Ой, устала я от ваших вопросов."),
        ],
        "user": "Устала, говорю.",
        "known": "устала от разговора",
        "objectives": "коротко завершить или продолжить",
        "must_hit": ["простите", "извините", "поняла", "коротко", "быстро"],
        "banned_phrases": ["лекарства", "настроение"],
    },
    {
        "id": "no-answer",
        "history": [
            ("assistant", "Как вы себя чувствуете?"),
            ("user", "Алло, алло, вас не слышно."),
        ],
        "user": "Алло?",
        "known": "плохо слышно",
        "objectives": "проверить связь",
        "must_hit": ["слышно", "связь", "повторите", "громче"],
        "banned_phrases": ["записала", "самочувствие хорошее"],
    },
    {
        "id": "wellness-good",
        "history": [
            ("assistant", "Как вы себя чувствуете?"),
            ("user", "Хорошо себя чувствую."),
        ],
        "user": "Да, всё отлично.",
        "known": "самочувствие хорошее",
        "objectives": "настроение",
        "must_hit": ["рада", "хорошо", "отлично", "замечательно"],
        "banned_phrases": ["жаль", "сочувствую", "лекарства"],
    },
    {
        "id": "night-pain",
        "history": [
            ("assistant", "А ночью не болело?"),
            ("user", "Ночью ныло, да.",
        )],
        "user": "Под утро отпустило.",
        "known": "ночью ныло, под утро отпустило",
        "objectives": "как сейчас",
        "must_hit": ["ночью", "утро", "отпустило", "сейчас"],
        "banned_phrases": ["лекарства"],
    },
    {
        "id": "its-answer",
        "history": [
            ("assistant", "Есть ли сейчас ещё что-то важное, о чём мне стоит знать?"),
            ("user", "Да нет, всё вроде."),
        ],
        "user": "Нет, ничего больше.",
        "known": "жалоб больше нет",
        "objectives": "поблагодарить и завершить",
        "must_hit": ["спасибо", "хорошо", "поняла"],
        "banned_phrases": ["лекарства", "беспокоит"],
    },
    {
        "id": "sleep-followup",
        "history": [
            ("assistant", "Как вы спали?"),
            ("user", "До двух детектив читал.",
        )],
        "user": "Ага, детектив.",
        "known": "читал детектив до двух",
        "objectives": "выспался ли",
        "must_hit": ["детектив", "интересн", "зачитал"],
        "banned_phrases": ["лекарства"],
    },
]

_QUESTION = "?"
_GREETING = re.compile(r"(здравствуйте|доброе утро|добрый вечер)", re.I)
_STATE_LEAK = re.compile(
    r"(goal|wellness\s*=|sleep\s*=|объектив|служебно|желательно узнать|точно известно)",
    re.I,
)
_PROMISE = re.compile(r"(вызову|приеду|гарантирую|обещаю|позвоню\s+врачу)", re.I)
_TY = re.compile(r"(^|[\s,.!])(давай|слушай|ты\s+же)([\s,.!]|$)", re.I)


def judge(case: dict, text: str) -> dict:
    """Deterministic checks. Returns {pass: bool, fails: [reasons]}."""
    fails: list[str] = []
    t = (text or "").strip()
    if not t:
        return {"pass": False, "fails": ["empty"]}
    low = t.lower()
    if not any(k.lower() in low for k in case["must_hit"]):
        fails.append(f"thread-miss (need one of {case['must_hit']})")
    for b in case["banned_phrases"]:
        if b.lower() in low:
            fails.append(f"banned: {b!r}")
    if t.count(_QUESTION) > 1:
        fails.append("two-questions")
    if case["id"] != "goodbye" and _GREETING.search(t):
        fails.append("greeting-repeat")
    if _STATE_LEAK.search(t):
        fails.append("state-leak")
    if _PROMISE.search(t):
        fails.append("promise")
    if _TY.search(t):
        fails.append("familiar-ty")
    if len(t.split()) > 40:
        fails.append("too-long")
    return {"pass": not fails, "fails": fails}


def run_harness(model_id: str, max_tokens: int = 48) -> dict:
    from mlx_lm import load, stream_generate

    model, tokenizer = load(model_id)
    # warmup
    msgs = build_messages([], "Привет.", "ничего", "нет")
    prompt = tokenizer.apply_chat_template(
        msgs, add_generation_prompt=True, enable_thinking=False
    )
    for _ in stream_generate(model, tokenizer, prompt=prompt, max_tokens=4):
        pass
    results = []
    total_ms = 0.0
    for case in CASES:
        msgs = build_messages(
            case["history"], case["user"], case["known"], case["objectives"]
        )
        prompt = tokenizer.apply_chat_template(
            msgs, add_generation_prompt=True, enable_thinking=False
        )
        t0 = time.monotonic()
        out = ""
        for chunk in stream_generate(
            model, tokenizer, prompt=prompt, max_tokens=max_tokens
        ):
            out += chunk.text if hasattr(chunk, "text") else str(chunk)
        ms = (time.monotonic() - t0) * 1000.0
        total_ms += ms
        verdict = judge(case, out)
        results.append({"id": case["id"], "ms": round(ms, 1), **verdict, "text": out.strip()[:220]})
    passed = sum(1 for r in results if r["pass"])
    return {
        "model": model_id,
        "passed": passed,
        "total": len(results),
        "avg_ms": round(total_ms / len(results), 1),
        "results": results,
    }


if __name__ == "__main__":
    import json
    import sys

    model_id = sys.argv[1] if len(sys.argv) > 1 else "mlx-community/Qwen3-1.7B-4bit"
    report = run_harness(model_id)
    print(f"{report['model']}: {report['passed']}/{report['total']} avg {report['avg_ms']} ms")
    for r in report["results"]:
        mark = "PASS" if r["pass"] else "FAIL"
        print(f"[{mark}] {r['id']} ({r['ms']} ms) {r['fails'] if not r['pass'] else ''}")
        print(f"       {r['text']}")
    with open(f".run/harness_{model_id.split('/')[-1]}.json", "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
