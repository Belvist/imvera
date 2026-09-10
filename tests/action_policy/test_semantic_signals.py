from __future__ import annotations

from packages.dialogue_engine.action_policy.semantic_signals import derive_unresolved_concern


def test_vague_negative_wellness_without_issue_is_unresolved() -> None:
    class _Fact:
        field = "wellness"
        value = "negative"

    assert derive_unresolved_concern(
        goal_facts=(_Fact(),),
        kernel_ambiguities=("vague_issue",),
    )


def test_grounded_issue_blocks_unresolved_concern() -> None:
    class _Mention:
        label = "headache"

    assert not derive_unresolved_concern(issue_mentions=(_Mention(),))
