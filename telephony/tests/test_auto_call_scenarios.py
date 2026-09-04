"""Automated multi-turn call scenarios — ConversationFacade regression harness.

Runs scripted conversations without Zoiper/audio. Asserts product invariants:
no dead-end minimal fallback, agenda advances, goodbye on close, safety paths.
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from dataclasses import dataclass, field
from typing import Sequence

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from conversation_system.integration.facade import ConversationFacade
from conversation_system.reply.guards import (
    MINIMAL_FALLBACK,
    _ACTION_PROMISE_RE,
    looks_like_rescue_framing,
    reply_looks_broken,
)

Turn = tuple[str, str | None, float | None]


@dataclass
class ScenarioExpect:
    """Per-scenario assertions beyond global invariants."""

    name: str
    turns: Sequence[Turn]
    must_contain_any: tuple[str, ...] = ()
    must_end_terminal: bool = False
    must_have_goodbye: bool = False
    must_have_record_notify: bool = False
    must_not_contain: tuple[str, ...] = ()
    no_dead_end: bool = True
    max_turns_without_question: int = 3


def _run_facade_scenario(
    expect: ScenarioExpect,
) -> tuple[list[str], list[str], bool]:
    """Return (replies, problems, terminal_seen)."""
    facade = ConversationFacade()
    handle, greeting = facade.begin_call(
        call_id=expect.name,
        greeting_played=True,
    )
    problems: list[str] = []
    replies: list[str] = [greeting]
    terminal_seen = False
    consecutive_no_q = 0

    for text, reason, conf in expect.turns:
        plan = facade.plan_turn(
            handle,
            transcript=text,
            reason=reason,
            stt_confidence=conf,
        )
        reply = (plan.spoken_reply or "").strip()
        replies.append(reply)

        if not reply:
            problems.append(f"empty reply for user={text!r}")
        elif expect.no_dead_end and reply == MINIMAL_FALLBACK:
            problems.append(f"dead-end minimal for user={text!r}")
        elif expect.no_dead_end and reply.rstrip(".") == "Услышала вас" and "?" not in reply:
            problems.append(f"dead-end heard-you for user={text!r}")

        if "?" in reply:
            consecutive_no_q = 0
        else:
            consecutive_no_q += 1
            if consecutive_no_q > expect.max_turns_without_question:
                problems.append(
                    f"{consecutive_no_q} replies without question after {text!r}",
                )

        if reply.count("?") > 1:
            problems.append(f"double question: {reply!r}")

        if _ACTION_PROMISE_RE.search(reply) or looks_like_rescue_framing(reply):
            problems.append(f"promise/rescue: {reply!r}")

        if reply_looks_broken(reply):
            problems.append(f"broken reply: {reply!r}")

        for bad in expect.must_not_contain:
            if bad.lower() in reply.lower():
                problems.append(f"forbidden {bad!r} in {reply!r}")

        if plan.terminal:
            terminal_seen = True

        facade.commit_turn(handle, plan, reply)

    facade.end_call(handle)
    combined = " ".join(replies).lower()

    for needle in expect.must_contain_any:
        if needle.lower() in combined:
            break
    else:
        if expect.must_contain_any:
            problems.append(
                f"missing any of {expect.must_contain_any!r} in conversation",
            )

    if expect.must_end_terminal and not terminal_seen:
        problems.append("expected terminal plan on last turn")

    if expect.must_have_goodbye:
        if not re.search(
            r"до свидания|всего доброго|берегите|выздоравливайте|спокойной|"
            r"хорошего вечера|хорошего отдыха|тёплого",
            combined,
        ):
            problems.append("no goodbye phrase in conversation")

    if expect.must_have_record_notify:
        if not re.search(r"записал|приложен|родн|близк|семь", combined):
            problems.append("no record-notify phrase in conversation")

    return replies, problems, terminal_seen


SCENARIOS: tuple[ScenarioExpect, ...] = (
    ScenarioExpect(
        "good_wellness_full",
        (
            ("хорошо себя чувствую", None, 0.9),
            ("настроение хорошее", None, 0.9),
            ("спала нормально", None, 0.9),
            ("пойду в магазин", None, 0.9),
            ("да", None, 0.9),
        ),
        must_have_record_notify=True,
    ),
    ScenarioExpect(
        "bad_symptom_headache",
        (
            ("плохо, болит голова", None, 0.9),
            ("сильно ноет", None, 0.9),
            ("утром началось", None, 0.9),
            ("да", None, 0.9),
        ),
        must_contain_any=("бол", "беспокоит", "легче", "голов", "запис"),
        max_turns_without_question=5,
    ),
    ScenarioExpect(
        "bad_symptom_severity_short",
        (
            ("плохо", None, 0.9),
            ("болит голова", None, 0.9),
            ("сильно", None, 0.9),
            ("утром", None, 0.9),
        ),
        must_have_record_notify=True,
        must_not_contain=("Услышала вас",),
        no_dead_end=True,
    ),
    ScenarioExpect(
        "bad_symptom_headache_intensifier_live",
        (
            ("болит голова", None, 0.9),
            ("сильно", None, 0.9),
            ("утром", None, 0.9),
        ),
        must_have_record_notify=True,
        must_contain_any=("записал", "приложен", "родн", "близк"),
    ),
    ScenarioExpect(
        "critical_fall",
        (("я упал и не могу встать", None, 0.9),),
        must_have_record_notify=True,
        must_end_terminal=True,
    ),
    ScenarioExpect(
        "goodbye_mid_good_path",
        (
            ("всё хорошо", None, 0.9),
            ("до свидания", None, 0.9),
        ),
        must_end_terminal=True,
        must_have_goodbye=True,
    ),
    ScenarioExpect(
        "closing_direct_poka",
        (
            ("хорошо", None, 0.9),
            ("давайте, пока", None, 0.9),
        ),
        must_end_terminal=True,
    ),
    ScenarioExpect(
        "refusal_wrap",
        (
            ("всё нормально", None, 0.9),
            ("нет, спасибо", None, 0.9),
        ),
        must_end_terminal=True,
        must_have_goodbye=True,
    ),
    ScenarioExpect(
        "silence_ladder_not_anchor_first",
        (
            ("", "empty", None),
            ("", "empty", None),
            ("", "empty", None),
        ),
        max_turns_without_question=5,
    ),
    ScenarioExpect(
        "low_conf_then_anchor",
        (
            ("", "low_conf", 0.35),
            ("хорошо", None, 0.9),
        ),
    ),
    ScenarioExpect(
        "stt_uncertain_mood_854cb8c",
        (
            ("Привет, хорошо себя чувствую.", None, 0.9),
            ("Хорошее настроение.", "stt_uncertain", 0.65),
            ("Хорошее настроение.", "stt_uncertain", 0.65),
            ("Хорошо.", None, 0.9),
        ),
        must_not_contain=("Повторите",),
        must_have_record_notify=True,
    ),
    ScenarioExpect(
        "short_da_after_probe",
        (
            ("хорошо", None, 0.9),
            ("да", None, 0.9),
            ("да", None, 0.9),
        ),
    ),
    ScenarioExpect(
        "positive_not_false_red",
        (
            ("отлично, ничего не болело", None, 0.9),
            ("настроение хорошее", None, 0.9),
        ),
        must_not_contain=("скорую", "вызову", "тревог"),
    ),
    ScenarioExpect(
        "symptom_improvement",
        (
            ("голова болит", None, 0.9),
            ("стало легче", None, 0.9),
            ("да", None, 0.9),
        ),
    ),
    ScenarioExpect(
        "safety_confirm_chain",
        (
            ("голова сильно болит", None, 0.9),
            ("да", None, 0.9),
            ("стало легче", None, 0.9),
        ),
    ),
    ScenarioExpect(
        "negated_fall_ok",
        (
            ("я не упал", None, 0.9),
            ("всё хорошо", None, 0.9),
        ),
        must_not_contain=("тревог", "скорую"),
    ),
    ScenarioExpect(
        "echo_then_speech",
        (
            ("", "echo", None),
            ("всё хорошо", None, 0.9),
        ),
    ),
    ScenarioExpect(
        "repair_repeat",
        (
            ("хорошо", None, 0.9),
            ("повторите пожалуйста", None, 0.9),
        ),
    ),
    ScenarioExpect(
        "side_question",
        (
            ("какое сегодня число?", None, 0.9),
        ),
        must_contain_any=("имвера", "вера", "забот"),
        no_dead_end=False,
    ),
    ScenarioExpect(
        "narrative_story",
        (
            (
                "Внучка приезжала, мы чай пили на кухне и долго разговаривали",
                None,
                0.9,
            ),
            ("да", None, 0.9),
        ),
        no_dead_end=True,
    ),
    ScenarioExpect(
        "greeting_back",
        (
            ("здравствуйте", None, 0.9),
            ("хорошо", None, 0.9),
        ),
        must_contain_any=("здравствуйте", "добр"),
    ),
    ScenarioExpect(
        "medium_wellness",
        (
            ("ну так себе", None, 0.9),
            ("устала немного", None, 0.9),
            ("спала прерывисто", None, 0.9),
        ),
    ),
    ScenarioExpect(
        "wellness_good_short",
        (
            ("всё хорошо", None, 0.9),
            ("нормально", None, 0.9),
            ("выспался", None, 0.9),
        ),
    ),
    ScenarioExpect(
        "help_request",
        (
            ("мне нужна помощь", None, 0.9),
        ),
        must_not_contain=("вызову", "позвоню"),
        no_dead_end=False,
    ),
)


class AutoCallScenarioTests(unittest.TestCase):
    def test_all_scenarios_pass_invariants(self):
        failures: list[str] = []
        for spec in SCENARIOS:
            _replies, problems, _ = _run_facade_scenario(spec)
            if problems:
                failures.append(f"{spec.name}: " + "; ".join(problems))
        if failures:
            self.fail(
                f"{len(failures)}/{len(SCENARIOS)} scenarios failed:\n"
                + "\n".join(failures),
            )

    def test_greeting_pool_has_minimum_variants(self):
        """Greeting pool must have ≥5 variants (product spec)."""
        from conversation_system.reply.pools import GREETING_POOL

        self.assertGreaterEqual(len(GREETING_POOL), 5)
        joined = " ".join(GREETING_POOL).lower()
        self.assertTrue(
            "чувствуете" in joined or "поживаете" in joined,
            msg=GREETING_POOL,
        )

    def test_silence_first_turn_is_repeat_not_anchor(self):
        spec = ScenarioExpect(
            "silence_order_check",
            (("", "empty", None),),
        )
        replies, problems, _ = _run_facade_scenario(spec)
        self.assertFalse(problems, msg=problems)
        first = replies[1].lower() if len(replies) > 1 else ""
        self.assertTrue(
            "повтор" in first or "ещё раз" in first or "еще раз" in first
            or "расслышала" in first,
            msg=replies,
        )
        self.assertNotIn("хорошо или плохо", first)

    def test_goodbye_terminal_has_no_minimal_fallback(self):
        spec = ScenarioExpect(
            "goodbye_check",
            (("всё хорошо", None, 0.9), ("до свидания", None, 0.9)),
            must_end_terminal=True,
            must_have_goodbye=True,
        )
        replies, problems, terminal = _run_facade_scenario(spec)
        self.assertFalse(problems, msg=problems)
        self.assertTrue(terminal)
        self.assertNotEqual(replies[-1], MINIMAL_FALLBACK)

    def test_bad_symptom_intensifier_triggers_record_notify_turn3(self):
        """Live 8e9a0456: «болит голова» + «сильно» + timing → record for family."""
        spec = ScenarioExpect(
            "bad_symptom_live_turn3",
            (
                ("болит голова", None, 0.9),
                ("сильно", None, 0.9),
                ("утром", None, 0.9),
            ),
            must_have_record_notify=True,
        )
        replies, problems, _ = _run_facade_scenario(spec)
        self.assertFalse(problems, msg=problems)
        notify_reply = next(
            (r for r in replies if re.search(
                r"записал|приложен|родн|близк|семь", r.lower())),
            "",
        )
        self.assertTrue(notify_reply, msg=f"replies={replies}")
        self.assertNotRegex(
            notify_reply.lower(),
            r"родные\s+получит\b",
            msg=f"grammar bug in notify: {notify_reply!r}",
        )

    def test_record_notify_pool_grammar(self):
        from conversation_system.reply.pools import RECORD_NOTIFY_POOL

        for line in RECORD_NOTIFY_POOL:
            low = line.lower()
            self.assertNotRegex(
                low,
                r"родные\s+получит\b",
                msg=f"subject-verb mismatch: {line!r}",
            )
            self.assertNotRegex(
                low,
                r"записала\s+родные\s+[^,]",
                msg=f"missing comma after записала: {line!r}",
            )


if __name__ == "__main__":
    unittest.main()
