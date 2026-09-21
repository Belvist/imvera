"""Live-call regressions from fs-1b34dc2b (user heard, analyzed turn by turn).

1. Multi-symptom utterance keeps ALL issues (was: 1 of 4).
2. Bare-verb labels never render as "Про болит" questions.
3. Onset answers ("Сегодня.") land in the episode and advance.
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine.effects import SpeakEffect
from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.semantic import SemanticAct, SemanticTurn
from packages.dialogue_engine.state import Question, QuestionPhase

pytestmark = pytest.mark.dialogue_engine

LIVE_COMPLAINT = (
    "Ой, Вер, не знаю, как сказать. И тошнит, и жопа болит, "
    "и голова, и всё-всё-всё болит у меня, всё тело ломит."
)


def test_live_complaint_keeps_all_issues() -> None:
    from packages.dialogue_engine.issue_mention_extract import (
        extract_issue_mentions,
    )

    labels = {m.label for m in extract_issue_mentions(LIVE_COMPLAINT)}
    assert "тошнота" in labels
    assert "боль в ягодицах" in labels
    assert "головная боль" in labels
    assert "ломота в теле" in labels


def test_no_false_issue_on_pill_phrase() -> None:
    from packages.dialogue_engine.issue_mention_extract import (
        extract_issue_mentions,
    )

    assert extract_issue_mentions("Таблетки от головы выпила утром.") == ()


def test_negation_splits_status() -> None:
    from packages.dialogue_engine.issue_mention_extract import (
        extract_issue_mentions,
    )

    mentions = {
        m.label: m.status
        for m in extract_issue_mentions("Голова не болит, а живот болит.")
    }
    assert mentions.get("головная боль") == "resolved"
    assert mentions.get("боль в животе") == "active"


def test_bare_verb_never_renders_topic_question() -> None:
    from types import SimpleNamespace

    from packages.dialogue_engine.conversation_policy import _bridge_ack_for_episode

    ep = SimpleNamespace(body_site=None, primary_label="болит", kind="symptom")
    assert _bridge_ack_for_episode(ep) == "Хорошо."
    ep2 = SimpleNamespace(body_site="голова", primary_label="болит", kind="symptom")
    assert _bridge_ack_for_episode(ep2) == "Хорошо."


def test_onset_answer_lands_and_advances() -> None:
    engine = DialogueEngine(call_id="onset-live", elder_display_name="Тест")
    engine.start()
    engine.state.delivered_question = Question(
        question_id="q1",
        slot="onset",
        text="Когда это началось?",
        phase=QuestionPhase.DELIVERED,
        intent="ask_onset",
        goal_id="onset",
    )
    sem = SemanticTurn(
        act=SemanticAct.ANSWER,
        target_slot="onset",
        confidence=0.9,
        source_quote="Сегодня.",
        value="Сегодня.",
    )
    effects = engine.on_user_turn("t1", "Сегодня.", sem)
    assert engine.state.delivered_question is None
    intents = [e.intent for e in effects if isinstance(e, SpeakEffect)]
    assert intents, "onset answer must advance, not stall"
    assert not any("onset" in intent for intent in intents), intents
