"""Proof bundle v1 — trace schema + immutable logger + builder + verifier.

Implements ADR-024 slice 1 (and the verifier half of slice 2). The chain:

```text
decision → utterance → observable response → delayed outcome
```

Separation is structural: the logger writes facts; the verifier proves
properties. The logger never imports the verifier, so a proof-code bug
cannot destroy source data.

Machine-enforced contracts (not documentation):

- ``select_from_legal()`` — the only way to pick an action: scores over an
  explicit legal set, argmax inside it. A model technically never generates
  an action ID. Raises ``IllegalSelectionError`` otherwise.
- ``allow_surface()`` — ``deterministic AND semantic`` with veto-only
  semantics: a neural checker can deny, never approve alone.
- ``BANNED_RANKER_FEATURES_V1`` + ``check_ranker_features()`` — leaky
  features (timestamp, weekday, duration, user/conversation id) are
  rejected for ranker v1 until semantic linkage is proven.

Raw text is stored for audit but is never a join key: turns, decisions and
outcomes link by ids and hashes only.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

_log = logging.getLogger("imvera.proof")

SCHEMA_VERSION = 1

SelectionSource = Literal["heuristic", "ranker"]
OutcomeLevel = Literal["turn", "local_goal", "episode"]


class IllegalSelectionError(ValueError):
    """Raised when a selection leaves the legal set. Never swallowed."""


# ---------------------------------------------------------------- schema

class StateSnapshot(BaseModel):
    protocol_version: str = ""
    state_id: str = ""
    slot_state: dict[str, str] = Field(default_factory=dict)
    memory_refs: list[str] = Field(default_factory=list)

    model_config = {"frozen": True}


class DecisionRecord(BaseModel):
    legal_action_ids: list[str] = Field(default_factory=list)
    legal_set_complete: bool = False
    selected_action_id: str = ""
    selection_source: SelectionSource = "heuristic"
    ranker_version: str | None = None
    scores: dict[str, float] | None = None

    model_config = {"frozen": True}


class SemanticContract(BaseModel):
    act: str = ""
    grounded_facts: list[str] = Field(default_factory=list)
    required_content: list[str] = Field(default_factory=list)
    forbidden_content: list[str] = Field(default_factory=list)
    preserved_quotes: list[str] = Field(default_factory=list)
    question_budget: int = 0

    model_config = {"frozen": True}


class SurfaceRecord(BaseModel):
    canonical_text: str = ""
    proposed_text: str = ""
    paraphraser_version: str | None = None
    validator_version: str = ""
    validator_checks: list[str] = Field(default_factory=list)
    validator_pass: bool | None = None
    fallback_used: bool = False
    spoken_text_hash: str = ""

    model_config = {"frozen": True}


class ImmediateResult(BaseModel):
    user_replied: bool | None = None
    silence: bool | None = None
    refusal: bool | None = None
    interruption: bool | None = None
    slot_changed: bool | None = None
    escalation: bool | None = None

    model_config = {"frozen": True}


class DelayedOutcome(BaseModel):
    slot_resolved: bool | None = None
    goal_resolved: bool | None = None
    call_completed: bool | None = None
    human_review: str | None = None
    outcome_version: str = "v1"

    model_config = {"frozen": True}


class TurnRecord(BaseModel):
    schema_version: int = SCHEMA_VERSION
    kind: Literal["turn"] = "turn"
    turn_id: str = ""
    call_id: str = ""
    utterance_id: str = ""
    recorded_at: str = ""
    state_snapshot: StateSnapshot = Field(default_factory=StateSnapshot)
    decision: DecisionRecord = Field(default_factory=DecisionRecord)
    contract: SemanticContract = Field(default_factory=SemanticContract)
    surface: SurfaceRecord = Field(default_factory=SurfaceRecord)
    immediate: ImmediateResult | None = None
    delayed: DelayedOutcome | None = None

    model_config = {"frozen": True}


class OutcomeRecord(BaseModel):
    schema_version: int = SCHEMA_VERSION
    kind: Literal["outcome"] = "outcome"
    turn_id: str = ""
    call_id: str = ""
    level: OutcomeLevel = "turn"
    recorded_at: str = ""
    user_replied: bool | None = None
    silence: bool | None = None
    refusal: bool | None = None
    interruption: bool | None = None
    slot_changed: bool | None = None
    slot_resolved: bool | None = None
    goal_resolved: bool | None = None
    call_completed: bool | None = None
    escalation: bool | None = None
    human_review: str | None = None
    outcome_version: str = "v1"

    model_config = {"frozen": True}


# ------------------------------------------------------- machine contracts

def select_from_legal(
    legal_action_ids: list[str],
    scores: dict[str, float] | None = None,
    heuristic_choice: str | None = None,
) -> str:
    """The only legal way to pick an action (ADR-024 §4).

    Ranker-shaped input (scores over a set), argmax strictly inside the
    legal set. ``heuristic_choice`` is accepted only if inside the set.
    Anything else raises — it can never silently return an illegal id.
    """
    legal = list(legal_action_ids or [])
    if not legal:
        raise IllegalSelectionError("empty legal set: no action may be selected")
    if scores:
        in_legal = {k: v for k, v in scores.items() if k in legal}
        if not in_legal:
            raise IllegalSelectionError(
                "scores cover no legal action: refusing to invent one"
            )
        best = max(in_legal.items(), key=lambda kv: (kv[1], kv[0]))
        return best[0]
    if heuristic_choice is not None and heuristic_choice in legal:
        return heuristic_choice
    raise IllegalSelectionError(
        f"heuristic choice {heuristic_choice!r} outside legal set {legal}"
    )


def allow_surface(
    deterministic_pass: bool, semantic_pass: bool | None
) -> bool:
    """Veto-only composition (ADR-024 §7).

    ALLOW = deterministic AND semantic. A neural checker abstaining (None)
    or approving (True) can never approve alone; only an explicit
    deterministic pass combined with no veto speaks.
    """
    if not deterministic_pass:
        return False
    return semantic_pass is not False


BANNED_RANKER_FEATURES_V1 = frozenset(
    {
        "timestamp",
        "weekday",
        "hour",
        "absolute_call_duration",
        "call_duration",
        "user_id",
        "elder_id",
        "conversation_id",
        "call_id",
    }
)


def check_ranker_features(features: dict[str, Any] | list[str]) -> list[str]:
    """Names from the banned v1 set present in a feature bundle."""
    names = list(features) if isinstance(features, dict) else list(features or [])
    lowered = {str(n).lower() for n in names}
    return sorted(n for n in BANNED_RANKER_FEATURES_V1 if n in lowered)


def text_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- builder

def build_turn_record(
    *,
    turn_id: str,
    call_id: str,
    utterance_id: str = "",
    protocol_version: str = "",
    state_id: str = "",
    slot_state: dict[str, str] | None = None,
    memory_refs: list[str] | None = None,
    legal_action_ids: list[str] | None = None,
    legal_set_complete: bool = False,
    selected_action_id: str = "",
    selection_source: SelectionSource = "heuristic",
    ranker_version: str | None = None,
    scores: dict[str, float] | None = None,
    act: str = "",
    grounded_facts: list[str] | None = None,
    required_content: list[str] | None = None,
    forbidden_content: list[str] | None = None,
    preserved_quotes: list[str] | None = None,
    question_budget: int = 0,
    canonical_text: str = "",
    proposed_text: str = "",
    paraphraser_version: str | None = None,
    validator_version: str = "",
    validator_checks: list[str] | None = None,
    validator_pass: bool | None = None,
    fallback_used: bool = False,
) -> TurnRecord:
    """Pure builder: facts in, frozen record out. No I/O, no inference."""
    spoken = proposed_text or canonical_text
    return TurnRecord(
        turn_id=turn_id,
        call_id=call_id,
        utterance_id=utterance_id,
        recorded_at=time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        state_snapshot=StateSnapshot(
            protocol_version=protocol_version,
            state_id=state_id,
            slot_state=dict(slot_state or {}),
            memory_refs=list(memory_refs or []),
        ),
        decision=DecisionRecord(
            legal_action_ids=list(legal_action_ids or []),
            legal_set_complete=bool(legal_set_complete),
            selected_action_id=selected_action_id,
            selection_source=selection_source,
            ranker_version=ranker_version,
            scores=dict(scores) if scores is not None else None,
        ),
        contract=SemanticContract(
            act=act,
            grounded_facts=list(grounded_facts or []),
            required_content=list(required_content or []),
            forbidden_content=list(forbidden_content or []),
            preserved_quotes=list(preserved_quotes or []),
            question_budget=int(question_budget),
        ),
        surface=SurfaceRecord(
            canonical_text=canonical_text,
            proposed_text=proposed_text or canonical_text,
            paraphraser_version=paraphraser_version,
            validator_version=validator_version,
            validator_checks=list(validator_checks or []),
            validator_pass=validator_pass,
            fallback_used=bool(fallback_used),
            spoken_text_hash=text_hash(spoken),
        ),
    )


def link_outcome(
    turn: TurnRecord,
    level: OutcomeLevel,
    *,
    user_replied: bool | None = None,
    silence: bool | None = None,
    refusal: bool | None = None,
    interruption: bool | None = None,
    slot_changed: bool | None = None,
    slot_resolved: bool | None = None,
    goal_resolved: bool | None = None,
    call_completed: bool | None = None,
    escalation: bool | None = None,
    human_review: str | None = None,
) -> OutcomeRecord:
    """Append-only outcome linked by turn_id. Records are never mutated."""
    return OutcomeRecord(
        turn_id=turn.turn_id,
        call_id=turn.call_id,
        level=level,
        recorded_at=time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        user_replied=user_replied,
        silence=silence,
        refusal=refusal,
        interruption=interruption,
        slot_changed=slot_changed,
        slot_resolved=slot_resolved,
        goal_resolved=goal_resolved,
        call_completed=call_completed,
        escalation=escalation,
        human_review=human_review,
    )


# ---------------------------------------------------------------- logger

def proof_dir() -> Path:
    root = os.environ.get("IMVERA_PROOF_DIR", "").strip()
    path = Path(root) if root else Path(__file__).resolve().parents[2] / ".run" / "proof"
    path.mkdir(parents=True, exist_ok=True)
    return path


def proof_path(day: date | None = None) -> Path:
    return proof_dir() / f"proof-{(day or date.today()).isoformat()}.jsonl"


class ProofLogger:
    """Immutable append-only logger. Writes facts, never raises."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path or proof_path()

    def append(self, record: TurnRecord | OutcomeRecord) -> bool:
        try:
            path = self.path
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(record.model_dump_json(exclude_none=False) + "\n")
                fh.flush()
            return True
        except Exception as exc:  # noqa: BLE001 — logger never breaks the call
            _log.warning("proof append failed: %s", exc)
            return False


def read_records(path: Path | None = None) -> list[dict]:
    rows: list[dict] = []
    target = path or proof_path()
    if not target.exists():
        return rows
    try:
        with open(target, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    except OSError as exc:
        _log.warning("proof read failed: %s", exc)
    return rows


# ---------------------------------------------------------------- verifier

def verify_turn_record(record: TurnRecord) -> list[str]:
    """Offline property checks over one logged turn. Returns violations."""
    violations: list[str] = []
    if record.schema_version != SCHEMA_VERSION:
        violations.append(f"schema_mismatch: {record.schema_version}")
    decision = record.decision
    if decision.legal_set_complete and decision.legal_action_ids:
        if decision.selected_action_id not in decision.legal_action_ids:
            violations.append(
                "illegal_selection: selected outside complete legal set"
            )
    surface = record.surface
    if surface.validator_pass is False and not surface.fallback_used:
        violations.append("failed_validation_spoken_without_fallback")
    if surface.spoken_text_hash != text_hash(
        surface.proposed_text or surface.canonical_text
    ):
        violations.append("spoken_hash_mismatch")
    return violations


def verify_outcome_chain(
    turn: TurnRecord, outcomes: list[OutcomeRecord]
) -> list[str]:
    """Outcomes must reference their turn; raw text is never a join key."""
    violations: list[str] = []
    linked = [o for o in outcomes if o.turn_id == turn.turn_id]
    if outcomes and not linked:
        violations.append("outcome_without_turn_link")
    for outcome in linked:
        if outcome.call_id != turn.call_id:
            violations.append("outcome_call_mismatch")
    return violations


def verify_ranker_bundle(
    features: dict[str, Any] | list[str], selected: str, legal: list[str]
) -> list[str]:
    """Pre-training gate: banned features + legal-set membership."""
    violations = [
        f"banned_feature:{name}" for name in check_ranker_features(features)
    ]
    if selected not in list(legal or []):
        violations.append("illegal_selection")
    return violations
