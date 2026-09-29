"""Bounded neuro pipeline (ADR-024 slices 3-6, interfaces first).

Nothing here owns speech or state. Every component operates strictly
inside the protocol:

- ``interfaces``: Generator / SemanticChecker / Ranker protocols.
- ``paraphrase``: deterministic-pool generator (honestly NON-neural
  baseline implementing the interface, so the pipeline is complete and
  testable end-to-end before any model exists) + validator composition.
- ``ranker``: cross-entropy loss over legal sets, feature-allowlist
  enforcement, synthetic/frozen evaluator.
- ``shadow``: monitor-only scoring + disagreement logging into the proof
  log. Wired behind ``IMVERA_NEURO_SHADOW`` (default off); never diverts
  speech, never fills slots.

A real model plugs in by implementing the protocols. Until then every
neural slot abstains and the deterministic path answers unchanged.
"""
