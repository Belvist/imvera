"""PendingQuestion — typed control questions awaiting a valid answer."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence, Tuple


class PendingQuestionType(str, Enum):
    """How a short caller answer should be validated."""

    YES_NO = "yes_no"
    CHOICE = "choice"
    OPEN = "open"


@dataclass
class PendingQuestion:
    """One open control question Vera asked and expects a typed answer."""

    kind: PendingQuestionType
    prompt: str
    choices: Tuple[str, ...] = ()
    expected_slot: str = ""
    asked_turn: int = 0

    def matches_choice(self, text: str) -> bool:
        """True when text selects one of the declared choices."""
        low = (text or "").strip().lower()
        if not low or not self.choices:
            return False
        for choice in self.choices:
            c = choice.strip().lower()
            if not c:
                continue
            if low == c or c in low or low in c:
                return True
        return False


_YES_NO_WORDS = frozenset((
    "да", "нет", "ага", "угу", "неа", "не", "ну да", "ну нет",
))


def validate_pending_answer(
    pending: PendingQuestion | None,
    text: str,
) -> tuple[bool, str]:
    """
    Validate caller text against an open pending question.

    Returns (valid, reason). ``reason`` is empty when valid; otherwise a short
    machine tag (``choice_needs_pick``, ``yes_no_only``, etc.).
    """
    if pending is None:
        return True, ""
    raw = (text or "").strip()
    if not raw:
        return False, "empty"

    low = re.sub(r"[^\w\s]", " ", raw.lower()).strip()
    words = low.split()

    if pending.kind == PendingQuestionType.OPEN:
        return True, ""

    if pending.kind == PendingQuestionType.YES_NO:
        if low in _YES_NO_WORDS or (len(words) <= 2 and any(w in _YES_NO_WORDS for w in words)):
            return True, ""
        if len(words) <= 3:
            return False, "yes_no_only"
        return True, ""

    if pending.kind == PendingQuestionType.CHOICE:
        if low in _YES_NO_WORDS and len(words) <= 2:
            return False, "choice_needs_pick"
        if pending.matches_choice(raw):
            return True, ""
        if len(words) <= 2 and low in _YES_NO_WORDS:
            return False, "choice_needs_pick"
        return True, ""

    return True, ""


def _clean_choice_label(raw: str) -> str:
    """Normalize one choice label from probe text."""
    cleaned = re.sub(r"[^\wё\s\-]+", " ", (raw or "").lower()).strip()
    words = [w for w in cleaned.split() if w]
    if not words:
        return ""
    if len(words) >= 2 and words[0].startswith("что") and "другое" in words:
        return " ".join(words[: min(3, len(words))])
    return words[-1]


def _extract_or_choices(low: str) -> Tuple[str, ...]:
    """Pull choice labels from «X или Y» and comma/or lists."""
    qpart = low.split("?", 1)[0]
    if " или " not in qpart:
        return ()
    parts = re.split(r"\s+или\s+", qpart)
    if len(parts) < 2:
        return ()
    left_raw = parts[0]
    right_raw = parts[-1]
    choices: list[str] = []

    if "," in left_raw:
        left_body = left_raw
        if "—" in left_body:
            left_body = left_body.split("—", 1)[-1]
        elif " - " in left_body:
            left_body = left_body.split(" - ", 1)[-1]
        elif ":" in left_body:
            left_body = left_body.split(":", 1)[-1]
        for segment in re.split(r"\s*,\s*", left_body):
            label = _clean_choice_label(segment)
            if label and label not in choices:
                choices.append(label)
    else:
        left_words = [w for w in re.sub(r"[^\wё\s\-]+", " ", left_raw).split() if w]
        if left_words:
            label = _clean_choice_label(left_words[-1])
            if label:
                choices.append(label)

    right_label = _clean_choice_label(right_raw)
    if right_label and right_label not in choices:
        choices.append(right_label)

    return tuple(choices[:6]) if len(choices) >= 2 else ()


def infer_pending_from_prompt(
    prompt: str,
    *,
    turn_no: int = 0,
) -> PendingQuestion | None:
    """Heuristic: derive pending-question type from Vera's last question."""
    p = (prompt or "").strip()
    if not p or "?" not in p:
        return None
    low = p.lower()
    if re.search(
            r"(верно|правильно|так ли|подтверд|согласн|да или нет|хорошо или плохо)",
            low):
        return PendingQuestion(
            kind=PendingQuestionType.YES_NO,
            prompt=p,
            expected_slot="yes_no",
            asked_turn=turn_no,
        )
    if re.search(r"\s+или\s+", low):
        choices = _extract_or_choices(low)
        if len(choices) >= 2:
            return PendingQuestion(
                kind=PendingQuestionType.CHOICE,
                prompt=p,
                choices=choices[:6],
                expected_slot="choice",
                asked_turn=turn_no,
            )
    return PendingQuestion(
        kind=PendingQuestionType.OPEN,
        prompt=p,
        expected_slot="open",
        asked_turn=turn_no,
    )


def apply_pending_to_memory(
    memory: object,
    prompt: str,
    *,
    turn_no: int = 0,
    explicit: PendingQuestion | None = None,
) -> PendingQuestion | None:
    """
    Set PendingQuestion on memory and observer_state at composition time.

    ``infer_pending_from_prompt`` remains the fallback when ``explicit`` is None.
    """
    pq = explicit or infer_pending_from_prompt(prompt, turn_no=turn_no)
    if pq is None:
        return None
    if hasattr(memory, "pending_question"):
        memory.pending_question = pq  # type: ignore[attr-defined]
    state = getattr(memory, "observer_state", None)
    if state is not None and hasattr(state, "pending_question"):
        state.pending_question = pq
    return pq
