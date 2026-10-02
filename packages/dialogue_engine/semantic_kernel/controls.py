"""Canonical control contract — single enum across Kernel and DialogueEngine."""

from __future__ import annotations

import re
from dataclasses import dataclass

CANONICAL_CONTROLS = frozenset(
    {
        "none",
        "stop_call",
        "revoke_consent",
        "defer",
        "wrong_person",
        "pause",
    }
)

# Exact phrase → (dialogue_act, control). yes/no/repeat/unknown are NOT controls.
_REPAIR_PREFIXES: tuple[str, ...] = (
    "алло",
    "повторите",
    "повтори",
    "ещё раз",
    "еще раз",
    "не понял",
    "не поняла",
    "не расслышал",
    "не расслышала",
    "что вы сказали",
    "слышите",
    "слышишь",
    "ты меня",
    "вы меня",
)

_LEVEL0_EXACT: dict[str, tuple[str, str]] = {
    "угу": ("backchannel", "none"),
    "ага": ("backchannel", "none"),
    "мм": ("backchannel", "none"),
    "ммм": ("backchannel", "none"),
    "стоп": ("answer", "stop_call"),
    "хватит": ("answer", "stop_call"),
    "остановите": ("answer", "stop_call"),
    "до свидания": ("answer", "stop_call"),
    "всего доброго": ("answer", "stop_call"),
    "пока": ("answer", "stop_call"),
    "заканчиваем": ("answer", "stop_call"),
    "закончим": ("answer", "stop_call"),
    "закончим разговор": ("answer", "stop_call"),
    "давайте закончим": ("answer", "stop_call"),
    "хватит разговор": ("answer", "stop_call"),
    "подождите": ("answer", "pause"),
    "подожди": ("answer", "pause"),
    "минуточку": ("answer", "pause"),
    "секундочку": ("answer", "pause"),
    "погодите": ("answer", "pause"),
    "позже": ("answer", "defer"),
    "не хочу разговаривать": ("answer", "revoke_consent"),
    "не хочу": ("answer", "revoke_consent"),
    "не звоните": ("answer", "stop_call"),
    "больше не звоните": ("answer", "stop_call"),
    "не надо звонить": ("answer", "stop_call"),
    "не беспокойте": ("answer", "stop_call"),
    "не беспокоить": ("answer", "stop_call"),
    "не ваш человек": ("answer", "wrong_person"),
    "не тот номер": ("answer", "wrong_person"),
}


@dataclass(frozen=True)
class Level0Match:
    dialogue_act: str
    control: str


def _addressed_clauses(text: str):
    """Current speaker clauses outside quotations and reported history."""
    from packages.dialogue_engine.semantic_kernel.clauses import clause_bounds
    from packages.safety.patterns import is_past_without_present, is_third_party_only

    unquoted = re.sub(r'«[^»]*»|“[^”]*”|"[^"]*"', " ", text or "")
    clauses = clause_bounds(unquoted)
    for index, (_, _, clause) in enumerate(clauses):
        if not clause.strip():
            continue
        if is_third_party_only(clause) or is_past_without_present(clause):
            continue
        if re.search(r"\b(?:сказал\w*|говорил\w*|попросил\w*)\b", clause, re.I):
            continue
        if index + 1 < len(clauses) and re.match(
            r"^(?:так\s+)?(?:сказал\w*|говорил\w*|попросил\w*)\b",
            clauses[index + 1][2], re.I,
        ):
            continue
        yield clause


def is_local_question_refusal(text: str) -> bool:
    """An answering/topic object declines that question, never future calls."""
    return any(re.search(
        r"\bне\s+(?:хоч[уы]|буд[уы])\s+(?:больше\s+)?(?:"
        r"(?:отвеча\w*|ответить|обсужда\w*)\b|"
        r"(?:про|таблет\w*|лекар\w*)\b|"
        r"(?:говорить|разговаривать|рассказывать)\s+(?:про|об|о)\s+"
        r"(?:этот\s+вопрос|эту\s+тему|таблет\w*|лекар\w*|сон|сне|настроен\w*))",
        clause, re.I,
    ) for clause in _addressed_clauses(text))


def wants_to_continue_talking(text: str) -> bool:
    """Positive speaker volition to talk; never a health answer or consent."""
    from packages.dialogue_engine.semantic_kernel.morphology import normalize_token
    from packages.safety.patterns import is_negated_at

    talk_verbs = {"поговорить", "говорить", "разговаривать", "общаться", "пообщаться",
                  "беседовать", "побеседовать", "поболтать"}
    for clause in _addressed_clauses(text):
        tokens = list(re.finditer(r"[а-яё]+", clause, re.I))
        for index, token in enumerate(tokens):
            raw = token.group().lower()
            invitation = raw in {"давай", "давайте"}
            if not invitation and raw not in {"хочу", "хочется", "хотел", "хотела"}:
                continue
            if raw in {"хотел", "хотела"} and not re.search(r"\bбы\b", clause, re.I):
                continue
            if is_negated_at(clause, token.start()):
                continue
            for other_index in range(max(0, index - 4), min(len(tokens), index + 5)):
                other = tokens[other_index]
                if normalize_token(other.group()) not in talk_verbs:
                    continue
                if invitation and (
                    other_index <= index
                    or re.search(r"(?:им|ем)(?:ся)?$|ть(?:ся)?$", other.group(), re.I) is None
                ):
                    # Addressed invitation + infinitive / first-person plural,
                    # never a proposal that another person should speak.
                    continue
                if is_negated_at(clause, other.start()) or re.search(
                    r"\bне\s+(?:будем|надо|нужно)(?:\s+\w+){0,2}\s*$",
                    clause[:other.start()], re.I,
                ):
                    continue
                return True
    return False


def is_negated_call_ending(text: str) -> bool:
    """A negated finish with a call object does not refuse a goal answer."""
    return any(re.search(
        r"\bне\s+(?:хочу|буду|надо|нужно|собираюсь)(?:\s+\w+){0,2}\s+"
        r"(?:заканчива\w*|закончить|заверша\w*|завершить|прерыва\w*|прервать)"
        r"\s+(?:(?:этот|наш)\s+)?(?:разговор|звонок)\b",
        clause, re.I,
    ) for clause in _addressed_clauses(text))


def has_addressed_finish(pattern: re.Pattern[str], text: str) -> bool:
    """A finish verb must be asserted by the speaker, outside modal negation."""
    from packages.safety.patterns import is_negated_at

    for clause in _addressed_clauses(text):
        for match in pattern.finditer(clause):
            if is_negated_at(clause, match.start()):
                continue
            if re.search(
                r"\bне\s+(?:хочу|буду|надо|нужно|собираюсь)(?:\s+\w+){0,2}\s*$",
                clause[:match.start()], re.I,
            ):
                continue
            return True
    return False


def match_repair(text: str) -> Level0Match | None:
    norm = text.strip().lower().rstrip(".!?…")
    if not norm:
        return None
    if re.match(r"^(что|чего|чё|ась)\??$", norm):
        return Level0Match(dialogue_act="repair", control="none")
    # «О чём ты говоришь?» / «чего ты сказала?» — didn't hear, needs a
    # repeat of Vera's last question (live: user explicitly asked for this).
    if re.search(
        r"(о\s+ч[её]м\s+ты\s+(говоришь|говорите|сказала|толкуешь)|"
        r"чего\s+ты\s+(сказала|говоришь)|"
        r"что\s+ты\s+(сказала|говоришь)|"
        r"не\s+услышал[а]?)",
        norm,
    ):
        return Level0Match(dialogue_act="repair", control="none")
    # Clarify the question's meaning, including the observed STT form.
    # A mixed request + real complaint must continue through the kernel,
    # otherwise LEVEL0 would erase the clinical evidence.
    if re.match(
        r"^(?:уточни(?:те)?|конкретизируй(?:те)?|конкретнись|"
        r"не\s+понимаю|что\s+значит)\b", norm,
    ):
        from packages.dialogue_engine.semantic_kernel.span_parser import parse_spans
        from packages.dialogue_engine.semantic_kernel.types import SpanType

        if not any(s.type == SpanType.ISSUE for s in parse_spans(norm)):
            return Level0Match(dialogue_act="repair", control="none")
        return None
    for prefix in sorted(_REPAIR_PREFIXES, key=len, reverse=True):
        if norm == prefix or norm.startswith(prefix + " ") or norm.startswith(prefix + ","):
            return Level0Match(dialogue_act="repair", control="none")
    if re.search(r"(слыш\w*|повтор\w*)", norm):
        return Level0Match(dialogue_act="repair", control="none")
    return None


def match_level0(text: str) -> Level0Match | None:
    repair = match_repair(text)
    if repair is not None:
        return repair
    for clause in _addressed_clauses(text):
        norm = re.sub(r"^(?:(?:спасибо|пожалуйста|ну|ладно)[\s,]*|я\s+)+", "",
                      clause.strip().lower()).rstrip(".!?…")
        if not norm or is_local_question_refusal(norm):
            continue
        if re.match(r"не\s+(?:хочу|буду)\s+больше\s+(?:разговаривать|говорить|общаться)\b",
                    norm):
            # Ending this conversation is not withdrawal of future consent.
            # The existing exact legacy mappings below stay compatible.
            return Level0Match(dialogue_act="answer", control="stop_call")
        if re.match(r"(?:давайте\s+)?закончим\b", norm):
            return Level0Match(dialogue_act="answer", control="stop_call")
    # Retain the old exact/prefix contract for existing refusal/consent paths.
    # In particular, polite composite refusals still reach their DECLINE owner.
    norm = text.strip().lower().rstrip(".!?…")
    if is_local_question_refusal(text) or not any(_addressed_clauses(text)):
        return None
    for phrase, (act, control) in sorted(_LEVEL0_EXACT.items(), key=lambda x: -len(x[0])):
        if not (norm == phrase or norm.startswith(phrase + " ")):
            continue
        if phrase == "не хочу" and norm != phrase and not re.match(
            r"не хочу\s+(?:разговаривать|общаться)\b", norm,
        ):
            # Wanting no food or no answer is not a call subscription act.
            continue
        return Level0Match(dialogue_act=act, control=control)
    return None


def normalize_control(value: str) -> str:
    if value in CANONICAL_CONTROLS:
        return value
    legacy = {
        "stop": "stop_call",
        "refuse": "revoke_consent",
        "yes": "none",
        "no": "none",
        "unknown": "none",
        "repeat": "none",
        "backchannel": "none",
    }
    return legacy.get(value, "none")
