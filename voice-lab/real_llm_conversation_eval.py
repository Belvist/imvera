#!/usr/bin/env python3
"""Full-path conversation eval: plan → stream → spoken → commit (Phase 5)."""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Iterator, List, Sequence

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "telephony"))

from conversation_system.integration.facade import ConversationFacade
from conversation_system.reply.spoken import resolve_spoken_reply
from conversation_system.reply.prompts import _clean_llm
from core.call_mirror import CallMirror
from core.conversation_v2_bridge import turn_plan_to_legacy
from core.events import reply_segments


@dataclass
class Scenario:
    name: str
    turns: Sequence[tuple[str, str]]
    checks: Sequence[str]


class _ScriptedLlm:
    """Deterministic LLM for harness when no API key."""

    def __init__(self, replies: Sequence[str]) -> None:
        self._replies = list(replies)
        self._idx = 0

    def chat_stream(self, _messages, **_kwargs) -> Iterator[str]:
        if self._idx >= len(self._replies):
            return iter(())
        text = self._replies[self._idx]
        self._idx += 1
        yield text


def _run_scenario(sc: Scenario) -> List[str]:
    facade = ConversationFacade()
    mirror = CallMirror()
    llm_lines = [spoken for _, spoken in sc.turns if spoken]
    mirror.llm = _ScriptedLlm(llm_lines)
    handle, greeting = facade.begin_call(
        call_id=f"eval-{sc.name}", greeting_played=True)
    mirror.commit_reply(greeting)
    spoken_log: List[str] = [greeting]
    for user_text, llm_hint in sc.turns:
        plan = facade.plan_turn(
            handle, transcript=user_text, stt_confidence=0.9)
        legacy = turn_plan_to_legacy(plan)
        legacy["text"] = user_text
        mirror.record_user(user_text)
        llm_text = ""
        if legacy.get("allow_llm") and mirror.llm is not None and llm_hint:
            llm_text = "".join(reply_segments(mirror, legacy, max_segments=3))
        spoken = resolve_spoken_reply(
            mirror,
            legacy,
            llm_text,
            transcript=user_text,
            clean_llm=_clean_llm,
        ) or plan.spoken_reply
        facade.commit_turn(handle, plan, spoken)
        mirror.commit_reply(spoken)
        spoken_log.append(spoken)
    return spoken_log


def _check(name: str, spoken_log: List[str], checks: Sequence[str]) -> bool:
    joined = "\n".join(spoken_log).lower()
    for token in checks:
        if token.startswith("!"):
            if token[1:].lower() in joined:
                print(f"FAIL {name}: forbidden '{token[1:]}' found")
                return False
        elif token.lower() not in joined:
            print(f"FAIL {name}: missing '{token}'")
            return False
    return True


SCENARIOS = (
    Scenario(
        "good_path_wrap",
        (
            ("хорошо", ""),
            ("бодрое", "Рада слышать. Как спали?"),
            ("спокойно", "Понятно. Есть планы на день?"),
            ("прогулка", "Записала для близких."),
        ),
        ("записала", "!настроение настроение"),
    ),
    Scenario(
        "side_resume_sleep",
        (
            ("хорошо", ""),
            ("бодрое", "Хорошо."),
            ("кто вы?", "Я Вера из Имвера."),
            ("понятно", "Как спали ночью?"),
            ("нормально", "Чем займётесь?"),
        ),
        ("имвера", "спал", "!кто вы"),
    ),
    Scenario(
        "no_duplicate_mood",
        (
            ("хорошо", ""),
            ("весёлое", "Отлично."),
            ("кто звонит?", "Сервис Имвера."),
            ("ясно", "Как спали?"),
        ),
        ("!настроение настроение",),
    ),
    Scenario(
        "repair_repeat",
        (
            ("нормально", "Как настроение?"),
            ("что вы спросили?", "Как настроение сегодня?"),
        ),
        ("настроение",),
    ),
    Scenario(
        "correction_spina",
        (
            ("голова болит", "Как голова?"),
            ("нет спина", "Поняла, спина. Как сейчас?"),
        ),
        ("спин",),
    ),
    Scenario(
        "barge_in_cancel_sim",
        (
            ("хорошо", ""),
            ("бодрое", "Как настроение?"),
        ),
        ("настроение",),
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    passed = 0
    for sc in SCENARIOS:
        log = _run_scenario(sc)
        ok = _check(sc.name, log, sc.checks)
        if ok:
            passed += 1
            print(f"PASS {sc.name}")
        elif args.strict:
            return 1
    print(f"{passed}/{len(SCENARIOS)} scenarios PASS")
    return 0 if passed == len(SCENARIOS) else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
