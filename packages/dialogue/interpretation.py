"""Structured interpretation of elder speech — not raw VALID from STT."""

import re

from pydantic import BaseModel, Field

from packages.contracts.enums import (
    AnswerJudgement,
    AsrQuality,
    ConsentState,
    DialogueAct,
    FsmState,
)
from packages.contracts.interpretation import FactCandidate, TurnInterpretation
from packages.dialogue.fact_extraction import extract_fact_candidates
from packages.dialogue.state import DialogueState

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
    r"(^нет\b|не\s+соглас|не\s+хочу|не\s+надо|не\s+я\b|это\s+не\s+я)",
    re.I,
)
_REVOKE = re.compile(
    r"(не\s+звоните|не\s+звонить|хватит\s+звон|больше\s+не\s+звон)",
    re.I,
)
_RISK_FALSE_ALARM = re.compile(
    r"(сосед\w*|не\s+я\s+упал|другая\s+упала|про\s+друг|ошибк|не\s+со\s+мной)",
    re.I,
)
_WRONG_PERSON = re.compile(
    r"(ошибл\w*\s+номер|не\s+туда\s+попали|не\s+тот\s+номер|ошиблись)",
    re.I,
)
_REPEAT = re.compile(
    r"\b(повторите|повтори|еще\s+раз|ещё\s+раз|не\s+понял[аи]?|не\s+расслышал[аи]?|что\s+вы\s+сказали)\b",
    re.I,
)
_STOP_CALL = re.compile(
    r"\b(закончим|закончить\s+разговор|хватит\s+разговор|давайте\s+закончим)\b",
    re.I,
)
_WHO_ARE_YOU = re.compile(
    r"(^\s*(кто|что|зачем|где|как)\s+вы|кто\s+вы\s+такая|что\s+это\s+за|как\s+вас\s+зовут)",
    re.I,
)
_DEFER = re.compile(r"\b(потом|позже|не\s+сейчас|давайте\s+потом|перезвоните)\b", re.I)
_RHETORICAL_DENY = re.compile(r"(да\s+вы\s+что|что\s+вы\s+такое|вы\s+что)", re.I)
_WELLNESS_HINT = re.compile(
    r"\b(нормально|хорошо|отлично|плохо|нехорошо|не\s+очень|болит|устал\w*|слаб\w*|"
    r"голов\w*|температур\w*|чувствую\s+себя)\b",
    re.I,
)
_TOPIC_REFUSAL = re.compile(
    r"не\s+(хочу|буду)\s+(говорить\s+)?(о|про)\s+(\S+)",
    re.I,
)
_REFUSE_GENERIC = re.compile(r"\bне\s+хочу\b", re.I)
_PAUSE = re.compile(r"\b(подождите|подожди|минуточку|секундочку|погодите)\b", re.I)
_TOPIC_TO_SLOT: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"сн|спал|спать", re.I), "sleep"),
    (re.compile(r"настроен", re.I), "mood"),
    (re.compile(r"здоров|самочувств", re.I), "wellness"),
    (re.compile(r"план", re.I), "plans"),
)
_WELLNESS_POSITIVE = re.compile(
    r"(чувствую\s+себя\s+(хорошо|нормально|отлично)|отлично|"
    r"пока\s+вс[её]\s+хорошо|вс[её]\s+хорошо|не\s+плохо)",
    re.I,
)
_MOOD_HINT = re.compile(r"\b(хорош\w*|грустн\w*|весел\w*|плох\w*|нормальн\w*)\b", re.I)
_SLEEP_HINT = re.compile(r"\b(спал\w*|сон\w*|не\s+спал\w*|нормальн\w*)\b", re.I)
_PLANS_HINT = re.compile(r"\b(дома|врач\w*|нигде|гуля\w*|магазин\w*|внук\w*)\b", re.I)


class UserInterpretation(BaseModel):
    judgement: AnswerJudgement
    dialogue_act: DialogueAct = DialogueAct.UNCLEAR
    affirms: bool = False
    declines: bool = False
    fills_pending_slot: bool = False
    slot_value: str | None = None
    fact_candidates: list[FactCandidate] = Field(default_factory=list)
    sets_consent: ConsentState | None = None
    confirms_identity: bool = False
    confirms_can_talk: bool = False
    requests_goodbye: bool = False
    confirms_goodbye: bool = False
    declines_goodbye: bool = False
    requests_repeat: bool = False
    revoke_consent: bool = False
    wrong_person: bool = False
    defers_call: bool = False
    asks_who_are_you: bool = False
    risk_false_alarm: bool = False
    pause_requested: bool = False
    declines_topic_slot: str | None = None


def _strip_punct(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text.lower()).strip()


def _contains_goodbye(text: str) -> bool:
    lower = text.lower()
    if re.search(r"пока\s+вс[её]", lower) or re.search(r"пока\s+норм", lower):
        return False
    if "до свидания" in lower or "всего доброго" in lower:
        return True
    core = _strip_punct(text)
    if core == "пока":
        return True
    if re.search(r"\bпока\s*,?\s*(до|вечером|спать)\b", lower):
        return True
    return False


def _is_affirmation(text: str) -> bool:
    if _RHETORICAL_DENY.search(text.lower()):
        return False
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
    if words and words[0] == "да" and len(words) <= 4 and not _RHETORICAL_DENY.search(text.lower()):
        return True
    return False


def _is_backchannel_only(text: str) -> bool:
    return _strip_punct(text) in _BACKCHANNEL_EXACT


def _slot_hint_matches(slot: str, text: str) -> bool:
    hints = {
        "wellness": _WELLNESS_HINT,
        "mood": _MOOD_HINT,
        "sleep": _SLEEP_HINT,
        "plans": _PLANS_HINT,
    }
    pattern = hints.get(slot)
    if not pattern:
        return False
    lower = text.lower()
    if slot == "wellness" and _WELLNESS_POSITIVE.search(lower):
        return True
    return bool(pattern.search(lower))


def _negated_wellness_is_positive(text: str) -> bool:
    lower = text.lower()
    return bool(
        re.search(r"нет\s*,?\s*(чувствую|себя).*(хорош|норм|отличн)", lower)
        or re.search(r"не\s+плохо", lower)
    )


def _slot_answer_value(slot: str, text: str) -> str:
    return text.strip()


def _topic_refusal_slot(text: str, pending_slot: str | None) -> str | None:
    match = _TOPIC_REFUSAL.search(text)
    if match:
        topic_word = match.group(4)
        for pattern, slot in _TOPIC_TO_SLOT:
            if pattern.search(topic_word):
                return slot
    if pending_slot and _REFUSE_GENERIC.search(text) and len(text.split()) <= 6:
        return pending_slot
    return None


def _effective_pending_slot(state: DialogueState) -> str | None:
    if state.pending_slot:
        return state.pending_slot
    if state.fsm_state == FsmState.DAILY_CHECK:
        from packages.dialogue.question_ledger import next_open_slot

        return next_open_slot(state.slots)
    return None


def _looks_like_slot_answer(state: DialogueState, text: str) -> bool:
    pending = _effective_pending_slot(state)
    if not pending:
        return False
    if _is_backchannel_only(text) or _contains_goodbye(text):
        return False
    if _WHO_ARE_YOU.search(text.lower()) or _REPEAT.search(text.lower()):
        return False
    if _DEFER.search(text.lower()):
        return False
    core = _strip_punct(text)
    if len(core) < 2:
        return False
    if state.pending_slot == "wellness" and _negated_wellness_is_positive(text):
        return True
    if _DENY.search(text.lower()) and not _negated_wellness_is_positive(text):
        return False
    return _slot_hint_matches(pending, text)


def _build_slot_fact(state: DialogueState, text: str) -> FactCandidate | None:
    pending = _effective_pending_slot(state)
    if not pending or not _looks_like_slot_answer(state, text):
        return None
    return FactCandidate(
        field=pending,
        value=_slot_answer_value(pending, text),
        source_quote=text.strip(),
        answers_pending=True,
    )


def interpret_user_turn(state: DialogueState, user_text: str) -> UserInterpretation:
    """Derive structured meaning from transcript + dialogue context."""
    text = user_text.strip()
    if not text:
        return UserInterpretation(
            judgement=AnswerJudgement.NO_ANSWER,
            dialogue_act=DialogueAct.UNCLEAR,
        )

    normalized = text.lower()

    if state.is_terminal():
        return UserInterpretation(
            judgement=AnswerJudgement.BACKCHANNEL,
            dialogue_act=DialogueAct.BACKCHANNEL,
        )

    if _REVOKE.search(normalized):
        return UserInterpretation(
            judgement=AnswerJudgement.DECLINE,
            dialogue_act=DialogueAct.REVOKE_CONSENT,
            declines=True,
            revoke_consent=True,
            sets_consent=ConsentState.DECLINED,
        )

    if _WRONG_PERSON.search(normalized):
        return UserInterpretation(
            judgement=AnswerJudgement.VALID,
            dialogue_act=DialogueAct.WRONG_PERSON,
            wrong_person=True,
        )

    if state.fsm_state in (FsmState.RED_SIGNAL, FsmState.CONFIRM_SITUATION):
        if _RISK_FALSE_ALARM.search(normalized):
            return UserInterpretation(
                judgement=AnswerJudgement.VALID,
                dialogue_act=DialogueAct.CORRECTION,
                risk_false_alarm=True,
            )
        if _REVOKE.search(normalized):
            return UserInterpretation(
                judgement=AnswerJudgement.DECLINE,
                dialogue_act=DialogueAct.REVOKE_CONSENT,
                declines=True,
                revoke_consent=True,
                sets_consent=ConsentState.DECLINED,
            )
        if _contains_goodbye(text):
            return UserInterpretation(
                judgement=AnswerJudgement.SIDE_TOPIC,
                dialogue_act=DialogueAct.STOP_CALL,
                requests_goodbye=True,
            )
        if _is_affirmation(text) and not _DENY.search(normalized):
            return UserInterpretation(
                judgement=AnswerJudgement.VALID,
                dialogue_act=DialogueAct.ANSWER,
                affirms=True,
            )
        if _DENY.search(normalized):
            return UserInterpretation(
                judgement=AnswerJudgement.DECLINE,
                dialogue_act=DialogueAct.CORRECTION,
                declines=True,
            )
        return UserInterpretation(
            judgement=AnswerJudgement.UNCLEAR,
            dialogue_act=DialogueAct.UNCLEAR,
        )

    if state.awaiting_goodbye_confirm:
        if _is_affirmation(text) and not _DENY.search(normalized):
            return UserInterpretation(
                judgement=AnswerJudgement.VALID,
                dialogue_act=DialogueAct.ANSWER,
                affirms=True,
                confirms_goodbye=True,
            )
        if _DENY.search(normalized) or _is_backchannel_only(text):
            return UserInterpretation(
                judgement=AnswerJudgement.DECLINE,
                dialogue_act=DialogueAct.ANSWER,
                declines=True,
                declines_goodbye=True,
            )

    if _contains_goodbye(text):
        return UserInterpretation(
            judgement=AnswerJudgement.SIDE_TOPIC,
            dialogue_act=DialogueAct.STOP_CALL,
            requests_goodbye=True,
        )

    if _STOP_CALL.search(normalized):
        return UserInterpretation(
            judgement=AnswerJudgement.SIDE_TOPIC,
            dialogue_act=DialogueAct.STOP_CALL,
            requests_goodbye=True,
        )

    if _REPEAT.search(normalized):
        return UserInterpretation(
            judgement=AnswerJudgement.UNCLEAR,
            dialogue_act=DialogueAct.REPEAT,
            requests_repeat=True,
        )

    if _WHO_ARE_YOU.search(normalized) or ("?" in text and "кто" in normalized):
        return UserInterpretation(
            judgement=AnswerJudgement.SIDE_TOPIC,
            dialogue_act=DialogueAct.QUESTION,
            asks_who_are_you=True,
        )

    if _DEFER.search(normalized):
        if state.fsm_state == FsmState.CHECK_CAN_TALK:
            return UserInterpretation(
                judgement=AnswerJudgement.UNCLEAR,
                dialogue_act=DialogueAct.DEFER,
                defers_call=True,
            )
        return UserInterpretation(
            judgement=AnswerJudgement.UNCLEAR,
            dialogue_act=DialogueAct.DEFER,
        )

    if _PAUSE.search(normalized) and state.fsm_state == FsmState.DAILY_CHECK:
        return UserInterpretation(
            judgement=AnswerJudgement.SIDE_TOPIC,
            dialogue_act=DialogueAct.PAUSE,
            pause_requested=True,
        )

    refusal_slot = _topic_refusal_slot(text, state.pending_slot)
    if refusal_slot and state.fsm_state == FsmState.DAILY_CHECK:
        return UserInterpretation(
            judgement=AnswerJudgement.DECLINE,
            dialogue_act=DialogueAct.ANSWER,
            declines=True,
            declines_topic_slot=refusal_slot,
        )

    if _DENY.search(normalized) and not _negated_wellness_is_positive(text):
        if state.fsm_state == FsmState.CHECK_CONSENT:
            return UserInterpretation(
                judgement=AnswerJudgement.DECLINE,
                dialogue_act=DialogueAct.ANSWER,
                declines=True,
                sets_consent=ConsentState.DECLINED,
            )
        if state.fsm_state == FsmState.IDENTIFY_PERSON:
            return UserInterpretation(
                judgement=AnswerJudgement.DECLINE,
                dialogue_act=DialogueAct.ANSWER,
                declines=True,
            )
        if state.fsm_state == FsmState.CHECK_CAN_TALK:
            return UserInterpretation(
                judgement=AnswerJudgement.DECLINE,
                dialogue_act=DialogueAct.ANSWER,
                declines=True,
            )
        if state.pending_slot:
            return UserInterpretation(
                judgement=AnswerJudgement.DECLINE,
                dialogue_act=DialogueAct.ANSWER,
                declines=True,
            )

    if state.fsm_state == FsmState.IDENTIFY_PERSON and _is_affirmation(text):
        return UserInterpretation(
            judgement=AnswerJudgement.VALID,
            dialogue_act=DialogueAct.ANSWER,
            affirms=True,
            confirms_identity=True,
        )

    if state.fsm_state == FsmState.CHECK_CONSENT and _is_affirmation(text):
        return UserInterpretation(
            judgement=AnswerJudgement.VALID,
            dialogue_act=DialogueAct.ANSWER,
            affirms=True,
            sets_consent=ConsentState.ACTIVE,
        )

    if state.fsm_state == FsmState.CHECK_CAN_TALK and _is_affirmation(text):
        return UserInterpretation(
            judgement=AnswerJudgement.VALID,
            dialogue_act=DialogueAct.ANSWER,
            affirms=True,
            confirms_can_talk=True,
        )

    if state.fsm_state == FsmState.GREETING and state.greeted:
        return UserInterpretation(
            judgement=AnswerJudgement.BACKCHANNEL,
            dialogue_act=DialogueAct.BACKCHANNEL,
        )

    if (
        state.pending_slot
        and state.fsm_state == FsmState.DAILY_CHECK
        and _is_backchannel_only(text)
    ):
        return UserInterpretation(
            judgement=AnswerJudgement.BACKCHANNEL,
            dialogue_act=DialogueAct.BACKCHANNEL,
        )

    candidates = extract_fact_candidates(text, _effective_pending_slot(state))
    if candidates:
        pending = state.pending_slot
        answered_pending = pending is not None and any(c.field == pending for c in candidates)
        is_correction = pending is not None and any(
            c.field != pending for c in candidates
        ) and bool(state.facts)
        act = DialogueAct.CORRECTION if is_correction else DialogueAct.ANSWER
        primary = next((c for c in candidates if c.field == pending), candidates[0])
        return UserInterpretation(
            judgement=AnswerJudgement.VALID,
            dialogue_act=act,
            affirms=True,
            fills_pending_slot=answered_pending,
            slot_value=primary.value,
            fact_candidates=candidates,
        )

    fact = _build_slot_fact(state, text)
    if fact:
        return UserInterpretation(
            judgement=AnswerJudgement.VALID,
            dialogue_act=DialogueAct.ANSWER,
            affirms=True,
            fills_pending_slot=True,
            slot_value=fact.value,
            fact_candidates=[fact],
        )

    if state.pending_slot:
        return UserInterpretation(
            judgement=AnswerJudgement.UNCLEAR,
            dialogue_act=DialogueAct.UNCLEAR,
        )

    if state.fsm_state in (
        FsmState.IDENTIFY_PERSON,
        FsmState.CHECK_CONSENT,
        FsmState.CHECK_CAN_TALK,
    ):
        return UserInterpretation(
            judgement=AnswerJudgement.UNCLEAR,
            dialogue_act=DialogueAct.UNCLEAR,
        )

    return UserInterpretation(
        judgement=AnswerJudgement.SIDE_TOPIC,
        dialogue_act=DialogueAct.QUESTION,
    )


def to_turn_interpretation(
    state: DialogueState,
    turn_id: int,
    user_text: str,
    interp: UserInterpretation,
    *,
    state_version: int,
    asr_quality: AsrQuality | None = None,
) -> TurnInterpretation:
    from packages.contracts.enums import AsrQuality as AsrQ

    return TurnInterpretation(
        call_id=state.call_id,
        turn_id=turn_id,
        raw_text=user_text,
        state_version=state_version,
        asr_quality=asr_quality or AsrQ.GOOD,
        dialogue_act=interp.dialogue_act,
        judgement=interp.judgement,
        fact_candidates=list(interp.fact_candidates),
        answers_pending_question=any(
            c.answers_pending for c in interp.fact_candidates
        )
        or interp.fills_pending_slot,
        ambiguous=interp.judgement == AnswerJudgement.UNCLEAR,
    )
