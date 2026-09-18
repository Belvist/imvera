#!/usr/bin/env python3
"""Text-only dialogue soak — 100 full calls, no TTS / no SIP.

Builds questions from product pack; asserts we do not hang up unresolved,
do not re-ask known temporal for abdomen, and close warmly.

Usage:
  python3 scripts/dialogue_text_soak.py
  python3 scripts/dialogue_text_soak.py --n 100
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.scenario_runner import ScenarioRunner


@dataclass(frozen=True)
class Script:
    name: str
    turns: tuple[str, ...]
    require_substrings: tuple[str, ...] = ()
    forbid_substrings: tuple[str, ...] = ()
    forbid_intents: tuple[str, ...] = ("partial_unresolved_close",)


SCRIPTS: tuple[Script, ...] = (
    Script(
        name="multi_head_belly_nausea",
        turns=(
            "У меня болит голова, живот болит и меня тошнит.",
            "С утра.",
            "Терпимо.",
            "Ещё тошнит.",
            "Ещё болит.",
            "Не знаю.",
        ),
        require_substrings=("тошнота", "живот", "берегите"),
        forbid_substrings=("когда это началось — сегодня или раньше?",),
    ),
    Script(
        name="present_headache",
        turns=(
            "Голова болит.",
            "С утра.",
            "Терпимая.",
            "Нет, только голова.",
            "Нет.",
        ),
        require_substrings=("до свидания",),
    ),
    Script(
        name="morning_headache_past",
        turns=(
            "Хорошо, чувствую на утро что-то голова болела.",
            "Сейчас уже полегче.",
            "Нет.",
        ),
        require_substrings=("а сейчас",),
        forbid_substrings=("сильная или терпимая",),
    ),
    Script(
        name="headache_with_time_in_opening",
        turns=(
            "Голова болит с утра.",
            "Терпимо.",
            "Только голова.",
            "Нет.",
        ),
        forbid_substrings=("когда начала болеть голова",),
    ),
    Script(
        name="good_day",
        turns=("Хорошо, всё нормально.", "Нет."),
        require_substrings=("до свидания",),
    ),
    Script(
        name="sleep_bad",
        turns=("Плохо спал.", "Несколько ночей.", "Днём устаю.", "Нет."),
        require_substrings=("до свидания",),
    ),
    Script(
        name="belly_only",
        turns=("Живот болит.", "С утра.", "Ещё болит.", "Нет."),
        require_substrings=("живот",),
    ),
    Script(
        name="ne_znayu_warm",
        turns=(
            "Голова болит.",
            "С утра.",
            "Сильная.",
            "Только голова.",
            "Не знаю.",
        ),
        require_substrings=("берегите",),
        forbid_substrings=("не получилось узнать",),
    ),
    Script(
        name="mvp_egor_like",
        turns=(
            "Чувствую себя плохо, голова утром болела.",
            "Утром голова болела, а сейчас живот болит.",
            "Живот только сейчас заболел.",
            "Почти прошла уже.",
            "Да, более-менее нормально.",
            "Нет, всё норм.",
        ),
        require_substrings=("до свидания",),
    ),
    Script(
        name="allo_then_answer",
        turns=("Голова болит.", "Алло.", "С утра.", "Терпимо.", "Нет.", "Нет."),
        forbid_intents=("partial_unresolved_close",),
    ),
)


def _run_one(script: Script, call_id: str) -> tuple[bool, str]:
    r = ScenarioRunner(call_id=call_id, elder_display_name="Анна")
    r.run([CallStarted()])
    for user in script.turns:
        r.run([user])
        if r.state.call_closed:
            break
    # Soft push to close if still open after script
    for extra in ("Нет.", "До свидания."):
        if r.state.call_closed:
            break
        r.run([extra])

    texts = " ".join(e.text for e in r.effects if getattr(e, "text", None)).lower()
    intents = [e.intent for e in r.effects if getattr(e, "intent", None)]

    for bad in script.forbid_intents:
        if bad in intents:
            return False, f"{script.name}: forbidden intent {bad}"

    for needle in script.require_substrings:
        if needle.lower() not in texts:
            return False, f"{script.name}: missing «{needle}» in spoken text"

    for needle in script.forbid_substrings:
        if needle.lower() in texts:
            return False, f"{script.name}: forbidden «{needle}» still spoken"

    if not r.state.call_closed:
        return False, f"{script.name}: call not closed"

    return True, "ok"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=100, help="number of text calls")
    args = parser.parse_args()
    n = max(1, args.n)

    ok = 0
    failures: list[str] = []
    for i in range(n):
        script = SCRIPTS[i % len(SCRIPTS)]
        passed, detail = _run_one(script, call_id=f"soak-{i:03d}-{script.name}")
        if passed:
            ok += 1
        else:
            failures.append(f"#{i}: {detail}")
            if len(failures) >= 12:
                break

    print(f"text_soak: {ok}/{n} passed (scripts={len(SCRIPTS)}, no TTS)")
    if failures:
        print("FAILURES:")
        for line in failures:
            print(" ", line)
        return 1
    print("VERIFIED: all text calls closed without unresolved hangup")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
