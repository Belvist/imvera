"""Speech variety: greeting/questions/acks rotate, canonical pinned by day.

Same day = same phrasing (redials consistent, differential/corpus stable).
New day = new phrasing. pool[0] is always canonical — tests pin
IMVERA_SPEECH_DAY to a multiple of the pool size for byte-identical asserts.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.dialogue_engine


def test_day_zero_yields_canonical(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.dialogue_engine import questions

    monkeypatch.setenv("IMVERA_SPEECH_DAY", "102")  # 102 % 6 == 0
    assert questions.slot_question("wellness") == "Как вы себя чувствуете?"
    assert questions.slot_question("mood") == "А какое у вас сегодня настроение?"
    assert questions.slot_question("sleep") == "Как вы спали?"
    assert questions.probe_question("concern") == "Что именно беспокоит?"
    # The ITS transition acknowledgement is its own field now: the canonical
    # question no longer carries it and the renderer composes the surface.
    its_ack, its_question = questions.its_question_and_ack()
    assert its_ack == "Поняла вас."
    assert its_question == "А кроме этого — по самочувствию ничего не тревожит?"
    assert questions.important_to_share_question() == its_question


def test_rotation_varies_by_day(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.dialogue_engine import questions

    seen = set()
    for day in ("102", "103", "104"):
        monkeypatch.setenv("IMVERA_SPEECH_DAY", day)
        seen.add(questions.slot_question("wellness"))
        seen.add(questions.important_to_share_question())
    assert len(seen) >= 4, seen


def test_greeting_has_brand_name_and_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from packages.dialogue_engine import questions

    for day in ("102", "103", "104"):
        monkeypatch.setenv("IMVERA_SPEECH_DAY", day)
        g = questions.opening_speech("Даниил")
        assert "Амвера" in g and "Даниил" in g and g.rstrip().endswith("?")
        assert ". Даниил," in g


def test_greeting_prior_followup_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.dialogue_engine import questions

    monkeypatch.setenv("IMVERA_SPEECH_DAY", "103")
    g = questions.opening_speech("Даниил", {"wellness_concern": "голова болит"})
    assert "голов" in g.lower()


def test_bare_ack_rotates_no_immediate_repeat() -> None:
    from types import SimpleNamespace

    from packages.dialogue_engine.conversation_policy import (
        _grounded_ack_for_mentions,
    )

    acks = {
        _grounded_ack_for_mentions(
            SimpleNamespace(
                issue_mentions=[
                    SimpleNamespace(label="болеть", body_site="", role="primary")
                ],
                utterance_id=f"u-{i}",
            )
        )
        for i in (3, 4)
    }
    assert len(acks) == 2, acks


def test_bridge_ack_fresh_episode_stays_canonical() -> None:
    from types import SimpleNamespace

    from packages.dialogue_engine.conversation_policy import _bridge_ack_for_episode

    ep = SimpleNamespace(body_site=None, primary_label="болит", kind="symptom")
    assert _bridge_ack_for_episode(ep) == "Хорошо."


def test_phrase_banks_have_depth() -> None:
    from packages.dialogue_engine import questions

    for slot, pool in questions._SLOT_QUESTION_VARIANTS.items():
        assert len(pool) >= 6, (slot, len(pool))
        assert len(set(pool)) == len(pool), f"dupes in {slot}"
    for phase, pool in questions._PROBE_QUESTION_VARIANTS.items():
        assert len(pool) >= 6, (phase, len(pool))
        assert len(set(pool)) == len(pool), f"dupes in {phase}"
    assert len(questions._ITS_QUESTION_VARIANTS) >= 6
    assert len(set(questions._ITS_QUESTION_VARIANTS)) == len(
        questions._ITS_QUESTION_VARIANTS
    )
