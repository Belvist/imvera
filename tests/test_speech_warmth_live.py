"""Live-speech warmth: acks carry empathy, never clerk stamps.

Rotation sizes are pinned (call rotation depends on them); banned
standalones stay banned. New wordings keep the label verbatim.
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine import questions as Q
from packages.dialogue_engine.conversation_policy import _BARE_ACK_ROTATION
from packages.dialogue_engine.speech_ledger import is_banned_standalone

pytestmark = pytest.mark.dialogue_engine


def test_episode_pools_keep_sizes_and_labels() -> None:
    assert len(Q._EPISODE_ACK["new"]) == 3
    assert len(Q._EPISODE_ACK["answer"]) == 3
    assert len(Q._EPISODE_ACK["strong"]) == 3
    assert len(Q._EPISODE_ACK["improving"]) == 2
    for kind, pool in Q._EPISODE_ACK.items():
        for template in pool:
            out = Q.episode_ack(kind, "Головная боль", turn_seq=0)
            assert "Головная боль" in out
            assert not is_banned_standalone(out)
            break


def test_no_clerk_stamps() -> None:
    flat = " ".join(
        t
        for pool in Q._EPISODE_ACK.values()
        for t in pool
    )
    for stamp in ("— учла.", "— услышала.", "— это запишу."):
        assert stamp not in flat
    assert "Да, слышу вас." not in _BARE_ACK_ROTATION
    assert "Угу, слушаю." not in Q.BACKCHANNEL_ACKS


def test_its_has_no_forms() -> None:
    assert len(Q._ITS_QUESTION_VARIANTS) == 6
    joined = " ".join(Q._ITS_QUESTION_VARIANTS)
    assert "на что мне стоит обратить внимание" not in joined
    assert "о чём мне стоит знать" not in joined
    for variant in Q._ITS_QUESTION_VARIANTS:
        assert not is_banned_standalone(variant)
