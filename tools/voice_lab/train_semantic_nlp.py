"""Train the semantic-NLP act classifier (RuModernBERT-base + head).

Frozen encoder + mean-pool + linear head. MPS/CPU minutes. Versioned
artifact: models/semantic_nlp/v1/{head.pt, labels.json, metrics.json}.
Eval gate: held-out accuracy must clear --min-acc or the artifact is NOT
written (no silent bad model). Retrain loop: add rows to
build_semantic_nlp_dataset.SEED_ROWS (or live_rows.jsonl after review),
rerun, gate, promote version.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

ARTIFACT_ROOT = ROOT / "models" / "semantic_nlp"


def encode_texts(tokenizer, model, texts: list[str], device: str) -> object:
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
    parser.add_argument("--version", default="v1")
    parser.add_argument("--min-acc", type=float, default=0.80)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--unfreeze-top", type=int, default=0)
    parser.add_argument("--lr", type=float, default=2e-3)
    parser.add_argument(
        "--train-all",
        action="store_true",
        help="retrain on 100%% rows for the release artifact (after the gate passes)",
    )
    args = parser.parse_args()

    import torch
    import torch.nn as nn

    from packages.dialogue_engine.semantic_nlp.labels import ACT_INDEX, ACTS, MODEL_ID

    random.seed(args.seed)
    torch.manual_seed(args.seed)

    seed_path = ROOT / "packages" / "dialogue_engine" / "semantic_nlp" / "seed.jsonl"
    if not seed_path.is_file():
        print("run build_semantic_nlp_dataset.py first")
        raise SystemExit(2)
    rows = [
        json.loads(line)
        for line in seed_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    n_seed = len(rows)
    live_path = ROOT / "tools" / "voice_lab" / "live_rows.jsonl"
    n_live = 0
    if live_path.is_file():
        for line in live_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("act") not in ACT_INDEX or not str(row.get("text", "")).strip():
                continue
            rows.append(
                {"question": str(row.get("question", "")), "text": row["text"], "act": row["act"]}
            )
            n_live += 1
    print(f"rows: seed={n_seed} live={n_live} total={len(rows)}")
    inputs = [f"[Q] {r['question']} [U] {r['text']}" for r in rows]
    targets = [ACT_INDEX[r["act"]] for r in rows]

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    from transformers import AutoModel, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=False)
    encoder = AutoModel.from_pretrained(MODEL_ID, trust_remote_code=False).to(device)
    if args.unfreeze_top > 0:
        for param in encoder.parameters():
            param.requires_grad = False
        for layer in encoder.layers[-args.unfreeze_top :]:
            for param in layer.parameters():
                param.requires_grad = True
    else:
        for param in encoder.parameters():
            param.requires_grad = False
    with torch.no_grad():
        probe = encode_texts(tokenizer, encoder, inputs[:4], device)
    dim = probe.shape[1]
    print(f"encoder dim={dim} device={device} rows={len(rows)}")

    index = list(range(len(rows)))
    # Stratified deterministic split: every label keeps 20% (min 1) in held.
    # Random reshuffles at n~100 make the gate luck; the split is derived
    # from --seed only, so reruns with the same seed compare like-for-like.
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
    label_counts: dict[str, int] = {}
    for row in rows:
        label_counts[row["act"]] = label_counts.get(row["act"], 0) + 1
    print("label distribution:", sorted(label_counts.items()))

    with torch.no_grad():
        X_train = encode_texts(tokenizer, encoder, [inputs[i] for i in train], device)
        X_held = (
            encode_texts(tokenizer, encoder, [inputs[i] for i in held], device)
            if held
            else None
        )
    y_train = torch.tensor([targets[i] for i in train])
    y_held = torch.tensor([targets[i] for i in held])

    head = nn.Linear(dim, len(ACTS))
    trainable = list(head.parameters())
    if args.unfreeze_top > 0:
        # Encode on the fly when the encoder trains (small data, fits MPS).
        trainable += [p for p in encoder.parameters() if p.requires_grad]
        optimizer = torch.optim.AdamW(trainable, lr=args.lr, weight_decay=1e-4)
    else:
        optimizer = torch.optim.AdamW(head.parameters(), lr=2e-3, weight_decay=1e-4)
    loss_fn = nn.CrossEntropyLoss()
    head.train()
    if args.unfreeze_top > 0:
        encoder.train()
    for epoch in range(args.epochs):
        optimizer.zero_grad()
        if args.unfreeze_top > 0:
            Xb = encode_texts(tokenizer, encoder, [inputs[i] for i in train], device)
            loss = loss_fn(head(Xb), y_train)
        else:
            loss = loss_fn(head(X_train), y_train)
        loss.backward()
        optimizer.step()
    head.eval()
    encoder.eval()
    with torch.no_grad():
        if args.unfreeze_top > 0:
            Xh = (
                encode_texts(tokenizer, encoder, [inputs[i] for i in held], device)
                if held
                else None
            )
            Xt = encode_texts(tokenizer, encoder, [inputs[i] for i in train], device)
        else:
            Xh, Xt = X_held, X_train
        if Xh is not None:
            pred = head(Xh).argmax(dim=1)
            acc = float((pred == y_held).float().mean())
        else:
            pred, acc = None, 1.0
        pred_all = head(Xt).argmax(dim=1)
        train_acc = float((pred_all == y_train).float().mean())
    print(f"train_acc={train_acc:.3f} held_acc={acc:.3f} (n_held={len(held)})")
    errors = []
    if pred is not None:
        for position, idx in enumerate(held):
            if int(pred[position]) != targets[idx]:
                errors.append(
                    {
                        "text": rows[idx]["text"],
                        "question": rows[idx]["question"],
                        "true": rows[idx]["act"],
                        "pred": ACTS[int(pred[position])],
                    }
                )
    print(f"errors: {json.dumps(errors, ensure_ascii=False)[:2000]}")
    if not args.train_all and acc < args.min_acc:
        print(f"GATE FAILED: held_acc {acc:.3f} < {args.min_acc}")
        raise SystemExit(1)
    out_dir = ARTIFACT_ROOT / args.version
    out_dir.mkdir(parents=True, exist_ok=True)
    torch.save(head.state_dict(), out_dir / "head.pt")
    if args.unfreeze_top > 0:
        encoder.save_pretrained(out_dir / "encoder")
    (out_dir / "labels.json").write_text(
        json.dumps({"acts": list(ACTS)}, ensure_ascii=False, indent=2),
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
