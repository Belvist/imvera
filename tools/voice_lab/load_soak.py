"""Load soak — 100 consecutive full calls through CallSession + DialogueEngine.

Reactive driver answers by intent (robust to ordering), personas cover the
wellness segment (good / so-so middles / bad / garbage / mixed subjects /
correction) plus standard flows. Measures completion, per-turn engine
latency vs SLO (p50<1s/p95<=2s, text path — no STT/TTS audio), cross-call
isolation, RSS drift, zero exceptions.

Usage:
  python3 tools/voice_lab/load_soak.py --calls 100 [--parallel 8] [--run-id X]
Artifacts: .run/load_soak/<run_id>/{summary.json,calls.jsonl}
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RUN_ROOT = ROOT / ".run" / "load_soak"
MAX_TURNS = 30


def _env() -> None:
    os.environ["IMVERA_DIALOGUE_ENGINE"] = "1"
    os.environ["IMVERA_COVERAGE_LADDER"] = "1"


# intent -> reply. Unknown intents fall back to a safe no-op answer.
BASE_REPLIES = {
    "opening_wellness": None,  # filled per persona
    "clarify_wellness": None,
    "probe_concern": "Голова болит.",
    "probe_concern_options": "Голова.",
    "probe_duration": "С утра.",
    "probe_severity": "Терпимо.",
    "probe_current": "Ещё болит.",
    "check_mood": "Нормальное.",
    "check_sleep": "Спал нормально.",
    "check_plans": "Дома буду.",
    "background_nutrition": "Поела.",
    "background_medication": "Нет.",
    "background_mood": "Ничего не тревожит.",
    "background_sleep": "Выспалась.",
    "background_plans": "Ничего особенного.",
    "important_to_share": "Нет.",
    "summary": "До свидания.",
    "goodbye_confirm": "Да.",
}

PERSONAS: list[dict] = [
    {"name": "good", "wellness": "Хорошо."},
    {"name": "good-long", "wellness": "Хорошо, настроение нормальное, всё хорошо."},
    {"name": "soso-tak-sebe", "wellness": "Мне так себе.", "concern": "Нет, ничего не болит."},
    {"name": "soso-bolee", "wellness": "По состоянию мне более-менее."},
    {"name": "soso-shatko", "wellness": "Ни шатко ни валко."},
    {"name": "soso-koe-kak", "wellness": "Кое-как."},
    {"name": "bad", "wellness": "Плохо."},
    {"name": "garbage", "wellness": "Абракадабра.", "wellness2": "Хорошо."},
    {"name": "mixed", "wellness": "У мужа плохо, а у меня более-менее."},
    {"name": "correction", "wellness": "Плохо… хотя нет, хорошо."},
    {"name": "dontknow", "wellness": "Не знаю.", "wellness2": "Нормально."},
    {"name": "complaint", "wellness": "Голова болит."},
]


@dataclass
class CallRecord:
    call_id: str
    persona: str
    ok: bool
    turns: int
    intents: list[str] = field(default_factory=list)
    turn_ms: list[float] = field(default_factory=list)
    error: str = ""
    consecutive_break: bool = False


def _build_turn(session, text: str, uid: str):
    from packages.dialogue.interpretation import (
        interpret_user_turn,
        to_turn_interpretation,
    )
    from packages.dialogue_engine.semantic_kernel.kernel import (
        interpret as kernel_interpret,
    )
    from packages.dialogue_engine.semantic_kernel.kernel import (
        kernel_to_rich_turn,
    )

    answer_slot = None
    try:
        answer_slot = session._engine.answer_context_slot()
    except Exception:
        pass
    kr = kernel_interpret(
        text, utterance_id=uid, engine_state=session._engine.state,
        answer_slot=answer_slot,
    )
    rich = kernel_to_rich_turn(
        kr, answer_slot=answer_slot, engine_state=session._engine.state
    )
    interp = interpret_user_turn(session.state, text)
    contract = to_turn_interpretation(
        session.state, session.turn_id + 1, text, interp,
        state_version=session.state.state_version,
    )
    return interp, contract, rich


def run_call(idx: int) -> CallRecord:
    from packages.contracts.enums import AsrQuality
    from packages.core.memory_store import InMemoryCallRecordStore
    from packages.dialogue.session import CallSession

    persona = PERSONAS[idx % len(PERSONAS)]
    call_id = f"soak-{idx:03d}-{persona['name']}"
    rec = CallRecord(call_id=call_id, persona=persona["name"], ok=False, turns=0)
    try:
        session = CallSession(
            call_id=call_id, family_id="soak",
            elder_display_name="Тест",
            store=InMemoryCallRecordStore(),
        )
        opening = session.start()
        if opening.speak_effect is not None:
            rec.intents.append(opening.speak_effect.intent)
            session._playout_meta[opening.speak_effect.generation_id] = (
                opening.speak_effect.generation, opening.speak_effect.question_id)
            session._playout_effect_meta[opening.speak_effect.generation_id] = (
                opening.speak_effect.effect_id)
            session._engine.on_playout_started(
                opening.speak_effect.generation, opening.speak_effect.question_id)
            session.mark_spoken_action(opening.speak_effect.generation_id)

        used_wellness2 = False
        for t in range(MAX_TURNS):
            pending = session._engine.state.goodbye_confirmed
            last_intent = rec.intents[-1] if rec.intents else ""
            if last_intent == "goodbye_final" and pending:
                rec.ok = True
                break
            if last_intent in ("opening_wellness", "clarify_wellness"):
                key = "wellness2" if (used_wellness2 is False and "wellness2" in persona
                                      and last_intent == "clarify_wellness") else "wellness"
                if key == "wellness2":
                    used_wellness2 = True
                text = persona.get(key, persona["wellness"])
            elif last_intent == "probe_concern" and "concern" in persona:
                text = persona["concern"]
            else:
                text = BASE_REPLIES.get(last_intent, "Хорошо.")
            uid = f"u-{t}"
            interp, contract, rich = _build_turn(session, text, uid)
            t0 = time.perf_counter()
            result = session.handle_user_text(
                text, interp=interp, contract=contract, utterance_id=uid,
                asr_quality=AsrQuality.GOOD, rich_turn=rich)
            rec.turn_ms.append((time.perf_counter() - t0) * 1000.0)
            rec.turns += 1
            if result.speak_effect is not None:
                rec.intents.append(result.speak_effect.intent)
                if result.speak_effect.marks_question:
                    session._playout_meta[result.speak_effect.generation_id] = (
                        result.speak_effect.generation,
                        result.speak_effect.question_id)
                    session._playout_effect_meta[result.speak_effect.generation_id] = (
                        result.speak_effect.effect_id)
                    session._engine.on_playout_started(
                        result.speak_effect.generation,
                        result.speak_effect.question_id)
                session.mark_spoken_action(result.speak_effect.generation_id)
            follow = session.pop_engine_playout_followup()
            while follow is not None:
                if follow.speak_effect is not None:
                    rec.intents.append(follow.speak_effect.intent)
                    session.mark_spoken_action(
                        follow.speak_effect.generation_id)
                follow = session.pop_engine_playout_followup()
        else:
            rec.error = f"no goodbye_final in {MAX_TURNS} turns: {rec.intents[-3:]}"
        if not rec.ok and not rec.error:
            rec.error = f"ended without goodbye: {rec.intents[-3:]}"
        # isolation: fresh session must not see previous caller's slots
        if session._engine.state.call_id != call_id:
            rec.ok = False
            rec.error = (rec.error + " | call_id bleed").strip(" |")
    except Exception as exc:  # noqa: BLE001 — exceptions are the metric
        rec.error = f"{type(exc).__name__}: {exc}"
    return rec


def _pct(v: list[float], q: float) -> float:
    s = sorted(v)
    return s[min(len(s) - 1, int(len(s) * q))] if s else float("nan")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--calls", type=int, default=100)
    ap.add_argument("--parallel", type=int, default=1)
    ap.add_argument("--run-id", default="")
    args = ap.parse_args(argv)
    _env()
    run_id = args.run_id or datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    out = RUN_ROOT / run_id
    out.mkdir(parents=True, exist_ok=True)

    def _rss_mb() -> int:
        try:
            out = subprocess.run(
                ["ps", "-o", "rss=", "-p", str(os.getpid())],
                capture_output=True, text=True, timeout=10,
            ).stdout.strip().split()[0]
            return int(out) // 1024
        except Exception:
            return -1

    rss0 = _rss_mb()
    t0 = time.monotonic()
    records: list[CallRecord] = []
    if args.parallel <= 1:
        for i in range(args.calls):
            records.append(run_call(i))
    else:
        with ThreadPoolExecutor(max_workers=args.parallel) as pool:
            futs = {pool.submit(run_call, i): i for i in range(args.calls)}
            ordered: dict[int, CallRecord] = {}
            for fut in as_completed(futs):
                ordered[futs[fut]] = fut.result()
            records = [ordered[i] for i in range(args.calls)]
    wall = time.monotonic() - t0
    rss1 = _rss_mb()

    ok = sum(1 for r in records if r.ok)
    # longest unbroken consecutive streak (ADR-014 asks for consecutive)
    best = cur = 0
    for r in records:
        cur = cur + 1 if r.ok else 0
        best = max(best, cur)
    all_ms = [m for r in records for m in r.turn_ms]
    by_persona: dict[str, dict] = {}
    for r in records:
        d = by_persona.setdefault(r.persona, {"calls": 0, "ok": 0})
        d["calls"] += 1
        d["ok"] += 1 if r.ok else 0
    errs = {}
    for r in records:
        if not r.ok:
            errs[r.error[:100]] = errs.get(r.error[:100], 0) + 1
    summary = {
        "run_id": run_id, "calls": args.calls, "parallel": args.parallel,
        "ok": ok, "failed": args.calls - ok,
        "consecutive_best": best, "consecutive_required": args.calls,
        "turns": len(all_ms),
        "turn_ms_p50": round(_pct(all_ms, 0.5), 2),
        "turn_ms_p95": round(_pct(all_ms, 0.95), 2),
        "turn_ms_max": round(max(all_ms), 2) if all_ms else 0,
        "slo_p50_1000": _pct(all_ms, 0.5) < 1000 if all_ms else False,
        "slo_p95_2000": _pct(all_ms, 0.95) <= 2000 if all_ms else False,
        "wall_s": round(wall, 1), "calls_per_s": round(args.calls / wall, 2),
        "rss_mb_before": rss0, "rss_mb_after": rss1,
        "by_persona": by_persona, "errors": errs,
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (out / "calls.jsonl").open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps({
                "call_id": r.call_id, "persona": r.persona, "ok": r.ok,
                "turns": r.turns, "intents": r.intents, "error": r.error,
                "turn_ms_max": round(max(r.turn_ms), 2) if r.turn_ms else 0,
            }, ensure_ascii=False) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"artifacts: {out}")
    return 0 if ok == args.calls else 1


if __name__ == "__main__":
    raise SystemExit(main())
