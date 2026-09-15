"""Reluctance detection — deterministic, no model.

The client is not an interrogation subject: when they signal they are done
(short answers in a row, irritation, explicit finish), Vera must close warmly
with what is already recorded instead of squeezing the call into partial.

Scoring (per user turn, capped):
  +10  explicit finish: хватит/заканчиваем/надоело/отстань/некогда/тороплюсь
  +3   tired of talking: устал говорить/тяжело говорить/не могу говорить
  +2   irritation without content: insults, «хуйня», «ты дура»
  +1   one-word/backchannel answer to a content question
  +1   «не знаю» / «не помню» as the whole answer

Threshold >= 3 → early warm close (summary with recorded facts).
The tiny-LLM assist (when enabled) only disambiguates borderline short
utterances; it never lowers a deterministic signal.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.dialogue_engine.state import EngineState
    from packages.dialogue_engine.turn_understanding import RichUserTurn

EARLY_CLOSE_THRESHOLD = 3

_FINISH_NOW = re.compile(
    r"(хватит|хватит\s+уже|давай\s+заканчива\w*|заканчива\w*|"
    r"надоело|надоели|отстань|отстаньте|не\s+звони|"
    r"некогда\s+(мне|говорить)?|тороплюсь|мне\s+пора|"
    r"ой\s+вс[её]|давай\s+пока|всё,\s*пока|все,\s*пока)",
    re.I,
)
_TIRED_OF_TALKING = re.compile(
    r"(устал\w*(?:\s+\w+){0,2}\s+говорить|тяжело\s+говорить|"
    r"не\s+могу\s+говорить|тяжело\s+мне\s+говорить|долго\s+говорим)",
    re.I,
)
_IRRITATION = re.compile(
    r"(хуйня|хуйню|дура|дурак|дебил|идиот|тупая|тупой|"
    r"задолбал|достал[аи]?|бесишь|замолчи|помолчи)",
    re.I,
)
_ONE_WORD = re.compile(r"^[\wё\-]+\.?$", re.I)
_BACKCHANNEL_WORDS = frozenset({"да", "нет", "ага", "угу", "ну", "алло", "неа"})
# Verb answers to fact-check slots («успели», «принял», «поела») — content,
# never stalls, even as single words (live fs-d99db688 «Успели.»).
_SHORT_CONTENT_VERBS = re.compile(
    r"\b(успел\w*|принял\w*|выпил\w*|поел\w*|поела|покушал\w*|попил\w*|"
    r"смог\w*|смогла|получилось|удалось|ложусь|встал\w*|проснул\w*)\b",
    re.I,
)
# Pure stall words in ANY slot (never a valid answer, only a placeholder).
_STALL_WORDS = frozenset({"ага", "угу", "алло", "ну"})
# Slots where yes/no/don't-know IS the valid answer (fact-checks, closes).
_STALL_EXEMPT_SLOTS = frozenset(
    {
        "important_to_share",
        "plans",
        "mood",
        "sleep",
        "wellness",
        "background_medication",
        "background_nutrition",
        "background_mood",
        "background_sleep",
    }
)
_VAGUE_NO = re.compile(r"^(да\s+)?вроде\s+бы?\s*нет\.?$", re.I)
_DONT_KNOW = re.compile(
    r"^(не\s+знаю|не\s+помню|хз|без\s+понятия)\.?$", re.I
)


def reluctance_points(raw_text: str, *, answers_pending: bool) -> int:
    text = (raw_text or "").strip()
    if not text:
        return 0
    if _FINISH_NOW.search(text):
        return 10
    if _TIRED_OF_TALKING.search(text):
        return 3
    points = 0
    if _IRRITATION.search(text):
        # Irritation WITH a grounded complaint still carries information —
        # the scheduler records it; only pure venting counts double.
        points += 2
    if answers_pending:
        low = text.lower().rstrip(".!?")
        if low in _BACKCHANNEL_WORDS or _ONE_WORD.match(text):
            points += 1
        if _DONT_KNOW.match(text) or _VAGUE_NO.match(text):
            points += 1
    return points


def _grounded_short_answer(text: str, answer_slot: str | None) -> bool:
    """Short reply carrying real content for the pending slot — not a stall."""
    if _DONT_KNOW.match((text or "").strip()) or _VAGUE_NO.match((text or "").strip()):
        return False
    from packages.dialogue_engine.issue_memory import (
        extract_grounded_onset_value,
        extract_grounded_severity_value,
    )

    if extract_grounded_onset_value(text) is not None:
        return True
    if extract_grounded_severity_value(text) is not None:
        return True
    if (answer_slot or "") in _STALL_EXEMPT_SLOTS:
        # Food/med verbs («успели», «принял», «поела») answer fact-checks —
        # but never temporal probes («Колю покушал когда?» stays debris).
        if _SHORT_CONTENT_VERBS.search(text or ""):
            return True
    from packages.dialogue_engine.issue_memory import (
        extract_grounded_onset_value,
        extract_grounded_severity_value,
    )

    if extract_grounded_onset_value(text) is not None:
        return True
    if extract_grounded_severity_value(text) is not None:
        return True
    if (answer_slot or "") in _STALL_EXEMPT_SLOTS:
        # Fact-check slots accept yes/no, clear polarity («нормально»,
        # «плохо») and any substantive multi-word reply («да, принял»,
        # «поела нормально») — but not fragments («пло.», «э-э») and never
        # «не знаю» (handled as a weak signal by the caller).
        low = (text or "").strip().lower().rstrip(".!?")
        if low in {"да", "нет", "неа"} or len((text or "").split()) >= 2:
            return True
        from packages.dialogue_engine.fast_interpreter import _detect_polarity

        try:
            return _detect_polarity(text) in ("positive", "negative")
        except Exception:  # noqa: BLE001
            return False
    return False


def note_reluctance(
    state: EngineState,
    turn: RichUserTurn,
    *,
    answer_slot: str | None,
    cooperative_fill: bool = False,
) -> int:
    """Add this turn's points to state.reluctance_score (cap 10).

    Turns that filled a slot / gave grounded facts are cooperation, not
    reluctance: weak signals (one-word, «не знаю») are skipped for them.
    Explicit finish / tiredness / irritation always count.
    """
    text = (turn.raw_text or "").strip()
    if _FINISH_NOW.search(text) or _TIRED_OF_TALKING.search(text):
        state.reluctance_score = min(10, state.reluctance_score + (
            10 if _FINISH_NOW.search(text) else 3
        ))
        return state.reluctance_score
    if cooperative_fill:
        if _IRRITATION.search(text):
            state.reluctance_score = min(10, state.reluctance_score + 2)
        if turn.tiny_route == "reluctance":
            state.reluctance_score = min(10, state.reluctance_score + 1)
        return 0
    # Short polarity-bearing answers («хорошо», «нормально», «плохо»)
    # fill their slot — cooperation, not reluctance, even when the fill was
    # harvested outside newly_filled_slots. «Не знаю» stays a weak signal.
    if len(text.split()) <= 2 and not _IRRITATION.search(text):
        from packages.dialogue_engine.fast_interpreter import _detect_polarity

        try:
            if _detect_polarity(text) in ("positive", "negative"):
                return 0
        except Exception:  # noqa: BLE001 — fall through to weak signals
            pass
    answers_pending = bool(turn.answers_pending_question) or bool(answer_slot)
    low = text.lower().rstrip(".!?")
    # Pure stall one-worders (ага/угу/алло/ну) answer nothing in any slot.
    if answers_pending and low in _STALL_WORDS:
        gained = 1
    # Grounded short replies (severity/temporal anchors, valid yes/no for
    # fact-check slots) are answers, never stalls.
    elif answers_pending and _grounded_short_answer(text, answer_slot):
        if _IRRITATION.search(text):
            state.reluctance_score = min(10, state.reluctance_score + 2)
        return 0
    elif answers_pending and (low in _BACKCHANNEL_WORDS or _ONE_WORD.match(text)):
        gained = 1
    else:
        gained = reluctance_points(turn.raw_text, answers_pending=answers_pending)
    # Advisory tiny-model vote: bounded, never closes a call alone.
    if turn.tiny_route == "reluctance":
        gained += 1
    if gained:
        state.reluctance_score = min(10, state.reluctance_score + gained)
    return gained


def wants_early_close(state: EngineState) -> bool:
    return state.reluctance_score >= EARLY_CLOSE_THRESHOLD
