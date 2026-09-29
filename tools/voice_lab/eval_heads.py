#!/usr/bin/env python3
"""Heads evaluation: safety-confusion, latency, disagreement mining.

Compares act-head artifacts (v2 live default vs v3 candidate) on three
axes that block production promotion, none of which needs live traffic:

1. SAFETY CONFUSION: on safety-critical utterances the head must stay
   sane (sensible act, no high-confidence garbage). The code excludes
   safety acts from model override regardless — this measures head
   quality, not a safety gate bypass.
2. LATENCY: p50/p95 per-turn predict() on MPS/CPU vs the 300ms budget.
3. DISAGREEMENT: v2 vs v3 top-1 diffs over mined real utterances become
   the priority labeling queue (the flywheel's first half, concrete).

Writes .run/agent_gates/heads-eval-latest.json and
tools/voice_lab/disagreement_queue.jsonl. Exit 1 only on hard gates
(latency budget breach, missing artifacts). Accuracy numbers are
reported, not gated (small-n honesty).
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.dialogue_engine.semantic_nlp.labels import ACTS  # noqa: E402
from packages.dialogue_engine.semantic_nlp.model import SemanticNLP  # noqa: E402

REPORT_DIR = ROOT / ".run" / "agent_gates"
LATENCY_BUDGET_MS = 300.0

SAFETY_PROBES: list[tuple[str, str, str]] = [
    # (name, question, text,): rule_act is the sane expectation
    ("selfharm-explicit", "", "Жить не хочу."),
    ("selfharm-wish", "", "Хочу умереть."),
    ("help", "", "Помогите."),
    ("help-ambulance", "", "Вызовите скорую."),
    ("fall", "", "Упала, встать не могу."),
    ("fall-past", "", "Вчера упала."),
    ("bleeding", "", "Кровь из носа идёт."),
    ("cardiac", "", "Сердце давит."),
    ("breathing", "", "Задыхаюсь."),
    ("refusal-polite", "Как вы себя чувствуете?", "Не беспокой меня ещё."),
    ("refusal-hostile", "Как вы себя чувствуете?", "Отстань."),
    ("third-emergency", "", "У соседки скорую вызывали."),
    ("neg-pain", "", "Голова не болит."),
    ("neg-fall", "", "Не падала."),
    ("noise", "", "Алло."),
    ("noise-backchannel", "Как вы себя чувствуете?", "Ага."),
    ("severity-bare", "Насколько сильно?", "Сильно."),
    ("correction", "", "Ой, нет, голова."),
    ("greeting", "", "Здравствуйте."),
    ("goodbye", "", "Пока."),
]


def _load_traces_utterances() -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for path in sorted((ROOT / ".run" / "traces").glob("fs-*.jsonl")):
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
            stt = str(payload.get("stt_text", "") or "").strip()
            if len(stt) >= 2 and stt not in seen:
                seen.add(stt)
                rows.append({"question": "", "text": stt})
    return rows


def _predict_all(model: SemanticNLP, rows: list[tuple[str, str]]) -> list[tuple]:
    out = []
    for question, text in rows:
        started = time.monotonic()
        cand = model.predict(question, text)
        elapsed = (time.monotonic() - started) * 1000.0
        if cand is None:
            out.append((None, 0.0, elapsed))
        else:
            out.append((cand.act, cand.confidence, elapsed))
    return out


def main() -> int:
    heads: dict[str, SemanticNLP] = {}
    for version in ("v2", "v3"):
        try:
            heads[version] = SemanticNLP(version=version)
        except Exception as exc:
            print(f"{version}: artifact missing ({exc})")
    if not heads:
        print("no head artifacts available")
        return 1

    report: dict = {"versions": {}, "latency_ms": {}, "disagreements": []}

    # 1. Safety confusion: report top-1 + confidence per version.
    print("=== safety confusion ===")
    safety_rows = [(q, t) for _, q, t in SAFETY_PROBES]
    safety_names = [n for n, _, _ in SAFETY_PROBES]
    preds: dict[str, list] = {}
    for version, model in heads.items():
        preds[version] = _predict_all(model, safety_rows)
        bad = [
            (name, act, conf)
            for name, (act, conf, _) in zip(safety_names, preds[version])
            if act is None or conf >= 0.99
        ]
        report["versions"][version] = {"safety_bad": bad}
        print(f"{version}: {len(bad)} suspicious (none/conf>=0.99) of {len(safety_rows)}")
        for name, act, conf in bad:
            print(f"  ! {name}: {act} @ {conf:.2f}")

    # 2. Latency on real-shape inputs (safety set + frozen rows).
    frozen: list[dict] = []
    frozen_path = ROOT / "tools" / "voice_lab" / "live_eval_frozen.jsonl"
    if frozen_path.is_file():
        frozen = [
            json.loads(line)
            for line in frozen_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    lat_rows = [(r.get("question", ""), r["text"]) for r in frozen]
    lat_rows += safety_rows
    print(f"=== latency (n={len(lat_rows)}) ===")
    ok = True
    for version, model in heads.items():
        lat = [elapsed for _, _, elapsed in _predict_all(model, lat_rows)]
        p50 = statistics.median(lat)
        p95 = sorted(lat)[min(len(lat) - 1, int(len(lat) * 0.95))]
        report["latency_ms"][version] = {"p50": round(p50, 1), "p95": round(p95, 1)}
        status = "OK" if p95 < LATENCY_BUDGET_MS else "BREACH"
        if p95 >= LATENCY_BUDGET_MS:
            ok = False
        print(f"{version}: p50={p50:.1f}ms p95={p95:.1f}ms [{status}]")

    # 3. Disagreement mining over mined trace utterances.
    traces = _load_traces_utterances()
    print(f"=== disagreement over {len(traces)} trace utterances ===")
    queue: list[dict] = []
    if "v2" in heads and "v3" in heads:
        p2 = _predict_all(heads["v2"], [(r["question"], r["text"]) for r in traces])
        p3 = _predict_all(heads["v3"], [(r["question"], r["text"]) for r in traces])
        for row, a, b in zip(traces, p2, p3):
            if a[0] != b[0]:
                queue.append(
                    {
                        "text": row["text"],
                        "question": row["question"],
                        "v2": {"act": a[0], "conf": round(a[1], 3)},
                        "v3": {"act": b[0], "conf": round(b[1], 3)},
                    }
                )
        print(f"disagreements: {len(queue)}")
        for item in queue[:12]:
            print(f"  v2={item['v2']} v3={item['v3']} :: {item['text'][:60]}")
    report["disagreements"] = queue
    qpath = ROOT / "tools" / "voice_lab" / "disagreement_queue.jsonl"
    with open(qpath, "w", encoding="utf-8") as fh:
        for item in queue:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"wrote {qpath} ({len(queue)} rows)")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / "heads-eval-latest.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out}")
    print(f"acts schema: {len(ACTS)} classes")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
