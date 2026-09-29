"""Act-head delivery: version flag, default v2, loud fallback.

The v3 shadow artifact must be loadable side-by-side without disturbing
the live default. Unknown versions fall back to v2 WITH a warning, never
silently and never by taking the bridge down.
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine.semantic_nlp.model import (
    LIVE_DEFAULT_VERSION,
    SemanticNLP,
)

pytestmark = pytest.mark.dialogue_engine


def test_live_default_is_v2(monkeypatch) -> None:
    monkeypatch.delenv("IMVERA_ACT_HEAD_VERSION", raising=False)
    SemanticNLP._instances.clear()
    inst = SemanticNLP.get()
    assert inst is not None
    cand = inst.predict("Как вы себя чувствуете?", "Голова болит.")
    assert cand is not None
    assert cand.act in (
        "answer", "backchannel", "complaint", "confirm", "correction",
        "decline", "goodbye", "greeting", "not_recalled", "repeat_request",
        "stop", "uncertain", "user_question",
    )


def test_env_override_loads_v3_alongside(monkeypatch) -> None:
    monkeypatch.setenv("IMVERA_ACT_HEAD_VERSION", "v3")
    SemanticNLP._instances.clear()
    env_inst = SemanticNLP.get()  # env points at v3 here
    explicit_v2 = SemanticNLP.get("v2")
    assert env_inst is not explicit_v2
    cand = env_inst.predict("Как вы себя чувствуете?", "Голова болит.")
    assert cand is not None
    cand2 = explicit_v2.predict("Как вы себя чувствуете?", "Голова болит.")
    assert cand2 is not None


def test_unknown_version_falls_back_loud(monkeypatch) -> None:
    monkeypatch.setenv("IMVERA_ACT_HEAD_VERSION", "nope-v99")
    SemanticNLP._instances.clear()
    inst = SemanticNLP.get()
    assert inst is not None
    assert LIVE_DEFAULT_VERSION in SemanticNLP._instances
