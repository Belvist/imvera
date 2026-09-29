#!/usr/bin/env python3
"""Mine real-call traces for act-classifier training rows.

Reads forensic/live traces (.run/traces/fs-*.jsonl + live_e2e server
traces), extracts (pending_question, stt_text) pairs, labels each with the
deterministic act pipeline (normalize_act = class semantics), and splits
into:
- tools/voice_lab/live_rows.jsonl (reviewed train additions), and
- tools/voice_lab/live_eval_frozen.jsonl (NEVER trained on: the honest
  generalization metric on real speech).

Anti-circularity rules (documented, not hidden):
- rows identical/near-identical to existing seeds are dropped (no padding);
- only utterances ADDING phrasing coverage are kept: STT noise,
  corrections, severity answers, refusals, inflections, fragments;
- labels come from the deterministic acts (rules define class meaning);
  the model learns phrasing robustness, not new semantics.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.dialogue_engine.protocol.acts import normalize_act  # noqa: E402
from packages.dialogue_engine.state import EngineState  # noqa: E402

TRACE_GLOBS = ["../.run/traces/fs-*.jsonl", "../.run/live_e2e/*/call-*/server_trace.jsonl"]


def _fresh_state() -> EngineState:
    return EngineState(call_id="mine", elder_display_name="T")


def _norm(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _existing_seed_keys() -> set[str]:
    keys = set()
    for name in ("seed.jsonl",):
        path = ROOT / "packages" / "dialogue_engine" / "semantic_nlp" / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            keys.add(_norm(str(row.get("text", ""))))
    return keys


def _collect_pairs() -> list[dict]:
    pairs: list[dict] = []
    seen: set[str] = set()
    roots = sorted((ROOT / ".run" / "traces").glob("fs-*.jsonl"))
    roots += sorted((ROOT / ".run" / "live_e2e").glob("*/call-*/server_trace.jsonl"))
    for path in roots:
        pending = ""
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            payload = event.get("payload", {}) if isinstance(event, dict) else {}
            # Track the last Vera question as pending context.
            text = str(payload.get("text", "") or "")
            if event.get("type") in ("stage.timing",) and "phrase" in str(payload):
                continue
            speaker = str(payload.get("speaker", "") or payload.get("role", ""))
            if speaker in ("vera", "assistant") and text.strip().endswith("?"):
                pending = text.strip()
                continue
            stt = str(payload.get("stt_text", "") or "").strip()
            if stt and len(stt) >= 2:
                key = _norm(stt)
                if key in seen:
                    continue
                seen.add(key)
                pairs.append(
                    {
                        "question": pending,
                        "text": stt,
                        "source": f"{path.parent.name}/{path.name}",
                    }
                )
    return pairs


_COVERAGE_PATTERNS = [
    r"ч[её]\b|шо\b|нич[еёо]\b",  # dialect/contractions
    r"\bне\b.*\b(болит|беспокоит|надо)\b",  # negations
    r"^(сильно|чуть|немного|средне|очень|ужасно|терпимо)\.?$",  # bare severity
    r"^(давай пока|не беспокой|не хочу|оставь|хватит|отстань)",  # refusals
    r"\b(вчера|со вчера|давно|неделю|утром|вечером)\b",  # time anchors
    r"\.\.\.|--|эээ|ну,|вот,|значит",  # fragments/fillers
    r"\b(зуб|спина|нога|горло|ухо|сустав)\w*\b",  # newly covered sites
    r"\b(тяжесть|жжение|онемение|шум|туман|кровь)\w*\b",  # sensations
    r"^(ой,?\s+)?нет[,.]?\s+\w+",  # corrections
]


def _adds_coverage(text: str) -> str | None:
    low = text.lower()
    for i, pattern in enumerate(_COVERAGE_PATTERNS):
        if re.search(pattern, low):
            return f"coverage-{i}"
    return None


_PROTOCOL_TO_CLASSIFIER_ACT = {
    # The act head is trained on the classifier taxonomy, not protocol
    # acts. Only unambiguous correspondences are kept; the rest (e.g.
    # SIDE_TOPIC) has no classifier counterpart and is dropped rather
    # than mislabeled.
    "ISSUE_SITE": "complaint",
    "DECLINE": "decline",
}


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--eval-frac", type=float, default=0.3)
    args = ap.parse_args()

    seed_keys = _existing_seed_keys()
    pairs = _collect_pairs()
    print(f"collected {len(pairs)} unique STT utterances from traces")

    st = _fresh_state()
    train_rows: list[dict] = []
    eval_rows: list[dict] = []
    skipped_dup = 0
    skipped_nocoverage = 0
    for pair in pairs:
        key = _norm(pair["text"])
        if key in seed_keys or len(key) < 3:
            skipped_dup += 1
            continue
        reason = _adds_coverage(pair["text"])
        if reason is None:
            skipped_nocoverage += 1
            continue
        try:
            act = normalize_act(st, pair["text"])
        except Exception:
            continue
        if not act:
            continue
        mapped = _PROTOCOL_TO_CLASSIFIER_ACT.get(act)
        if mapped is None:
            continue
        row = {
            "question": pair["question"],
            "text": pair["text"],
            "act": mapped,
            "source": pair["source"],
            "coverage": reason,
        }
        (eval_rows if hash(key) % 100 < int(args.eval_frac * 100) else train_rows).append(row)

    print(f"kept train={len(train_rows)} eval={len(eval_rows)} "
          f"dup={skipped_dup} nocoverage={skipped_nocoverage}")
    if args.write:
        live_path = ROOT / "tools" / "voice_lab" / "live_rows.jsonl"
        eval_path = ROOT / "tools" / "voice_lab" / "live_eval_frozen.jsonl"
        with open(live_path, "w", encoding="utf-8") as fh:
            for row in train_rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        with open(eval_path, "w", encoding="utf-8") as fh:
            for row in eval_rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"wrote {live_path} + {eval_path}")
    else:
        print("dry run (pass --write to persist)")
        for row in (train_rows + eval_rows)[:15]:
            print(f"  [{row['act']}] {row['text'][:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
