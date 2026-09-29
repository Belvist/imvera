"""Speech discipline — the systematic end of robotic speech.

Two enforced rules, no exceptions:

1. No verbatim repeat: Vera never asks the same question twice word-for-word
   in a row within a call (the ledger records every surface; repeats are
   fixed at the decision layer, e.g. topic skip-on-repeat).
2. No content-free standalone acks: a whole Vera turn must carry content —
   «Поняла вас.», «Хорошо.», «Понятно.» alone are banned tics. Listener
   backchannels («Слушаю вас.») are allowed: they signal listening, not
   answering.

Banks are scanned statically; live flows are scanned dynamically.
"""

from __future__ import annotations

import time

import pytest

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.dialogue_engine import questions as Q
from packages.dialogue_engine.semantic_kernel.kernel import (
    interpret as _ki,
)
from packages.dialogue_engine.semantic_kernel.kernel import (
    kernel_to_rich_turn as _k2rt,
)
from packages.dialogue_engine.speech_ledger import (
    is_banned_standalone,
    normalize,
)

pytestmark = pytest.mark.dialogue_engine


def _bank_strings() -> list[str]:
    """Every speech-bank surface in questions.py (pools only, not markers)."""
    out: list[str] = []
    names = [
        "_SLOT_QUESTION_VARIANTS",
        "_PROBE_QUESTION_VARIANTS",
        "_ITS_QUESTION_VARIANTS",
        "BACKCHANNEL_ACKS",
        "_EPISODE_ACK",
        "_WELLNESS_ACK_TAILS",
        "_REFUSAL_ACK",
    ]
    for name in names:
        pool = getattr(Q, name, None)
        if isinstance(pool, dict):
            for variants in pool.values():
                if isinstance(variants, (list, tuple)):
                    out.extend(variants)
                elif isinstance(variants, str):
                    out.append(variants)
        elif isinstance(pool, (list, tuple)):
            out.extend(pool)
    for name in (
        "_WELLNESS_ACK_GOOD",
        "_WELLNESS_ACK_UNCERTAIN",
        "_WELLNESS_ACK_NEGATIVE",
        "_REVOKE_FINAL",
        "_DEFER_FINAL",
        "_PAUSE_ACK",
        "_REPAIR_ACK",
        "_SUMMARY_TEXT",
        "_GOODBYE_FINAL",
        "_GOODBYE_CONFIRM",
    ):
        val = getattr(Q, name, None)
        if isinstance(val, str) and val.strip():
            out.append(val)
    return out


def test_no_bank_holds_a_banned_standalone() -> None:
    bad = [s for s in _bank_strings() if is_banned_standalone(s)]
    assert not bad, f"banned standalone surfaces in banks: {bad}"
    # wellness_ack() can never emit bare: every polarity × rotation step
    # must carry a content tail.
    for polarity in ("positive", "uncertain", "negative", None):
        for seq in range(4):
            for value in ("Нормально.", "Так себе.", "Плохо.", "Хорошо."):
                out = Q.wellness_ack(polarity=polarity, value=value, turn_seq=seq)
                assert not is_banned_standalone(out), (polarity, seq, value, out)


def _run(texts: list[str]) -> list[str]:
    session = CallSession(
        call_id=f"sp-{time.time_ns()}",
        family_id="speech-discipline",
        elder_display_name="Тамара Юрьевна",
        store=InMemoryCallRecordStore(),
    )
    opening = session.start()
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    session.mark_spoken_action(opening.proposal.generation_id)
    eng = session._engine
    assert eng is not None
    vera: list[str] = []
    for i, text in enumerate(texts):
        slot = eng.answer_context_slot()
        rt = _k2rt(
            _ki(text, utterance_id=f"u{i}", engine_state=eng.state, answer_slot=slot),
            answer_slot=slot,
            engine_state=eng.state,
        )
        result = session.handle_user_text(text, rich_turn=rt)
        session.mark_spoken_action(result.proposal.generation_id)
        speech = (result.proposal.speech or "").strip()
        if speech:
            vera.append(speech)
    effects = session._engine.state.spoken_surfaces
    assert effects, "ledger recorded nothing"
    return vera


FLOWS: list[list[str]] = [
    ["Здравствуйте.", "Голова болит.", "С утра.", "Терпимо.", "Нет."],
    ["Здравствуйте.", "Живот болит.", "Давно уже.", "Сильно."],
    ["Здравствуйте.", "Так себе.", "Не выспался.", "Нет."],
    ["Здравствуйте.", "Хорошо.", "Позавтракал.", "Принял таблетки.", "Пока."],
    ["Здравствуйте.", "Не беспокой меня ещё.", "Пока."],
    ["Здравствуйте.", "Что-то животик болит у меня.", "Не знаю.", "Пока."],
    ["Здравствуйте.", "У внука голова болит сильно.", "Пока."],
    ["Здравствуйте.", "умру от смеха", "Пока."],
    ["Здравствуйте.", "Ага.", "Ага.", "Ага."],
    ["Здравствуйте.", "Спина болит.", "Ой, нет, нога.", "Давно."],
    ["Здравствуйте.", "Тяжесть в животе.", "Со вчера.", "Пока."],
    ["Здравствуйте.", "Шум в ушах.", "Давно.", "Пока."],
    ["Здравствуйте.", "Привет.", "Нормально.", "Пока."],
    ["Здравствуйте.", "Плохо.", "Живот болит.", "Сильно.", "Пока."],
    ["Здравствуйте.", "Со вчера головная боль.", "Да.", "Пока."],
]


@pytest.mark.parametrize("texts", FLOWS, ids=[f"flow-{i}" for i in range(len(FLOWS))])
def test_flow_has_no_repeat_no_empty_ack(texts: list[str]) -> None:
    vera = _run(texts)
    banned = [v for v in vera if is_banned_standalone(v)]
    assert not banned, f"banned standalone acks: {banned}"
    norms = [normalize(v) for v in vera if v.endswith("?")]
    dupes = {n for n in norms if norms.count(n) > 1}
    assert not dupes, f"verbatim repeated questions: {dupes}"
