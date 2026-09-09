"""Evidence invariant — no invented body sites."""

from __future__ import annotations

from packages.contracts.semantic import Evidence, IssueMention
from packages.dialogue_engine.evidence_invariant import (
    question_references_forbidden_site,
    sanitize_issue_mention,
)
from packages.dialogue_engine.issue_memory import ingest_rich_turn
from packages.dialogue_engine.state import EngineState
from packages.dialogue_engine.turn_understanding import build_rich_turn_from_text


def test_stomach_question_forbidden_without_evidence() -> None:
    state = EngineState(call_id="t", elder_display_name="Тест")
    ingest_rich_turn(
        state,
        build_rich_turn_from_text("Голова болит и тошнит.", utterance_id="u-1"),
    )
    assert question_references_forbidden_site(
        state,
        "А сейчас живот ещё беспокоит?",
    )


def test_llm_hallucinated_body_site_stripped() -> None:
    mention = IssueMention(
        mention_id="im-1",
        kind="symptom",
        label="боль в животе",
        role="primary",
        body_site="живот",
        temporal_scope="now",
        status="active",
        evidence=Evidence(start=0, end=6, quote="тошнит"),
    )
    cleaned = sanitize_issue_mention(mention, "тошнит")
    assert cleaned is not None
    assert cleaned.body_site is None
    assert cleaned.label == "тошнота"
