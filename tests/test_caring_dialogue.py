"""Caring persona (fs-338ee6ab shape): no broken acks, no drilling, pain heard.

1. Bare-verb / broken-glue labels never render («Болеть — зафиксировала»).
2. Temporal refusal («не могу сказать, когда») drops onset for good —
   the same question is never re-armed for the episode.
3. Fresh strong pain is acknowledged («сильная боль — это тяжело»),
   never answered with «Хорошо».
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.scenario_runner import ScenarioRunner

pytestmark = pytest.mark.dialogue_engine


def _texts(r: ScenarioRunner) -> list[str]:
    return [str(getattr(e, "text", "")) for e in r.effects]


def test_bare_verb_ack_drops_label() -> None:
    from types import SimpleNamespace

    from packages.dialogue_engine.conversation_policy import (
        _grounded_ack_for_mentions,
    )

    bare = SimpleNamespace(label="болеть", body_site="", role="primary")
    assert _grounded_ack_for_mentions(SimpleNamespace(issue_mentions=[bare])) == (
        "Поняла вас."
    )
    bare2 = SimpleNamespace(label="Беспокоит", body_site="", role="primary")
    assert _grounded_ack_for_mentions(SimpleNamespace(issue_mentions=[bare2])) == (
        "Поняла вас."
    )


def test_broken_glue_ack_prefers_full_label() -> None:
    from types import SimpleNamespace

    from packages.dialogue_engine.conversation_policy import (
        _grounded_ack_for_mentions,
    )

    dupes = [
        SimpleNamespace(label="голова боль", body_site="голова", role="primary"),
        SimpleNamespace(label="головная боль", body_site="голова", role="primary"),
    ]
    assert _grounded_ack_for_mentions(SimpleNamespace(issue_mentions=dupes)) == (
        "Головная боль — жаль, что беспокоит."
    )
    alone = [
        SimpleNamespace(label="голова боль", body_site="голова", role="primary"),
    ]
    assert _grounded_ack_for_mentions(SimpleNamespace(issue_mentions=alone)) == (
        "Поняла вас."
    )


def test_sited_ack_kept() -> None:
    from types import SimpleNamespace

    from packages.dialogue_engine.conversation_policy import (
        _grounded_ack_for_mentions,
    )

    ok = SimpleNamespace(label="Живот болит", body_site="живот", role="primary")
    assert _grounded_ack_for_mentions(SimpleNamespace(issue_mentions=[ok])) == (
        "Живот болит — жаль, что беспокоит."
    )


def test_temporal_refusal_drops_onset_for_good() -> None:
    r = ScenarioRunner(call_id="caring-temporal", elder_display_name="Тест")
    r.run(
        [
            CallStarted(),
            "Голова болит.",
            "Ну, не помню, во сколько начала болеть.",
            "Терпимая.",
            "Сегодня.",
        ]
    )
    texts = _texts(r)
    onset_qs = [
        t
        for t in texts
        if "когда начала болеть" in t.lower() or "когда это началось" in t.lower()
    ]
    # Onset asked once; the refusal is honored, never re-armed.
    assert len(onset_qs) == 1, onset_qs
    head = next(
        ep
        for ep in r.state.issue_episodes.values()
        if (ep.body_site or "") == "голова"
    )
    assert head.known_attributes.get("_temporal_skipped") == "1"


def test_strong_pain_acknowledged_not_okayed() -> None:
    r = ScenarioRunner(call_id="caring-pain", elder_display_name="Тест")
    r.run(
        [
            CallStarted(),
            "Голова болит и живот болит.",
            "Не могу сказать, когда началось.",
            "Сильно.",
        ]
    )
    texts = _texts(r)
    assert any("сильная боль — это тяжело" in t.lower() for t in texts), texts
    assert not any(
        t.strip().lower().startswith("хорошо.")
        and "когда это началось" in t.lower()
        for t in texts
    ), texts
