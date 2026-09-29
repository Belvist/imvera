"""Paraphrase pipeline (ADR-024 slice 3, pre-model stage).

Composition (structural, not advisory)::

    ALLOW = deterministic_contract_pass AND semantic_check_pass

- ``PoolGenerator``: deterministic, honestly NON-neural baseline. Reorders
  and lightly rewords from fixed pools keyed by signature class, so the
  pipeline (generate → validate → veto → allow/fallback) is complete and
  testable before any model exists. Version string says ``pool-v1`` —
  never impersonates a model.
- ``AbstainingChecker``: the semantic slot before a model exists. Always
  abstains (None): veto power present, approval power absent.
- ``compose_proposal``: runs generator → deterministic validator fn →
  checker veto → returns (allowed_text, fallback_used). On ANY failure
  mode the canonical text speaks. No exception path speaks a proposal.
"""

from __future__ import annotations

from collections.abc import Callable

from packages.dialogue_engine.neuro.interfaces import ParaphraseProposal
from packages.dialogue_engine.proof_bundle import allow_surface

POOL_VERSION = "pool-v1"
ABSTAIN_VERSION = "none-v1"

_POOLS: dict[str, tuple[str, ...]] = {
    "ack": (
        "{label} — записала.",
        "{label} — поняла, записываю.",
        "{label} — услышала.",
    ),
    "question": (
        "{label} — подскажите?",
        "Уточните, пожалуйста: {label}?",
        "{label} — расскажите чуть подробнее?",
    ),
}


def _pool_key(signature: str) -> str:
    return "question" if "?" in signature else "ack"


class PoolGenerator:
    """Deterministic baseline generator (NOT a model)."""

    version = POOL_VERSION

    def propose(
        self, signature: str, canonical_text: str, n: int = 3
    ) -> list[ParaphraseProposal]:
        pool = _POOLS[_pool_key(signature)]
        label = signature.split("?", 1)[0].strip() or canonical_text
        out: list[ParaphraseProposal] = []
        for template in pool[: max(n, 0)]:
            try:
                text = template.format(label=label)
            except (IndexError, KeyError):
                continue
            if text != canonical_text:
                out.append(
                    ParaphraseProposal(
                        text=text, generator_version=self.version, signature=signature
                    )
                )
        return out


class AbstainingChecker:
    """Semantic slot with no model: always abstains, never approves."""

    version = ABSTAIN_VERSION

    def check(self, signature: str, proposed_text: str) -> bool | None:
        return None


def compose_proposal(
    signature: str,
    canonical_text: str,
    deterministic_pass: Callable[[str], bool],
    checker: AbstainingChecker | None = None,
    n: int = 3,
) -> tuple[str, bool]:
    """Returns (text_to_speak, fallback_used).

    First proposal passing ``ALLOW = deterministic AND NOT semantic-veto``
    speaks; otherwise the canonical text speaks with fallback_used=True.
    """
    generator = PoolGenerator()
    semantic = checker or AbstainingChecker()
    for proposal in generator.propose(signature, canonical_text, n=n):
        det = bool(deterministic_pass(proposal.text))
        sem = semantic.check(signature, proposal.text)
        if allow_surface(det, sem):
            return proposal.text, False
    return canonical_text, True
