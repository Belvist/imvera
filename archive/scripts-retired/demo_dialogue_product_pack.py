#!/usr/bin/env python3
"""Demo path: multi-symptom → product pack questions → ITS → warm close.

Usage:
  python3 scripts/demo_dialogue_product_pack.py
"""

from __future__ import annotations

from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.scenario_runner import ScenarioRunner

SCRIPT = [
    "У меня болит голова, живот болит и меня тошнит.",
    "С утра.",
    "Терпимо.",
    "Ещё тошнит.",
    "Ещё болит.",
    "Не знаю.",
]


def main() -> int:
    r = ScenarioRunner(call_id="demo-pack", elder_display_name="Анна")
    r.run([CallStarted()])
    opening = [e.text for e in r.effects if getattr(e, "text", None)]
    print("VERA:", opening[-1] if opening else "(silence)")
    for user in SCRIPT:
        print("USER:", user)
        res = r.run([user])
        for e in res.speak_effects:
            print(f"VERA [{e.intent}]:", e.text)
        if r.state.call_closed:
            break
    print("---")
    print("closed:", r.state.call_closed, "reason:", r.state.closing_reason)
    print("asks_by_family:", dict(r.state.product_asks_by_family))
    print("content_asks:", r.state.product_content_asks)
    print(
        "hangup_ok:",
        "partial_unresolved_close"
        not in [e.intent for e in r.effects if getattr(e, "intent", None)],
    )
    return 0 if r.state.call_closed and r.state.closing_reason != "partial_unresolved" else 1


if __name__ == "__main__":
    raise SystemExit(main())
