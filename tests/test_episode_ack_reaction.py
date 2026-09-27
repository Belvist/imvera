"""Acknowledgment must react to what happened, not repeat a form.

Every episode turn used to open with «Поняла вас. … — зафиксировала.» — an
administrative monotone that made Vera sound like a form, not a listener.
The acknowledgment is now chosen by MEANING (a deterministic signal) from a
small bank in questions.py (PhraseSelect discipline, not bank inflation).

Pinned here:
- the label is spoken, not a debug string;
- the label stays grammatically standalone («<label> — …», never
  «Хорошо, <clause> — …»);
- the kind follows the signal, not the wording of the turn;
- an unknown signal falls back to the neutral form instead of inventing one.
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine.questions import episode_ack

pytestmark = pytest.mark.dialogue_engine

_LABELS = ["Живот болит", "Головная боль", "Боль в животе", "Зуб болит"]


@pytest.mark.parametrize("label", _LABELS)
@pytest.mark.parametrize("kind", ["new", "answer", "strong", "improving"])
def test_ack_is_grammatical_for_every_label_shape(kind: str, label: str) -> None:
    """A noun-phrase label and a clause label must both read naturally."""
    for seq in range(4):
        text = episode_ack(kind, label, turn_seq=seq)
        assert text.startswith(label), text
        assert " — " in text, text
        # No comma splice: the label is never embedded mid-clause.
        head, _, tail = text.partition(" — ")
        assert "," not in head, text
        assert tail.strip(), text


def test_unknown_signal_falls_back_without_inventing() -> None:
    assert episode_ack("nonsense", "Живот болит") == "Поняла вас. Живот болит — зафиксировала."


def test_no_administrative_monotone_in_the_bank() -> None:
    """«Поняла вас.» may stay only as the unknown-signal fallback."""
    for kind in ("new", "answer", "strong", "improving"):
        assert not episode_ack(kind, "Живот болит").startswith("Поняла вас.")
