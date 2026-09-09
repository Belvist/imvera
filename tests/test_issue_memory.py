"""Issue episode memory ingest."""

from __future__ import annotations

from packages.contracts.semantic import Evidence, IssueMention, SemanticPayload
from packages.dialogue_engine.issue_memory import (
    get_active_episode,
    has_abdominal_episode,
    ingest_rich_turn,
)
from packages.dialogue_engine.state import EngineState
from packages.dialogue_engine.turn_understanding import (
    build_rich_turn_from_payload,
    build_rich_turn_from_text,
)


def _payload_answer(text: str, *, answers_pending: bool = True) -> SemanticPayload:
    return SemanticPayload(
        dialogue_act="answer",
        control="none",
        consent_answer="not_applicable",
        answers_pending_question=answers_pending,
        needs_clarification=False,
    )


def test_headache_nausea_single_episode_no_abdominal() -> None:
    state = EngineState(call_id="t", elder_display_name="Тест")
    turn = build_rich_turn_from_text(
        "Голова болит и тошнит.",
        utterance_id="u-1",
    )
    ingest_rich_turn(state, turn)
    assert state.active_episode_id is not None
    ep = state.issue_episodes[state.active_episode_id]
    assert "голов" in ep.primary_label.lower()
    assert any(m.label == "тошнота" for m in ep.mentions)
    assert not has_abdominal_episode(state)


def test_two_independent_episodes() -> None:
    state = EngineState(call_id="t", elder_display_name="Тест")
    turn = build_rich_turn_from_text(
        "Голова болит, ещё живот ноет.",
        utterance_id="u-1",
    )
    ingest_rich_turn(state, turn)
    assert state.active_episode_id is not None
    assert state.pending_episode_ids
    assert has_abdominal_episode(state)


def test_onset_and_severity_filled_from_pending_answers() -> None:
    state = EngineState(call_id="t", elder_display_name="Тест")
    ingest_rich_turn(
        state,
        build_rich_turn_from_text("Голова болит и тошнит.", utterance_id="u-1"),
    )
    state.pending_episode_attribute = "onset"
    ingest_rich_turn(
        state,
        build_rich_turn_from_payload(
            _payload_answer("С 10 утра"),
            utterance_id="u-2",
            raw_text="С 10 утра",
        ),
    )
    ep = get_active_episode(state)
    assert ep is not None
    assert ep.known_attributes.get("onset") == "С 10 утра"

    state.pending_episode_attribute = "severity"
    ingest_rich_turn(
        state,
        build_rich_turn_from_payload(
            _payload_answer("Сильная"),
            utterance_id="u-3",
            raw_text="Сильная",
        ),
    )
    assert ep.known_attributes.get("severity") == "Сильная"


def test_open_issue_from_llm_payload() -> None:
    state = EngineState(call_id="t", elder_display_name="Тест")
    quote = "першит горло"
    payload = SemanticPayload(
        dialogue_act="answer",
        control="none",
        consent_answer="not_applicable",
        answers_pending_question=True,
        needs_clarification=False,
        issue_mentions=(
            IssueMention(
                mention_id="im-1",
                kind="symptom",
                label="першение в горле",
                role="primary",
                body_site="горло",
                temporal_scope="now",
                status="active",
                evidence=Evidence(start=0, end=len(quote), quote=quote),
            ),
        ),
    )
    ingest_rich_turn(
        state,
        build_rich_turn_from_payload(payload, utterance_id="u-1", raw_text=quote),
    )
    ep = get_active_episode(state)
    assert ep is not None
    assert "горл" in ep.primary_label.lower()


def test_correction_does_not_duplicate_mention() -> None:
    state = EngineState(call_id="t", elder_display_name="Тест")
    quote = "живот болит"
    mention = IssueMention(
        mention_id="im-1",
        kind="symptom",
        label="боль в животе",
        role="primary",
        body_site="живот",
        temporal_scope="now",
        status="active",
        evidence=Evidence(start=0, end=len(quote), quote=quote),
    )
    ingest_rich_turn(
        state,
        build_rich_turn_from_payload(
            SemanticPayload(
                dialogue_act="answer",
                control="none",
                consent_answer="not_applicable",
                answers_pending_question=False,
                needs_clarification=False,
                issue_mentions=(mention,),
            ),
            utterance_id="u-1",
            raw_text=quote,
        ),
    )
    ep_id = state.active_episode_id
    assert ep_id is not None
    before = len(state.issue_episodes[ep_id].mentions)

    correction_quote = "я же говорил, живот болит"
    ingest_rich_turn(
        state,
        build_rich_turn_from_payload(
            SemanticPayload(
                dialogue_act="correction",
                control="none",
                consent_answer="not_applicable",
                answers_pending_question=False,
                needs_clarification=False,
                issue_mentions=(
                    mention.model_copy(
                        update={
                            "mention_id": "im-2",
                            "evidence": Evidence(
                                start=correction_quote.find("живот"),
                                end=correction_quote.find("живот") + len("живот болит"),
                                quote="живот болит",
                            ),
                        }
                    ),
                ),
            ),
            utterance_id="u-2",
            raw_text=correction_quote,
        ),
    )
    after = len(state.issue_episodes[ep_id].mentions)
    assert after == before + 1
