"""False-world frames must not open speaker pain ISSUE_SITE (map:
docs/plans/Understand-false-worlds.md).

Third-party illness, past-resolved pain, joke/hyperbole and off-protocol
side chatter are Understand frames, not complaints. Fix is SIDE_TOPIC +
suppress (mirror dream/film), never phrase banks. Real speaker pivots
("а сейчас у меня болит", mixed subjects) must still reach ISSUE_SITE.
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
from packages.dialogue_engine.issue_mention_extract import extract_issue_mentions
from packages.dialogue_engine.protocol.acts import normalize_act
from packages.dialogue_engine.state import EngineState

pytestmark = pytest.mark.dialogue_engine


def _state() -> EngineState:
    return EngineState(call_id="t", elder_display_name="T")


def test_third_party_pain_suppressed() -> None:
    for text in ("У внука голова болит сильно.", "У мужа голова болит."):
        assert is_other_person_health_frame(text), text
        assert suppress_health_issues_for_non_complaint_frame(text), text
        assert not extract_issue_mentions(text), text
        assert normalize_act(_state(), text) == "SIDE_TOPIC", text


def test_novel_relative_same_frame_no_new_code() -> None:
    # Criterion «система, не затычка»: another kin, same frame, no patch.
    for text in ("У племянницы живот болит.", "У зятя спина болит."):
        assert suppress_health_issues_for_non_complaint_frame(text), text
        assert not extract_issue_mentions(text), text
        assert normalize_act(_state(), text) == "SIDE_TOPIC", text


def test_mixed_subjects_keep_speaker_site() -> None:
    text = "у мужа плохо, а у меня голова болит"
    assert not suppress_health_issues_for_non_complaint_frame(text), text
    mentions = extract_issue_mentions(text)
    assert [(m.label, m.body_site) for m in mentions] == [
        ("головная боль", "голова")
    ], mentions
    assert normalize_act(_state(), text) == "ISSUE_SITE", text


def test_past_resolved_not_issue() -> None:
    text = "Раньше болела голова, сейчас всё хорошо."
    assert is_past_noncurrent_frame(text), text
    assert suppress_health_issues_for_non_complaint_frame(text), text
    assert not extract_issue_mentions(text), text
    assert normalize_act(_state(), text) == "SIDE_TOPIC", text


def test_past_only_keeps_grounding() -> None:
    """A past marker alone is NOT a false world.

    «Раньше болело.» / «Со вчера головная боль.» / «Вчера ухо заложило.»
    stay recorded symptoms: grounding outranks the past frame, and the
    onset probe is the useful next question. Pinned by
    tests/test_live_path_simplification.py and
    tests/test_surface_label_canonical.py.
    """
    for text in (
        "Раньше болело.",
        "Со вчера головная боль.",
        "Вчера ухо заложило.",
        "Живот болел вчера.",
    ):
        assert not is_past_noncurrent_frame(text), text
        assert not suppress_health_issues_for_non_complaint_frame(text), text


def test_novel_past_wording_same_frame() -> None:
    text = "позавчера болело, сегодня норм"
    assert suppress_health_issues_for_non_complaint_frame(text), text
    assert not extract_issue_mentions(text), text
    assert normalize_act(_state(), text) == "SIDE_TOPIC", text


def test_present_pivot_after_past_still_issue() -> None:
    for text in ("После фильма голова разболелась.", "а сейчас у меня болит"):
        assert not suppress_health_issues_for_non_complaint_frame(text), text
        assert normalize_act(_state(), text) == "ISSUE_SITE", text


def test_joke_hyperbole_no_red_frame() -> None:
    for text in ("умру от смеха", "шучу конечно, голова не болит"):
        assert is_joke_hyperbole_frame(text), text
        assert suppress_health_issues_for_non_complaint_frame(text), text
        assert not extract_issue_mentions(text), text
    # Pure joke → SIDE_TOPIC; joke + explicit denial → DECLINE (priority:
    # DECLINE first — denial forbids probes, equally safe direction).
    assert normalize_act(_state(), "умру от смеха") == "SIDE_TOPIC"
    assert normalize_act(_state(), "шучу конечно, голова не болит") == "DECLINE"


def test_novel_joke_wording_same_frame() -> None:
    text = "прикалываюсь"
    assert suppress_health_issues_for_non_complaint_frame(text), text
    assert not extract_issue_mentions(text), text
    assert normalize_act(_state(), text) == "SIDE_TOPIC", text
    # Joke + explicit all-good → DECLINE wins per priority (denial forbids
    # probes, same safe direction as SIDE_TOPIC here).
    assert normalize_act(_state(), "прикалываюсь, всё хорошо") == "DECLINE"


def test_side_chatter_marked_not_silent() -> None:
    text = "Суп вкусный, борщ варила."
    assert is_side_topic_chatter(text), text
    assert normalize_act(_state(), text) == "SIDE_TOPIC", text
