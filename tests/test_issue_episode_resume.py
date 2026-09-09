"""IssueEpisode resume after topic flow — generic issues, not TopicFamily."""

from __future__ import annotations

import pytest

from packages.contracts.enums import SlotStatus
from packages.contracts.semantic import Evidence, IssueMention, SemanticPayload
from packages.dialogue_engine.events import CallStarted, User
from packages.dialogue_engine.issue_memory import ingest_rich_turn
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.state import EngineState
from packages.dialogue_engine.turn_understanding import build_rich_turn_from_payload

pytestmark = pytest.mark.dialogue_engine


def _mention(label: str, quote: str, *, body_site: str | None = None) -> IssueMention:
    return IssueMention(
        mention_id="im-test",
        kind="symptom",
        label=label,
        role="primary",
        body_site=body_site,
        temporal_scope="now",
        status="active",
        evidence=Evidence(
            start=0,
            end=len(quote),
            quote=quote,
        ),
    )


def _mention_in(text: str, label: str, quote: str, *, body_site: str | None = None) -> IssueMention:
    start = text.lower().find(quote.lower())
    if start < 0:
        start = 0
    return IssueMention(
        mention_id="im-test",
        kind="symptom",
        label=label,
        role="primary",
        body_site=body_site,
        temporal_scope="now",
        status="active",
        evidence=Evidence(start=start, end=start + len(quote), quote=quote),
    )


def test_pending_attribute_stays_on_original_episode() -> None:
    state = EngineState(call_id="t", elder_display_name="Тест")
    headache = _mention("головная боль", "Голова болит", body_site="голова")
    ingest_rich_turn(
        state,
        build_rich_turn_from_payload(
            SemanticPayload(
                dialogue_act="answer",
                control="none",
                consent_answer="not_applicable",
                answers_pending_question=False,
                needs_clarification=False,
                issue_mentions=(headache,),
            ),
            utterance_id="u-1",
            raw_text="Голова болит.",
        ),
    )
    headache_id = state.active_episode_id
    assert headache_id is not None
    state.pending_episode_attribute = "onset"

    quote = "Не знаю, но ещё грудь давит."
    chest = _mention_in(quote, "давление в груди", "грудь давит", body_site="грудь")
    ingest_rich_turn(
        state,
        build_rich_turn_from_payload(
            SemanticPayload(
                dialogue_act="answer",
                control="none",
                consent_answer="not_applicable",
                answers_pending_question=True,
                needs_clarification=False,
                issue_mentions=(chest,),
            ),
            utterance_id="u-2",
            raw_text=quote,
        ),
    )

    headache_ep = state.issue_episodes[headache_id]
    chest_ep = next(
        ep for ep_id, ep in state.issue_episodes.items() if ep_id != headache_id
    )
    assert headache_ep.known_attributes.get("onset") == quote
    assert chest_ep.known_attributes.get("onset") is None


def test_resume_generic_throat_episode_after_sleep_topic() -> None:
    runner = ScenarioRunner(call_id="throat", elder_display_name="Тест")
    runner.run([CallStarted(), "Плохо спал."])

    quote = "Проснулся в четыре, и ещё першит горло."
    throat = _mention_in(quote, "першение в горле", "першит горло", body_site="горло")
    payload = SemanticPayload(
        dialogue_act="answer",
        control="none",
        consent_answer="not_applicable",
        answers_pending_question=True,
        needs_clarification=False,
        issue_mentions=(throat,),
    )
    result = runner.run(
        [
            User(
                text=quote,
                rich_turn=build_rich_turn_from_payload(
                    payload,
                    utterance_id="u-2",
                    raw_text=quote,
                ),
            )
        ]
    )
    assert any("горл" in ep.primary_label.lower() for ep in result.state.issue_episodes.values())
    assert result.state.pending_episode_ids

    result = runner.run(["Усталость есть."])
    intents = [e.intent for e in result.speak_effects]
    texts = " ".join(e.text.lower() for e in result.speak_effects)
    assert result.state.slots["sleep"] == SlotStatus.FILLED
    assert "check_mood" not in intents
    assert "настроен" not in texts
    assert any(
        i.startswith("episode_") and "onset" in i for i in intents
    ) or "горл" in texts
