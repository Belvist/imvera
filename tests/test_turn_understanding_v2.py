"""P2 Cut 1 parity: V2 facade output identical to legacy builders."""

from __future__ import annotations

import pytest

from packages.dialogue_engine.turn_understanding import (
    TurnUnderstandingV2,
    build_rich_turn_from_text,
)

pytestmark = pytest.mark.dialogue_engine

PHRASES: tuple[str, ...] = (
    "Хорошо.",
    "Плохо… хотя нет, нормально.",
    "Голова сильно болит со вчера.",
    "Не помню, когда началось.",
    "Ага.",
    "До свидания.",
    "Нет, я про живот говорил.",
    "Давление сто сорок на девяносто.",
    "Спал нормально.",
    "Повтори.",
    "Отстань.",
    "Ничего.",
)


@pytest.mark.parametrize("text", PHRASES)
def test_resolve_matches_legacy_build(text: str) -> None:
    import json
    import re

    uid = "u-parity"
    legacy = build_rich_turn_from_text(text, utterance_id=uid)
    resolved = TurnUnderstandingV2().resolve(text, utterance_id=uid)
    legacy_dump = legacy.model_dump(mode="json")
    resolved_dump = resolved.turn.model_dump(mode="json")
    # kernel_elapsed_ms is wall-clock noise; span/evidence ids are random
    # per build — mask both, compare everything else.
    def canon(dump: dict) -> str:
        text = json.dumps(dump, ensure_ascii=False, sort_keys=True)
        text = re.sub(r'"[a-z_]*span_id": "[^"]+"', '"span_id": "ID"', text)
        text = re.sub(r'"[a-z_]*mention_id": "[^"]+"', '"mention_id": "ID"', text)
        text = re.sub(
            r'"[a-z_]*observation_id": "[^"]+"', '"observation_id": "ID"', text
        )
        text = re.sub(r'"id": "(sp|im|obs)-[^"]+"', '"id": "ID"', text)
        return text

    legacy_dump.pop("kernel_elapsed_ms", None)
    resolved_dump.pop("kernel_elapsed_ms", None)
    assert canon(resolved_dump) == canon(legacy_dump)
    assert resolved.interpret_path == "v2_resolve"
    assert len(resolved.trace) == 1
    assert resolved.total_elapsed_ms >= 0.0


def test_adjudicate_final_branches() -> None:
    from packages.dialogue.state import DialogueState
    from packages.dialogue_engine.semantic import SemanticAct, SemanticTurn
    from packages.dialogue_engine.turn_understanding import TurnUnderstandingV2

    v2 = TurnUnderstandingV2()
    sem = SemanticTurn(act=SemanticAct.BACKCHANNEL, source_quote="Ага.")
    from types import SimpleNamespace

    legacy = DialogueState(call_id="adj", family_id="fam")
    rich_empty = SimpleNamespace(issue_mentions=[])

    interp, path = v2.adjudicate_final(
        use_rich_deterministic=True, rich_turn=rich_empty, fast_confident=True,
        kernel_has_meaning=False, sem=sem, incoming_path="fast_rules",
        legacy_state=legacy, text="Ага.", fsm_override=None,
    )
    assert path == "fast_rules"
    assert interp.dialogue_act.value == "backchannel"

    interp2, path2 = v2.adjudicate_final(
        use_rich_deterministic=False, rich_turn=None, fast_confident=False,
        kernel_has_meaning=False, sem=sem, incoming_path="fast_rules",
        legacy_state=legacy, text="хм", fsm_override=None,
    )
    assert path2 == "rules_fallback"

    interp3, path3 = v2.adjudicate_final(
        use_rich_deterministic=False, rich_turn=None, fast_confident=True,
        kernel_has_meaning=False, sem=sem, incoming_path="fast_rules",
        legacy_state=legacy, text="Ага.", fsm_override=None,
    )
    assert path3 == "fast_rules"
    assert interp3.dialogue_act.value == "backchannel"
