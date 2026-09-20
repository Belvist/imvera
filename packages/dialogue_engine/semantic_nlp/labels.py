"""Semantic NLP label schema (expert-designed, versioned with the model).

The classifier input is always "[Q] {question} [U] {text}" — context-aware
by construction ("Не помню" needs the question). Output is a candidate
act; the deterministic validator owns the decision (safety/deterministic
win conflicts). No off switch: the path is live, hierarchy is architecture.
"""

from __future__ import annotations

ACTS: tuple[str, ...] = (
    "greeting",
    "backchannel",
    "goodbye",
    "confirm",
    "decline",
    "answer",
    "not_recalled",
    "uncertain",
    "correction",
    "complaint",
    "user_question",
    "repeat_request",
    "stop",
)

ACT_INDEX: dict[str, int] = {name: index for index, name in enumerate(ACTS)}

MODEL_ID = "deepvk/RuModernBERT-base"
ARTIFACT_DIRNAME = "semantic_nlp"
