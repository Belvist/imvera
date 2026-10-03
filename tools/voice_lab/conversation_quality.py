#!/usr/bin/env python3
"""Conversation-quality metrics over REAL call traces (and text replays).

Purpose: make "Вера стала разговаривать по-человечески" a measured claim
instead of an opinion. Reads existing trace JSONL (no new runtime owner, no
state), pairs every Vera phrase with the user speech that preceded it and
reports:

  turns             substantive user turns per call (median/p25/p75)
  reaction_rate     Vera turns that pick up at least one content word the
                    person just said
  question_only     Vera turns that ask something without reacting first
  verbatim_reask    Vera turns whose text repeats an earlier Vera turn in the
                    same call
  close_no_reaction calls that end without Vera reacting to the last thing the
                    person said

Boundary: this measures *text* that reached the renderer trace. It is not
acoustic warmth, not prosody, not comprehension. Blind listener ratings stay a
separate, human gate.

Usage:
  python3 tools/voice_lab/conversation_quality.py --traces-dir .run/traces
  python3 tools/voice_lab/conversation_quality.py --limit 40 --json out.json
  python3 tools/voice_lab/conversation_quality.py --call fs-84260140 --show
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Utterances that are not answers and carry no content to react to.
BACKCHANNEL = {
    "ага", "угу", "да", "нет", "алло", "ало", "хм", "мм", "ээ", "ну", "так",
    "ясно", "понятно", "хорошо", "ладно", "ок", "окей", "спасибо", "пока",
    "до свидания", "здравствуйте", "здрасьте", "привет", "слушаю", "говорите",
}

STOPWORDS = {
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то",
    "все", "она", "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за",
    "бы", "по", "только", "ее", "мне", "было", "вот", "от", "меня", "еще",
    "нет", "о", "из", "ему", "теперь", "когда", "даже", "ну", "вдруг", "ли",
    "если", "уже", "или", "ни", "быть", "был", "него", "до", "вас", "нибудь",
    "опять", "уж", "вам", "ведь", "там", "потом", "себя", "ничего", "ей",
    "может", "они", "тут", "где", "есть", "надо", "ней", "для", "мы", "тебя",
    "их", "чем", "была", "сам", "чтоб", "без", "будто", "чего", "раз", "тоже",
    "себе", "под", "будет", "ж", "тогда", "кто", "этот", "того", "потому",
    "этого", "какой", "совсем", "ним", "здесь", "этом", "один", "почти",
    "мой", "тем", "чтобы", "нее", "сейчас", "были", "куда", "зачем", "всех",
    "никогда", "можно", "при", "наконец", "два", "об", "другой", "хоть",
    "после", "над", "больше", "тот", "через", "эти", "нас", "про", "всего",
    "них", "какая", "много", "разве", "три", "эту", "моя", "впрочем",
    "хорошо", "ваш", "который", "которая", "которые", "это", "эта", "эти",
    "свой", "свои", "такое", "такой", "надо", "очень", "нужно",
}

CLOSING_RE = re.compile(
    r"(до свидания|всего (вам )?хорошего|берегите себя|всего доброго)", re.I
)
WORD_RE = re.compile(r"[а-яёa-z]+", re.I)


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower().replace("ё", "е")
    return re.sub(r"\s+", " ", text).strip()


def content_keys(text: str) -> set[str]:
    """Content stems a reaction could legitimately pick up (4-char prefix)."""
    out = set()
    for w in WORD_RE.findall(norm(text)):
        if len(w) < 4 or w in STOPWORDS:
            continue
        out.add(w[:4])
    return out


def repeat_key(text: str) -> str:
    """Text identity for repeat detection, ignoring a leading recall interjection.

    «Алло. Поняла вас. Есть ли…» is the same question as «Поняла вас. Есть ли…»
    for the person on the phone, so the comparison must not be fooled by it.
    """
    n = norm(text)
    for lead in ("алло.", "алло ", "ало.", "ало "):
        if n.startswith(lead):
            n = n[len(lead):].strip()
            break
    return n[:80]


def is_substantive(text: str) -> bool:
    n = norm(text).strip(" .,!?-—")
    if len(n) < 3:
        return False
    if n in BACKCHANNEL:
        return False
    return len(content_keys(n)) >= 1


# Vera's grounded reaction shapes: «Про внуков поняла.», «Хорошо, что поели.»
# A reaction can be about the person without reusing their exact stem (спала →
# «Хорошо, что выспались»), so lexical overlap alone undercounts it.
REACTION_SHAPE_RE = re.compile(
    r"^(?:про\s+\S+\s+(?:поняла|услышала)|поняла\s+про\s+\S+|"
    r"спасибо,?\s+что\s+(?:сказали|рассказали)|"
    r"хорошо,?\s+что|понимаю,?\s+что|жаль,?\s+что|рада,?\s+что)",
    re.I,
)


# Canonical reaction shapes. A call that answers four different topics with the
# same shape still sounds like a form even when every sentence is unique.
SHAPE_PATTERNS = (
    ("pro-understood", re.compile(r"\bпро \S+ поняла\b")),
    ("understood-pro", re.compile(r"\bпоняла про \S+")),
    ("thanks-told-about", re.compile(r"\bспасибо что рассказали про \S+")),
    ("pro-heard", re.compile(r"\bпро \S+ услышала\b")),
    ("good-that", re.compile(r"\bхорошо что\b")),
    ("thanks-that", re.compile(r"\bспасибо что (?:сказали|рассказали)\b")),
    ("understand-that", re.compile(r"\bпонимаю что\b")),
    ("sorry-that", re.compile(r"\bжаль что\b")),
)


def shape_of(vera: str) -> str | None:
    """The reaction shape of a Vera turn, or None when it only asks."""
    low = vera.lower().replace("ё", "е")
    for name, pattern in SHAPE_PATTERNS:
        if pattern.search(low):
            return name
    return None


def reacts(vera: str, user: str) -> bool:
    """True when Vera's line answers the person rather than only asking."""
    if content_keys(vera) & content_keys(user):
        return True
    return bool(REACTION_SHAPE_RE.match(vera.strip()))


def load_trace(path: Path) -> list[tuple[str, str]]:
    """Ordered (role, text) events: role in {user, vera}."""
    events: list[tuple[str, str]] = []
    with path.open(encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            if '"stt.final"' in line:
                kind, key = "user", "stt.final"
            elif '"renderer.phrase_ready"' in line:
                kind, key = "vera", "renderer.phrase_ready"
            elif '"dialogue.speak"' in line:
                kind, key = "vera", "dialogue.speak"
            else:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("type") != key and ev.get("event_type") != key:
                continue
            text = (ev.get("payload") or {}).get("text") or ""
            if text:
                events.append((kind, text))
    return events


def analyse(events: list[tuple[str, str]]) -> dict | None:
    turns = []          # (user_text, vera_text|None) pairs
    pending_user: str | None = None
    for role, text in events:
        if role == "user":
            pending_user = text
        else:
            turns.append((pending_user or "", text))
            pending_user = None

    substantives = [u for u, _ in turns if is_substantive(u)]
    if not turns:
        return None

    reacted = q_only = 0
    for user, vera in turns:
        r = reacts(vera, user) if is_substantive(user) else None
        if r is True:
            reacted += 1
        if "?" in vera:
            if r is not True:
                q_only += 1

    shapes = [shape_of(vera) for _, vera in turns]
    shapes = [s for s in shapes if s]
    shape_repeats = sum(
        1 for a, b in zip(shapes, shapes[1:]) if a == b
    )

    seen: Counter[str] = Counter()
    verbatim = 0
    for _, vera in turns:
        key = repeat_key(vera)
        if seen[key]:
            verbatim += 1
        seen[key] += 1

    closed_flat = False
    if turns:
        user, vera = turns[-1]
        if CLOSING_RE.search(vera) and is_substantive(user):
            closed_flat = not reacts(vera, user)

    return {
        "user_turns": len(turns),
        "substantive_user_turns": len(substantives),
        "vera_turns": len(turns),
        "reacted_turns": reacted,
        "question_only_turns": q_only,
        "verbatim_reask_turns": verbatim,
        "closed_without_reaction": closed_flat,
        "reaction_shapes": shapes,
        "shape_repeats": shape_repeats,
    }


def pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 1) if d else 0.0


def aggregate(rows: list[dict]) -> dict:
    calls = len(rows)
    turns = [r["substantive_user_turns"] for r in rows]
    vera = sum(r["vera_turns"] for r in rows)
    reacted = sum(r["reacted_turns"] for r in rows)
    q_only = sum(r["question_only_turns"] for r in rows)
    verbatim = sum(r["verbatim_reask_turns"] for r in rows)
    flat = sum(1 for r in rows if r["closed_without_reaction"])
    shapes = sum((r.get("reaction_shapes") or [] for r in rows), [])
    shape_repeats = sum(r.get("shape_repeats", 0) for r in rows)
    turns_sorted = sorted(turns)

    def q(frac: float) -> int:
        if not turns_sorted:
            return 0
        idx = min(len(turns_sorted) - 1, int(frac * (len(turns_sorted) - 1)))
        return turns_sorted[idx]

    return {
        "calls": calls,
        "vera_turns": vera,
        "substantive_user_turns_median": statistics.median(turns) if turns else 0,
        "substantive_user_turns_p25": q(0.25),
        "substantive_user_turns_p75": q(0.75),
        "substantive_user_turns_max": max(turns) if turns else 0,
        "calls_with_1_or_0_turns": sum(1 for t in turns if t <= 1),
        "calls_with_le_2_turns": sum(1 for t in turns if t <= 2),
        "reaction_rate_pct": pct(reacted, vera),
        "question_only_rate_pct": pct(q_only, vera),
        "verbatim_reask_rate_pct": pct(verbatim, vera),
        "calls_closed_without_reaction": flat,
        "calls_closed_without_reaction_pct": pct(flat, calls),
        "reaction_shapes_used": len(set(shapes)),
        "shape_repeat_rate_pct": pct(shape_repeats, max(1, len(shapes) - 1)),
    }


CLOSING_INTENTS = ("summary", "goodbye_final", "partial_unresolved_close",
                   "urgent_close", "early_close")


def replay_call(user_turns: list[str], call_id: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Run real user turns through the live engine, return (user, vera) pairs.

    Same engine, same inputs; only the realization arm differs between runs.
    """
    import os

    os.environ.setdefault("IMVERA_DIALOGUE_ENGINE", "1")
    os.environ.setdefault("IMVERA_SPEECH_DAY", "102")
    os.environ.setdefault("IMVERA_SPEECH_HOUR", "14")

    from packages.core.memory_store import InMemoryCallRecordStore
    from packages.dialogue.session import CallSession

    session = CallSession(call_id=f"replay-{call_id}", family_id="replay",
                          elder_display_name="Тамара Юрьевна",
                          store=InMemoryCallRecordStore())
    opening = session.start()
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    session.mark_spoken_action(opening.proposal.generation_id)
    engine = session._engine
    pairs: list[tuple[str, str]] = []
    intents: list[str] = []
    for i, text in enumerate(user_turns):
        if engine.state.call_closed:
            break
        # Use the same complete understanding boundary as the SDK/CallActor.
        # A raw kernel projection omits question adjudication and mission
        # meaning, so its replies are not evidence of the live engine path.
        uid = f"u{i}"
        rich = engine.build_rich_turn(text, utterance_id=uid)
        result = session.handle_user_text(text, rich_turn=rich, utterance_id=uid)
        session.mark_spoken_action(result.proposal.generation_id)
        pairs.append((text, (result.proposal.speech or "").strip()))
        intents.append(str(getattr(result.speak_effect, "intent", "") or ""))
    return pairs, intents


def length_before() -> None:
    """Disable the adaptive-length continuation for a measurement run only."""
    from packages.dialogue_engine import reducer

    reducer._open_continuation = lambda state: None  # type: ignore[assignment]


def arm_before() -> None:
    """Disable the realization composer for a measurement run only."""
    from packages.dialogue_engine import realization

    realization.reaction_clause = lambda state, facts=(): ""  # type: ignore[assignment]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--traces-dir", default=str(ROOT / ".run" / "traces"))
    ap.add_argument("--limit", type=int, default=0, help="use N most recent traces")
    ap.add_argument("--since", default="", help="only traces with ts >= this prefix")
    ap.add_argument("--call", default="", help="analyse a single call id")
    ap.add_argument("--show", action="store_true", help="print turns of a single call")
    ap.add_argument("--replay", action="store_true",
                    help="replay real user turns through the engine instead of "
                         "reading historical Vera replies")
    ap.add_argument("--arm", choices=("before", "after"), default="after",
                    help="with --replay: realisation off (before) or on (after)")
    ap.add_argument("--length", choices=("before", "after"), default="after",
                    help="with --replay: adaptive length off (before) or on (after)")
    ap.add_argument("--json", default="", help="write full result JSON here")
    args = ap.parse_args()

    if args.replay and args.arm == "before":
        arm_before()
    if args.replay and args.length == "before":
        length_before()

    if args.call:
        path = Path(args.traces_dir) / f"{args.call}.jsonl"
        if not path.exists():
            print(f"no trace: {path}")
            return 1
        events = load_trace(path)
        if args.show:
            for role, text in events:
                print(f"{'U' if role == 'user' else 'V'}: {text}")
        row = analyse(events)
        print(json.dumps(row, ensure_ascii=False, indent=2))
        return 0

    paths = sorted(Path(args.traces_dir).glob("*.jsonl"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    rows, used = [], []
    for path in paths:
        if args.limit and len(used) >= args.limit:
            break
        events = load_trace(path)
        if not events:
            continue
        # A trace without a single recognised user utterance has nothing to
        # react to; counting its Vera lines would deflate every rate.
        if not any(is_substantive(t) for role, t in events if role == "user"):
            continue
        if args.since:
            try:
                head = path.open(encoding="utf-8", errors="ignore").readline()
                if json.loads(head).get("ts", "") < args.since:
                    continue
            except Exception:
                pass
        if args.replay:
            user_turns = [t for role, t in events if role == "user"]
            if not any(is_substantive(t) for t in user_turns):
                continue
            pairs, intents = replay_call(user_turns, path.stem)
            events = []
            for user, vera in pairs:
                events.append(("user", user))
                events.append(("vera", vera))
        row = analyse(events)
        if args.replay and row is not None:
            close_at = next(
                (i + 1 for i, intent in enumerate(intents)
                 if any(intent.startswith(c) for c in CLOSING_INTENTS)),
                None,
            )
            row["closed_by_vera"] = close_at is not None
            row["vera_turns_before_close"] = close_at
        if row and row["vera_turns"]:
            row["call_id"] = path.stem
            rows.append(row)
            used.append(path)

    if not rows:
        print(f"no traces with dialogue found (looked in {args.traces_dir})")
        return 1

    agg = aggregate(rows)
    print(f"conversation quality over {agg['calls']} real calls "
          f"({agg['vera_turns']} Vera turns)\n")
    print(f"  substantive user turns   median {agg['substantive_user_turns_median']}"
          f"  p25 {agg['substantive_user_turns_p25']}  p75 {agg['substantive_user_turns_p75']}"
          f"  max {agg['substantive_user_turns_max']}")
    print(f"  calls with <=1 turn      {agg['calls_with_1_or_0_turns']}"
          f" ({pct(agg['calls_with_1_or_0_turns'], agg['calls'])}%)")
    print(f"  calls with <=2 turns     {agg['calls_with_le_2_turns']}"
          f" ({pct(agg['calls_with_le_2_turns'], agg['calls'])}%)")
    print(f"  reaction rate            {agg['reaction_rate_pct']}%")
    print(f"  question-only rate       {agg['question_only_rate_pct']}%")
    print(f"  verbatim re-ask rate     {agg['verbatim_reask_rate_pct']}%")
    print(f"  reaction shapes used     {agg['reaction_shapes_used']}"
          f"  | same shape back-to-back {agg['shape_repeat_rate_pct']}%")
    print(f"  closed without reaction  {agg['calls_closed_without_reaction']}"
          f" ({agg['calls_closed_without_reaction_pct']}%)")

    if any("closed_by_vera" in r for r in rows):
        closed = [r for r in rows if r.get("closed_by_vera")]
        before = sorted(r["vera_turns_before_close"] for r in closed
                        if r.get("vera_turns_before_close"))
        print(f"\n  Vera closed the call     {len(closed)}/{len(rows)}"
              f" ({pct(len(closed), len(rows))}%)")
        if before:
            print(f"  turns before close       median {statistics.median(before)}"
                  f"  min {before[0]}  max {before[-1]}")

    worst = sorted(rows, key=lambda r: (r["reacted_turns"] / max(1, r["vera_turns"]),
                                        -r["vera_turns"]))[:5]
    print("\n  lowest-reaction calls:")
    for r in worst:
        print(f"    {r['call_id']:<46} turns={r['substantive_user_turns']:<3}"
              f" reacted={r['reacted_turns']}/{r['vera_turns']}"
              f" reask={r['verbatim_reask_turns']}")

    if args.json:
        Path(args.json).write_text(
            json.dumps({"aggregate": agg, "calls": rows}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"\n  wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
