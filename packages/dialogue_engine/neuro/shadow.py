"""Shadow scoring + disagreement logging (ADR-024 slice 3 feed).

Monitor-only: given a turn's (signature, canonical, heuristic choice,
legal set), runs the pipeline in shadow and logs what WOULD have happened
versus what did. Never diverts speech, never fills slots, never raises.

Wired behind ``IMVERA_NEURO_SHADOW`` (default off). The disagreement rows
it writes are the future training queue: (signature, heuristic, ranker
scores, ranker_choice, agreed) joined to proof turns by ids.
"""

from __future__ import annotations

import logging
import os

from packages.dialogue_engine.neuro.interfaces import RankScores
from packages.dialogue_engine.neuro.paraphrase import (
    AbstainingChecker,
    PoolGenerator,
)
from packages.dialogue_engine.proof_bundle import ProofLogger, allow_surface

_log = logging.getLogger("imvera.neuro.shadow")


def shadow_enabled() -> bool:
    return os.environ.get("IMVERA_NEURO_SHADOW", "0").strip() in {"1", "true", "yes"}


def score_shadow(
    *,
    signature: str,
    canonical_text: str,
    heuristic_choice: str,
    legal_action_ids: list[str],
    rank_scores: RankScores | None = None,
    deterministic_pass: bool = True,
    call_id: str = "",
    turn_id: str = "",
) -> dict | None:
    """Run the full pipeline in shadow. Returns the disagreement row (also
    logged). Returns None when disabled or on any internal error."""
    if not shadow_enabled():
        return None
    try:
        checker = AbstainingChecker()
        generator = PoolGenerator()
        proposals = generator.propose(signature, canonical_text)
        allowed = [
            p.text
            for p in proposals
            if allow_surface(deterministic_pass, checker.check(signature, p.text))
        ]
        ranker_choice: str | None = None
        agreed: bool | None = None
        if rank_scores is not None:
            in_legal = {
                k: v for k, v in rank_scores.scores.items() if k in legal_action_ids
            }
            if in_legal:
                ranker_choice = max(in_legal.items(), key=lambda kv: (kv[1], kv[0]))[0]
                agreed = ranker_choice == heuristic_choice
        row = {
            "kind": "neuro_shadow",
            "schema_version": 1,
            "call_id": call_id,
            "turn_id": turn_id,
            "signature": signature,
            "heuristic_choice": heuristic_choice,
            "ranker_choice": ranker_choice,
            "agreed": agreed,
            "proposals": [p.text for p in proposals],
            "allowed_proposals": allowed,
            "ranker_version": rank_scores.ranker_version if rank_scores else None,
        }
        ProofLogger().append_row(row)
        return row
    except Exception as exc:  # noqa: BLE001 — shadow never breaks the call
        _log.warning("neuro shadow failed: %s", exc)
        return None
