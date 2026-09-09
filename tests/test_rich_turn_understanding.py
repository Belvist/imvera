"""RichUserTurn contract and payload bridge."""

from __future__ import annotations

from packages.contracts.semantic import SemanticPayload
from packages.dialogue_engine.turn_understanding import (
    build_rich_turn_from_text,
    payload_to_rich_turn,
)


def test_payload_to_rich_turn_preserves_correction_and_question() -> None:
    payload = SemanticPayload(
        dialogue_act="correction",
        control="none",
        consent_answer="not_applicable",
        answers_pending_question=False,
        needs_clarification=False,
        user_question=None,
    )
    turn = payload_to_rich_turn(
        payload,
        utterance_id="u-1",
        raw_text="Я же говорил, сердце болит.",
    )
    assert turn.correction is True
    assert turn.dialogue_act == "correction"


def test_build_rich_turn_headache_and_nausea() -> None:
    turn = build_rich_turn_from_text(
        "Состояние не очень, голова болит и тошнит.",
        utterance_id="u-1",
    )
    labels = {m.label for m in turn.issue_mentions}
    assert "головная боль" in labels
    assert "тошнота" in labels
    assert not any("живот" in (m.body_site or "") for m in turn.issue_mentions)


def test_user_question_detected() -> None:
    turn = build_rich_turn_from_text("А вы кто вообще?", utterance_id="u-2")
    assert turn.user_question is not None
    assert turn.dialogue_act == "question"
