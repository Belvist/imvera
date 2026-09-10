from __future__ import annotations

from packages.dialogue_engine.action_policy.semantic_signals import (
    classify_turn_issues,
    derive_turn_risk_level,
    derive_unresolved_concern,
    has_grounded_speaker_issue,
)
from packages.dialogue_engine.semantic_kernel.types import Observation, SubjectKind


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


def test_other_person_issue_does_not_block_unresolved_concern() -> None:
    obs = Observation(
        observation_id="o1",
        attribute="issue",
        value="back pain",
        subject=SubjectKind.OTHER_PERSON,
    )

    class _PositiveWellness:
        field = "wellness"
        value = "positive"
        subject = "speaker"

    assert not derive_unresolved_concern(
        issue_mentions=(object(),),
        observations=(obs,),
        goal_facts=(_PositiveWellness(),),
    )

    class _NegativeWellness:
        field = "wellness"
        value = "negative"
        subject = "speaker"

    assert derive_unresolved_concern(
        raw_text="У мужа болит спина, а мне самому плохо.",
        issue_mentions=(object(),),
        observations=(obs,),
        goal_facts=(_NegativeWellness(),),
    )
    assert not has_grounded_speaker_issue(issue_mentions=(object(),), observations=(obs,))
    speaker, other = classify_turn_issues(issue_mentions=(object(),), observations=(obs,))
    assert not speaker
    assert other


def test_turn_risk_from_raw_text_without_check_path() -> None:
    assert derive_turn_risk_level(raw_text="Не могу дышать") == "urgent"
    assert derive_turn_risk_level(raw_text="Всё нормально") == "none"
