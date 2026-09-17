"""Issue episode memory ingest."""

from __future__ import annotations

import pytest

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


@pytest.mark.parametrize("ladder", ["0", "1"])
@pytest.mark.parametrize("attribute", ["onset", "duration"])
@pytest.mark.parametrize("current", [None, "active", "resolved"])
def test_temporal_answer_does_not_invent_current(monkeypatch, ladder, attribute, current) -> None:
    from packages.dialogue_engine.state import IssueEpisode

    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", ladder)
    ep = IssueEpisode(
        episode_id="headache", primary_label="головная боль", kind="symptom",
        body_site="голова", subject="speaker",
        known_attributes={} if current is None else {"current": current},
    )
    state = EngineState(
        call_id="temporal-only", issue_episodes={ep.episode_id: ep},
        active_episode_id=ep.episode_id, pending_episode_attribute=attribute,
    )
    text = "С 10 утра"
    ingest_rich_turn(
        state,
        build_rich_turn_from_payload(
            _payload_answer(text), utterance_id="u-temporal", raw_text=text,
        ),
    )
    ep = state.issue_episodes[ep.episode_id]
    assert ep.known_attributes[attribute] == text
    assert ep.known_attributes.get("current") == current
    assert state.pending_episode_attribute is None
    if current is None:
        assert ep.status == "open"


@pytest.mark.parametrize("ladder", ["0", "1"])
def test_runtime_temporal_only_keeps_current_unresolved(monkeypatch, ladder) -> None:
    from packages.dialogue_engine.effects import SpeakEffect
    from packages.dialogue_engine.engine import DialogueEngine
    from packages.dialogue_engine.semantic_kernel.kernel import interpret, kernel_to_rich_turn

    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", ladder)
    engine = DialogueEngine(call_id="temporal-runtime")

    def deliver(effects):
        speaks = [effect for effect in effects if isinstance(effect, SpeakEffect)]
        for effect in speaks:
            engine.on_playout_started(effect.generation, effect.question_id)
            engine.on_playout_completed(effect.generation, effect.question_id)
        return speaks

    def reply(text):
        slot = engine.answer_context_slot()
        uid = f"u-{engine.state.revision}"
        parsed = interpret(text, utterance_id=uid, engine_state=engine.state, answer_slot=slot)
        turn = kernel_to_rich_turn(parsed, answer_slot=slot, engine_state=engine.state)
        return deliver(engine.on_user_turn(uid, text, rich_turn=turn))

    deliver(engine.start())
    reply("Меня знобит.")
    ep_id = engine.state.active_episode_id
    assert ep_id is not None
    assert engine.state.pending_episode_attribute == "onset"
    ep_before = engine.state.issue_episodes[ep_id]
    current_before = ep_before.known_attributes.get("current")
    speaks = reply("С 10 утра")
    ep = engine.state.issue_episodes[ep_id]
    assert ep.known_attributes["onset"] == "С 10 утра"
    assert ep.known_attributes.get("current") == current_before
    assert speaks
    assert not engine.state.call_closed


@pytest.mark.parametrize("text, current", [("Ещё болит.", "active"), ("Уже не болит.", "resolved")])
def test_explicit_current_answer_remains_grounded(text, current) -> None:
    from packages.dialogue_engine.state import IssueEpisode

    ep = IssueEpisode(
        episode_id="headache", primary_label="головная боль", kind="symptom",
        body_site="голова", subject="speaker", known_attributes={"onset": "С утра"},
    )
    state = EngineState(
        call_id="explicit-current", issue_episodes={ep.episode_id: ep},
        active_episode_id=ep.episode_id, pending_episode_attribute="current",
    )
    ingest_rich_turn(
        state,
        build_rich_turn_from_payload(
            _payload_answer(text), utterance_id="u-current", raw_text=text,
        ),
    )
    assert state.issue_episodes[ep.episode_id].known_attributes["current"] == current
