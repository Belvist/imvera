"""Repeated symptom words retain their own original anatomical/subject span."""

import pytest

from packages.dialogue_engine.semantic_kernel.clauses import clause_bounds, clause_for_position
from packages.dialogue_engine.semantic_kernel.kernel import interpret, kernel_to_rich_turn

pytestmark = pytest.mark.dialogue_engine


@pytest.mark.parametrize("text", ["Голова болит, живот болит.", "Голова болит. Живот болит."])
def test_same_verb_in_two_complaints_uses_each_original_occurrence(text):
    mentions = kernel_to_rich_turn(interpret(text, utterance_id="repeated")).issue_mentions
    for site in ("голова", "живот"):
        mention = next(m for m in mentions if m.body_site == site)
        evidence = mention.evidence
        assert text[evidence.start : evidence.end] == evidence.quote
        clause = clause_for_position(clause_bounds(text), evidence.start).lower()
        assert site in clause


def test_foreign_first_occurrence_cannot_supply_callers_evidence():
    text = "У дочери голова болит, у меня живот болит."
    mentions = kernel_to_rich_turn(interpret(text, utterance_id="mixed")).issue_mentions
    mention = next(m for m in mentions if m.body_site == "живот" and m.subject == "speaker")
    assert mention.evidence.start > text.index(",")


def test_compatibility_proposal_without_original_spans_cannot_guess_repeated_quote():
    from packages.dialogue_engine.semantic_kernel.observation_memory import (
        observations_to_issue_mentions,
    )
    from packages.dialogue_engine.semantic_kernel.types import Observation

    proposal = Observation(
        observation_id="ambiguous",
        attribute="issue",
        value="живот болит",
        body_site="живот",
        issue_normalized="болеть",
        evidence="болит",
    )
    assert (
        observations_to_issue_mentions((proposal,), "У дочери голова болит, у меня живот болит.")
        == ()
    )
