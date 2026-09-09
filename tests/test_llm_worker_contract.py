"""LLM worker /v1/interpret contract — mocked model, no MLX inference."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from packages.contracts.semantic import Evidence, IssueMention, SemanticPayload
from packages.dialogue_engine.turn_understanding import payload_to_rich_turn
from services.llm import worker as llm_worker

pytestmark = pytest.mark.dialogue_engine


def _evidence(quote: str) -> Evidence:
    return Evidence(start=0, end=len(quote), quote=quote)


def _client_ready() -> TestClient:
    llm_worker.state.ready = True
    llm_worker.state.model_revision = "test-mock"
    llm_worker._model = object()
    llm_worker._tokenizer = object()
    return TestClient(llm_worker.app)


def _post_interpret(client: TestClient, raw_text: str, payload: dict) -> dict:
    encoded = json.dumps(payload, ensure_ascii=False)
    with patch.object(llm_worker, "_generate_sync", return_value=encoded):
        resp = client.post(
            "/v1/interpret",
            json={"context": {"raw_text": raw_text}, "timeout_ms": 5000},
        )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_interpret_headache_nausea_issue_mentions() -> None:
    quote = "Голова болит и тошнит."
    payload = SemanticPayload(
        dialogue_act="answer",
        control="none",
        consent_answer="not_applicable",
        answers_pending_question=True,
        needs_clarification=False,
        issue_mentions=(
            IssueMention(
                mention_id="m1",
                kind="symptom",
                label="головная боль",
                role="primary",
                body_site="голова",
                temporal_scope="now",
                status="active",
                evidence=_evidence("Голова болит"),
            ),
            IssueMention(
                mention_id="m2",
                kind="symptom",
                label="тошнота",
                role="associated",
                body_site=None,
                temporal_scope="now",
                status="active",
                evidence=_evidence("тошнит"),
            ),
        ),
    ).model_dump(mode="json")
    data = _post_interpret(_client_ready(), quote, payload)
    validated = SemanticPayload.model_validate(data["payload"])
    labels = {m.label.lower() for m in validated.issue_mentions}
    assert "головная боль" in labels
    assert "тошнота" in labels
    assert not any(m.body_site == "живот" for m in validated.issue_mentions if m.body_site)


def test_interpret_throat_generic_issue() -> None:
    quote = "першит горло"
    payload = SemanticPayload(
        dialogue_act="answer",
        control="none",
        consent_answer="not_applicable",
        answers_pending_question=False,
        needs_clarification=False,
        issue_mentions=(
            IssueMention(
                mention_id="m1",
                kind="symptom",
                label="першение в горле",
                role="primary",
                body_site="горло",
                temporal_scope="now",
                status="active",
                evidence=_evidence(quote),
            ),
        ),
    ).model_dump(mode="json")
    data = _post_interpret(_client_ready(), quote, payload)
    validated = SemanticPayload.model_validate(data["payload"])
    assert validated.issue_mentions[0].body_site == "горло"


def test_interpret_unknown_with_chest_no_fake_onset() -> None:
    quote = "не знаю, но грудь давит"
    chest_quote = "грудь давит"
    payload = SemanticPayload(
        dialogue_act="answer",
        control="none",
        consent_answer="not_applicable",
        answers_pending_question=True,
        needs_clarification=False,
        issue_mentions=(
            IssueMention(
                mention_id="m1",
                kind="symptom",
                label="давление в груди",
                role="primary",
                body_site="грудь",
                temporal_scope="now",
                status="active",
                evidence=_evidence(chest_quote),
            ),
        ),
    ).model_dump(mode="json")
    data = _post_interpret(_client_ready(), quote, payload)
    validated = SemanticPayload.model_validate(data["payload"])
    rich = payload_to_rich_turn(validated, utterance_id="u-1", raw_text=quote)
    assert rich.answers_pending_question
    assert validated.issue_mentions
    assert all(m.onset is None for m in validated.issue_mentions)


def test_interpret_user_question() -> None:
    quote = "А кто вы?"
    payload = SemanticPayload(
        dialogue_act="question",
        control="none",
        consent_answer="not_applicable",
        answers_pending_question=False,
        needs_clarification=False,
        user_question=quote,
    ).model_dump(mode="json")
    data = _post_interpret(_client_ready(), quote, payload)
    validated = SemanticPayload.model_validate(data["payload"])
    assert validated.dialogue_act == "question"
    assert validated.user_question


def test_interpret_correction() -> None:
    quote = "Я же говорил, что болит"
    payload = SemanticPayload(
        dialogue_act="correction",
        control="none",
        consent_answer="not_applicable",
        answers_pending_question=True,
        needs_clarification=False,
    ).model_dump(mode="json")
    data = _post_interpret(_client_ready(), quote, payload)
    validated = SemanticPayload.model_validate(data["payload"])
    rich = payload_to_rich_turn(validated, utterance_id="u-1", raw_text=quote)
    assert rich.correction or validated.dialogue_act == "correction"
