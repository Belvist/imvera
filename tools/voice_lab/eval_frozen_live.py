#!/usr/bin/env python3
"""Frozen live-speech eval: v2 head vs v3 head on real utterances.

The frozen set (live_eval_frozen.jsonl) was NEVER trained on by either
version. This is the honest generalization metric: expert seeds teach
classes, live rows teach phrasing noise. Reports per-version accuracy +
per-row disagreements. No artifacts written, no promotion implied.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.dialogue_engine.semantic_nlp.labels import ACT_INDEX, ACTS, MODEL_ID


def load_head(version: str, device: str, dim: int):
    import torch
    import torch.nn as nn

    head = nn.Linear(dim, len(ACTS))
    head.load_state_dict(
        torch.load(ROOT / "models" / "semantic_nlp" / version / "head.pt", map_location=device)
    )
    head.eval()
    return head


def main() -> int:
    import torch
    from transformers import AutoModel, AutoTokenizer

    rows = [
        json.loads(line)
        for line in (ROOT / "tools" / "voice_lab" / "live_eval_frozen.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=False)
    encoder = AutoModel.from_pretrained(MODEL_ID, trust_remote_code=False).to(device)
    encoder.eval()
    for param in encoder.parameters():
        param.requires_grad = False

    inputs = [f"[Q] {r.get('question', '')} [U] {r['text']}" for r in rows]
    targets = [ACT_INDEX[r["act"]] for r in rows]
    with torch.no_grad():
        vectors = []
        for text in inputs:
            batch = tokenizer(text, return_tensors="pt", truncation=True, max_length=128)
            mask = batch["attention_mask"].to(device)
            batch = {k: v.to(device) for k, v in batch.items()}
            hidden = encoder(**batch).last_hidden_state
            pooled = (hidden * mask.unsqueeze(-1)).sum(1) / mask.sum(1).unsqueeze(-1)
            vectors.append(pooled.cpu())
        X = torch.cat(vectors, dim=0)
        y = torch.tensor(targets)

    print(f"frozen rows={len(rows)} device={device}")
    results = {}
    for version in ("v2", "v3"):
        try:
            head = load_head(version, device, X.shape[1])
        except (OSError, ValueError) as exc:
            print(f"{version}: artifact missing ({exc})")
            continue
        with torch.no_grad():
            pred = head(X).argmax(dim=1)
        acc = float((pred == y).float().mean())
        results[version] = acc
        print(f"{version}: frozen_acc={acc:.3f}")
        for row, t, p in zip(rows, y.tolist(), pred.tolist()):
            if t != p:
                print(f"  miss [{row['act']}->{ACTS[p]}]: {row['text'][:70]}")
    if "v2" in results and "v3" in results:
        print(f"delta_v3_minus_v2={results['v3'] - results['v2']:+.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
