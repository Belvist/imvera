"""Meaning-driven realization: Vera reflects the person's own words.

Contracts under test:

* the reaction is composed from grounded content only — no invented fact;
* it abstains (empty) whenever morphology is uncertain or nothing was said;
* a content-free acknowledgement is replaced, a meaningful one is kept;
* safety/control/urgent surfaces never pass through the composer;
* the composed surface stays one move: reaction + question, never standalone;
* exact repeats are refused through the existing speech ledger.
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine import realization
from packages.dialogue_engine.response_plan import ResponsePlan, composed_text, render_response_plan
from packages.dialogue_engine.state import EngineState

pytestmark = pytest.mark.dialogue_engine


def _state(text: str = "", **kwargs) -> EngineState:
    state = EngineState(call_id="realization-test")
    state.last_user_text = text
    for key, value in kwargs.items():
        setattr(state, key, value)
    return state


# --------------------------------------------------------------- topic picking


def test_topic_comes_from_the_persons_own_noun():
    topic = realization.heard_topic("Внуки-то приезжают, слава богу, в воскресенье были.")
    assert topic is not None
    assert topic.noun == "внук"          # particle stripped, normal form
    assert topic.acc == "внуков"          # inflected for «про …»
    assert topic.quote.startswith("Внуки-то")


def test_no_topic_is_invented_from_a_backchannel_or_a_question():
    for text in ("Хорошо.", "Спасибо.", "Ага.", "А вы кто вообще?", "Да."):
        assert realization.heard_topic(text) is None


def test_time_words_are_not_reflected_as_topics():
    for text in ("Со вчерашнего вечера, наверное.", "Сегодня уже нормально.", "Вечером."):
        assert realization.heard_topic(text) is None


def test_verb_only_answer_has_no_topic():
    assert realization.heard_topic("Да, сегодня уже нормально поел.") is None


# ------------------------------------------------------------------ composing


def test_reaction_uses_the_persons_word():
    clause = realization.reaction_clause(_state("Голова побаливает иногда."))
    assert clause.startswith("Про голов")
    assert "голов" in clause.lower()


def test_reaction_abstains_when_nothing_can_be_grounded():
    assert realization.reaction_clause(_state("Хорошо.")) == ""
    assert realization.reaction_clause(_state("")) == ""


def test_same_topic_is_not_parroted_twice_in_a_row():
    state = _state("Внуки приезжают.")
    first = realization.reaction_clause(state)
    assert first
    state.spoken_surfaces = [first.lower().replace(".", "")]
    assert realization.reaction_clause(state) == ""


def test_answered_domain_gives_a_reaction_without_a_noun():
    from packages.dialogue_engine.context import SlotValue

    state = _state("Да, поел.")
    state.slot_records["nutrition"] = SlotValue(
        value="поел", source_text="Да, поел.", polarity="positive"
    )
    clause = realization.reaction_clause(state, ["nutrition"])
    assert clause == "Хорошо, что поели."


def test_domain_reaction_respects_negative_polarity():
    from packages.dialogue_engine.context import SlotValue

    state = _state("Не поел сегодня.")
    state.slot_records["nutrition"] = SlotValue(
        value="не поел", source_text="Не поел сегодня.", polarity="negative"
    )
    clause = realization.reaction_clause(state, ["nutrition"])
    assert clause == "Понимаю, что поесть не получилось."


# ------------------------------------------------------------------ wiring in


def test_content_free_ack_is_replaced_by_the_reaction():
    state = _state("Голова побаливает.")
    plan = ResponsePlan(action="speak", acknowledge="Хорошо.",
                        mandatory_question="Что ещё беспокоит?")
    rendered = render_response_plan(plan, state)
    assert rendered.acknowledge.startswith("Про голов")
    assert rendered.mandatory_question == "Что ещё беспокоит?"
    assert composed_text(rendered) == f"{rendered.acknowledge} Что ещё беспокоит?"


def test_meaningful_acknowledgement_is_kept():
    state = _state("Терпимо.")
    meaningful = "Поняла, сейчас терпимо."
    plan = ResponsePlan(action="speak", acknowledge=meaningful,
                        mandatory_question="Что ещё беспокоит?")
    rendered = render_response_plan(plan, state)
    assert rendered.acknowledge == meaningful


def test_safety_and_control_surfaces_are_untouched():
    state = _state("Мне плохо, вызовите скорую.")
    urgent = ResponsePlan(action="close_urgent")
    assert render_response_plan(urgent, state).mandatory_question == (
        render_response_plan(ResponsePlan(action="close_urgent"), _state()).mandatory_question
    )
    control = ResponsePlan(action="speak", control="pause", mandatory_question="")
    assert render_response_plan(control, state).acknowledge == ""


def test_reaction_is_never_a_standalone_turn():
    state = _state("Голова побаливает.")
    plan = ResponsePlan(action="speak", acknowledge="Хорошо.",
                        mandatory_question="Что ещё беспокоит?")
    rendered = render_response_plan(plan, state)
    assert rendered.mandatory_question          # the move still asks
    assert not rendered.acknowledge.endswith("?")  # reaction is not a question


def test_closing_line_reflects_the_person_before_the_summary():
    state = _state("Внуки приезжают, пирог пекла.")
    state.elder_display_name = "Тамара Юрьевна"
    plan = ResponsePlan(action="close_summary", acknowledge="Спасибо, что рассказали.")
    rendered = render_response_plan(plan, state)
    assert "внук" in rendered.acknowledge.lower()
    assert "Спасибо, что рассказали." not in rendered.acknowledge


def test_ledger_refuses_a_repeated_reaction():
    state = _state("Внуки приезжают.")
    plan = ResponsePlan(action="speak", acknowledge="Хорошо.", mandatory_question="Что ещё?")
    first = render_response_plan(plan, state).acknowledge
    state.spoken_surfaces = [realization.__dict__ and first.lower().replace(".", "")]
    second = render_response_plan(
        ResponsePlan(action="speak", acknowledge="Хорошо.", mandatory_question="Что ещё?"), state
    ).acknowledge
    assert second != first


# ------------------------------------------- grounding by evidence, not plan


def test_slot_answered_this_turn_needs_no_plan_declaration():
    """The scheduler often drops acknowledge_facts; evidence still grounds it."""
    from packages.dialogue_engine.context import SlotValue

    state = _state("Чувствую себя хорошо.")
    state.last_user_utterance_id = "u-7"
    state.slot_records["wellness"] = SlotValue(
        value="хорошо", source_text="Чувствую себя хорошо.",
        polarity="positive", source_turn_id="u-7",
    )
    assert realization.reaction_clause(state, []) == (
        "Спасибо, что сказали, как себя чувствуете."
    )


def test_a_slot_from_an_earlier_turn_is_not_re_acknowledged():
    from packages.dialogue_engine.context import SlotValue

    state = _state("Да, поела уже.")
    state.last_user_utterance_id = "u-8"
    state.slot_records["wellness"] = SlotValue(
        value="хорошо", source_text="Чувствую себя хорошо.",
        polarity="positive", source_turn_id="u-2",   # an earlier turn
    )
    assert realization.reaction_clause(state, []) == ""


def test_an_answered_baseline_domain_is_grounded_too():
    state = _state("Нет, сегодня не надо ничего принимать.")
    state.last_answered_domain = "medication"
    assert realization.reaction_clause(state, []) == "Хорошо, что сказали про лекарства."


def test_every_check_in_slot_has_a_reaction():
    """A slot without a clause silently loses its reaction — that was a bug."""
    from packages.dialogue_engine.context import SlotValue

    for slot in ("wellness", "mood", "sleep", "plans"):
        state = _state("Всё хорошо.")
        state.last_user_utterance_id = "u-1"
        state.slot_records[slot] = SlotValue(
            value="хорошо", source_text="Всё хорошо.",
            polarity="positive", source_turn_id="u-1",
        )
        assert realization.reaction_clause(state, []), slot
