from __future__ import annotations

import pytest

import packages.dialogue_engine.semantic_kernel.morphology as morphology


class _FakeParse:
    def __init__(self, normal_form: str) -> None:
        self.normal_form = normal_form


class _FakeMorph:
    _LEMMAS = {
        "болит": "болеть",
        "болел": "болеть",
        "болела": "болеть",
        "болеть": "болеть",
        "животе": "живот",
        "голову": "голова",
    }

    def parse(self, token: str):
        return [_FakeParse(self._LEMMAS.get(token, token))]


@pytest.fixture
def morph_present(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(morphology, "_MORPH", _FakeMorph())
    monkeypatch.setattr(morphology, "_MORPH_TRIED", True)
    morphology.normalize_token.cache_clear()
    yield
    morphology.normalize_token.cache_clear()


@pytest.fixture
def morph_absent(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(morphology, "_MORPH", None)
    monkeypatch.setattr(morphology, "_MORPH_TRIED", True)
    morphology.normalize_token.cache_clear()
    yield
    morphology.normalize_token.cache_clear()


def _kernel_mentions(text: str):
    from packages.dialogue_engine.semantic_kernel.kernel import interpret
    from packages.dialogue_engine.semantic_kernel.observation_memory import (
        build_observations,
        observations_to_issue_mentions,
    )

    result = interpret(text, utterance_id="u-1")
    observations = build_observations(result)
    return observations_to_issue_mentions(observations, result.raw_text)


def test_surface_label_with_morphology(morph_present) -> None:
    mentions = _kernel_mentions("У меня живот болит.")
    assert mentions
    assert mentions[0].label == "живот болит"
    assert mentions[0].canonical_key == "живот болеть"


def test_negated_siteless_mention_spawns_no_episode() -> None:
    """Live 2257cab2: «Ничего меня не беспокоит» built a 'беспокоит'
    episode + onset probe. A negated site-less mention is a denied
    complaint — no mention, no episode. Sited mentions keep behavior."""
    assert _kernel_mentions("Ничего меня не беспокоит.") == ()
    assert _kernel_mentions("Ничего не болит.") == ()
    kept = _kernel_mentions("Голова не болит, а живот болит.")
    sites = {(m.label, m.body_site) for m in kept}
    assert any(site == "живот" for _, site in sites), sites


def test_surface_label_without_morphology(morph_absent) -> None:
    mentions = _kernel_mentions("У меня живот болит.")
    assert mentions
    assert mentions[0].label == "живот болит"


def test_surface_label_identical_across_environments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(morphology, "_MORPH", _FakeMorph())
    monkeypatch.setattr(morphology, "_MORPH_TRIED", True)
    morphology.normalize_token.cache_clear()
    with_morph = _kernel_mentions("У меня живот болит.")[0].label
    morphology.normalize_token.cache_clear()
    monkeypatch.setattr(morphology, "_MORPH", None)
    monkeypatch.setattr(morphology, "_MORPH_TRIED", True)
    morphology.normalize_token.cache_clear()
    without_morph = _kernel_mentions("У меня живот болит.")[0].label
    morphology.normalize_token.cache_clear()
    assert with_morph == without_morph == "живот болит"


def test_canonical_key_equal_across_inflections(morph_present) -> None:
    first = _kernel_mentions("У меня живот болит.")[0]
    second = _kernel_mentions("Живот болел вчера.")[0]
    assert first.label == "живот болит"
    assert first.canonical_key == second.canonical_key == "живот болеть"


def test_mixed_turn_subject_split_with_morphology(
    morph_present, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "1")
    from packages.dialogue_engine.events import CallStarted
    from packages.dialogue_engine.scenario_runner import ScenarioRunner

    r = ScenarioRunner(call_id="subj", elder_display_name="Тест")
    r.run([CallStarted(), "У мужа голова, а у меня живот болит."])
    labels = {e.primary_label: e.subject for e in r.state.issue_episodes.values()}
    assert labels.get("живот болит") == "speaker"
    assert "голова" not in " ".join(
        e.primary_label for e in r.state.issue_episodes.values() if e.subject == "speaker"
    )


def test_observation_match_uses_canonical_key(morph_present) -> None:
    from packages.dialogue_engine.semantic_kernel.observation_memory import (
        _match_episode_for_observation,
    )
    from packages.dialogue_engine.semantic_kernel.types import Observation, SubjectKind
    from packages.dialogue_engine.state import EngineState, IssueEpisode
    from packages.dialogue_engine.turn_understanding import RichUserTurn

    state = EngineState(call_id="canon", elder_display_name="Тест")
    state.issue_episodes["ep-1"] = IssueEpisode(
        episode_id="ep-1",
        primary_label="живот болит",
        canonical_key="живот болеть",
        kind="symptom",
        body_site="живот",
        subject="speaker",
    )
    turn = RichUserTurn(
        utterance_id="u-2",
        raw_text="Тошнит.",
        dialogue_act="answer",
        control="none",
        answers_pending_question=False,
        needs_clarification=False,
    )
    obs = Observation(
        observation_id="o-1",
        attribute="issue",
        value="тошнит",
        normalized_value="тошнить",
        body_site=None,
        issue_normalized="болеть",
        subject=SubjectKind.SPEAKER,
        source_turn_id="u-2",
        evidence="болеть",
        status="confirmed",
    )
    assert _match_episode_for_observation(state, obs, turn) == "ep-1"


def test_followup_mention_attaches_to_same_episode(morph_present) -> None:
    from packages.dialogue_engine.issue_memory import _find_episode_for_mention
    from packages.dialogue_engine.semantic_kernel.kernel import interpret
    from packages.dialogue_engine.semantic_kernel.observation_memory import (
        build_observations,
        observations_to_issue_mentions,
    )
    from packages.dialogue_engine.state import EngineState, IssueEpisode

    first = _kernel_mentions("У меня живот болит.")[0]
    state = EngineState(call_id="canon", elder_display_name="Тест")
    state.issue_episodes["ep-1"] = IssueEpisode(
        episode_id="ep-1",
        primary_label=first.label,
        canonical_key=first.canonical_key,
        kind=first.kind,
        body_site=first.body_site,
        subject="speaker",
    )
    result = interpret("Живот болит.", utterance_id="u-2")
    second = observations_to_issue_mentions(
        build_observations(result), result.raw_text
    )[0]
    assert second.label == "живот болит"
    assert _find_episode_for_mention(state, second) == "ep-1"
