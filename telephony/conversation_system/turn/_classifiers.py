"""Text classifiers — ported from core.dialogue.classifiers (logic only)."""
from __future__ import annotations

import re

from conversation_system.turn._cleaners import short_real_answer

_CLOSING_DIRECT_RE = re.compile(
    r"(давай(те)?\s*,?\s*пока|пока\s*,?\s*давай(те)?|"
    r"(вс[еёю]|ну|ладно|хватит)\s*,?\s*(давай\s*)?пока|"
    r"да\s*,?\s*вс[её]\s*пока|"
    r"буду прощаться|будем прощаться|пора прощаться|заканчиваю разговор)",
    re.IGNORECASE,
)

_CLOSING_RE = re.compile(
    r"(до свидания|до свиданья|досвидания|всего доброго|всего хорошего|"
    r"до встречи|прощайте|спасибо за звонок|на сегодня всё|заканчиваем|"
    r"не буду мешать|пойду отдыхать|позвоню позже|будьте здоровы|"
    r"берегите себя|пока пока|пока-пока|давай(те)?\s*,?\s*пока|"
    r"пока\s*,?\s*давай|"
    r"(вс[еёю]|ну|ладно|хватит)\s*,?\s*(давай\s*)?пока|"
    r"да\s*,?\s*вс[её]\s*пока|"
    r"буду прощаться|будем прощаться|пора прощаться|заканчиваю разговор|"
    r"давай(те)?\s+пок[ао]\w*|"
    r"(?:^|[\s,])[а-яё]{2,}\s+пока\s*[!?.]*$|"
    r"(?:^|[\s,])пока\s*[!?.]*$)",
    re.IGNORECASE,
)

_CLOSING_TYPO_RE = re.compile(
    r"давай(те)?\s+пок[ао]\w*",
    re.IGNORECASE,
)

_REFUSAL_RE = re.compile(
    r"^\s*(нет\s*[,]?\s*спасибо|нет\s*[,]?\s*не\s*(надо|нужно)|"
    r"не\s*(надо|нужно)|спасибо\s*[,]?\s*не\s*(надо|нужно)|"
    r"ничего\s*[,]?\s*не\s*(надо|нужно|хочу|буду)|"
    r"ничего\s*не\s*хочу|ничего\s*не\s*буду|нет\s*ничего|"
    r"всё\s*[,]?\s*ничего|всё\s*есть|всё\s*есть\s*у\s*меня)",
    re.IGNORECASE,
)

_GREETING_RE = re.compile(
    r"^\s*(здравствуйте|здравствуй|привет|добрый\s+(день|утро|вечер)|"
    r"доброе\s+утро|добрый\s+день|"
    r"алло|ало|алле|алё|ала)\s*[!?.]*$",
    re.IGNORECASE,
)

_REPAIR_RE = re.compile(
    r"(?:повтори|повторите|ещё\s+раз|еще\s+раз|скажи\s+ещё|скажите\s+ещё|"
    r"что\s+ты\s+сказал|что\s+вы\s+сказал|как\s+вы\s+сказал|"
    r"что\s+вы\s+спросил|что\s+ты\s+спросил|"
    r"я\s+не\s+понял\w*\s+вопрос|я\s+не\s+понял\w*\s+вопрос|"
    r"что\s+за\s+вопрос|можно\s+ещё\s+раз\s+вопрос|можно\s+еще\s+раз\s+вопрос|"
    r"повторите\s+вопрос|"
    r"не\s+расслышал|не\s+расслышала|не\s+слышу|плохо\s+слышно)",
    re.IGNORECASE,
)

_ACK_RE = re.compile(
    r"^\s*(понятно|ясно|ладно|хорошо)\s*[!?.]*$",
    re.IGNORECASE,
)

_SHORT_REPAIR_RE = re.compile(
    r"^\s*(?:что|а|чего|зачем|где|когда)\s*\??\s*$",
    re.IGNORECASE,
)

_HELP_RE = re.compile(
    r"\b(помогите|помощь\s+нужн|нужна\s+помощь|помоги|спасите)\b",
    re.IGNORECASE,
)

_WORRY_RE = re.compile(
    r"(беспоко\w*|волну\w*|пережива\w*).*(?:за|о)\s+(?:меня|нас|бабушк|дедушк|мам|пап)",
    re.IGNORECASE,
)

_QUESTION_WORDS = (
    "скажи", "расскажи", "что", "как", "почему", "зачем", "где",
    "куда", "откуда", "когда", "кто", "сколько", "чей", "какой",
    "какая", "какое", "какие", "который", "которая", "которое",
    "которые", "говори", "можешь", "может", "слышишь", "понимаешь",
    "поможешь", "what", "how", "why",
)

_YES_NO_QUESTION_RE = re.compile(
    r"^(?:вы|ты)\s+(?:меня\s+)?(?:записыва\w*|слыш\w*|понима\w*|"
    r"вид\w*|помн\w*|зна\w*|звон\w*|переда\w*|мож\w*)\b",
    re.IGNORECASE,
)

_SIDE_PRIVACY_RE = re.compile(
    r"(записыва|запись\s+разговор|слуша|прослуш|конфиденц|"
    r"личн\w*\s+данн|\bадрес\b|\bпаспорт\b|"
    r"кто\s+услышит|кто\s+увидит|переда\w*\s+родн)",
    re.IGNORECASE,
)
_SIDE_PURPOSE_RE = re.compile(
    r"(зачем\s+(?:вы|ты)\s+звон|почему\s+(?:вы|ты)?\s*звон|"
    r"зачем\s+этот\s+звон|для\s+чего\s+(?:вы|ты)?\s*звон)",
    re.IGNORECASE,
)
_SIDE_IDENTITY_RE = re.compile(
    r"(кто\s+(?:вы|ты)|как\s+вас\s+зовут|кто\s+такая\s+(?:вера|имвера)|"
    r"что\s+за\s+сервис|что\s+такое\s+имвера)",
    re.IGNORECASE,
)


def is_closing_direct(text: str) -> bool:
    return bool(text and _CLOSING_DIRECT_RE.search(text))


def is_closing(text: str) -> bool:
    if not text:
        return False
    if _CLOSING_RE.search(text):
        return True
    low = text.strip().lower()
    if _CLOSING_TYPO_RE.search(low):
        return True
    if re.search(r"(?:^|[\s,])[а-яё]{2,}\s+пока\s*[!?.]*$", low):
        return True
    if re.search(r"(?:^|[\s,])пока\s*[!?.]*$", low):
        return True
    return False


_REFUSAL_CANONICAL = frozenset((
    "помощь не нужна",
    "не хочу",
    "не стоит",
    "ничего не нужно",
))


def is_refusal(text: str) -> bool:
    if not text or len(text.split()) > 8:
        return False
    low = text.strip().lower()
    if low in _REFUSAL_CANONICAL:
        return True
    return bool(_REFUSAL_RE.match(low))


def is_greeting(text: str) -> bool:
    if not text:
        return False
    return bool(_GREETING_RE.match(text.strip()))


def is_repair(text: str) -> bool:
    if not text:
        return False
    if _SHORT_REPAIR_RE.match(text.strip()):
        return True
    return bool(_REPAIR_RE.search(text))


def is_ack(text: str) -> bool:
    """Conversation-management ack — not wellness content."""
    return bool(text and _ACK_RE.match(text.strip()))


def is_help_request(text: str) -> bool:
    return bool(text and _HELP_RE.search(text.lower()))


def is_worry(text: str) -> bool:
    return bool(text and _WORRY_RE.search(text))


def is_meta_confusion(text: str) -> bool:
    if not text or is_repair(text):
        return False
    low = text.strip().lower()
    if _SHORT_REPAIR_RE.match(low):
        return True
    return bool(re.search(
        r"(?:^|\s)не\s+понял\w*\s*\??\s*$|"
        r"(?:^|\s)не\s+понимаю|"
        r"зачем\s*\??\s*$|"
        r"что\s+(ты|вы|она)?\s*(говор|рассказ|слуш)|"
        r"что\s+говорит|что\s+рассказыв|что\s+это\s+ты|"
        r"плохо\s+слышно|не\s+слышишь|слышишь\s+меня|"
        r"что\s+плохо\s+слышно",
        low))


def is_text_question(text: str) -> bool:
    if not text:
        return False
    if "?" in text:
        return True
    low = text.strip().lower()
    if not low:
        return False
    # Whisper often omits question punctuation and keeps a discourse marker:
    # «а кто вы такая», «ну какое сегодня число».
    probe = re.sub(
        r"^(?:(?:а|ну|простите|извините)\s*[,—-]?\s+)+",
        "",
        low,
    )
    probe = re.sub(r"^(?:скажите|подскажите)\s+", "", probe)
    for w in _QUESTION_WORDS:
        end = len(w)
        if probe[:end] == w and (end >= len(probe) or probe[end] not in "-—"):
            return True
    return bool(_YES_NO_QUESTION_RE.search(probe))


def side_question_kind(text: str) -> str:
    """Classify supported side questions for deterministic fallbacks."""
    cleaned = (text or "").strip()
    if _SIDE_PRIVACY_RE.search(cleaned):
        return "privacy"
    if _SIDE_PURPOSE_RE.search(cleaned):
        return "purpose"
    if _SIDE_IDENTITY_RE.search(cleaned):
        return "identity"
    return "unsupported"


def skips_stt_confirm(text: str) -> bool:
    if not text:
        return False
    if is_closing(text) or is_closing_direct(text):
        return True
    if short_real_answer(text):
        return True
    low = text.lower().strip()
    if re.search(
            r"хорошо[,\s]*(позвоню|скажу|поняла|ясно|ладно|спасибо)|"
            r"^(ладно|ясно|понятно)[,\s]",
            low):
        return True
    return False
