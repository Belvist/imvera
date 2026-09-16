"""Contextual NLU — phrase meaning depends on delivered question and open goals."""

from __future__ import annotations

import re

from packages.contracts.enums import FsmState
from packages.dialogue_engine import questions
from packages.dialogue_engine.context import InterpretContext, SlotCandidate, StructuredMeaning
from packages.dialogue_engine.fast_interpreter import (
    _BACKCHANNEL,
    _HEARING_CHECK,
    _MOOD_NEGATIVE,
    _MOOD_NEGATIVE_PHRASE,
    _MOOD_POSITIVE,
    _NORMAL,
    _PLANS_ANSWER,
    _REPAIR,
    _SLEEP_ANSWER,
    _SO_SO,
    _UNCERTAIN,
    _WELLNESS_NEGATIVE,
    _WELLNESS_POSITIVE,
    _detect_polarity,
    _normalize_core,
)
from packages.dialogue_engine.semantic import SemanticAct, SemanticTurn

_SHORT_ACK = frozenset(
    {
        "хорошо",
        "нормально",
        "отлично",
        "прекрасно",
        "пойдёт",
        "пойдет",
        "сойдёт",
        "сойдет",
        "так себе",
        "терпимо",
        "ага",
        "угу",
        "да",
        "ладно",
    }
)

_PLANS_INVALID_SHORT = frozenset(
    {
        "хорошо", "нормально", "отлично", "пойдёт", "пойдет",
        "сойдёт", "сойдет", "так себе", "терпимо", "ага", "угу",
    }
)

_MOOD_IN_TEXT = re.compile(
    r"(настроени\w*\s+(?:плох\w*|ужасн\w*|груст\w*|хорош\w*|отличн\w*|великолепн\w*|"
    r"прекрасн\w*|никак\w*|не\s+очень|плохое|хорошее)|"
    r"(?:великолепн\w*|прекрасн\w*|отличн\w*|хорош\w*)\s+настроени\w*|"
    r"не\s+очень.{0,40}настроени\w*|"
    r"настроени\w*.{0,40}не\s+очень|"
    r"но\s+настроени\w*\s+\w+)",
    re.I,
)
_WELLNESS_IN_TEXT = re.compile(
    r"(чувствую\s+себя\s+\w+|себя\s+чувствую\s+\w+|"
    r"сам[\s-]?(?:то\s+)?(?:нормально|хорошо|плохо)|"
    r"мне\s+(?:плохо|хорошо|нормально))",
    re.I,
)
_CORRECTION = re.compile(
    r"(хотя\s+нет|нет,\s*(?:вс[её]-таки\s+)?(?:плох\w*|не\s+очень)|"
    r"исправлюсь:\s*|вернее,\s*|"
    r"(?:нет,?\s+)?я\s+про\s+(?:мужа|жену|сына|дочь|мать|отца|соседа|соседку)|"
    r"это\s+у\s+(?:мужа|жены|сына|дочери|матери|отца|соседа|соседки)|"
    r"не\s+у\s+меня|не\s+я\s+болею)",
    re.I,
)
_CONTRAST = re.compile(r"\s+но\s+", re.I)


def contextual_interpret(
    text: str,
    ctx: InterpretContext,
) -> tuple[SemanticTurn, bool]:
    """Return (semantic, confident). Uses delivered-question context + multi-slot."""
    structured = interpret_structured(text, ctx)
    return structured_to_semantic(structured), structured.confidence >= 0.85


def interpret_structured(text: str, ctx: InterpretContext) -> StructuredMeaning:
    raw = text.strip()
    if not raw:
        return StructuredMeaning(
            act=SemanticAct.NO_ANSWER.value,
            raw_text=raw,
            confidence=1.0,
        )

    normalized = raw.lower()
    core = _normalize_core(raw)

    if re.match(r"^что\??$", core, re.I) or re.match(
        r"^(какое|какая|какой|какие)\??$", core, re.I
    ) or _REPAIR.search(normalized) or _HEARING_CHECK.search(normalized):
        return StructuredMeaning(
            act=SemanticAct.REPAIR_REQUEST.value,
            answers_to=ctx.answer_slot,
            repair=True,
            raw_text=raw,
            confidence=0.98,
        )

    if ctx.answer_slot and ctx.answer_slot.startswith("probe_"):
        probe = ctx.answer_slot.removeprefix("probe_")
        if probe == "duration":
            from packages.dialogue_engine.check_path import (
                is_urgent_concern,
                looks_like_duration_answer,
            )

            if looks_like_duration_answer(raw) or is_urgent_concern(raw):
                return StructuredMeaning(
                    act=SemanticAct.ANSWER.value,
                    answers_to=ctx.answer_slot,
                    slots={
                        ctx.answer_slot: SlotCandidate(
                            value=raw,
                            polarity="negative" if is_urgent_concern(raw) else "neutral",
                            confidence=0.93,
                        )
                    },
                    raw_text=raw,
                    confidence=0.93,
                )
        if len(core.split()) >= 1 and core not in _BACKCHANNEL:
            return StructuredMeaning(
                act=SemanticAct.ANSWER.value,
                answers_to=ctx.answer_slot,
                slots={
                    ctx.answer_slot: SlotCandidate(
                        value=raw,
                        polarity=_detect_polarity(raw) or "neutral",
                        confidence=0.9,
                    )
                },
                raw_text=raw,
                confidence=0.9,
            )

    if any(marker in normalized for marker in questions._GOODBYE_MARKERS):
        return StructuredMeaning(
            act=SemanticAct.GOODBYE_REQUEST.value,
            raw_text=raw,
            confidence=0.97,
        )

    if ctx.awaiting_goodbye_confirm and core in {"да", "ага", "угу", "конечно", "ладно", "yes"}:
        return StructuredMeaning(
            act=SemanticAct.GOODBYE_CONFIRM.value,
            raw_text=raw,
            confidence=0.96,
        )

    if ctx.fsm_state in (FsmState.SUMMARY, FsmState.GOODBYE) or ctx.summary_spoken:
        if core in _SHORT_ACK or core in _BACKCHANNEL:
            return StructuredMeaning(
                act=SemanticAct.BACKCHANNEL.value,
                backchannel=True,
                raw_text=raw,
                confidence=0.94,
            )

    multi = _extract_multi_slots(raw, ctx)
    if len(multi) >= 2:
        return StructuredMeaning(
            act=SemanticAct.ANSWER.value,
            answers_to=ctx.answer_slot,
            slots=multi,
            raw_text=raw,
            confidence=0.93,
        )

    if _CORRECTION.search(normalized):
        corrected = _apply_correction(raw, ctx)
        if corrected:
            return corrected

    if _CONTRAST.search(normalized):
        mixed = _extract_mixed_sentiment(raw, ctx)
        if mixed:
            return mixed

    if ctx.answer_slot == "plans" and core in _PLANS_INVALID_SHORT:
        return StructuredMeaning(
            act=SemanticAct.BACKCHANNEL.value,
            answers_to="plans",
            backchannel=True,
            raw_text=raw,
            confidence=0.95,
        )

    if core in _BACKCHANNEL and ctx.answer_slot:
        if ctx.answer_slot == "plans" or core in {"ага", "угу"}:
            return StructuredMeaning(
                act=SemanticAct.BACKCHANNEL.value,
                answers_to=ctx.answer_slot,
                backchannel=True,
                raw_text=raw,
                confidence=0.92,
            )

    if _UNCERTAIN.match(core):
        slot = ctx.answer_slot or "wellness"
        if slot == "wellness":
            # "не знаю" is not a valid wellness answer (judge: garbage).
            # Closing the entry slot on it slides to food without knowing
            # anything — re-ask instead. Other slots keep skip semantics.
            return StructuredMeaning(
                act=SemanticAct.UNCLEAR.value,
                answers_to=slot,
                raw_text=raw,
                confidence=0.2,
            )
        return StructuredMeaning(
            act=SemanticAct.ANSWER.value,
            answers_to=slot,
            slots={slot: SlotCandidate(value=raw, polarity="uncertain", confidence=0.92)},
            raw_text=raw,
            confidence=0.92,
        )

    try:
        from packages.dialogue_engine.policy import _is_other_person_only as _other_only

        if ctx.answer_slot in ("wellness", "mood", "sleep") and _other_only(raw):
            return StructuredMeaning(
                act=SemanticAct.UNCLEAR.value,
                answers_to=ctx.answer_slot,
                raw_text=raw,
                confidence=0.2,
            )
    except Exception:  # noqa: BLE001
        pass

    polarity = _detect_polarity(raw)
    if polarity and ctx.answer_slot:
        slot = ctx.answer_slot
        if slot == "plans" and core in _PLANS_INVALID_SHORT:
            return StructuredMeaning(
                act=SemanticAct.BACKCHANNEL.value,
                backchannel=True,
                raw_text=raw,
                confidence=0.94,
            )
        return StructuredMeaning(
            act=SemanticAct.ANSWER.value,
            answers_to=slot,
            slots={slot: SlotCandidate(value=raw, polarity=polarity, confidence=0.96)},
            polarity=polarity,
            raw_text=raw,
            confidence=0.96,
        )

    if ctx.answer_slot == "mood" and _MOOD_NEGATIVE.match(core):
        return StructuredMeaning(
            act=SemanticAct.ANSWER.value,
            answers_to="mood",
            slots={"mood": SlotCandidate(value=raw, polarity="negative", confidence=0.94)},
            raw_text=raw,
            confidence=0.94,
        )

    if ctx.answer_slot == "mood" and (
        _MOOD_NEGATIVE_PHRASE.search(normalized)
        or (
            re.search(r"настроени\w*", normalized)
            and re.search(r"не\s+очень|плох\w*|ужасн\w*|груст\w*|никак\w*", normalized)
        )
    ):
        return StructuredMeaning(
            act=SemanticAct.ANSWER.value,
            answers_to="mood",
            slots={"mood": SlotCandidate(value=raw, polarity="negative", confidence=0.94)},
            raw_text=raw,
            confidence=0.94,
        )

    if ctx.answer_slot == "mood" and re.search(
        r"великолепн\w*|прекрасн\w*|отличн\w*", normalized
    ) and re.search(r"настроени\w*", normalized):
        return StructuredMeaning(
            act=SemanticAct.ANSWER.value,
            answers_to="mood",
            slots={"mood": SlotCandidate(value=raw, polarity="positive", confidence=0.94)},
            raw_text=raw,
            confidence=0.94,
        )

    if ctx.answer_slot == "plans" and _PLANS_ANSWER.search(normalized):
        return StructuredMeaning(
            act=SemanticAct.ANSWER.value,
            answers_to="plans",
            slots={"plans": SlotCandidate(value=raw, polarity="neutral", confidence=0.94)},
            raw_text=raw,
            confidence=0.94,
        )

    if ctx.answer_slot == "sleep" and (
        _SLEEP_ANSWER.search(normalized)
        or _SO_SO.match(core)
        or _NORMAL.match(core)
        or re.search(r"хорошо[,\s]+спал", normalized)
    ):
        pol = _detect_polarity(raw) or "neutral"
        if "не спал" in normalized or "плохо" in normalized:
            pol = "negative"
        return StructuredMeaning(
            act=SemanticAct.ANSWER.value,
            answers_to="sleep",
            slots={"sleep": SlotCandidate(value=raw, polarity=pol, confidence=0.93)},
            raw_text=raw,
            confidence=0.93,
        )

    if ctx.answer_slot == "mood" and (
        _WELLNESS_POSITIVE.search(normalized) or _MOOD_POSITIVE.search(normalized)
    ):
        return StructuredMeaning(
            act=SemanticAct.ANSWER.value,
            answers_to="mood",
            slots={"mood": SlotCandidate(value=raw, polarity="positive", confidence=0.94)},
            raw_text=raw,
            confidence=0.94,
        )

    if ctx.answer_slot == "wellness" and _WELLNESS_NEGATIVE.search(normalized):
        return StructuredMeaning(
            act=SemanticAct.ANSWER.value,
            answers_to="wellness",
            slots={"wellness": SlotCandidate(value=raw, polarity="negative", confidence=0.95)},
            raw_text=raw,
            confidence=0.95,
        )

    if ctx.answer_slot == "wellness" and _WELLNESS_POSITIVE.search(normalized):
        return StructuredMeaning(
            act=SemanticAct.ANSWER.value,
            answers_to="wellness",
            slots={"wellness": SlotCandidate(value=raw, polarity="positive", confidence=0.94)},
            raw_text=raw,
            confidence=0.94,
        )

    single = _extract_multi_slots(raw, ctx)
    if single:
        slot = next(iter(single))
        return StructuredMeaning(
            act=SemanticAct.ANSWER.value,
            answers_to=slot,
            slots=single,
            raw_text=raw,
            confidence=0.88,
        )

    return StructuredMeaning(
        act=SemanticAct.UNCLEAR.value,
        answers_to=ctx.answer_slot,
        raw_text=raw,
        confidence=0.2,
    )


def structured_to_semantic(structured: StructuredMeaning) -> SemanticTurn:
    act = SemanticAct(structured.act)
    target = structured.answers_to
    if structured.slots and not target:
        target = next(iter(structured.slots))
    primary_polarity = structured.polarity
    if not primary_polarity and structured.slots and target:
        cand = structured.slots.get(target)
        if cand:
            primary_polarity = cand.polarity
    return SemanticTurn(
        act=act,
        answers_to=structured.answers_to,
        slots=dict(structured.slots),
        target_slot=target,
        polarity=primary_polarity,
        confidence=structured.confidence,
        source_quote=structured.raw_text,
        value=structured.raw_text,
        correction=structured.correction,
        repair=structured.repair,
        backchannel=structured.backchannel,
    )


def _extract_multi_slots(text: str, ctx: InterpretContext) -> dict[str, SlotCandidate]:
    normalized = text.lower()
    core = _normalize_core(text)
    slots: dict[str, SlotCandidate] = {}
    try:
        from packages.dialogue_engine.policy import _is_other_person_only

        if _is_other_person_only(text):
            # Someone else's complaint alone never fills speaker slots
            # («у мужа плохо» ≠ speaker wellness). Mixed turns with speaker
            # markers proceed; per-clause split is handled by callers.
            return {}
    except Exception:  # noqa: BLE001
        pass

    if _WELLNESS_IN_TEXT.search(normalized) or (
        ctx.answer_slot == "wellness" and _detect_polarity(text)
    ):
        pol = _detect_polarity(text) or "positive"
        if _WELLNESS_NEGATIVE.search(normalized):
            pol = "negative"
        if re.search(r"\b(отлично|прекрасно|замечательно)\b", normalized):
            pol = "positive"
        if "нормально" in normalized and "плохо" not in normalized:
            pol = "positive"
        slots["wellness"] = SlotCandidate(value=text, polarity=pol, confidence=0.9)
    elif ctx.answer_slot == "wellness" and re.search(
        r"\b(отлично|прекрасно|хорошо|плохо|так\s+себе)\b", normalized
    ):
        pol = _detect_polarity(text) or (
            "negative" if "плохо" in normalized else "positive"
        )
        slots["wellness"] = SlotCandidate(value=text, polarity=pol, confidence=0.88)

    if _MOOD_IN_TEXT.search(normalized):
        if re.search(r"плох\w*|ужасн\w*|груст\w*|никак\w*|не\s+очень", normalized):
            slots["mood"] = SlotCandidate(value=text, polarity="negative", confidence=0.91)
        else:
            slots["mood"] = SlotCandidate(value=text, polarity="positive", confidence=0.9)

    if _SLEEP_ANSWER.search(normalized) or re.search(
        r"(не\s+спал\w*|почти\s+не\s+спал\w*|выспал\w*|мало\s+спал\w*|"
        r"хорошо[,\s]+спал\w*|спало\s+\w+)",
        normalized,
    ):
        pol = "negative" if re.search(r"не\s+спал|плохо|мало|беспокойн", normalized) else "positive"
        slots["sleep"] = SlotCandidate(value=text, polarity=pol, confidence=0.9)

    if _PLANS_ANSWER.search(normalized) or re.search(
        r"(пойду\s+гуля\w*|гуля\w*\s+с\s+\w+|"
        r"план\w*\s+никак|никак\w*\s+план|план\w*\s+нет\w*|"
        r"вечером\s+к\s+врач|к\s+врач\w*|"
        r"ничего\s+не\s+(?:буду|делать)|сидеть\s+дома)",
        normalized,
    ):
        slots["plans"] = SlotCandidate(value=text, polarity="neutral", confidence=0.9)

    if len(slots) == 1 and ctx.answer_slot and ctx.answer_slot in slots:
        return slots

    if len(slots) >= 2:
        open_only = {k: v for k, v in slots.items() if k in ctx.open_slots or k == ctx.answer_slot}
        return open_only or slots

    if not slots and ctx.answer_slot:
        pol = _detect_polarity(text)
        if pol and core in _SHORT_ACK:
            if ctx.answer_slot != "plans" or core not in _PLANS_INVALID_SHORT:
                slots[ctx.answer_slot] = SlotCandidate(value=text, polarity=pol, confidence=0.88)

    return slots


def _extract_mixed_sentiment(text: str, ctx: InterpretContext) -> StructuredMeaning | None:
    parts = _CONTRAST.split(text, maxsplit=1)
    if len(parts) != 2:
        return None
    slots: dict[str, SlotCandidate] = {}
    first, second = parts[0].strip(), parts[1].strip()
    if _detect_polarity(first) or "нормально" in first.lower():
        slots["wellness"] = SlotCandidate(
            value=first,
            polarity=(
                "positive"
                if "нормально" in first.lower()
                else (_detect_polarity(first) or "positive")
            ),
            confidence=0.9,
        )
    if _MOOD_IN_TEXT.search(second) or re.search(r"настроени\w*", second, re.I):
        pol = "negative" if re.search(r"ужасн|плох|груст|никак", second, re.I) else "positive"
        slots["mood"] = SlotCandidate(value=second, polarity=pol, confidence=0.91)
    elif _SLEEP_ANSWER.search(second) or "не спал" in second.lower():
        slots["sleep"] = SlotCandidate(value=second, polarity="negative", confidence=0.9)
    if len(slots) >= 2:
        return StructuredMeaning(
            act=SemanticAct.ANSWER.value,
            answers_to=ctx.answer_slot,
            slots=slots,
            raw_text=text,
            confidence=0.92,
        )
    return None


def _apply_correction(text: str, ctx: InterpretContext) -> StructuredMeaning | None:
    normalized = text.lower()
    if _CORRECTION.search(normalized):
        parts = re.split(r"хотя\s+нет[,\s]*", normalized, maxsplit=1)
        if len(parts) == 2 and parts[1].strip():
            normalized = parts[1].strip()
    slot = ctx.answer_slot or "wellness"
    if re.search(r"плох\w*|не\s+очень|ужасн", normalized) and not re.search(
        r"хорош\w*|нормально|отлично", normalized
    ):
        return StructuredMeaning(
            act=SemanticAct.ANSWER.value,
            answers_to=slot,
            slots={slot: SlotCandidate(value=text, polarity="negative", confidence=0.94)},
            correction=True,
            raw_text=text,
            confidence=0.94,
        )
    if re.search(r"хорош\w*|нормально|отлично", normalized):
        return StructuredMeaning(
            act=SemanticAct.ANSWER.value,
            answers_to=slot,
            slots={slot: SlotCandidate(value=text, polarity="positive", confidence=0.93)},
            correction=True,
            raw_text=text,
            confidence=0.93,
        )
    return None
