"""Adversarial dialogue eval — semantic assertions on ConversationFacade.

Run:
    python3 voice-lab/adversarial_dialogue_eval.py
    python3 voice-lab/adversarial_dialogue_eval.py --strict
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from typing import Callable, List, Sequence, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
_TELEPHONY = os.path.join(os.path.dirname(_HERE), "telephony")
sys.path.insert(0, _TELEPHONY)

from conversation_system.integration.facade import ConversationFacade  # noqa: E402

Turn = Tuple[str, float | None]
Scenario = Tuple[str, Sequence[Turn], Callable[[List[str], List[str]], Tuple[bool, str]]]


def _run_dialogue(turns: Sequence[Turn]) -> Tuple[List[str], List[str]]:
    facade = ConversationFacade()
    handle, greeting = facade.begin_call(
        call_id="adv-eval",
        greeting_played=True,
    )
    replies: List[str] = [greeting]
    users: List[str] = []
    for text, conf in turns:
        users.append(text)
        plan = facade.plan_turn(
            handle,
            transcript=text,
            stt_confidence=conf if conf is not None else 0.9,
        )
        reply = (plan.spoken_reply or "").strip()
        facade.commit_turn(handle, plan, reply)
        replies.append(reply)
    facade.end_call(handle)
    return users, replies


def _no_unhandled(_users: List[str], replies: List[str]) -> Tuple[bool, str]:
    blob = " ".join(replies).lower()
    if "fsm_fallback" in blob:
        return False, "fsm_fallback leaked into reply"
    return True, ""


def _must_contain(*words: str) -> Callable:
    def check(_users: List[str], replies: List[str]) -> Tuple[bool, str]:
        last = (replies[-1] if replies else "").lower()
        for w in words:
            if w.lower() not in last:
                return False, f"missing '{w}' in: {last[:80]}"
        return True, ""
    return check


def _must_answer_question(keywords: Sequence[str]) -> Callable:
    def check(users: List[str], replies: List[str]) -> Tuple[bool, str]:
        if not users:
            return False, "no user turns"
        q = users[-1].lower()
        r = (replies[-1] if replies else "").lower()
        if "?" not in q and not any(w in q for w in ("зачем", "почему", "кто")):
            return False, "last user turn not a question"
        if not any(k in r for k in keywords):
            return False, f"reply did not address question: {r[:100]}"
        return True, ""
    return check


def _ack_correction(_users: List[str], replies: List[str]) -> Tuple[bool, str]:
    r = (replies[-1] if replies else "").lower()
    if any(w in r for w in ("спин", "понял", "поняла", "исправ", "уточн")):
        return True, ""
    return False, f"no correction ack: {r[:100]}"


def _repair_repeats(_users: List[str], replies: List[str]) -> Tuple[bool, str]:
    if len(replies) < 2:
        return False, "need prior reply"
    prev, last = replies[-2].lower(), replies[-1].lower()
    if not prev or not last:
        return False, "empty reply"
    prev_w = set(re.findall(r"\w+", prev))
    last_w = set(re.findall(r"\w+", last))
    if not prev_w:
        return False, "no words in prev"
    overlap = len(prev_w & last_w) / max(len(prev_w), 1)
    if overlap >= 0.35:
        return True, ""
    return False, f"repair did not echo prior (overlap={overlap:.2f})"


def _choice_not_closed_by_da(users: List[str], replies: List[str]) -> Tuple[bool, str]:
    if users and users[-1].strip().lower() in ("да", "ага", "угу"):
        r = (replies[-1] if replies else "").lower()
        if "?" in r and any(w in r for w in ("утр", "вечер", "или", "какой")):
            return True, ""
        return False, "bare да closed CHOICE without re-ask"
    return True, ""


def _symptom_improved_path(_users: List[str], replies: List[str]) -> Tuple[bool, str]:
    blob = " ".join(replies).lower()
    if any(w in blob for w in ("легче", "лучше", "рада", "хорош")):
        return True, ""
    return False, "no improvement acknowledgment"


SCENARIOS: List[Scenario] = [
    (
        "correction_not_head_back",
        (
            ("всё хорошо", 0.9),
            ("голова болит", 0.9),
            ("нет, не голова, спина болит", 0.9),
        ),
        lambda u, r: (_ack_correction(u, r)[0] and _no_unhandled(u, r)[0],
                      _ack_correction(u, r)[1] or _no_unhandled(u, r)[1]),
    ),
    (
        "contradiction_on_good_path",
        (
            ("отлично, ничего не болит", 0.9),
            ("на самом деле голова ноет", 0.9),
        ),
        lambda u, r: (
            _no_unhandled(u, r)[0]
            and any(w in (r[-1] if r else "").lower()
                    for w in ("голов", "бол", "уточн", "?")),
            "expected symptom follow-up after contradiction",
        ),
    ),
    (
        "why_call_question",
        (
            ("зачем вы звоните?", 0.9),
        ),
        lambda u, r: _must_answer_question(("имвера", "звон", "близк"))(u, r),
    ),
    (
        "privacy_question",
        (
            ("всё хорошо", 0.9),
            ("вы записываете разговор?", 0.9),
        ),
        lambda u, r: _must_answer_question(("запис", "близк", "родн"))(u, r),
    ),
    (
        "repair_repeat",
        (
            ("всё хорошо", 0.9),
            ("повторите пожалуйста", 0.9),
        ),
        lambda u, r: _repair_repeats(u, r),
    ),
    (
        "ambiguous_da_after_symptom",
        (
            ("плохо", 0.9),
            ("голова болит", 0.9),
            ("да", 0.9),
        ),
        lambda u, r: (
            _no_unhandled(u, r)[0] and "?" in (r[-1] if r else ""),
            "expected follow-up after bare да on symptom path",
        ),
    ),
    (
        "resolved_symptom",
        (
            ("голова болит", 0.9),
            ("стало легче", 0.9),
        ),
        _symptom_improved_path,
    ),
    (
        "topic_switch_side_question",
        (
            ("всё хорошо", 0.9),
            ("а кто такая Имвера?", 0.9),
        ),
        lambda u, r: _must_answer_question(("имвера", "вера", "сервис"))(u, r),
    ),
    (
        "narrative_not_ignored",
        (
            ("всё нормально", 0.9),
            (
                "внучка приезжала мы чай пили долго разговаривали",
                0.9,
            ),
        ),
        lambda u, r: (
            "?" in (r[-1] if r else ""),
            "narrative should get follow-up question",
        ),
    ),
    (
        "mid_call_help_not_unhandled",
        (
            ("всё хорошо", 0.9),
            ("помогите мне", 0.9),
        ),
        _no_unhandled,
    ),
]


@dataclass
class EvalResult:
    name: str
    passed: bool
    detail: str = ""
    replies: List[str] = field(default_factory=list)


def run_eval() -> List[EvalResult]:
    results: List[EvalResult] = []
    for name, turns, checker in SCENARIOS:
        users, replies = _run_dialogue(turns)
        ok, detail = checker(users, replies)
        results.append(EvalResult(name=name, passed=ok, detail=detail, replies=replies))
    return results


def main() -> int:
    strict = "--strict" in sys.argv
    results = run_eval()
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"adversarial_dialogue_eval: {passed}/{total} PASS")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.name}")
        if not r.passed and r.detail:
            print(f"         {r.detail}")
        if not r.passed and r.replies:
            print(f"         last reply: {r.replies[-1][:120]}")
    if strict and passed < 6:
        print(f"FAIL: need at least 6/10, got {passed}")
        return 1
    if strict and passed < total:
        print(f"WARN: {total - passed} scenario(s) still failing (Phase 2)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
