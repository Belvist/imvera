"""False-world frames must not open speaker pain ISSUE_SITE (map
docs/plans/Understand-false-worlds.md).

third-party / past-resolved / joke-hyperbole / side-chatter share one
Understand layer (suppress + SIDE_TOPIC), mirroring the dream/film
design — never phrase banks.
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine.check_path import (
    is_joke_hyperbole_frame,
    is_other_person_health_frame,
    is_past_noncurrent_frame,
    is_side_topic_chatter,
    suppress_health_issues_for_non_complaint_frame,
)
from packages.dialogue_engine.effects import SpeakEffect
from packages.dialogue_engine.events import CallStarted, User
from packages.dialogue_engine.issue_mention_extract import extract_issue_mentions
from packages.dialogue_engine.protocol.acts import normalize_act
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.semantic_kernel.kernel import interpret, kernel_to_rich_turn
from packages.dialogue_engine.state import EngineState

pytestmark = pytest.mark.dialogue_engine


def _fresh_state() -> EngineState:
    return EngineState(call_id="t", elder_display_name="T")


def _speeches(res) -> list[str]:
    return [e.text for e in res.speak_effects if isinstance(e, SpeakEffect)]


def _no_pain_probes(speeches: list[str]) -> None:
    joined = " ".join(speeches).lower()
    assert "когда появилась" not in joined
    assert "когда начала" not in joined
    assert "насколько сильная боль" not in joined


def _run_script(call_id: str, turns: list[str]):
    r = ScenarioRunner(call_id=call_id, elder_display_name="Тамара Юрьевна")
    r.run([CallStarted()])
    out = []
    for i, u in enumerate(turns):
        kr = interpret(u, utterance_id=f"u-{i}", engine_state=r.state)
        rich = kernel_to_rich_turn(kr)
        out.append(r.run([User(text=u, rich_turn=rich)]))
    return r, out


def test_third_party_helpers_and_act() -> None:
    for text in ("У внука голова болит сильно.", "У мужа голова болит."):
        assert is_other_person_health_frame(text)
        assert suppress_health_issues_for_non_complaint_frame(text)
        assert not extract_issue_mentions(text)
        assert normalize_act(_fresh_state(), text) == "SIDE_TOPIC"


def test_third_party_pain_no_onset_probe_no_episode() -> None:
    r, out = _run_script("third-party", ["У внука голова болит сильно."])
    _no_pain_probes(_speeches(out[-1]))
    assert "зафиксировала" not in " ".join(_speeches(out[-1])).lower()
    assert r.state.active_episode_id is None
    assert not (r.state.wellness_concern or "").strip()
    assert getattr(r.state, "last_protocol_act", None) == "SIDE_TOPIC"


def test_past_resolved_helpers_and_act() -> None:
    text = "Раньше болела голова, сейчас всё хорошо."
    assert is_past_noncurrent_frame(text)
    assert suppress_health_issues_for_non_complaint_frame(text)
    assert not extract_issue_mentions(text)
    assert normalize_act(_fresh_state(), text) == "SIDE_TOPIC"


def test_past_resolved_no_issue_no_summary_claim() -> None:
    r, out = _run_script(
        "past-resolved",
        ["Раньше болела голова, сейчас всё хорошо.", "Нет, ничего важного.", "Пока."],
    )
    joined = " ".join(s for res in out for s in _speeches(res)).lower()
    _no_pain_probes([joined])
    assert "сегодня беспокоили" not in joined
    assert not (r.state.wellness_concern or "").strip()
    assert getattr(r.state, "last_protocol_act", None) in ("SIDE_TOPIC", "DECLINE", None)


def test_joke_hyperbole_helpers_and_act() -> None:
    for text in ("умру от смеха", "шучу конечно, голова не болит"):
        assert is_joke_hyperbole_frame(text)
        assert suppress_health_issues_for_non_complaint_frame(text)
        assert not extract_issue_mentions(text)
    # Priority law: DECLINE > SIDE_TOPIC > ISSUE_SITE. Pure joke is SIDE_TOPIC;
    # an explicit denial ("голова не болит") is DECLINE and outranks the joke.
    assert normalize_act(_fresh_state(), "умру от смеха") == "SIDE_TOPIC"
    assert normalize_act(_fresh_state(), "шучу конечно, голова не болит") == "DECLINE"


def test_joke_death_no_red_no_onset() -> None:
    r, out = _run_script("joke", ["умру от смеха"])
    joined = " ".join(_speeches(out[-1])).lower()
    _no_pain_probes([joined])
    assert "передам" not in joined and "скорую" not in joined
    assert r.state.safety_mode != "red"


def test_side_chatter_helpers_and_act() -> None:
    text = "Суп вкусный, борщ варила."
    assert is_side_topic_chatter(text)
    assert not extract_issue_mentions(text)
    assert normalize_act(_fresh_state(), text) == "SIDE_TOPIC"


def test_side_chatter_no_concern_no_probe() -> None:
    r, out = _run_script("chatter", ["Суп вкусный, борщ варила."])
    assert not (r.state.wellness_concern or "").strip()
    intents = [
        e.intent or ""
        for res in out
        for e in res.speak_effects
        if isinstance(e, SpeakEffect)
    ]
    assert not any("onset" in i for i in intents)


def test_novel_wordings_same_frame_no_new_code() -> None:
    """System criterion: new wordings of the same frames pass untouched."""
    for text, helper in [
        ("У племянника температура.", is_other_person_health_frame),
        ("Позавчера болело, сегодня норм.", is_past_noncurrent_frame),
        ("Прикалываюсь, всё хорошо.", is_joke_hyperbole_frame),
    ]:
        assert helper(text), text
        assert suppress_health_issues_for_non_complaint_frame(text), text
        assert not extract_issue_mentions(text), text


def test_speaker_pivot_still_issue() -> None:
    assert not suppress_health_issues_for_non_complaint_frame(
        "После фильма голова разболелась."
    )
    assert not suppress_health_issues_for_non_complaint_frame(
        "у мужа плохо, а у меня голова болит"
    )
    assert (
        normalize_act(_fresh_state(), "После фильма голова разболелась.")
        == "ISSUE_SITE"
    )
    assert (
        normalize_act(_fresh_state(), "у мужа плохо, а у меня голова болит")
        == "ISSUE_SITE"
    )


def test_speaker_pivot_after_other_opens_episode_and_probes() -> None:
    """Helper-level SIDE_TOPIC is not enough: the speaker clause must
    actually open a site episode and ask the onset probe (Layer A)."""
    r, out = _run_script("fw-pivot", ["Всё хорошо.", "у мужа плохо, а у меня голова болит"])
    assert r.state.active_episode_id is not None
    assert not (r.state.wellness_concern or "").strip() or r.state.active_episode_id
    intents = [
        e.intent or ""
        for e in out[-1].speak_effects
        if isinstance(e, SpeakEffect)
    ]
    assert any("duration" in i or "onset" in i for i in intents)
