# ADR-024: Bounded Neuro Learning Inside the Protocol

Date: 2026-09-29
Status: accepted
Extends: [ADR-009](009-llm-understanding-code-state.md), [ADR-020](020-conversational-strategist.md),
[ADR-021](021-care-dialogue-kernel.md). Executed under [ADR-023](023-replacement-and-cleanup-law.md).

## Context

Dialogue banks have a coverage ceiling: variants are finite and never learn
from data. A free generative speaker is unacceptable: it invents facts, owns
state, and cannot prove safety. Competitors sell orchestration and guardrails
in words; our moat must be machine-checkable per utterance.

The system therefore learns *inside* a hard protocol: neuro ranks only
pre-approved actions and paraphrases only inside a validated contract.
Learning optimizes choice and wording within machine-verifiable allowed
behavior, and every executed step leaves reproducible proof of why it was
allowed.

## Decision

### 1. No second owner

Neuro never becomes a second owner of the system. It receives strictly
limited rights inside the existing CDK: rank legal actions, propose
surfaces inside a semantic contract. Protocol, state machine, safety
paths, consent, Core verdicts, and canonical banks stay untouched.

### 2. Proof bundle chains decision to delayed outcome

A proof bundle is not the spoken line alone. Required chain:

```text
decision → utterance → observable response → delayed outcome
```

Slice 1 artifact (`packages/dialogue_engine/proof_bundle.py`): event
schema v1 + immutable logger + proof-bundle builder + offline verifier.
Logger writes facts; verifier later proves properties — never mixed, so a
proof-code bug cannot destroy source data.

### 3. Raw text is never the architecture key

`action_id`, `state_id`, semantic signature, and grounding exist
independently of phrasing. Today's bank line and tomorrow's paraphrase
share one dataset because joins use ids and hashes, never raw strings.

### 4. The legal-set invariant is a type, not an if

```python
selected_action_id in legal_action_ids
```

enforced as a contract at the executor boundary
(`select_from_legal()` in `proof_bundle.py`), not as a conditional a
developer can forget. The ranker interface is scores-over-a-set, never
prediction:

```python
scores = model.score(state, legal_actions)
action = argmax_over_legal_set(scores)
```

A neuro component technically never generates an action ID.

### 5. Multi-level outcomes (no credit-assignment noise)

```text
turn outcome:    action → answered / silence / refusal / slot-changed
local-goal outcome: 2–5 turns → slot resolved
episode outcome: whole call → task done
```

Ranker v1 trains primarily on the **local** outcome; call outcome is an
auxiliary signal only. One early turn is never blamed for a whole call.

### 6. Leaky features banned for ranker v1

Until semantic linkage is proven, ranker v1 must not see:
timestamp, weekday, absolute call duration, user id, conversation id.
Machine-enforced via `BANNED_RANKER_FEATURES_V1` + `check_ranker_features()`.
Otherwise the model learns «users answer on Tuesdays» and reports pretty
offline accuracy with zero intelligence.

### 7. Paraphrase pipeline with veto-only semantics

```text
semantic contract → constrained generator → deterministic validator
        → semantic equivalence checker (veto only) → spoken text
```

Resolution rule (structural, not advisory):

```text
ALLOW = deterministic_contract_pass AND semantic_check_pass
```

A neural semantic checker can only veto, never approve alone.
`allow_surface()` encodes this: semantic abstention or approval without
deterministic pass both resolve to deny.

### 8. The FAIL-stays-FAIL invariant

**No learnable component may turn another learnable component's FAIL
into PASS.** If paraphraser → validator FAIL, no second model may say
«actually fine». Only the canonical fallback speaks. This invariant is
encoded in `allow_surface()` and checked by the offline verifier — not
documented as a wish.

## Consequences

- Slice order is fixed: (1) trace schema + immutable logger, (2) builder +
  offline verifier, (3) shadow paraphraser, (4) outcome labels, (5) shadow
  ranker, (6) counterfactual/frozen eval, (7) limited promotion,
  (8) heuristic removal only where the neural path is proven.
- The learning pipeline itself (model, loss, evaluator, synthetic/frozen
  harness) is built before traffic outcomes exist; production policy is
  never trained without them.
- Every slice goes through ADR-023 gates: red → green → live proof →
  old path deleted, never parallel owners.

## Alternatives Considered

- Free LLM speaker: rejected — invents facts, owns state, unprovable.
- Banks forever: rejected — finite, flat liveliness, no learning.
- Ranker without legal-set typing: rejected — a forgotten `if` away from
  an illegal transition.
- Single neural semantic approver: rejected — one model's opinion is not
  a safety argument.

## Interfaces

- `packages/dialogue_engine/proof_bundle.py`: schema (Pydantic),
  `ProofLogger` (append-only JSONL, fsync, never raises),
  `build_turn_record()`, `link_outcome()`, `select_from_legal()`,
  `allow_surface()`, `BANNED_RANKER_FEATURES_V1`,
  `check_ranker_features()`, offline `verify_*`.
- Proof store: `$IMVERA_PROOF_DIR` or `.run/proof/proof-YYYYMMDD.jsonl`.
- Raw text stored for audit; joins use ids/hashes only.

## Verification status

| Claim | Status |
|-------|--------|
| Schema + logger + builder + verifier implemented | CHANGED this slice |
| Production feed (monitor-only emit hook) | CHANGED this slice |
| Any behavior change | NOT VERIFIED (must stay none; suite proves) |
| Outcome labels, ranker, paraphraser | NOT STARTED (slices 3–5) |
| Live acceptance | NOT VERIFIED |

## NEXT GATE

Slice 2 (builder + offline verifier hardened on live-shape fixtures) is
already inside this commit; next is slice 3 (shadow paraphraser) only
after proof rows accumulate from real traffic.
