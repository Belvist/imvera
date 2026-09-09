"""RichUserTurn contract and payload bridge."""

from __future__ import annotations

from packages.contracts.semantic import Evidence, IssueMention, SemanticPayload
from packages.dialogue_engine.evidence_invariant import sanitize_issue_mention
from packages.dialogue_engine.turn_understanding import (
    build_rich_turn_from_payload,
    build_rich_turn_from_text,
    payload_to_rich_turn,
)


def _mention(
    *,
    label: str,
    quote: str,
    body_site: str | None = None,
    role: str = "primary",
) -> IssueMention:
    return IssueMention(
        mention_id="im-test",
        kind="symptom",
        label=label,
        role=role,
        body_site=body_site,
        temporal_scope="now",
        status="active",
        evidence=Evidence(start=0, end=len(quote), quote=quote),
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


def test_open_issue_from_payload_not_regex() -> None:
    quote = "онемел палец"
    payload = SemanticPayload(
        dialogue_act="answer",
        control="none",
        consent_answer="not_applicable",
        answers_pending_question=True,
        needs_clarification=False,
        issue_mentions=(
            _mention(label="онемение пальца", quote=quote, body_site="палец"),
        ),
    )
    turn = build_rich_turn_from_payload(payload, utterance_id="u-1", raw_text=quote)
    assert turn.issue_mentions[0].label == "онемение пальца"


def test_sanitize_rejects_nausea_to_abdominal_hallucination() -> None:
    mention = _mention(
        label="боль в животе",
        quote="тошнит",
        body_site="живот",
    )
    cleaned = sanitize_issue_mention(mention, "тошнит")
    assert cleaned is not None
    assert cleaned.label == "тошнота"
    assert cleaned.body_site is None
