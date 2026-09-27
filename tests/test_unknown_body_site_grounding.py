"""An unknown body part must still ground a speaker episode.

Live fs-4d8f5a8b: «Начал зук болит у меня.» produced NO mention at all, so
the freshest symptom of the call was silently dropped and the summary only
mentioned the belly. Two independent holes fed it:

1. the legacy extractor knew only five hardcoded body sites;
2. the kernel has no vocabulary for every body part and returns a bare verb
   («болит», no site), and the merge let that bare verb win.

Both are now structural: any noun + pain verb is a site, and a sited
mention outranks a bare verb in the merge.
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine.effects import SpeakEffect
from packages.dialogue_engine.events import CallStarted, User
from packages.dialogue_engine.issue_mention_extract import extract_issue_mentions
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.semantic_kernel.kernel import (
    interpret,
    kernel_to_rich_turn,
)
from packages.dialogue_engine.semantic_kernel.observation_memory import (
    merge_legacy_mentions,
)

pytestmark = pytest.mark.dialogue_engine

_BELLY = "Что-то животик болит у меня."
_TOOTH = "Начал зук болит у меня."


@pytest.mark.parametrize(
    "text",
    [
        "Начал зук болит у меня.",
        "зуб болит",
        "Спину болит.",
        "Нога болит сильно.",
        "Ребро болит очень.",
    ],
)
def test_any_noun_plus_pain_verb_is_a_body_site(text: str) -> None:
    mentions = extract_issue_mentions(text)
    assert mentions, text
    assert any(m.body_site for m in mentions), text
    # The label must be speakable, never a debug string.
    for m in mentions:
        assert ":" not in m.label, m.label


def test_specific_labels_do_not_regress() -> None:
    """The generic construction must not steal canonical labels."""
    assert extract_issue_mentions("Голова болит сильно.")[0].label == "головная боль"
    assert extract_issue_mentions(_BELLY)[0].label == "боль в животе"


def test_sited_mention_outranks_bare_verb() -> None:
    """Kernel returns a bare verb for an unknown part; legacy has the site."""
    from packages.dialogue_engine.semantic_kernel.observation_memory import (
        observations_to_issue_mentions,
    )

    result = interpret(_TOOTH, utterance_id="u-tooth")
    bare = observations_to_issue_mentions(result.observations, result.raw_text)
    assert bare and not any(m.body_site for m in bare), [
        (m.label, m.body_site) for m in bare
    ]
    legacy = extract_issue_mentions(_TOOTH)
    siteful = next(m for m in legacy if m.body_site)
    merged = merge_legacy_mentions(tuple(bare), legacy, _TOOTH)
    pairs = [(m.label, m.body_site) for m in merged]
    assert (siteful.label, siteful.body_site) in pairs, pairs
    assert not any(not m.body_site for m in merged), pairs


def test_fresh_symptom_is_not_lost_on_a_live_call() -> None:
    r = ScenarioRunner(call_id="unknown-site", elder_display_name="Тамара Юрьевна")
    r.run([CallStarted()])
    for i, text in enumerate(["Здравствуйте.", _BELLY, "Уже второй день.", _TOOTH]):
        kr = interpret(text, utterance_id=f"u{i}", engine_state=r.state)
        r.run([User(text=text, rich_turn=kernel_to_rich_turn(kr, engine_state=r.state))])
    assert r.state.active_episode_id is not None
    # The second symptom becomes its own episode instead of being dropped.
    # The site keeps the elder's own word («зук»), not a normalized form.
    episodes = [e for e in r.state.issue_episodes.values() if e.body_site]
    assert len(episodes) >= 2, [(e.body_site, e.primary_label) for e in episodes]
    assert {e.body_site for e in episodes} >= {"живот", "зук"}
    spoken = " ".join(
        e.text for e in r.effects if isinstance(e, SpeakEffect)
    )
    assert "Зук болит" in spoken, spoken[-200:]


def test_no_speculative_parts_from_bare_words() -> None:
    """The construction must not invent a body site out of thin air."""
    for text in ("Очень сильно.", "Всё хорошо.", "Погода плохая."):
        assert not extract_issue_mentions(text), text
