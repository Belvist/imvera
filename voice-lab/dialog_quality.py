"""Dialogue quality harness — ConversationFacade spoken path (prod engine).

Uses the same facade as live telephony (no legacy Agent).

Run:
    python3 voice-lab/dialog_quality.py            # print summary, exit 0
    python3 voice-lab/dialog_quality.py --strict  # exit 1 on scenario fail
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Sequence, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
_TELEPHONY = os.path.join(os.path.dirname(_HERE), "telephony")
sys.path.insert(0, _TELEPHONY)

from conversation_system.integration.facade import ConversationFacade  # noqa: E402
from conversation_system.reply.guards import (  # noqa: E402
    MINIMAL_FALLBACK,
    _ACTION_PROMISE_RE,
    looks_like_rescue_framing,
    reply_looks_broken,
)
from conversation_system.variety.dedupe import reply_too_similar  # noqa: E402

Turn = Tuple[str, str | None, float | None]
Scenario = Tuple[str, Sequence[Turn]]

SCENARIOS: List[Scenario] = [
    ("wellness_good_path", [
        ("всё хорошо", None, 0.9),
        ("настроение хорошее", None, 0.9),
        ("спала нормально", None, 0.9),
        ("пойду в магазин", None, 0.9),
        ("да", None, 0.9),
    ]),
    ("wellness_medium", [
        ("ну так себе", None, 0.9),
        ("устала немного", None, 0.9),
        ("спала прерывисто", None, 0.9),
        ("ничего особенного", None, 0.9),
        ("да", None, 0.9),
    ]),
    ("symptom_bad_path", [
        ("плохо, устала", None, 0.9),
        ("голова ноет", None, 0.9),
        ("терпимо", None, 0.9),
        ("утром", None, 0.9),
        ("да", None, 0.9),
    ]),
    ("symptom_improvement", [
        ("голова болит", None, 0.9),
        ("стало легче", None, 0.9),
        ("да", None, 0.9),
    ]),
    ("critical_fall", [
        ("я упал и не могу встать", None, 0.9),
    ]),
    ("safety_confirm_yes", [
        ("голова сильно болит", None, 0.9),
        ("да", None, 0.9),
        ("стало легче", None, 0.9),
    ]),
    ("positive_not_red", [
        ("отлично, ничего не болело", None, 0.9),
        ("настроение хорошее", None, 0.9),
        ("спала хорошо", None, 0.9),
        ("да", None, 0.9),
    ]),
    ("closing_direct", [
        ("всё хорошо", None, 0.9),
        ("до свидания", None, 0.9),
    ]),
    ("refusal_wrap", [
        ("всё нормально", None, 0.9),
        ("нет, спасибо", None, 0.9),
    ]),
    ("greeting_back", [
        ("здравствуйте", None, 0.9),
        ("хорошо", None, 0.9),
    ]),
]

CONVERSATIONAL_SCENARIOS: List[Scenario] = [
    ("silence_ladder", [
        ("", "empty", None),
        ("", "empty", None),
        ("", "empty", None),
    ]),
    ("low_conf_anchor", [
        ("", "low_conf", 0.35),
        ("хорошо", None, 0.9),
    ]),
    ("echo_turn", [
        ("", "echo", None),
        ("всё хорошо", None, 0.9),
    ]),
    ("repair_repeat", [
        ("повторите пожалуйста", None, 0.9),
        ("хорошо", None, 0.9),
    ]),
    ("side_question", [
        ("какое сегодня число?", None, 0.9),
        ("спасибо", None, 0.9),
        ("всё хорошо", None, 0.9),
    ]),
    ("narrative_story", [
        (
            "Внучка приезжала, мы чай пили на кухне и долго разговаривали",
            None,
            0.9,
        ),
        ("да", None, 0.9),
    ]),
    ("short_acks", [
        ("да", None, 0.9),
        ("ага", None, 0.9),
        ("хорошо", None, 0.9),
    ]),
    ("negated_fall_ok", [
        ("я не упал", None, 0.9),
        ("всё хорошо", None, 0.9),
    ]),
]


def _check_reply(
    reply: str,
    *,
    metrics: Dict[str, int],
    recent: List[str],
) -> List[str]:
    problems: List[str] = []
    text = (reply or "").strip()
    if not text:
        problems.append("  empty reply")
        return problems

    if text.strip() == MINIMAL_FALLBACK.rstrip("."):
        problems.append(f"  dead-end minimal: {text!r}")
        metrics["dead_end"] = metrics.get("dead_end", 0) + 1

    metrics["turns"] += 1
    if text.count("?") > 1:
        metrics["double_q"] += 1
        problems.append(f"  double question: {text!r}")

    if _ACTION_PROMISE_RE.search(text) or looks_like_rescue_framing(text):
        metrics["promise_count"] += 1
        problems.append(f"  promise/rescue: {text!r}")

    if reply_looks_broken(text):
        problems.append(f"  broken reply: {text!r}")

    for prev in recent[-5:]:
        if reply_too_similar(text, prev):
            metrics["repeat_rate"] += 1
            problems.append(f"  repeat vs previous: {text!r}")
            break

    if "?" in text:
        metrics["total_questions"] += 1

    recent.append(text)
    return problems


def run_scenario(
    name: str,
    turns: Sequence[Turn],
    *,
    metrics: Dict[str, int],
) -> Tuple[bool, List[str], List[str]]:
    facade = ConversationFacade()
    handle, _greeting = facade.begin_call(
        call_id=name,
        greeting_played=True,
    )
    problems: List[str] = []
    replies: List[str] = []
    recent: List[str] = []

    for text, reason, conf in turns:
        plan = facade.plan_turn(
            handle,
            transcript=text,
            reason=reason,
            stt_confidence=conf,
        )
        reply = plan.spoken_reply or ""
        replies.append(reply)
        problems.extend(_check_reply(reply, metrics=metrics, recent=recent))
        facade.commit_turn(handle, plan, reply)

    facade.end_call(handle)
    return len(problems) == 0, problems, replies


def _run_section(
    title: str,
    scenarios: Sequence[Scenario],
    metrics: Dict[str, int],
    results: List[Tuple[str, bool, List[str]]],
) -> None:
    print(f"\n=== {title} ===")
    for name, turns in scenarios:
        ok, problems, _ = run_scenario(name, turns, metrics=metrics)
        results.append((name, ok, problems))
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        for p in problems:
            print(p)


def main() -> int:
    strict = "--strict" in sys.argv
    if "--help" in sys.argv:
        print(__doc__)
        return 0

    metrics: Dict[str, int] = {
        "repeat_rate": 0,
        "forced_topic": 0,
        "double_q": 0,
        "promise_count": 0,
        "turns": 0,
        "intent_repetitions": 0,
        "total_questions": 0,
        "topic_drifts": 0,
    }
    results: List[Tuple[str, bool, List[str]]] = []

    _run_section("CHECK-IN / SAFETY", SCENARIOS, metrics, results)
    _run_section(
        "CONVERSATIONAL (Track A)",
        CONVERSATIONAL_SCENARIOS,
        metrics,
        results,
    )

    total = metrics["turns"] or 1
    print("\n--- МЕТРИКИ (ConversationFacade) ---")
    print(f"ходов                 {metrics['turns']}")
    print(f"повторов              {metrics['repeat_rate']}"
          f" ({metrics['repeat_rate'] / total:.0%} ходов)")
    print(f"форсированных тем    {metrics['forced_topic']}")
    print(f"двойных вопросов     {metrics['double_q']}")
    print(f"обещаний             {metrics['promise_count']}")
    print(f"повтор интентов      {metrics['intent_repetitions']}"
          f" ({metrics['intent_repetitions'] / total:.0%} ходов)")
    qpr = metrics["total_questions"] / total
    print(f"вопросов на реплику   {qpr:.2f}")
    print(f"сдвигов темы         {metrics['topic_drifts']}")

    failures = [n for n, ok, _ in results if not ok]
    print(f"\nсценариев: {len(results) - len(failures)}/{len(results)} PASS")
    if strict and failures:
        print(f"FAILED: {failures}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
