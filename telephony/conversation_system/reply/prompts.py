"""VERA LLM prompts and output cleaning — conversation_system canonical."""
from __future__ import annotations

import os
import re

from conversation_system.reply.guards import feminize_self
from conversation_system.reply.pools import GREETING_POOL

MVERA_GREETING = GREETING_POOL[0]

OK_WORDS = (
    "хорош", "нормал", "порядк", "отлично", "прекрас", "замечатель",
    "неплохо", "бодр", "здоров", "всё ок", "в порядке", "не жал",
    "приемле", "норм", "полегча", "полегче", "легче", "лучше",
    "супер", "класс", "шикарно", "весел", "бодряч", "неплох", "окей", "ок",
)
BAD_WORDS = (
    "плохо", "не очень", "слабо", "устал", "устала", "худо",
    "нездор", "подавле", "груст", "тревожно", "сильно устал",
    "неважно", "не важ", "хуже", "тяжел", "тревог", "сильно плохо",
)
DISTRESS_WORDS = (
    "скора", "упал", "упала", "ушиб", "сильно болит",
    "не могу встать", "не встаю", "трудно дышать", "не дыш",
    "температур", "всё болит", "вызовите врача", "врача",
    "неотложн", "срочно", "проанализ", "скорой", "не дышать",
)
MED_WORDS = (
    "принял", "приняла", "принимал", "принимала", "принял лекарство",
    "выпил", "выпила", "пью таблетки", "лекарства", "таблетки",
    "таблетку", "таблетку принял",
)
HELP_WORDS = (
    "помощь", "помогите", "помочь", "купить", "продукты", "магазин",
    "нужны лекар", "надо лекар", "врачу", "в больницу", "попросить",
    "помоге", "сходить", "позвонить близким",
)

VERA_LLM_ID = os.environ.get("MOSS_LLM_MODEL", "mlx-community/Qwen3-7B-8bit")
VERA_LLM_URL = os.environ.get("MOSS_LLM_URL", "http://127.0.0.1:9500")

VERA_SYSTEM_PROMPT = (
    "Ты — Вера, голосовой помощник сервиса Имвера. Звонишь пожилому человеку "
    "по телефону (голос, без экрана). Тёплая, уважительная, спокойная.\n"
    "ОТВЕТ: 1–2 естественные фразы (примерно 5–8 секунд речи). "
    "Сначала коротко откликнись на сказанное. Вопрос — только если уместен "
    "(0 или 1 вопросительный знак), не обязателен каждый ход.\n"
    "Стиль: женский род, обращение на «вы». Сначала выслушай и откликнись на "
    "содержание, не перебивай повесткой.\n"
    "Ты помощник сервиса, не родственница: не называй себя внучкой, дочерью, "
    "внуком и не притворяйся близким.\n"
    "Check-in идёт по темам (самочувствие → настроение → сон → планы → родные), "
    "формулируй по-новому, без шаблонов. Если человек не хочет тему — "
    "примите отказ и мягко перейди дальше.\n"
    "НИКОГДА не повторяй ту же фразу или тот же вопрос, что только что звучал.\n"
    "НЕЛЬЗЯ: выдумки (не видишь человека), эхо слов, медсоветы, "
    "обещания позвонить/вызвать/отправить, спрашивать адрес/деньги/паспорт, "
    "командный тон («давайте», «скажите сейчас»).\n"
    "На побочный вопрос абонента — ответь по существу, без вопроса по повестке "
    "в том же ответе.\n"
    "Факты и контекст передаются — используй. Формулируй свободно.\n"
    "Формат: ТОЛЬКО фраза-ответ, без кавычек и заголовков."
)

SCENARIOS_FILE = os.environ.get(
    "MOSS_SCENARIOS_FILE",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "vera_scenarios.txt",
    ),
)


def _load_scenarios(path: str | None = None) -> str:
    try:
        with open(path or SCENARIOS_FILE, encoding="utf-8") as f:
            lines = [ln.rstrip() for ln in f]
        text = "\n".join(
            ln for ln in lines if ln.strip() and not ln.lstrip().startswith("#")
        )
        return text.strip()
    except OSError:
        return ""


VERA_SCENARIOS = _load_scenarios()

_HALLUCINATION_RE = re.compile(
    r"выглядите|выглядишь|голос (хорош|звучит)|какой у вас голос", re.I
)


def _clean_llm(text: str) -> str:
    """Make model output safe for TTS."""
    t = " ".join((text or "").split())
    t = re.sub(r"^(Вера|Assistant|Ответ)\s*:\s*", "", t, flags=re.IGNORECASE)
    sentences = [s for s in re.split(r"(?<=[.!?…])\s+", t) if s.strip()]
    q_seen = False
    kept = []
    for s in sentences:
        if "?" in s:
            if q_seen:
                break
            q_seen = True
        kept.append(feminize_self(s))
    t = " ".join(kept).strip() or " ".join(sentences[:1]).strip()
    if len(t) > 380:
        cut = t[:380].rfind(" ")
        t = t[:cut].rstrip() + "."
    return t


def reply_looks_hallucinated(reply: str, transcript: str) -> bool:
    if not reply:
        return False
    if _HALLUCINATION_RE.search(reply):
        return True
    m = re.search(
        r"вы (хорошо )?(выглядите|себя чувствуете сегодня отлично)",
        reply,
        re.I,
    )
    return bool(m) and "чувствует" not in (transcript or "").lower()
