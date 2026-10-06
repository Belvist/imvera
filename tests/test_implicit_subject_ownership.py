"""Foreign stories cannot silently become the caller's clinical reports."""
from __future__ import annotations

import pytest

from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.questions import concern_summary_phrase
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.semantic_kernel.types import SubjectKind
from packages.dialogue_engine.turn_understanding import build_rich_turn_from_text

pytestmark = pytest.mark.dialogue_engine


@pytest.fixture(autouse=True)
def live_flags(monkeypatch):
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "1")
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "off")
    monkeypatch.setenv("IMVERA_LLM_INTERPRET", "0")
    monkeypatch.setenv("IMVERA_MISSION_LLM_INTERPRET", "0")


@pytest.mark.parametrize("text", [
    "Я чувствую себя хорошо. Дочь приехала. Плохо спала.",
    "Мне хорошо. Дочь приехала. А ещё плохо спала.",
    "Мне хорошо. Дочь приехала, а плохо спала.",
    "Мне хорошо. Дочь приехала, но плохо спала.",
    "У дочери голова болит. Плохо спала.",
    "Мне хорошо. Внук приехал. Голова болит.",
    "Дочь рассказала: «У меня живот болит. Голова тоже болит».",
])
def test_full_exchange_never_probes_or_recaps_ambiguous_story_as_callers_health(text):
    runner = ScenarioRunner(call_id="implicit-owner")
    runner.run([CallStarted()])
    turn = build_rich_turn_from_text(text, utterance_id="owned-test", engine_state=runner.state)
    assert turn.issue_mentions  # Keep the report, rather than silently losing it.
    assert all(m.subject != "speaker" for m in turn.issue_mentions)
    out = runner.run([text])
    assert runner.state.issue_episodes
    assert all(ep.subject != "speaker" for ep in runner.state.issue_episodes.values())
    assert not runner.state.pending_episode_attribute
    assert not any(s.intent.startswith("episode_") for s in out.speak_effects)
    assert "сон" not in concern_summary_phrase(runner.state).lower()
    assert "голов" not in concern_summary_phrase(runner.state).lower()
    assert "sleep" not in runner.state.slot_records
    assert not any("тяжёлая" in s.text or "плохой сон" in s.text.lower()
                   for s in out.speak_effects)
    assert all(text[m.evidence.start:m.evidence.end] == m.evidence.quote
               for m in turn.issue_mentions)


@pytest.mark.parametrize("text", [
    "Мне хорошо. Дочь приехала. Я плохо спала.",
    "Дочь выспалась, а я плохо спала.",
    "Я плохо спала. Дочь приехала.",
])
def test_explicit_caller_sleep_survives_a_family_story(text):
    runner = ScenarioRunner(call_id="explicit-owner")
    out = runner.run([CallStarted(), text])
    assert any(ep.subject == "speaker" and ep.kind == "sleep_problem"
               for ep in runner.state.issue_episodes.values())
    assert "плохо спала" in runner.state.slot_records["sleep"].source_text.lower()
    assert "дочь" not in runner.state.slot_records["sleep"].source_text.lower()
    assert any("плохой сон" in s.text.lower() or "тяжёлая" in s.text
               for s in out.speak_effects)


def test_additive_return_keeps_both_owned_complaints_across_social_aside():
    runner = ScenarioRunner(call_id="owned-return")
    out = runner.run([CallStarted(), "Живот болит. Внук приезжал. А ещё спина."])
    owned = [ep for ep in runner.state.issue_episodes.values() if ep.subject == "speaker"]
    assert {ep.body_site for ep in owned} == {"живот", "спина"}
    assert runner.state.pending_episode_attribute == "onset"
    assert any("живот" in s.text.lower() and "спина" in s.text.lower()
               for s in out.speak_effects)


def test_contrastive_present_complaint_is_not_lost_in_social_family_clause():
    runner = ScenarioRunner(call_id="contrast-owner")
    out = runner.run([CallStarted(), "С дочерью чай пили, а голова болит."])
    assert any(ep.subject == "speaker" and ep.body_site == "голова"
               for ep in runner.state.issue_episodes.values())
    assert any(s.intent == "episode_headache_duration" for s in out.speak_effects)


def test_same_words_in_different_subject_clauses_bind_by_position():
    from packages.dialogue_engine.semantic_kernel.subject_resolver import resolve_issue_subjects

    text = "У дочери голова болит. У меня голова болит."
    first = text.index("болит")
    second = text.rindex("болит")
    subjects = resolve_issue_subjects(text, (second, first, second))
    assert subjects[first] == SubjectKind.OTHER_PERSON
    assert subjects[second] == SubjectKind.SPEAKER


def test_quote_across_sentence_boundaries_cannot_establish_implicit_speaker():
    from packages.dialogue_engine.semantic_kernel.subject_resolver import resolve_issue_subjects

    text = 'Дочь сказала: «Я плохо спала. Голова болит». Мне сейчас хорошо.'
    subjects = resolve_issue_subjects(text, (text.index("спала"), text.index("болит")))
    assert set(subjects.values()) == {SubjectKind.UNKNOWN}


@pytest.mark.parametrize("text", ["Голова болит.", "Живот болит. А ещё спина."])
def test_unambiguous_implicit_caller_complaint_still_has_its_old_owner(text):
    runner = ScenarioRunner(call_id="implicit-self")
    out = runner.run([CallStarted(), text])
    assert runner.state.issue_episodes
    assert all(ep.subject == "speaker" for ep in runner.state.issue_episodes.values())
    assert any(s.intent.startswith("episode_") for s in out.speak_effects)


def test_sdk_payload_cannot_assign_ambiguous_relative_continuation_to_caller():
    from packages.contracts.semantic import Evidence, FactCandidate, IssueMention, SemanticPayload
    from packages.dialogue_engine.turn_understanding import build_rich_turn_from_payload

    text = "Мне хорошо. Дочь приехала. Плохо спала."
    start = text.index("Плохо")
    mention = IssueMention(
        mention_id="model-proposal", kind="sleep_problem", label="плохой сон",
        role="primary", temporal_scope="today", status="active", subject="speaker",
        evidence=Evidence(start=start, end=len(text) - 1, quote=text[start:-1]),
    )
    turn = build_rich_turn_from_payload(SemanticPayload(
        dialogue_act="answer", control="none", consent_answer="not_applicable",
        answers_pending_question=True, needs_clarification=False, issue_mentions=(mention,),
        facts=(FactCandidate(field="sleep", value="negative", subject="speaker",
               temporal_scope="today", negated=False, evidence=mention.evidence),),
    ), utterance_id="payload-owner", raw_text=text)
    assert turn.issue_mentions[0].subject == "unknown"
    assert not any(f.field == "sleep" for f in turn.goal_facts)


def test_filtered_legacy_offset_is_rebased_to_unique_original_quote():
    from packages.contracts.semantic import Evidence, IssueMention
    from packages.dialogue_engine.semantic_kernel.observation_memory import resolve_mention_subjects

    text = "У дочери голова болит. Плохо спала."
    mention = IssueMention(
        mention_id="filtered", kind="sleep_problem", label="плохой сон",
        role="primary", temporal_scope="today", status="active",
        evidence=Evidence(start=0, end=11, quote="Плохо спала"),
    )
    resolved = resolve_mention_subjects((mention,), text)[0]
    assert resolved.subject == "unknown"
    assert resolved.evidence.start == text.index("Плохо")
    assert text[resolved.evidence.start:resolved.evidence.end] == resolved.evidence.quote


def test_duplicate_invalid_legacy_offset_never_guesses_an_owner():
    from packages.contracts.semantic import Evidence, IssueMention
    from packages.dialogue_engine.semantic_kernel.observation_memory import resolve_mention_subjects

    text = "Дочь плохо спала. Я плохо спала."
    mention = IssueMention(
        mention_id="ambiguous-source", kind="sleep_problem", label="плохой сон",
        role="primary", temporal_scope="today", status="active", subject="speaker",
        evidence=Evidence(start=0, end=11, quote="плохо спала"),
    )
    assert resolve_mention_subjects((mention,), text)[0].subject == "unknown"


def test_explicit_family_correction_can_resolve_a_retained_inactive_unknown_report():
    runner = ScenarioRunner(call_id="unknown-correction")
    runner.run([CallStarted(), "Я чувствую себя хорошо. Дочь приехала. Плохо спала."])
    ep = next(iter(runner.state.issue_episodes.values()))
    assert ep.subject == "unknown"
    out = runner.run(["Нет, я про дочь."])
    assert ep.subject == "other_person"
    assert not runner.state.pending_episode_attribute
    assert not any(s.intent.startswith("episode_") and s.marks_question
                   for s in out.speak_effects)
    assert not concern_summary_phrase(runner.state)
