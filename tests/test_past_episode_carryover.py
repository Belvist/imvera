"""Cross-call episode carryover — the past survives the call (ADR-023 slice).

Write: build_call_metadata projects up to 6 grounded speaker episodes as
`past_episodes` (string-only, snapshot contract intact).
Read: prior_followup_question speaks from the digest when the old keys
are absent; mid-call a grounded mention matching the digest marks
`past_episode_reopened` instead of interrogating a returning complaint
as brand new. Past alone never fires (corroboration only).
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine.check_path import (
    build_call_metadata,
    episode_digest,
    past_site_matches,
    prior_followup_question,
)
from packages.dialogue_engine.conversation_policy import (
    TurnContext,
    schedule_next_action,
)
from packages.dialogue_engine.issue_memory import ingest_rich_turn
from packages.dialogue_engine.state import EngineState, IssueEpisode
from packages.dialogue_engine.turn_understanding import build_rich_turn_from_text

pytestmark = pytest.mark.dialogue_engine


def _ep(
    episode_id: str,
    label: str,
    *,
    site: str | None = None,
    subject: str = "speaker",
    status: str = "open",
) -> IssueEpisode:
    return IssueEpisode(
        episode_id=episode_id,
        primary_label=label,
        kind="pain",
        body_site=site,
        subject=subject,
        status=status,  # type: ignore[arg-type]
    )


def _state_with(*eps: IssueEpisode) -> EngineState:
    state = EngineState(call_id="t-carry")
    for ep in eps:
        state.issue_episodes[ep.episode_id] = ep
    return state


def test_digest_carries_two_speaker_episodes() -> None:
    state = _state_with(
        _ep("e1", "головная боль", site="голова"),
        _ep("e2", "боль в животе", site="живот", status="resolved"),
    )
    digest = episode_digest(state)
    assert "головная боль@голова:open" in digest
    assert "боль в животе@живот:resolved" in digest
    assert build_call_metadata(state)["past_episodes"] == digest


def test_digest_skips_other_person_and_bare_verbs() -> None:
    state = _state_with(
        _ep("e1", "болит", site=None),
        _ep("e2", "голова болит у мужа", site="голова", subject="other_person"),
        _ep("e3", "боль в спине", site="спина"),
    )
    digest = episode_digest(state)
    assert digest == "боль в спине@спина:open"


def test_digest_empty_without_episodes() -> None:
    state = EngineState(call_id="t-empty")
    assert episode_digest(state) == ""
    assert "past_episodes" not in build_call_metadata(state)


def test_followup_speaks_from_digest_when_old_keys_absent() -> None:
    q = prior_followup_question(
        {"past_episodes": "головная боль@голова:resolved"}
    )
    assert q is not None
    assert "головной боли" in q


def test_followup_old_keys_still_win() -> None:
    q = prior_followup_question(
        {
            "wellness_concern": "болела голова",
            "past_episodes": "боль в животе@живот:open",
        }
    )
    assert q is not None
    assert "головной боли" in q


def test_followup_malformed_digest_is_silent() -> None:
    assert prior_followup_question({"past_episodes": "|||"}) is None
    assert prior_followup_question({}) is None


def test_past_site_matches_by_site_and_label() -> None:
    prior = {"past_episodes": "головная боль@голова:resolved"}
    assert (
        past_site_matches(prior, sites={"голова"}, labels=["голова болит"])
        == "головная боль"
    )
    assert past_site_matches(prior, sites={"живот"}, labels=["живот болит"]) is None
    assert past_site_matches({}, sites={"голова"}, labels=["голова болит"]) is None
    assert past_site_matches(prior, sites=set(), labels=[]) is None


def test_midcall_reopened_mark_on_returning_complaint() -> None:
    state = EngineState(call_id="t-reopen")
    state.prior_call_context = {"past_episodes": "головная боль@голова:resolved"}
    turn = build_rich_turn_from_text("Голова болит.", utterance_id="u-1")
    assert turn.issue_mentions
    ingest_rich_turn(state, turn)
    schedule_next_action(state, TurnContext(turn=turn, user_text=turn.raw_text))
    assert state.observations.get("past_episode_reopened") == "головная боль"


def test_midcall_no_mark_without_prior() -> None:
    state = EngineState(call_id="t-fresh")
    turn = build_rich_turn_from_text("Голова болит.", utterance_id="u-1")
    assert turn.issue_mentions
    ingest_rich_turn(state, turn)
    schedule_next_action(state, TurnContext(turn=turn, user_text=turn.raw_text))
    assert "past_episode_reopened" not in state.observations
