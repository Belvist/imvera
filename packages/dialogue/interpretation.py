"""Structured interpretation of elder speech — not raw VALID from STT."""

import re

from pydantic import BaseModel

from packages.contracts.enums import AnswerJudgement, ConsentState, FsmState
from packages.dialogue.state import DialogueState

_GOODBYE_MARKERS = ("до свидания", "пока", "всего доброго")
_BACKCHANNEL_EXACT = frozenset({"ага", "угу", "алло", "да", "нет"})
_AFFIRM_PHRASES = frozenset(
    {
        "да",
        "ага",
        "угу",
        "верно",
        "согласен",
        "согласна",
        "конечно",
        "хорошо",
        "ладно",
        "это я",
        "я это",
        "удобно",
    }
)
_DENY = re.compile(
    r"(^нет\b|не\s+соглас|не\s+хочу|не\s+надо|не\s+звоните|не\s+я\b|это\s+не\s+я)",
    re.I,
)
_REPEAT = re.compile(
    r"\b(повторите|повтори|еще\s+раз|ещё\s+раз|не\s+понял[аи]?|не\s+расслышал[аи]?|что\s+вы\s+сказали)\b",
    re.I,
)
_SIDE_QUESTION = re.compile(
    r"(^\s*(кто|что|зачем|где|как)\s+вы|кто\s+вы\s+такая|что\s+это\s+за|как\s+вас\s+зовут)",
    re.I,
)
_DEFER = re.compile(r"\b(потом|позже|не\s+сейчас|давайте\s+потом|перезвоните)\b", re.I)
_WELLNESS_HINT = re.compile(
    r"\b(нормально|хорошо|плохо|болит|устал\w*|слаб\w*|голов\w*|температур\w*)\b",
    re.I,
)
_MOOD_HINT = re.compile(r"\b(хорош\w*|грустн\w*|весел\w*|плох\w*|нормальн\w*)\b", re.I)
_SLEEP_HINT = re.compile(r"\b(спал\w*|сон\w*|не\s+спал\w*|нормальн\w*)\b", re.I)
_PLANS_HINT = re.compile(r"\b(дома|врач\w*|нигде|гуля\w*|магазин\w*|внук\w*)\b", re.I)


class UserInterpretation(BaseModel):
    judgement: AnswerJudgement
    affirms: bool = False
    declines: bool = False
    fills_pending_slot: bool = False
    sets_consent: ConsentState | None = None
    confirms_identity: bool = False
    confirms_can_talk: bool = False
    requests_goodbye: bool = False
    confirms_goodbye: bool = False
    declines_goodbye: bool = False
    requests_repeat: bool = False


def _strip_punct(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text.lower()).strip()


def _contains_goodbye(text: str) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in _GOODBYE_MARKERS)


def _is_affirmation(text: str) -> bool:
    core = _strip_punct(text)
    if not core:
        return False
    if _DEFER.search(text.lower()):
        return False
    if core in _AFFIRM_PHRASES:
        return True
    if "это я" in core or "я это" in core:
        return True
    words = core.split()
    if words and words[0] in _AFFIRM_PHRASES and len(words) <= 2:
        return True
    if words and words[0] == "да" and len(words) <= 4:
        return True
    return False


def _is_backchannel_only(text: str) -> bool:
    return _strip_punct(text) in _BACKCHANNEL_EXACT


def _is_side_or_meta(text: str) -> bool:
    lower = text.lower()
    if "?" in text:
        return True
    return bool(_SIDE_QUESTION.search(lower) or _REPEAT.search(lower))


def _slot_hint_matches(slot: str, text: str) -> bool:
    hints = {
        "wellness": _WELLNESS_HINT,
        "mood": _MOOD_HINT,
        "sleep": _SLEEP_HINT,
        "plans": _PLANS_HINT,
    }
    pattern = hints.get(slot)
    return bool(pattern and pattern.search(text.lower()))


def _looks_like_slot_answer(state: DialogueState, text: str) -> bool:
    if not state.pending_slot:
        return False
    if _is_backchannel_only(text) or _is_side_or_meta(text) or _contains_goodbye(text):
        return False
    if _DEFER.search(text.lower()):
        return False
    core = _strip_punct(text)
    if len(core) < 3:
        return False
    return _slot_hint_matches(state.pending_slot, text) or len(core.split()) >= 4


def interpret_user_turn(state: DialogueState, user_text: str) -> UserInterpretation:
    """Derive structured meaning from transcript + dialogue context."""
    text = user_text.strip()
    if not text:
        return UserInterpretation(judgement=AnswerJudgement.NO_ANSWER)

    normalized = text.lower()

    if state.awaiting_goodbye_confirm:
        if _is_affirmation(text) and not _DENY.search(normalized):
            return UserInterpretation(
                judgement=AnswerJudgement.VALID,
                affirms=True,
                confirms_goodbye=True,
            )
        if _DENY.search(normalized) or _is_backchannel_only(text):
            return UserInterpretation(
                judgement=AnswerJudgement.DECLINE,
                declines=True,
                declines_goodbye=True,
            )

    if _contains_goodbye(text):
        return UserInterpretation(
            judgement=AnswerJudgement.SIDE_TOPIC,
            requests_goodbye=True,
        )

    if _REPEAT.search(normalized):
        return UserInterpretation(
            judgement=AnswerJudgement.UNCLEAR,
            requests_repeat=True,
        )

    if _is_side_or_meta(text):
        return UserInterpretation(judgement=AnswerJudgement.SIDE_TOPIC)

    if _DEFER.search(normalized):
        return UserInterpretation(judgement=AnswerJudgement.UNCLEAR)

    if _DENY.search(normalized):
        if state.fsm_state == FsmState.CHECK_CONSENT:
            return UserInterpretation(
                judgement=AnswerJudgement.DECLINE,
                declines=True,
                sets_consent=ConsentState.DECLINED,
            )
        if state.fsm_state == FsmState.IDENTIFY_PERSON:
            return UserInterpretation(judgement=AnswerJudgement.DECLINE, declines=True)
        if state.fsm_state == FsmState.CHECK_CAN_TALK:
            return UserInterpretation(judgement=AnswerJudgement.DECLINE, declines=True)
        if state.pending_slot:
            return UserInterpretation(judgement=AnswerJudgement.DECLINE, declines=True)

    if state.fsm_state == FsmState.IDENTIFY_PERSON and _is_affirmation(text):
        return UserInterpretation(
            judgement=AnswerJudgement.VALID,
            affirms=True,
            confirms_identity=True,
        )

    if state.fsm_state == FsmState.CHECK_CONSENT and _is_affirmation(text):
        return UserInterpretation(
            judgement=AnswerJudgement.VALID,
            affirms=True,
            sets_consent=ConsentState.ACTIVE,
        )

    if state.fsm_state == FsmState.CHECK_CAN_TALK and _is_affirmation(text):
        return UserInterpretation(
            judgement=AnswerJudgement.VALID,
            affirms=True,
            confirms_can_talk=True,
        )

    if state.fsm_state == FsmState.GREETING and state.greeted:
        return UserInterpretation(judgement=AnswerJudgement.BACKCHANNEL)

    if state.pending_slot and _looks_like_slot_answer(state, text):
        return UserInterpretation(
            judgement=AnswerJudgement.VALID,
            affirms=True,
            fills_pending_slot=True,
        )

    if state.pending_slot:
        return UserInterpretation(judgement=AnswerJudgement.UNCLEAR)

    if state.fsm_state in (
        FsmState.IDENTIFY_PERSON,
        FsmState.CHECK_CONSENT,
        FsmState.CHECK_CAN_TALK,
    ):
        return UserInterpretation(judgement=AnswerJudgement.UNCLEAR)

    return UserInterpretation(judgement=AnswerJudgement.SIDE_TOPIC)
