"""Deterministic fast NLU — semantics only, sub-millisecond."""

from __future__ import annotations

import re

from packages.dialogue_engine.semantic import SemanticAct, SemanticTurn

_POSITIVE = re.compile(
    r"^(хорошо|нормально|отлично|прекрасно|замечательно|неплохо|не\s+плохо|"
    r"вс[её]\s+хорошо|вс[её]\s+нормально)\.?$",
    re.I,
)
_NEGATIVE = re.compile(
    r"^(плохо|ужасно|грустно|не\s+очень|нехорошо)\.?$",
    re.I,
)
_SO_SO = re.compile(
    r"^(так\s+себе|сойд[её]т|пойд[её]т|средн\w*|терпимо|такое|ну\s+такое)\.?$",
    re.I,
)
_NORMAL = re.compile(
    r"^(ничего|обычно|обычное|так\s+обычно|ничего\s+особенного|вс[её]\s+как\s+обычно)\.?$",
    re.I,
)
_UNCERTAIN = re.compile(r"^(не\s+знаю|затрудняюсь|сложно\s+сказать)\.?$", re.I)
_WELLNESS_POSITIVE = re.compile(
    r"(чувствую\s+себя\s+(хорошо|нормально|отлично|прекрасно)|"
    r"хорошо\s+себя\s+чувствую|"
    r"прекрасно\s+себя\s+чувствую|"
    r"неплохо\s+себя\s+чувствую|"
    r"себя\s+чувствую\s+(хорошо|нормально|отлично|прекрасно))",
    re.I,
)
_WELLNESS_NEGATIVE = re.compile(
    r"(мне\s+плохо|мне\s+нехорошо|тебе\s+плохо|плохо\s+мне|"
    r"плохо\s+себе\s+чувствую|плохо\s+себя\s+чувствую|плохо\s+чувствую|"
    r"не\s+очень\s+хорошо|совсем\s+плохо|очень\s+плохо|"
    r"чувствую\s+себя\s+плохо|"
    r"плохов\w*|болит|устал\w*|слаб\w*|температур\w*)",
    re.I,
)
_MOOD_NEGATIVE = re.compile(r"^(плох\w+|груст\w+|ужасн\w+|тоскл\w+)\.?$", re.I)
_SLEEP_ANSWER = re.compile(
    r"(спал\w*\s+(нормально|хорошо|плохо)|сон\s+(хорош\w*|плох\w*)|"
    r"не\s+спал\w*|выспал\w*|мало\s+спал\w*)",
    re.I,
)
_PLANS_ANSWER = re.compile(
    r"(никак\w*\s+план\w*\s+нет|нет\s+план\w*|ничего\s+не\s+план|"
    r"нигде|дома\s+посижу|дома|в\s+больниц\w*|врач\w*)",
    re.I,
)
_MOOD_POSITIVE = re.compile(
    r"(настроени\w*\s+хорош\w*|хорош\w*\s+настроени\w*|весел\w*|радост\w*|"
    r"^хороше\w*\.?$|^прекрасн\w*\.?$|^отличн\w*\.?$|^нормальн\w*\.?$|^обычн\w*\.?$|^спокойн\w*\.?$)",
    re.I,
)
_REPAIR = re.compile(
    r"\b(алло|повторите|повтори|ещ[её]\s+раз|не\s+понял[аи]?|"
    r"не\s+расслышал[аи]?|что\s+вы\s+сказали|слышите|слышишь|ты\s+меня)\b",
    re.I,
)
_HEARING_CHECK = re.compile(
    r"(вы\s+меня\s+слыш|ты\s+меня\s+слыш|меня\s+слыш|слышите\s+меня)",
    re.I,
)
_BACKCHANNEL = frozenset({"ага", "угу", "да", "нет"})


def _strip(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text.lower()).strip()


def _normalize_core(text: str) -> str:
    """Drop leading fillers so «ну плохо» → «плохо» for polarity rules."""
    core = _strip(text)
    for _ in range(3):
        m = re.match(r"^(ну|да|вот|сегодня)\s+", core, re.I)
        if not m:
            break
        core = core[m.end():].strip()
    return core


def fast_interpret_semantic(
    text: str,
    *,
    answer_slot: str | None,
) -> tuple[SemanticTurn, bool]:
    """Return (semantic, confident). confident=False → defer to LLM/rules."""
    raw = text.strip()
    if not raw:
        return (
            SemanticTurn(act=SemanticAct.NO_ANSWER, source_quote=raw, confidence=1.0),
            True,
        )

    normalized = raw.lower()
    core = _normalize_core(raw)

    if _REPAIR.search(normalized) or _HEARING_CHECK.search(normalized):
        return (
            SemanticTurn(
                act=SemanticAct.REPAIR_REQUEST,
                target_slot=answer_slot,
                confidence=0.98,
                source_quote=raw,
            ),
            True,
        )

    from packages.dialogue_engine import questions

    if any(marker in normalized for marker in questions._GOODBYE_MARKERS):
        return (
            SemanticTurn(
                act=SemanticAct.GOODBYE_REQUEST,
                confidence=0.97,
                source_quote=raw,
            ),
            True,
        )

    if core in _BACKCHANNEL:
        return (
            SemanticTurn(
                act=SemanticAct.BACKCHANNEL,
                target_slot=answer_slot,
                confidence=0.95,
                source_quote=raw,
            ),
            True,
        )

    if _UNCERTAIN.match(core):
        return (
            SemanticTurn(
                act=SemanticAct.ANSWER,
                target_slot=answer_slot,
                polarity="uncertain",
                confidence=0.92,
                source_quote=raw,
                value=raw,
            ),
            True,
        )

    polarity = _detect_polarity(raw)
    if polarity and answer_slot:
        slot = _resolve_slot(answer_slot, raw, polarity)
        return (
            SemanticTurn(
                act=SemanticAct.ANSWER,
                target_slot=slot,
                polarity=polarity,
                confidence=0.96,
                source_quote=raw,
                value=raw,
            ),
            True,
        )

    if answer_slot == "mood" and _MOOD_NEGATIVE.match(core):
        return (
            SemanticTurn(
                act=SemanticAct.ANSWER,
                target_slot="mood",
                polarity="negative",
                confidence=0.94,
                source_quote=raw,
                value=raw,
            ),
            True,
        )

    if answer_slot == "mood" and _SO_SO.match(core):
        return (
            SemanticTurn(
                act=SemanticAct.ANSWER,
                target_slot="mood",
                polarity="uncertain",
                confidence=0.92,
                source_quote=raw,
                value=raw,
            ),
            True,
        )

    if answer_slot == "plans" and _PLANS_ANSWER.search(normalized):
        return (
            SemanticTurn(
                act=SemanticAct.ANSWER,
                target_slot="plans",
                polarity="neutral",
                confidence=0.94,
                source_quote=raw,
                value=raw,
            ),
            True,
        )

    if answer_slot == "sleep" and (
        _SLEEP_ANSWER.search(normalized) or _SO_SO.match(core) or _NORMAL.match(core)
    ):
        pol = _detect_polarity(raw) or "neutral"
        return (
            SemanticTurn(
                act=SemanticAct.ANSWER,
                target_slot="sleep",
                polarity=pol,
                confidence=0.93,
                source_quote=raw,
                value=raw,
            ),
            True,
        )

    if answer_slot == "mood" and (
        _WELLNESS_POSITIVE.search(normalized) or _MOOD_POSITIVE.search(normalized)
    ):
        return (
            SemanticTurn(
                act=SemanticAct.ANSWER,
                target_slot="mood",
                polarity="positive",
                confidence=0.94,
                source_quote=raw,
                value=raw,
            ),
            True,
        )

    if answer_slot == "wellness" and _WELLNESS_NEGATIVE.search(normalized):
        return (
            SemanticTurn(
                act=SemanticAct.ANSWER,
                target_slot="wellness",
                polarity="negative",
                confidence=0.95,
                source_quote=raw,
                value=raw,
            ),
            True,
        )

    if answer_slot == "wellness" and _WELLNESS_POSITIVE.search(normalized):
        return (
            SemanticTurn(
                act=SemanticAct.ANSWER,
                target_slot="wellness",
                polarity="positive",
                confidence=0.94,
                source_quote=raw,
                value=raw,
            ),
            True,
        )

    return (
        SemanticTurn(
            act=SemanticAct.UNCLEAR,
            target_slot=answer_slot,
            confidence=0.2,
            source_quote=raw,
        ),
        False,
    )


def _detect_polarity(text: str) -> str | None:
    core = _normalize_core(text)
    normalized = text.lower()
    if _WELLNESS_NEGATIVE.search(normalized):
        return "negative"
    if re.match(r"^плох\w*", core) or re.search(r"мне\s+не\s+очень", normalized):
        return "negative"
    if _SO_SO.match(core):
        return "uncertain"
    if _NORMAL.match(core):
        return "positive"
    if _POSITIVE.match(core) or _WELLNESS_POSITIVE.search(normalized):
        return "positive"
    if _NEGATIVE.match(core) or _MOOD_NEGATIVE.match(core):
        return "negative"
    if _MOOD_POSITIVE.search(normalized):
        return "positive"
    return None


def _resolve_slot(answer_slot: str, text: str, polarity: str) -> str:
    if answer_slot == "mood" and polarity == "positive":
        return "mood"
    return answer_slot


def fast_interpret(text: str, *, answer_slot: str | None):
    from packages.dialogue_engine.semantic import fast_interpret_legacy

    return fast_interpret_legacy(text, answer_slot=answer_slot)
