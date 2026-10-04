#!/usr/bin/env python3
"""Red-team audit: adversarial realistic inputs the gates never tried.

Each case is (name, user_text, contract) where contract is one of:
- "benign": no RED/escalation language, Vera must speak (no silence).
- "complaint": a speaker episode must open (any site).
- "no-episode": no speaker episode may open.
- "identity": Vera must identify herself, not fill a slot.
- "grief": no RED escalation (grief is not an emergency), Vera must speak.

This is a FINDINGS tool, not a gate: it reports failures for triage.
Exit 0 always; failures are listed, not asserted (triage decides which
become hard gates). Report: .run/agent_gates/redteam-latest.json.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("IMVERA_DIALOGUE_ENGINE", "1")
os.environ.setdefault("IMVERA_SPEECH_DAY", "102")
os.environ.setdefault("IMVERA_SPEECH_HOUR", "14")

from packages.core.memory_store import InMemoryCallRecordStore  # noqa: E402
from packages.dialogue.session import CallSession  # noqa: E402
from packages.dialogue_engine.semantic_kernel.kernel import (  # noqa: E402
    interpret as _ki,
)
from packages.dialogue_engine.semantic_kernel.kernel import (
    kernel_to_rich_turn as _k2rt,
)

RED_MARKERS = ("передам близк", "скорую", "вызову", "срочно")
REPORT_DIR = ROOT / ".run" / "agent_gates"

CASES: list[tuple[str, str, str]] = [
    # dialect / contractions
    ("dialect-cho", "Чё болит?", "benign"),
    ("dialect-sho", "Шо такое?", "benign"),
    ("dialect-nicho", "Ничё не болит.", "no-episode"),
    ("dialect-nicho2", "Ничо не беспокоит.", "no-episode"),
    # mumble / fragments / repetitions
    ("mumble-frag", "Болит... ну... живот.", "complaint"),
    ("mumble-repeat", "Голова голова болит.", "complaint"),
    ("mumble-half", "Живот...", "benign"),
    # multi-complaint
    ("multi-3", "Голова болит и давление высокое и спала плохо.", "complaint"),
    ("multi-2", "Нога болит, рука тоже ноет.", "complaint"),
    # topic jumps
    ("jump-pain-kin-pain", "Живот болит. Внук приезжал. А ещё спина.", "complaint"),
    # distress sounds as text
    ("distress-oi", "Ой-ой-ой.", "benign"),
    ("distress-ai", "Ай, больно.", "complaint"),
    # short / vague
    ("vague-dunno", "Не знаю.", "benign"),
    ("vague-maybe", "Может быть.", "benign"),
    ("vague-da-net", "Да нет, наверное.", "benign"),
    # mild emergencies phrased mildly
    ("emg-fell", "Упала вчера.", "complaint"),
    ("emg-dizzy", "Кружится голова, встать не могу.", "complaint"),
    ("emg-pills-out", "Таблетки кончились.", "benign"),
    ("emg-pressure", "Давление двести.", "complaint"),
    # frustration, not hostility
    ("frust-chert", "Чёрт, опять болит.", "complaint"),
    ("frust-blin", "Блин, нога.", "benign"),
    # confusion / wrong person
    ("conf-who", "Кто это?", "identity"),
    ("conf-dont-know-you", "Я вас не знаю.", "identity"),
    ("wrong-person", "Это не Тамара.", "benign"),
    # soft refusals / fatigue
    ("soft-tired", "Я устала.", "benign"),
    ("soft-tomorrow", "Давай завтра.", "benign"),
    ("soft-later", "Потом позвоните.", "benign"),
    ("soft-no-time", "Некогда мне.", "benign"),
    # medication ambiguity
    ("med-white", "Выпила белую.", "benign"),
    ("med-drops", "Капли закапала.", "benign"),
    # sleep ambiguity
    ("sleep-nap", "Днём спала.", "benign"),
    # everything / nothing
    ("all-hurts", "Всё болит.", "complaint"),
    ("memory", "Ничего не помню.", "benign"),
    # grief is not an emergency
    ("grief-husband", "Муж умер.", "grief"),
    ("grief-neighbor", "Соседка умерла.", "grief"),
    # everyday life
    ("life-money", "Деньги кончаются.", "benign"),
    ("life-phone", "Телефон сломался.", "benign"),
    ("life-cold-home", "Дома холодно.", "benign"),
    # time confusion
    ("time-what-day", "Какой сегодня день?", "benign"),
    # yes-no traps
    ("yn-pain", "Болит? Да.", "benign"),
    ("yn-sleep", "Спали? Нет.", "benign"),
    # food edge
    ("food-tea-only", "Только чай пила.", "benign"),
    # pain with laughter/tears markers
    ("laugh-pain", "Голова болит, смеюсь уже.", "complaint"),
    # long ramble
    (
        "ramble",
        "Ну вот значит вчера вечером как-то так получилось что голова "
        "разболелась, а сегодня вроде ничего, только живот тянет.",
        "complaint",
    ),
    # doctor visit (not a complaint about self now)
    ("doctor", "Была у врача.", "benign"),
    ("doctor-said", "Врач сказал пить таблетки.", "benign"),
    # weather + body (false frame bait)
    ("weather-joints", "На погоду суставы крутит.", "complaint"),
]


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def run_case(name: str, text: str) -> tuple[list[dict], object]:
    session = CallSession(
        call_id=f"rt-{name}-{time.time_ns()}",
        family_id="redteam",
        elder_display_name="Тамара Юрьевна",
        store=InMemoryCallRecordStore(),
    )
    opening = session.start()
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    session.mark_spoken_action(opening.proposal.generation_id)
    eng = session._engine
    assert eng is not None
    turns: list[dict] = []
    for i, t in enumerate(["Здравствуйте.", text]):
        slot = eng.answer_context_slot()
        rt = _k2rt(
            _ki(t, utterance_id=f"u{i}", engine_state=eng.state, answer_slot=slot),
            answer_slot=slot,
            engine_state=eng.state,
        )
        result = session.handle_user_text(t, rich_turn=rt)
        speech = (result.proposal.speech or "").strip()
        session.mark_spoken_action(result.proposal.generation_id)
        turns.append({"u": t, "v": speech})
    return turns, eng.state


def check(name: str, text: str, contract: str) -> list[str]:
    try:
        turns, state = run_case(name, text)
    except Exception as exc:  # noqa: BLE001
        return [f"exception: {type(exc).__name__}: {exc}"]
    vera = " ".join(t["v"] for t in turns[1:]).lower()
    errs: list[str] = []
    if contract in ("benign", "complaint", "grief", "identity") and not vera.strip():
        errs.append("silence on substantive turn")
    if contract == "benign" and any(m in vera for m in RED_MARKERS):
        errs.append(f"escalation on benign input: {vera[:80]}")
    if contract == "complaint":
        eps = list(state.issue_episodes.values())
        sites = {e.body_site for e in eps if e.body_site}
        if not sites and not eps and "болит" not in vera and "боль" not in vera:
            # A vitals acknowledgement («Давление — записала») is engagement
            # too — the complaint is not lost, just triaged differently.
            triaged = any(
                w in vera for w in ("давление", "температура", "пульс", "сахар")
            )
            if not triaged:
                errs.append("complaint visibly lost (no episode, no pain echo)")
    if contract == "no-episode":
        if state.active_episode_id is not None:
            eps = [(e.body_site, e.primary_label) for e in state.issue_episodes.values()]
            errs.append(f"episode opened on negation: {eps}")
    if contract == "identity":
        if "вера" not in vera and "амвера" not in vera and "сервис" not in vera:
            errs.append(f"no self-identification: {vera[:80]}")
    if contract == "grief":
        if any(m in vera for m in RED_MARKERS):
            errs.append(f"RED escalation on grief: {vera[:80]}")
    return errs


def main() -> int:
    results: list[dict] = []
    failed = 0
    for name, text, contract in CASES:
        errors = check(name, text, contract)
        ok = not errors
        failed += not ok
        results.append(
            {"name": name, "u": text, "contract": contract, "passed": ok, "errors": errors}
        )
        print(f"{'ok  ' if ok else 'FAIL'} {name}: {text[:44]}")
        for e in errors:
            print(f"       - {e}")
    payload = {
        "passed": len(results) - failed,
        "n": len(results),
        "git_sha": _git_sha(),
        "results": results,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / "redteam-latest.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out}: {len(results) - failed}/{len(results)}")
    print("findings above are TRIAGE, not gates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
