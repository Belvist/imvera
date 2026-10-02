"""Call controls bind to the speaker's requested action, not a verb substring."""

from __future__ import annotations

import pytest

from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.reducer import _is_explicit_farewell
from packages.dialogue_engine.reluctance import reluctance_points
from packages.dialogue_engine.semantic_kernel.controls import match_level0

pytestmark = pytest.mark.dialogue_engine


def _deliver(engine):
    spoken = []
    while (effect := engine.pop_speak_effect()) is not None:
        spoken.append(effect)
        engine.on_playout_completed(effect.generation, effect.question_id)
    return spoken


def _reply(engine, text, uid):
    turn = engine.build_rich_turn(text, utterance_id=uid)
    engine.on_user_turn(uid, text, rich_turn=turn)
    return turn, _deliver(engine)


@pytest.mark.parametrize("text,control", [
    ("Спасибо, не хочу больше разговаривать.", "stop_call"),
    ("Я не хочу больше разговаривать.", "stop_call"),
    ("Не хочу больше говорить.", "stop_call"),
    ("Спасибо, давайте закончим разговор.", "stop_call"),
    ("Не хочу разговаривать.", "revoke_consent"),
    ("Не звоните больше.", "stop_call"),
    ("Больше не звоните мне.", "stop_call"),
])
def test_explicit_current_call_stop_and_pinned_controls(text, control):
    match = match_level0(text)
    assert match is not None and match.control == control


@pytest.mark.parametrize("text", [
    "Не хочу отвечать на этот вопрос, но поговорить хочу.",
    "Не буду отвечать на этот вопрос.",
    "Не хочу говорить про таблетки.",
    "Спасибо, не хочу обсуждать эту тему.",
    "Не хочу об этом рассказывать.",
    "Не хочу есть.",
])
def test_question_or_nonconversation_object_does_not_revoke_consent(text):
    match = match_level0(text)
    assert match is None or match.control == "none"


@pytest.mark.parametrize("text", [
    "Я не хочу заканчивать разговор.",
    "Я не буду заканчивать разговор.",
    "Не надо заканчивать разговор.",
    "Не заканчивайте разговор.",
    "Соседка сказала: заканчиваем разговор.",
    'Вчера я сказала: «До свидания».',
    '«До свидания», сказала соседка.',
    "До свидания сказала соседка.",
])
def test_negated_or_reported_ending_never_becomes_farewell_or_reluctance(text):
    assert not _is_explicit_farewell(text)
    assert reluctance_points(text, answers_pending=False) == 0
    match = match_level0(text)
    assert match is None or match.control == "none"


def test_affirmative_farewell_in_contrast_still_ends_call():
    text = "Не хочу заканчивать разговор, но пора. До свидания."
    assert _is_explicit_farewell(text)


@pytest.mark.parametrize("text", [
    "Не хочу больше разговаривать, сказала соседка.",
    "Не звоните больше, говорила я вчера.",
    "Не звоните дочке.",
])
def test_reported_or_other_recipient_refusal_is_not_current_speaker_control(text):
    match = match_level0(text)
    assert match is None or match.control == "none"


@pytest.mark.parametrize("listening", [False, True])
@pytest.mark.parametrize("text", [
    "Спасибо, не хочу больше разговаривать.",
    "Я не хочу заканчивать разговор.",
    "Не хочу отвечать на этот вопрос, но поговорить хочу.",
])
def test_real_sdk_control_meaning_before_and_during_delivered_listening(text, listening):
    engine = DialogueEngine(call_id="grounded-controls")
    engine.start()
    _deliver(engine)
    if listening:
        _reply(engine, "Внучка вчера приезжала, мы вместе смотрели фотографии.", "story-1")
        assert engine.state.thread_listening_delivered
    turn, speech = _reply(engine, text, "control-1")
    if "не хочу больше разговаривать" in text.lower():
        assert turn.control == "stop_call"
        assert engine.state.call_closed
        assert engine.state.closing_reason == "goodbye"
        assert speech[-1].intent == "goodbye_final"
    else:
        assert turn.control == "none"
        assert not engine.state.call_closed
        assert engine.state.closing_reason != "revoke_consent"
        assert all(effect.intent not in {"goodbye_final", "revoke_consent_final"}
                   for effect in speech)
    assert "consent_declined" not in engine.state.observations


def test_urgent_complaint_still_preempts_prefixed_current_call_stop():
    engine = DialogueEngine(call_id="grounded-controls-urgent")
    engine.start()
    _deliver(engine)
    _, speech = _reply(
        engine, "Спасибо, не хочу больше разговаривать. Не могу дышать.", "danger-1",
    )
    assert speech[-1].intent == "urgent_close"


@pytest.mark.parametrize("text", [
    "Я не хочу заканчивать разговор.",
    "Не буду заканчивать разговор.",
    "Не надо заканчивать звонок.",
])
def test_negated_call_ending_does_not_decline_delivered_health_question(text):
    engine = DialogueEngine(call_id="negated-ending-goal")
    engine.start()
    _deliver(engine)
    turn = engine.build_rich_turn(text, utterance_id="continue-1")
    assert turn.control == "none"
    assert turn.goal_dispositions == ()
    prior = engine.state.goals["wellness"].model_dump()
    engine.on_user_turn("continue-1", text, rich_turn=turn)
    assert engine.state.goals["wellness"].lifecycle.value != "DECLINED"
    assert engine.state.goals["wellness"].answer == prior["answer"]


def test_local_refusal_in_contrast_still_declines_only_delivered_question():
    engine = DialogueEngine(call_id="local-refusal-goal")
    engine.start()
    _deliver(engine)
    turn = engine.build_rich_turn(
        "Не хочу отвечать на этот вопрос, но поговорить хочу.", utterance_id="local-1",
    )
    assert turn.control == "none"
    assert len(turn.goal_dispositions) == 1
    assert turn.goal_dispositions[0].goal_id == "wellness"
    assert turn.goal_dispositions[0].disposition == "declined"


@pytest.mark.parametrize("text,expected", [
    ("Хочу поговорить.", True),
    ("Поговорить хочу.", True),
    ("Не хочу отвечать на этот вопрос, но поговорить хочу.", True),
    ("Я хотела бы немного пообщаться.", True),
    ("Не хочу разговаривать.", False),
    ("Поговорить не хочу.", False),
    ("Хочу не разговаривать, а поспать.", False),
    ("Дочка хочет поговорить.", False),
    ('Внучка сказала: «Хочу поговорить».', False),
    ("Вчера я хотела поговорить.", False),
    ("Не хочу отвечать на этот вопрос.", False),
])
def test_continuing_talk_requires_positive_addressed_volition(text, expected):
    from packages.dialogue_engine.semantic_kernel.controls import wants_to_continue_talking

    assert wants_to_continue_talking(text) is expected


@pytest.mark.parametrize("text,repair", [
    ("Что?", True),
    ("Что", True),
    ("Что вы сказали?", True),
    ("Не расслышала, повторите.", True),
    ("Что делать, если болит голова?", False),
    ("Что такое давление?", False),
    ("Что мне купить в магазине?", False),
])
def test_bare_what_is_hearing_repair_but_question_object_is_not(text, repair):
    from packages.dialogue_engine.semantic_kernel.controls import match_repair

    assert (match_repair(text) is not None) is repair


def test_real_sdk_medical_question_is_not_repeated_opening_greeting():
    engine = DialogueEngine(call_id="medical-question-control")
    engine.start()
    _deliver(engine)
    turn, speech = _reply(engine, "Что делать, если болит голова?", "question-1")
    assert turn.dialogue_act == "question"
    assert all(effect.intent != "repair_repeat" for effect in speech)
    assert engine.state.issue_episodes == {}


@pytest.mark.parametrize("text,expected", [
    ("Давайте просто поговорим.", True),
    ("Давай немного пообщаемся.", True),
    ("Давайте поговорим, не будем пока о здоровье.", True),
    ("Давайте не поговорим.", False),
    ("Давайте не будем разговаривать.", False),
    ("Не надо, давайте пока не будем вообще говорить.", False),
    ("Давайте дочь поговорит.", False),
    ("Давайте они поговорят.", False),
    ('Дочка сказала: «Давайте просто поговорим».', False),
    ("Вчера мы решили: давайте поговорим.", False),
])
def test_positive_addressed_invitation_can_open_the_talking_floor(text, expected):
    from packages.dialogue_engine.semantic_kernel.controls import wants_to_continue_talking

    assert wants_to_continue_talking(text) is expected


def test_exact_local_health_refusal_plus_invitation_keeps_real_sdk_listening():
    engine = DialogueEngine(call_id="local-refusal-positive-invitation")
    engine.start()
    _deliver(engine)
    text = "Не хочу отвечать про здоровье, давайте просто поговорим."
    turn, speech = _reply(engine, text, "invite-1")
    assert turn.control == "none"
    assert engine.state.goals["wellness"].lifecycle.value == "DECLINED"
    assert speech[-1].intent == "thread_invite"
    assert not speech[-1].marks_question and "?" not in speech[-1].text
    assert engine.state.thread_listening_delivered
    assert engine.state.delivered_question is None
    for number, statement in enumerate((
        "Просто много дел было сегодня.",
        "С утра готовила и потом смотрела новости.",
    )):
        _, continuation = _reply(engine, statement, f"story-{number}")
        assert continuation[-1].intent == "thread_listening_ack"
        assert not continuation[-1].marks_question
        assert not engine.state.call_closed
        assert engine.state.thread_listening_delivered
        assert engine.state.issue_episodes == {}
        assert not engine.state.slot_values
