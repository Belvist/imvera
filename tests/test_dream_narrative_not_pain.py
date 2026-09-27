"""Dream/narrative body mention must not open pain ISSUE_SITE (fs-80cf029f).

Live: sleep answer «Сталина во сне… руку тянул» → false «Когда появилась эта боль».
Same class as movie_dying: fiction ≠ elder complaint. Fix is Understand/acts
(SIDE_TOPIC + suppress issue mentions), not phrase banks.
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine.check_path import (
    is_narrative_fiction_frame,
    suppress_health_issues_for_narrative_frame,
)
from packages.dialogue_engine.effects import SpeakEffect
from packages.dialogue_engine.events import CallStarted, User
from packages.dialogue_engine.issue_mention_extract import extract_issue_mentions
from packages.dialogue_engine.protocol.acts import normalize_act
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.semantic_kernel.kernel import interpret, kernel_to_rich_turn
from packages.dialogue_engine.state import EngineState

pytestmark = pytest.mark.dialogue_engine

DREAM_STALIN = (
    "Великолепно спала. О, Сталина видела! Сталина во сне видела. "
    "Приходил ко мне руку тянул."
)


@pytest.fixture(autouse=True)
def _ladder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "1")


def test_dream_frame_helpers() -> None:
    assert is_narrative_fiction_frame(DREAM_STALIN)
    assert suppress_health_issues_for_narrative_frame(DREAM_STALIN)
    assert not extract_issue_mentions(DREAM_STALIN)
    assert normalize_act(EngineState(call_id="t", elder_display_name="T"), DREAM_STALIN) == (
        "SIDE_TOPIC"
    )


def test_film_dying_is_side_topic_not_issue() -> None:
    text = "Смотрела фильм, там все умирали."
    assert suppress_health_issues_for_narrative_frame(text)
    assert not extract_issue_mentions(text)
    assert normalize_act(EngineState(call_id="t", elder_display_name="T"), text) == (
        "SIDE_TOPIC"
    )


def test_real_complaint_after_film_still_issue() -> None:
    text = "После фильма голова разболелась."
    assert is_narrative_fiction_frame(text)
    assert not suppress_health_issues_for_narrative_frame(text)
    assert extract_issue_mentions(text)
    assert normalize_act(EngineState(call_id="t", elder_display_name="T"), text) == (
        "ISSUE_SITE"
    )


def test_kernel_dream_has_no_issue_mentions() -> None:
    kr = interpret(DREAM_STALIN, utterance_id="u-dream", answer_slot="sleep")
    rich = kernel_to_rich_turn(kr)
    assert kr.observations == ()
    assert rich.issue_mentions == ()


def test_sleep_dream_turn_no_pain_onset_probe() -> None:
    """Layer A: exact fs-80cf029f sleep turn must not open pain onset."""
    r = ScenarioRunner(call_id="dream-stalin", elder_display_name="Тамара Юрьевна")
    r.run([CallStarted()])
    for u in (
        "Нормально, всё хорошо.",
        "Ничего не беспокоит.",
        "Поела нормально.",
        "Лекарств нет.",
    ):
        r.run([u])
    assert "sleep" in (r.state.answer_context_slot() or "") or (
        r.state.delivered_question
        and "sleep" in (r.state.delivered_question.intent or "")
    )

    kr = interpret(
        DREAM_STALIN,
        utterance_id="u-dream",
        answer_slot="sleep",
        engine_state=r.state,
    )
    rich = kernel_to_rich_turn(kr)
    res = r.run([User(text=DREAM_STALIN, rich_turn=rich)])
    speeches = [
        e.text for e in res.speak_effects if isinstance(e, SpeakEffect)
    ]
    joined = " ".join(speeches).lower()
    assert "боль" not in joined
    assert "когда появилась" not in joined
    assert "зафиксировала" not in joined or "рука" not in joined
    assert r.state.active_episode_id is None
    assert not (r.state.wellness_concern or "").strip()
    assert getattr(r.state, "last_protocol_act", None) == "SIDE_TOPIC"
    assert not any(
        "onset" in (e.intent or "")
        for e in res.speak_effects
        if isinstance(e, SpeakEffect)
    )


def test_summary_must_not_claim_hand_pain_from_dream() -> None:
    r = ScenarioRunner(call_id="dream-summary", elder_display_name="Тамара Юрьевна")
    r.run([CallStarted()])
    for u in (
        "Нормально, всё хорошо.",
        "Ничего не беспокоит.",
        "Поела нормально.",
        "Лекарств нет.",
        DREAM_STALIN,
        "Нет, ничего важного.",
        "Пока.",
    ):
        kr = interpret(u, utterance_id=f"u-{hash(u) & 0xFFFF}", engine_state=r.state)
        rich = kernel_to_rich_turn(kr)
        res = r.run([User(text=u, rich_turn=rich)])
        for e in res.speak_effects:
            if isinstance(e, SpeakEffect):
                low = (e.text or "").lower()
                assert "рука тянул" not in low
                assert "беспокоили рука" not in low
