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
    r"(спал\w*\s+(?:нормально|хорошо|плохо|великолепн\w*|отличн\w*)|"
    r"спало\s+(?:нормально|хорошо|плохо|великолепн\w*|отличн\w*)|"
    r"хорошо[,\s]+спал\w*|"
    r"(?:нормально|плохо|отлично)\s+спал\w*|"
    r"сон\s+(?:хорош\w*|плох\w*|нормальн\w*)|"
    r"не\s+спал\w*|выспал\w*|мало\s+спал\w*|недоспал\w*|просыпал\w*|"
    r"часов\s+\w+|пять\s+часов|шесть\s+часов|беспокойн\w*)",
    re.I,
)
_PLANS_ANSWER = re.compile(
    r"(никак\w*\s+план\w*\s+нет|план\w*\s+никак\w*\s+нет\w*|"
    r"план\w*\s+нет\w*(?:\s+на\s+сегодня)?|нет\s+план\w*|ничего\s+не\s+план|"
    r"ничего\s+не\s+(?:буду|делать)|сидеть\s+дома|"
    r"дома\s+(?:сижу|посижу|никуда)|никуда\s+не\s+(?:пойду|еду)|"
    r"нигде|дома\s+посижу|дома|в\s+больниц\w*|врач\w*|"
    r"магазин|продукт|погуля|гуля\w*|при[её]м|делам|уборк|внук|дет|"
    r"отдых|лежать|телевизор|ничего\s+особенного)",
    re.I,
)
_MOOD_POSITIVE = re.compile(
    r"(настроени\w*\s+(?:хорош\w*|отличн\w*|великолепн\w*|прекрасн\w*|замечательн\w*)|"
    r"(?:хорош\w*|отличн\w*|великолепн\w*|прекрасн\w*)\s+настроени\w*|"
    r"хорош\w*\s+настроени\w*|весел\w*|радост\w*|"
    r"^хороше\w*\.?$|^прекрасн\w*\.?$|^отличн\w*\.?$|^великолепн\w*\.?$|"
    r"^нормальн\w*\.?$|^обычн\w*\.?$|^спокойн\w*\.?$)",
    re.I,
)
_MOOD_NEGATIVE_PHRASE = re.compile(
    r"(?:не\s+очень|плох\w*|ужасн\w*|груст\w*|никак\w*).{0,40}настроени\w*|"
    r"настроени\w*.{0,40}(?:не\s+очень|плох\w*|ужасн\w*|груст\w*|никак\w*)",
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
    """Drop leading fillers and corpus paraphrase wrappers."""
    core = _strip(text)
    # Paraphrase family wrappers (corpus + live colloquial).
    for pat in (
        r"^скажу\s+так\s*",
        r"^если\s+коротко\s*",
        r"^по\s+сну\s*",
        r"^планы\s+такие\s*",
        r"^настроение\s*",
    ):
        core = re.sub(pat, "", core, flags=re.I).strip()
    for _ in range(3):
        m = re.match(r"^(ну|да|вот|сегодня)\s+", core, re.I)
        if not m:
            break
        core = core[m.end():].strip()
    core = re.sub(r"\s+(вроде|наверное|кажется)\.?$", "", core, flags=re.I).strip()
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

    if re.match(r"^что\??$", core, re.I):
        return (
            SemanticTurn(
                act=SemanticAct.REPAIR_REQUEST,
                target_slot=answer_slot,
                confidence=0.97,
                source_quote=raw,
            ),
            True,
        )

    if re.match(r"^(какое|какая|какой|какие)\??$", core, re.I):
        return (
            SemanticTurn(
                act=SemanticAct.REPAIR_REQUEST,
                target_slot=answer_slot,
                confidence=0.97,
                source_quote=raw,
            ),
            True,
        )

    if answer_slot and answer_slot.startswith("probe_"):
        probe = answer_slot.removeprefix("probe_")
        if probe == "duration":
            from packages.dialogue_engine.check_path import (
                is_urgent_concern,
                looks_like_duration_answer,
            )

            if looks_like_duration_answer(raw) or is_urgent_concern(raw):
                return (
                    SemanticTurn(
                        act=SemanticAct.ANSWER,
                        target_slot=answer_slot,
                        polarity="negative" if is_urgent_concern(raw) else "neutral",
                        confidence=0.93,
                        source_quote=raw,
                        value=raw,
                    ),
                    True,
                )
        if len(core.split()) >= 1 and core not in _BACKCHANNEL:
            return (
                SemanticTurn(
                    act=SemanticAct.ANSWER,
                    target_slot=answer_slot,
                    polarity=_detect_polarity(raw) or "neutral",
                    confidence=0.9,
                    source_quote=raw,
                    value=raw,
                ),
                True,
            )

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

    if answer_slot == "mood" and _MOOD_NEGATIVE_PHRASE.search(normalized):
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

    if answer_slot == "mood" and re.search(
        r"великолепн\w*|прекрасн\w*|отличн\w*", normalized
    ) and re.search(r"настроени\w*", normalized):
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
    # Contradiction: «хорошо, но состояние не очень» must not read as positive.
    if re.search(r"\bно\b", normalized) and re.search(
        r"(не\s+очень|плох\w*|тяжел\w*|слаб\w*|плохое)",
        normalized,
    ):
        return "negative"
    if re.search(r"состояни\w*\s+не\s+очень|не\s+очень\s+хорош", normalized):
        return "negative"
    if _WELLNESS_NEGATIVE.search(normalized):
        return "negative"
    if re.match(r"^плох\w*", core) or re.search(r"мне\s+не\s+очень", normalized):
        return "negative"
    if re.search(r"настроени\w*", normalized) and re.search(
        r"не\s+очень|плох\w*|ужасн\w*|груст\w*|никак\w*", normalized
    ):
        return "negative"
    if re.search(r"великолепн\w*|прекрасн\w*", normalized) and re.search(
        r"настроени\w*", normalized
    ):
        return "positive"
    if _SO_SO.match(core) or re.search(
        r"\b(так\s+себе|сойд[её]т|пойд[её]т|средн\w*|терпимо|ну\s+такое)\b", core, re.I
    ):
        return "uncertain"
    if _NORMAL.match(core):
        return "positive"
    if re.match(
        r"^(отличн\w*|хорош\w*|прекрасн\w*|нормальн\w*|обычн\w*|спокойн\w*)\.?$",
        core,
        re.I,
    ):
        return "positive"
    if re.match(r"^(средн\w*|грустн\w*)\.?$", core, re.I):
        return "negative" if core.startswith("груст") else "uncertain"
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
