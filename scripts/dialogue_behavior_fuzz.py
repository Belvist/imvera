"""Behavior-class dialogue fuzzing — dynamics WITHOUT a model (ADR-014 safe).

We cannot predict what the client will say. Instead of enumerating phrases,
we enumerate BEHAVIOR CLASSES x DIALOGUE STATES and assert frozen invariants
for every combination:

  I1  every meaningful user turn gets a spoken outcome (never silent)
  I2  no hangup mid-probing (EndCall only via goodbye_final / partial / urgent)
  I3  no temporal loop (same onset/duration probe 3x in a row)
  I4  emergency lexicon never lands in partial_unresolved_close (no abandon)
  I5  explicit farewell closes the call within 3 turns
  I6  no exceptions / invariant violations

Phrase pools are mined from live calls (.run/traces/fs-*.jsonl, 2026-09-13)
plus systematic variants. Deterministic via --seed.

Usage:
  python3 scripts/dialogue_behavior_fuzz.py --n 200 --seed 7
  python3 scripts/dialogue_behavior_fuzz.py --n 1000 --seed 7 --dump .run/fuzz/
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from packages.dialogue_engine.effects import EndCallEffect, SpeakEffect, TimerEffect  # noqa: E402
from packages.dialogue_engine.events import CallStarted  # noqa: E402
from packages.dialogue_engine.scenario_runner import ScenarioRunner  # noqa: E402

# Behavior class -> phrase pool (live quotes first, then systematic variants).
BEHAVIORS: dict[str, list[str]] = {
    "direct_temporal": [
        "С утра.",
        "Со вчерашнего дня.",
        "После того как покушал.",
        "После еды.",
        "Вот когда утром макароны поел.",
        "Началось, когда покушал.",
        "Началось это буквально 3 ч назад.",
        "Двадцать минут назад.",
        "Уже с четырёх утра.",
        "В 4:00 утра голова заболела.",
        "Головная боль начала болеть с 6:00 утра до 8 вечера.",
    ],
    "direct_severity": [
        "Терпимая.",
        "Сильная.",
        "Боль была достаточно сильной, но она прошла.",
        "Болит чуток.",
        "Слабая.",
        "Невыносимая.",
    ],
    "direct_current": [
        "Ещё болит.",
        "Уже не болит.",
        "Сейчас уже полегче.",
        "Сейчас сердце болит.",
        "Да, ещё беспокоит.",
        "Прошла.",
    ],
    "direct_farewell": ["До свидания.", "Всё, спасибо большое, пока.", "Пока."],
    "direct_decline": ["Нет.", "Нет, обращать внимания ни на что не нужно.", "Ничего больше."],
    "vague": [
        "Ну так.",
        "Не знаю.",
        "Ага.",
        "Алло.",
        "Чего?",
        "Что?",
        "Ну, наверное.",
        "Да вроде бы нет.",
        "Я ж сказал уже всё.",
    ],
    "garbage": [
        "Поднял.",
        "Меняет.",
        "Люпимая.",
        "Спали того.",
        "Пло.",
        "Колю покушал когда?",
        "Э-э.",
        "Ну блядь, всё равно типа",
    ],
    "hostile_meta": [
        "Не, это хуйня, ты сразу всё спросил.",
        "Ты дура.",
        "Не звони больше.",
        "Почему она говорит Даниил? Откуда?",
        "Про что ты?",
        "А вы кто?",
    ],
    "topic_jump": [
        "Ноги.",
        "Таблетку забыла выпить от сосудов.",
        "Плохо спал.",
        "Забыла собаку выгулить.",
        "Надо сходить, ноги болят.",
        "У меня болит глаз сегодня.",
        "Грустно мне.",
    ],
    "multi_dump": [
        "У меня болит голова, забыла выпить таблетки от давления. У меня болит сердце.",
        "У меня болит глаз сегодня, забыла покапать в глаза лекарство. "
        "Забыла собаку выгулить. Забыла продукты купить в магазине.",
        "Чувствую себя плохо, головная боль и тошнотное состояние у меня сейчас.",
        "Живот болит после того, как покушал.",
    ],
    "contradiction": [
        "Уже не болит.",
        "Вообще-то всё нормально.",
        "Да нет, прошло уже.",
    ],
    "emergency": [
        "Сердце болит, я падаю, мне плохо, теряю сознание.",
        "Сейчас, я же говорю, я сейчас умру, я задыхаюсь уже.",
        "Вызовите скорую.",
        "Упал и не могу встать.",
        "Сердце давит.",
    ],
    "question_back": [
        "А вы кто?",
        "Зачем звоните?",
        "Про что ты?",
        "Что вы спросили?",
    ],
}

# Seed prefixes to reach distinct dialogue states before the fuzz turn.
SEEDS: dict[str, list[str]] = {
    "fresh": [],
    "wellness_answered": ["Хорошо."],
    "onset_pending": ["Живот болит."],
    "severity_pending": ["Голова болит.", "С утра."],
    "its_pending": ["Хорошо.", "Нет."],
    "multi_open": ["У меня болит голова, живот болит и меня тошнит.", "С утра."],
    "sleep_open": ["Плохо спал."],
}

EMERGENCY_LEX = (
    "падаю",
    "упал",
    "задыхаюсь",
    "теряю сознание",
    "умру",
    "умираю",
    "скорую",
    "не могу встать",
    "давит",
)

TERMINAL_OK = {"goodbye_final", "partial_unresolved_close", "close_urgent", "urgent_close"}


@dataclass
class FuzzFailure:
    seed: str
    behavior: str
    turns: list[str]
    invariant: str
    detail: str = ""
    transcript: list[str] = field(default_factory=list)


def _speak_intents(effects: list) -> list[str]:
    return [e.intent for e in effects if isinstance(e, SpeakEffect)]


def run_one(
    seed_name: str, prefix: list[str], behaviors: list[str], rng: random.Random
) -> list[FuzzFailure]:
    failures: list[FuzzFailure] = []
    r = ScenarioRunner(call_id=f"fuzz-{seed_name}", elder_display_name="Тест")
    transcript: list[str] = []
    played: list[str] = []
    try:
        res = r.run([CallStarted(), *prefix])
        for t in prefix:
            played.append(t)
            transcript.extend(f"ВЫ: {t}" for _ in [0])
            transcript.extend(f"ВЕРА: {(e.text or '')[:120]}" for e in res.speak_effects)
    except Exception as exc:  # noqa: BLE001
        failures.append(
            FuzzFailure(seed_name, "seed_prefix", prefix, "I6", f"{type(exc).__name__}: {exc}")
        )
        return failures

    temporal_run = 0
    temporal_slot = ""
    for turn_no, behavior in enumerate(behaviors):
        pool = BEHAVIORS[behavior]
        text = rng.choice(pool)
        played.append(text)
        try:
            res = r.run([text])
        except Exception as exc:  # noqa: BLE001
            failures.append(
                FuzzFailure(
                    seed_name,
                    behavior,
                    list(played),
                    "I6",
                    f"{type(exc).__name__}: {str(exc)[:200]}",
                    list(transcript) + [f"ВЫ: {text}", "<EXCEPTION>"],
                )
            )
            break
        speaks = res.speak_effects
        intents = _speak_intents(res.effects)
        transcript.append(f"ВЫ: {text}")
        transcript.extend(f"ВЕРА: {(e.text or '')[:120]}" for e in speaks)
        closed = res.state.call_closed
        ends = [e for e in res.effects if isinstance(e, EndCallEffect)]
        timers = [e for e in res.effects if isinstance(e, TimerEffect)]

        # I1: meaningful turn must produce an outcome (speak, EndCall, or an
        # explicit listen-wait timer for backchannels — never bare silence).
        if not closed and not speaks and not ends and not timers and text.strip():
            failures.append(
                FuzzFailure(
                    seed_name,
                    behavior,
                    list(played),
                    "I1",
                    "no speak and no EndCall",
                    list(transcript),
                )
            )
        # I2: hangup only via terminal intents.
        if ends and not (set(intents) & TERMINAL_OK):
            failures.append(
                FuzzFailure(
                    seed_name,
                    behavior,
                    list(played),
                    "I2",
                    f"EndCall without terminal intent: {intents}",
                    list(transcript),
                )
            )
        # I3: temporal loop guard — same question slot 3x in a row.
        slots = [e.slot for e in speaks if isinstance(e, SpeakEffect) and e.slot]
        if slots and all(("onset" in s or "duration" in s) for s in slots):
            if temporal_run > 0 and temporal_slot == slots[0]:
                temporal_run += 1
            else:
                temporal_run = 1
                temporal_slot = slots[0]
        else:
            temporal_run = 0
            temporal_slot = ""
        if temporal_run >= 3:
            failures.append(
                FuzzFailure(
                    seed_name,
                    behavior,
                    list(played),
                    "I3",
                    f"temporal probe 3x in a row: {temporal_slot}",
                    list(transcript),
                )
            )
            temporal_run = 0
        # I4: emergency must never be abandoned into partial.
        low = text.lower()
        if any(k in low for k in EMERGENCY_LEX) and "partial_unresolved_close" in intents:
            failures.append(
                FuzzFailure(
                    seed_name,
                    behavior,
                    list(played),
                    "I4",
                    "emergency abandoned via partial",
                    list(transcript),
                )
            )
        if closed:
            break
    else:
        # I5: farewell must close within the run.
        if any(t.lower().rstrip(".!") in ("до свидания", "пока") for t in played[-3:]):
            if not r.state.call_closed:
                failures.append(
                    FuzzFailure(
                        seed_name,
                        behavior,
                        list(played[-3:]),
                        "I5",
                        "farewell did not close",
                        list(transcript),
                    )
                )
    return failures


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--turns", type=int, default=3)
    ap.add_argument("--dump", type=str, default="")
    args = ap.parse_args()
    rng = random.Random(args.seed)
    seed_names = sorted(SEEDS)
    behavior_names = sorted(BEHAVIORS)
    combos: list[tuple[str, list[str]]] = []
    for _ in range(args.n):
        s = rng.choice(seed_names)
        behaviors = [rng.choice(behavior_names) for _ in range(args.turns)]
        combos.append((s, behaviors))
    failures: list[FuzzFailure] = []
    for seed_name, behaviors in combos:
        failures.extend(run_one(seed_name, SEEDS[seed_name], behaviors, rng))
    by_invariant: dict[str, int] = {}
    by_behavior: dict[str, int] = {}
    for f in failures:
        by_invariant[f.invariant] = by_invariant.get(f.invariant, 0) + 1
        by_behavior[f.behavior] = by_behavior.get(f.behavior, 0) + 1
    print(f"fuzz: {args.n} combos, {len(failures)} failures")
    print(f"by invariant: {by_invariant}")
    print(f"by behavior: {by_behavior}")
    for f in failures[:15]:
        print(f"--- [{f.invariant}] seed={f.seed} behavior={f.behavior}: {f.detail}")
        for line in f.transcript[-6:]:
            print(f"    {line}")
    if args.dump:
        out = Path(args.dump)
        out.mkdir(parents=True, exist_ok=True)
        payload = [f.__dict__ for f in failures]
        (out / f"fuzz_seed{args.seed}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(f"dumped {len(payload)} failures to {out}")
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
