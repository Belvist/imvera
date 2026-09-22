"""NLP candidate turns: model proposes, deterministic disposes (live path).

Called only when the fast deterministic tier is NOT confident. Safety
acts (stop, user_question routing) are never overridden — they fall
through to rules. Everything else maps to the existing SemanticTurn
contract, so the reducer/validator path is unchanged.
"""

from __future__ import annotations

import logging
import time

from packages.dialogue_engine.semantic import SemanticAct, SemanticTurn
from packages.dialogue_engine.semantic_nlp.model import CONFIDENCE_THRESHOLD, SemanticNLP

_log = logging.getLogger("dialogue.nlp_candidate")

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
        t0 = time.monotonic()
        inst = SemanticNLP.get()
        info["nlp_get_ms"] = round((time.monotonic() - t0) * 1000.0, 1)
        candidate = inst.predict(question, text)
    except Exception as exc:
        # Live fs-8a64bac9 turn 1: 6.3 s inside this call, no latency recorded.
        # Log so the next live call names it (load? MPS? input-specific?).
        _log.warning(
            "nlp_candidate failed len=%d err=%s:%s",
            len(text or ""),
            type(exc).__name__,
            str(exc)[:200],
        )
        info["nlp_error"] = f"{type(exc).__name__}"
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
