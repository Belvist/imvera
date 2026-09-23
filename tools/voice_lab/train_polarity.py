"""Train polarity v1: positive/negative/uncertain wellness valence.

Same proven recipe as act v2 (frozen RuModernBERT encoder + linear head,
stratified deterministic split, multi-seed gate). Motivation: _detect_polarity
misses positives with extra clauses («Ну хорошо, только что покушала» → None
→ judge 'answer' → 'uncertain' → concern probe on a healthy person, live
fs-27a3ced4). A learned boundary replaces the judge→uncertain heuristic.

Usage:
  python3 tools/voice_lab/train_polarity.py --seed 7
  python3 tools/voice_lab/train_polarity.py --seed 7 --train-all  # release artifact
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ARTIFACT_ROOT = ROOT / "models" / "semantic_nlp"
LABELS = ("negative", "positive", "uncertain")
LABEL_INDEX = {name: i for i, name in enumerate(LABELS)}


def encode_texts(tokenizer, model, texts: list[str], device: str):
    import torch

    model.eval()
    vectors = []
    with torch.no_grad():
        for text in texts:
            batch = tokenizer(
                text, return_tensors="pt", truncation=True, max_length=128
            )
            mask = batch["attention_mask"].to(device)
            batch = {k: v.to(device) for k, v in batch.items()}
            hidden = model(**batch).last_hidden_state
            pooled = (hidden * mask.unsqueeze(-1)).sum(1) / mask.sum(1).unsqueeze(-1)
            vectors.append(pooled.cpu())
    import torch as _t

    return _t.cat(vectors, dim=0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-acc", type=float, default=0.80)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--train-all", action="store_true")
    args = parser.parse_args()

    import torch
    import torch.nn as nn

    from packages.dialogue_engine.semantic_nlp.labels import MODEL_ID

    text = (ROOT / "datasets" / "semantic_nlu" / "polarity_v1.jsonl").read_text(
        encoding="utf-8"
    )
    rows = (
        json.loads(text)
        if text.lstrip().startswith("[")
        else [json.loads(line) for line in text.splitlines() if line.strip()]
    )
    inputs = [f"[U] {r['text']}" for r in rows]
    targets = [LABEL_INDEX[r["label"]] for r in rows]

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    from transformers import AutoModel, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=False)
    encoder = AutoModel.from_pretrained(MODEL_ID, trust_remote_code=False).to(device)
    for param in encoder.parameters():
        param.requires_grad = False
    with torch.no_grad():
        probe = encode_texts(tokenizer, encoder, inputs[:4], device)
    dim = probe.shape[1]
    print(f"encoder dim={dim} device={device} rows={len(rows)}")

    index = list(range(len(rows)))
    by_label: dict[int, list[int]] = {}
    for i in index:
        by_label.setdefault(targets[i], []).append(i)
    held, train = [], []
    rng = random.Random(args.seed)
    for label, members in sorted(by_label.items()):
        rng.shuffle(members)
        cut = max(1, int(len(members) * 0.2))
        held.extend(members[:cut])
        train.extend(members[cut:])
    rng.shuffle(train)
    if args.train_all:
        train = sorted(train + held)
        held = []
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["label"]] = counts.get(row["label"], 0) + 1
    print("label distribution:", sorted(counts.items()))

    with torch.no_grad():
        X_train = encode_texts(tokenizer, encoder, [inputs[i] for i in train], device)
        X_held = (
            encode_texts(tokenizer, encoder, [inputs[i] for i in held], device)
            if held
            else None
        )
    y_train = torch.tensor([targets[i] for i in train])
    y_held = torch.tensor([targets[i] for i in held])

    head = nn.Linear(dim, len(LABELS))
    optimizer = torch.optim.AdamW(head.parameters(), lr=2e-3, weight_decay=1e-4)
    loss_fn = nn.CrossEntropyLoss()
    head.train()
    for _ in range(args.epochs):
        optimizer.zero_grad()
        loss = loss_fn(head(X_train), y_train)
        loss.backward()
        optimizer.step()
    head.eval()
    with torch.no_grad():
        if X_held is not None:
            pred = head(X_held).argmax(dim=1)
            acc = float((pred == y_held).float().mean())
        else:
            pred, acc = None, 1.0
        pred_all = head(X_train).argmax(dim=1)
        train_acc = float((pred_all == y_train).float().mean())
    print(f"train_acc={train_acc:.3f} held_acc={acc:.3f} (n_held={len(held)})")
    errors = []
    if pred is not None:
        for position, idx in enumerate(held):
            if int(pred[position]) != targets[idx]:
                errors.append(
                    {
                        "text": rows[idx]["text"],
                        "true": rows[idx]["label"],
                        "pred": LABELS[int(pred[position])],
                    }
                )
    print(f"errors: {json.dumps(errors, ensure_ascii=False)[:2000]}")
    if not args.train_all and acc < args.min_acc:
        print(f"GATE FAILED: held_acc {acc:.3f} < {args.min_acc}")
        raise SystemExit(1)
    out_dir = ARTIFACT_ROOT / "polarity_v1"
    out_dir.mkdir(parents=True, exist_ok=True)
    torch.save(head.state_dict(), out_dir / "head.pt")
    (out_dir / "labels.json").write_text(
        json.dumps({"labels": list(LABELS)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "metrics.json").write_text(
        json.dumps(
            {
                "train_acc": train_acc,
                "held_acc": acc,
                "n_train": len(train),
                "n_held": len(held),
                "model_id": MODEL_ID,
                "seed": args.seed,
                "errors": errors,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"wrote {out_dir}")


if __name__ == "__main__":
    main()
