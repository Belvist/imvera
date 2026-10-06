"""One caller's routine fact must not borrow another person's quality/quote."""
import pytest

from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.issue_mention_extract import extract_goal_facts
from packages.dialogue_engine.scenario_runner import ScenarioRunner

pytestmark = pytest.mark.dialogue_engine


@pytest.mark.parametrize('text, own', [
    ('Мне хорошо. Дочь плохо спала, а я выспалась.', 'а я выспалась.'),
    ('Я выспалась. Дочь плохо спала.', 'Я выспалась'),
    ('Дочь плохо спала. Я спала отлично.', 'Я спала отлично.'),
    ('Дочь плохо спала, я выспалась.', 'я выспалась.'),
])
def test_sleep_evidence_is_callers_exact_clause_and_reaction_not_daughters(text, own):
    runner = ScenarioRunner(call_id='mixed-sleep')
    out = runner.run([CallStarted(), text])
    record = runner.state.slot_records['sleep']
    # Sleep's SDK record may have no valence; evidence/actual stance is the contract.
    assert record.polarity != 'negative'
    assert record.source_text == own
    assert 'дочь' not in runner.state.slot_records['wellness'].source_text.lower()
    assert 'дочь' not in record.source_text.lower()
    assert not any('тяжёлая' in speech.text for speech in out.speak_effects)
    assert not any(speech.intent.startswith('topic_sleep') for speech in out.speak_effects)
    fact = next(f for f in extract_goal_facts(text, answer_slot='wellness') if f.field == 'sleep')
    assert text[fact.evidence.start:fact.evidence.end] == fact.evidence.quote
    assert fact.evidence.quote == own


@pytest.mark.parametrize('text', [
    'Мне хорошо. Дочь выспалась, а я плохо спала.',
    'Дочь спала отлично. Я плохо спала.',
])
def test_daughters_positive_sleep_never_reverses_callers_negative_sleep(text):
    runner = ScenarioRunner(call_id='mixed-negative')
    out = runner.run([CallStarted(), text])
    record = runner.state.slot_records['sleep']
    assert record.polarity != 'positive'
    assert 'плохо спала' in record.source_text.lower()
    assert any(('плохой сон' in speech.text.lower() or 'тяжёлая' in speech.text)
               for speech in out.speak_effects)
    assert 'дочь' not in record.source_text.lower()


def test_unowned_continuation_of_daughters_story_is_not_callers_sleep():
    facts = extract_goal_facts('Я чувствую себя хорошо. Дочь приехала. Плохо спала.')
    assert not any(f.field == 'sleep' for f in facts)


def test_quoted_sleep_does_not_become_callers_fact():
    facts = extract_goal_facts('Мне хорошо. Дочь сказала: «Я плохо спала».')
    assert not any(f.field == 'sleep' for f in facts)


@pytest.mark.parametrize('text', [
    'Я чувствую себя хорошо. Дочь приехала. Плохо спала.',
    'Мне хорошо. Дочь сказала: «Я плохо спала».',
])
def test_contextual_candidate_cannot_resurrect_rejected_foreign_fact(monkeypatch, text):
    from packages.dialogue_engine.context import SlotCandidate
    from packages.dialogue_engine.semantic import SemanticAct, SemanticTurn
    from packages.dialogue_engine.turn_understanding import build_rich_turn_from_text

    proposal = SemanticTurn(act=SemanticAct.ANSWER, slots={
        'wellness': SlotCandidate(value=text), 'sleep': SlotCandidate(value=text)},
        confidence=0.99)
    monkeypatch.setattr('packages.dialogue_engine.contextual_interpreter.contextual_interpret',
                        lambda *args: (proposal, True))
    runner = ScenarioRunner(call_id='candidate-scope')
    runner.run([CallStarted()])
    turn = build_rich_turn_from_text(text, utterance_id='u-test', engine_state=runner.state)
    assert not any(f.field == 'sleep' for f in turn.goal_facts)
    wellness = next(f for f in turn.goal_facts if f.field == 'wellness')
    assert 'дочь' not in wellness.evidence.quote.lower()
    assert text[wellness.evidence.start:wellness.evidence.end] == wellness.evidence.quote


def test_delivered_mission_wellness_uses_same_original_subject_boundary():
    from packages.dialogue_engine.mission import daily_check_mission
    from packages.dialogue_engine.mission_seed import apply_mission_to_state

    text = 'Мне хорошо. Дочь плохо спала, а я выспалась.'
    runner = ScenarioRunner(call_id='mission-scope')
    apply_mission_to_state(runner.state, daily_check_mission())
    out = runner.run([CallStarted(), text])
    assert runner.state.slot_records['wellness'].source_text == 'Мне хорошо'
    assert runner.state.slot_records['sleep'].source_text == 'а я выспалась.'
    assert not any('тяжёлая' in speech.text for speech in out.speak_effects)
