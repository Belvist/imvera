"""NLP candidate turns: model proposes, deterministic disposes (live path).

Called only when the fast deterministic tier is NOT confident. Safety
acts (stop, user_question routing) are never overridden — they fall
through to rules. Everything else maps to the existing SemanticTurn
contract, so the reducer/validator path is unchanged.
"""

from __future__ import annotations

from packages.dialogue_engine.semantic import SemanticAct, SemanticTurn
from packages.dialogue_engine.semantic_nlp.model import CONFIDENCE_THRESHOLD, SemanticNLP

# Acts the model may resolve. stop/user_question stay deterministic.
USABLE_ACTS: dict[str, SemanticAct] = {
    "greeting": SemanticAct.BACKCHANNEL,
    "backchannel": SemanticAct.BACKCHANNEL,
    "goodbye": SemanticAct.GOODBYE_REQUEST,
    "confirm": SemanticAct.ANSWER,
    "decline": SemanticAct.ANSWER,
    "answer": SemanticAct.ANSWER,
    "not_recalled": SemanticAct.ANSWER,
    "uncertain": SemanticAct.ANSWER,
    "correction": SemanticAct.ANSWER,
    "complaint": SemanticAct.ANSWER,
    "repeat_request": SemanticAct.REPAIR_REQUEST,
}

_POLARITY: dict[str, str] = {
    "confirm": "positive",
    "decline": "negative",
    "uncertain": "uncertain",
    "not_recalled": "uncertain",
}


def nlp_candidate_turn(
    question: str,
    text: str,
    answer_slot: str | None,
) -> tuple[SemanticTurn | None, bool, dict[str, object]]:
    """Return (turn|None, used, info). Never raises; None on any doubt."""
    info: dict[str, object] = {"nlp_act": None, "nlp_conf": 0.0, "used": False}
    try:
        candidate = SemanticNLP.get().predict(question, text)
    except Exception:
        return None, False, info
    if candidate is None:
        return None, False, info
    info["nlp_act"] = candidate.act
    info["nlp_conf"] = round(candidate.confidence, 3)
    info["nlp_latency_ms"] = round(candidate.latency_ms, 1)
    if candidate.confidence < CONFIDENCE_THRESHOLD:
        return None, False, info
    mapped = USABLE_ACTS.get(candidate.act)
    if mapped is None:
        return None, False, info
    turn = SemanticTurn(
        act=mapped,
        target_slot=answer_slot,
        polarity=_POLARITY.get(candidate.act),
        confidence=candidate.confidence,
        source_quote=text.strip(),
        value=text.strip(),
        correction=candidate.act == "correction",
        not_recalled=candidate.act == "not_recalled",
    )
    info["used"] = True
    return turn, True, info
