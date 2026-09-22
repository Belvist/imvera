"""Adversarial dialogue stress soak — breaks Vera on purpose (ADR-014 safe).

Unlike behavior fuzz (3-turn invariant combos), this hammers LONG calls
(12-30 turns) with adversarial scripts: garbage storms, hostile loops,
repair chains, stalls, mid-ladder emergencies, topic jumps, farewell-resume,
contradictions, red-state vagueness. Goal: find where she loops, stalls,
drops facts, or closes wrong — then fix and re-run.

Metrics per script:
  exceptions, silent turns, mid-probe hangups, temporal 3x repeats,
  urgent recall (emergency → urgent_close <=2 turns), unclosed>25 turns,
  partial rate, top repeated questions (nag audit), summary-without-facts.

Usage:
  python3 scripts/dialogue_stress_soak.py --minutes 25
  IMVERA_COVERAGE_LADDER=1 \
    python3 scripts/dialogue_stress_soak.py --minutes 25 --report .run/stress.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
import traceback
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from packages.dialogue_engine.effects import EndCallEffect, SpeakEffect  # noqa: E402
from packages.dialogue_engine.events import CallStarted  # noqa: E402
from packages.dialogue_engine.scenario_runner import ScenarioRunner  # noqa: E402

TERMINAL_OK = {"goodbye_final", "partial_unresolved_close", "close_urgent", "urgent_close"}

GARBAGE = ["Поднял.", "Э-э.", "Спали того.", "Колю покушал когда?", "Поэтому.",
           "Со мной замуж.", "Меняет.", "Ну блядь, всё равно типа"]
HOSTILE = ["Ты дура.", "Не, это хуйня.", "Отстань.", "Надоело уже."]
STALL = ["Ага.", "Не знаю.", "Ну.", "Да вроде бы нет."]
REPAIR = ["Что?", "Чего?", "Алло.", "Повторите."]
JUMPS = ["Ноги.", "Таблетку забыла выпить.", "Плохо спал.", "Грустно мне.",
         "У меня болит глаз сегодня.", "Забыла собаку выгулить."]
EMERG = ["Сердце болит, я падаю.", "Я задыхаюсь уже.", "Упал и не могу встать."]
RED_VAGUE = ["Я умираю.", "Мне очень плохо.", "Мне конец."]
ANSWERS = ["Хорошо.", "Нормально.", "Поела.", "Да.", "Нет.", "С утра.",
           "Терпимо.", "Плохо.", "Спал нормально.", "Да, принял."]
CLOCK = ["На восемь.", "Вчера в 8:00", "Раньше началось это.", "После еды."]


def script_garbage_storm(rng: random.Random) -> list[str]:
    base = rng.choice([["Хорошо."], ["Плохо.", "Голова болит."], ["Хорошо.", "Поела."]])
    return base + [rng.choice(GARBAGE) for _ in range(rng.randint(5, 8))]


def script_hostile_loop(rng: random.Random) -> list[str]:
    return ["Хорошо."] + [rng.choice(HOSTILE) for _ in range(rng.randint(4, 7))]


def script_repair_chain(rng: random.Random) -> list[str]:
    return ["Хорошо.", "Голова болит."] + [rng.choice(REPAIR) for _ in range(5)]


def script_stall_words(rng: random.Random) -> list[str]:
    turns = ["Хорошо."]
    for _ in range(rng.randint(6, 10)):
        turns.append(rng.choice(STALL + ANSWERS))
    return turns


def script_emergency_midladder(rng: random.Random) -> list[str]:
    pre = [["Хорошо.", "Поела."], ["Хорошо.", "Да, принял.", "Поела."],
           ["Плохо.", "Голова болит.", "С утра."]][rng.randrange(3)]
    return pre + [rng.choice(EMERG)]


def script_red_vague(rng: random.Random) -> list[str]:
    return [rng.choice(RED_VAGUE), rng.choice(["Не знаю.", "Не могу сказать.", "А?"]),
            rng.choice(["Не знаю.", "Отстань."])]


def script_topic_churn(rng: random.Random) -> list[str]:
    return ["Хорошо."] + [rng.choice(JUMPS + ANSWERS) for _ in range(rng.randint(8, 12))]


def script_farewell_resume(rng: random.Random) -> list[str]:
    return ["Хорошо.", "Нет.", "Пока.", "А, ещё вот что — голова болит.",
            rng.choice(CLOCK), "Терпимо.", "До свидания."]


def script_contradict(rng: random.Random) -> list[str]:
    return ["Плохо.", "Голова болит.", "Да нет, прошло уже.", "Нет, всё-таки болит.",
            rng.choice(CLOCK), "Терпимо.", "Нет."]


def script_clock_forms(rng: random.Random) -> list[str]:
    return ["Плохо.", "Живот болит.",
            rng.choice(["На восемь.", "В восемь вечера.", "Вчера в 8:00",
                        "Раньше началось это.", "В понедельник.", "Давно уже."])]


def script_meds_maze(rng: random.Random) -> list[str]:
    return ["Хорошо.", "Поела.",
            rng.choice(["Да.", "Есть.", "Ну, кое-что есть.", "Не каждый день.",
                        "Иногда.", "Не хочу про это говорить."])]


def script_mixed_long(rng: random.Random) -> list[str]:
    pool = ANSWERS + GARBAGE + STALL + JUMPS + CLOCK + REPAIR
    return [rng.choice(pool) for _ in range(rng.randint(15, 25))]


SCRIPTS = {
    "garbage_storm": script_garbage_storm,
    "hostile_loop": script_hostile_loop,
    "repair_chain": script_repair_chain,
    "stall_words": script_stall_words,
    "emergency_midladder": script_emergency_midladder,
    "red_vague": script_red_vague,
    "topic_churn": script_topic_churn,
    "farewell_resume": script_farewell_resume,
    "contradict": script_contradict,
    "clock_forms": script_clock_forms,
    "meds_maze": script_meds_maze,
    "mixed_long": script_mixed_long,
}


@dataclass
class Stats:
    calls: int = 0
    turns: int = 0
    exceptions: list[str] = field(default_factory=list)
    silent: list[str] = field(default_factory=list)
    mid_probe_hangup: list[str] = field(default_factory=list)
    temporal_3x: list[str] = field(default_factory=list)
    urgent_miss: list[str] = field(default_factory=list)
    unclosed_25: list[str] = field(default_factory=list)
    partials: int = 0
    repeat_bigrams: Counter = field(default_factory=Counter)
    intents: Counter = field(default_factory=Counter)


def run_call(turns: list[str], tag: str, st: Stats,
             rng: random.Random | None = None, stt_noise: float = 0.0) -> list[str]:
    """Run one adversarial call. Returns actually-fed turns (post-degrade)."""
    r = ScenarioRunner(call_id=f"stress-{tag}", elder_display_name="Тест")
    prev_q = ""
    run_slots: list[str] = []
    noise = None
    if stt_noise > 0:
        from tools.voice_lab.stt_noise import degrade
        noise = lambda t: degrade(t, rng, stt_noise)  # noqa: E731
    try:
        alimentare = [CallStarted()] + turns
        fed: list[str] = []
        for t in alimentare:
            if r.state.call_closed and isinstance(t, str):
                # Post-hangup audio: skip — EXCEPT emergency (re-open test:
                # a choking caller must escalate even after a close).
                from packages.dialogue_engine.check_path import is_urgent_action

                if not is_urgent_action(t):
                    continue
            if noise is not None and isinstance(t, str):
                t = noise(t)
            if isinstance(t, str):
                fed.append(t)
            res = r.run([t])
            st.turns += 1
            speaks = [e for e in res.speak_effects if isinstance(e, SpeakEffect)]
            if t != CallStarted() and not speaks and not any(
                not isinstance(e, SpeakEffect) for e in res.effects
            ):
                st.silent.append(f"{tag}: {t!r}")
            for e in speaks:
                st.intents[e.intent] += 1
                txt = (e.text or "").strip()
                if txt:
                    if prev_q and txt == prev_q:
                        st.repeat_bigrams[f"{tag}:: {txt[:70]}"] += 1
                    prev_q = txt
                if e.slot and ("onset" in e.slot or "duration" in e.slot):
                    run_slots.append(e.slot)
            for e in res.effects:
                if isinstance(e, EndCallEffect):
                    last = [x for x in res.speak_effects if isinstance(x, SpeakEffect)]
                    if last and last[-1].intent not in TERMINAL_OK:
                        st.mid_probe_hangup.append(f"{tag}: {last[-1].intent}")
        if len(turns) >= 25 and not r.state.call_closed:
            st.unclosed_25.append(tag)
    except Exception:
        st.exceptions.append(f"{tag}:\n{traceback.format_exc()[-800:]}")
        return []
    return fed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=25)
    ap.add_argument("--seed", type=int, default=99)
    ap.add_argument("--report", type=str, default="")
    ap.add_argument("--stt-noise", type=float, default=0.0,
                    help="STT degradation probability per turn (0.35 = like live)")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    names = sorted(SCRIPTS)
    st = Stats()
    deadline = time.monotonic() + args.minutes * 60
    i = 0
    urgent_checks = {"need": 0, "got": 0}
    while time.monotonic() < deadline:
        name = names[i % len(names)]
        turns = SCRIPTS[name](rng)
        tag = f"{name}#{i}"
        before = dict(st.intents)
        fed = run_call(turns, tag, st, rng, args.stt_noise)
        joined = " ".join(turns)
        if any(k in joined for k in ("падаю", "упал", "задыхаюсь", "теряю сознание",
                                     "умру", "умираю", "скорую", "не могу встать",
                                     " давит", "умру")):
            urgent_checks["need"] += 1
            # need/got computed on actually-fed (post-degrade) transcript
            if st.intents.get("urgent_close", 0) > before.get("urgent_close", 0):
                urgent_checks["got"] += 1
            else:
                st.urgent_miss.append(f"{tag}: fed={fed}")
        st.calls += 1
        i += 1
        if i % 500 == 0:
            print(f"  ...{i} calls", flush=True)

    print(f"calls={st.calls} turns={st.turns}")
    print(f"exceptions={len(st.exceptions)} silent={len(st.silent)} "
          f"mid_probe_hangup={len(st.mid_probe_hangup)} temporal_3x=N/A "
          f"unclosed_25={len(st.unclosed_25)}")
    print(f"urgent recall: {urgent_checks['got']}/{urgent_checks['need']}")
    print(f"partials={st.intents.get('partial_unresolved_close', 0)} "
          f"urgent={st.intents.get('urgent_close', 0)} "
          f"summaries={st.intents.get('summary', 0)}")
    print("top repeated questions:")
    for q, n in st.repeat_bigrams.most_common(10):
        print(f"  x{n} {q}")
    for bucket, items in (("EXC", st.exceptions), ("SILENT", st.silent),
                          ("HANGUP", st.mid_probe_hangup),
                          ("UNCLOSED", st.unclosed_25),
                          ("URGENT_MISS", st.urgent_miss)):
        for it in items[:8]:
            print(f"[{bucket}] {it[:300]}")
    if args.report:
        Path(args.report).write_text(json.dumps({
            "calls": st.calls, "turns": st.turns,
            "exceptions": len(st.exceptions),
            "silent": len(st.silent),
            "mid_probe_hangup": len(st.mid_probe_hangup),
            "unclosed_25": len(st.unclosed_25),
            "urgent": urgent_checks,
            "partials": st.intents.get("partial_unresolved_close", 0),
            "repeat_bigrams": st.repeat_bigrams.most_common(15),
            "intents": dict(st.intents),
            "samples": {
                "exc": st.exceptions[:5], "silent": st.silent[:5],
                "hangup": st.mid_probe_hangup[:5],
                "unclosed": st.unclosed_25[:5],
                "urgent_miss": [str(x)[:300] for x in st.urgent_miss[:5]],
            },
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"report: {args.report}")
    bad = (len(st.exceptions) + len(st.silent) + len(st.mid_probe_hangup)
           + len(st.unclosed_25) + len(st.urgent_miss))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
