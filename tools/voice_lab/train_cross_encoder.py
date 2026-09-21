"""Train CrossEncoderV1: [Q] question [G] goal description [U] utterance.

Frozen RuModernBERT encoder + masked multi-task heads (relevance, value,
act, correction). All-goal scoring (no retriever yet): every labeled row
is paired with its goal (positive) plus all other catalog goals
(negatives). Splits by split_group (no call leakage) + unseen-goal
diagnostic split. Artifact: models/semantic_nlu/xenc_v1/ with real-count
metadata (n_total, positives, negatives, by-goal, dataset sha256).
Offline/shadow only — no live cutover.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

ARTIFACT_ROOT = ROOT / "models" / "semantic_nlp"

VALUE_LABELS = ("yes", "no", "unknown", "yesterday", "morning", "other")


def load_rows() -> tuple[list[dict], str]:

    path = ROOT / "datasets" / "semantic_nlu" / "v2.jsonl"
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    return rows, digest


def build_pairs(rows: list[dict]) -> list[dict]:
    from tools.voice_lab.build_semantic_dataset import GOALS

    # Auto-negation is SOUND only for closed-world control acts (greeting,
    # goodbye, backchannel, repeat, stop): nothing else can be relevant.
    # Content answers may address several goals at once — auto-false there
    # is label poisoning (reviewer catch).
    CLOSED_ACTS = {"greeting", "goodbye", "backchannel", "repeat_request", "stop"}
    goal_ids = sorted(GOALS)
    pairs = []
    for row in rows:
        if row["goal"] is None or row["relevant"] is None:
            continue
        goal = row["goal"]
        pairs.append(
            {
                "question": row["question"] or "",
                "goal": goal,
                "utterance": row["utterance"],
                "relevant": bool(row["relevant"]),
                "value": row.get("value"),
                "act": row.get("act"),
                "correction": bool(row.get("correction", False)),
                "group": row["split_group"],
            }
        )
        if row["relevant"] and row.get("act") in CLOSED_ACTS:
            for other_id in goal_ids:
                if other_id == goal["goal_id"]:
                    continue
                pairs.append(
                    {
                        "question": row["question"] or "",
                        "goal": dict(GOALS[other_id]),
                        "utterance": row["utterance"],
                        "relevant": False,
                        "value": None,
                        "act": row.get("act"),
                        "correction": bool(row.get("correction", False)),
                        "group": row["split_group"],
                    }
                )
    return pairs


def encode_texts(tokenizer, model, texts: list[str], device: str):
    import torch

    model.eval()
    vectors = []
    with torch.no_grad():
        for text in texts:
            batch = tokenizer(text, return_tensors="pt", truncation=True, max_length=192)
            mask = batch["attention_mask"].to(device)
            batch = {k: v.to(device) for k, v in batch.items()}
            hidden = model(**batch).last_hidden_state
            pooled = (hidden * mask.unsqueeze(-1)).sum(1) / mask.sum(1).unsqueeze(-1)
            vectors.append(pooled.cpu())
    return torch.cat(vectors, dim=0)


def encode_train(tokenizer, model, texts: list[str], device: str):
    """Training encode WITH gradients (reviewer catch: the old path wrapped
    everything in no_grad + .cpu(), so 'unfreezing' never trained)."""
    import torch

    model.train()
    vectors = []
    for text in texts:
        batch = tokenizer(text, return_tensors="pt", truncation=True, max_length=192)
        mask = batch["attention_mask"].to(device)
        batch = {k: v.to(device) for k, v in batch.items()}
        hidden = model(**batch).last_hidden_state
        pooled = (hidden * mask.unsqueeze(-1)).sum(1) / mask.sum(1).unsqueeze(-1)
        vectors.append(pooled)
    return torch.cat(vectors, dim=0)


def encode_pair_features(tokenizer, model, pairs: list[dict], device: str):
    """Bi-encoder inductive bias: separate U and [Q+G] encodings with
    explicit interaction features [u; g; u*g; |u-g|]. Forces the head to
    compare meanings instead of memorizing topic patterns."""
    import torch

    model.eval()
    with torch.no_grad():
        U = encode_texts(
            tokenizer, model, [p["utterance"] for p in pairs], device
        ).cpu()
        G = encode_texts(
            tokenizer,
            model,
            [f"[Q] {p['question']} [G] {p['goal']['description']}" for p in pairs],
            device,
        ).cpu()
    return torch.cat([U, G, U * G, (U - G).abs()], dim=1)


def format_input(question: str, goal: dict, utterance: str) -> str:
    allowed = ""
    if goal.get("allowed_values"):
        allowed = f" ({'/'.join(goal['allowed_values'])})"
    return (
        f"[Q] {question} [G] {goal['description']}{allowed} [U] {utterance}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="xenc_v1")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--unseen-goals", default="daughter_visit,utilities_paid")
    parser.add_argument("--eval-file", default=None)
    parser.add_argument("--calib-file", default=None)
    parser.add_argument("--extra-data", default=None)
    parser.add_argument(
        "--heads",
        default="rel,val,act,corr",
        help="comma subset to train this run (reviewer: relevance+value first)",
    )
    parser.add_argument("--unfreeze-top", type=int, default=0)
    parser.add_argument("--lr", type=float, default=2e-3)
    parser.add_argument("--encoder-lr", type=float, default=2e-5)
    parser.add_argument(
        "--arch",
        default="pair",
        choices=["pair", "bi"],
        help="pair: single [Q][G][U] encoding; bi: separate U and G+Q "
        "encodings with explicit interaction features",
    )
    args = parser.parse_args()

    import torch
    import torch.nn as nn

    from packages.dialogue_engine.semantic_nlp.labels import ACT_INDEX, ACTS, MODEL_ID

    random.seed(args.seed)
    torch.manual_seed(args.seed)

    rows, dataset_sha = load_rows()
    if args.extra_data:
        extra = [
            json.loads(line)
            for line in Path(args.extra_data).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        extra = [r for r in extra if r.get("split_group", "").startswith("train:")]
        if args.eval_file:
            eval_seen = {
                json.loads(line)["utterance"].strip().lower()
                for line in Path(args.eval_file).read_text(encoding="utf-8").splitlines()
                if line.strip()
            }
            before = len(extra)
            extra = [
                r for r in extra if r["utterance"].strip().lower() not in eval_seen
            ]
            print(f"extra-data: {before} -> {len(extra)} after eval-exclusion")
        rows = rows + extra
        print(f"extra-data: +{len(extra)} rows")
    pairs = build_pairs(rows)
    print(f"rows={len(rows)} pairs={len(pairs)} dataset_sha={dataset_sha[:12]}")

    unseen = {g.strip() for g in args.unseen_goals.split(",") if g.strip()}
    train_pairs, held_pairs, unseen_pairs = [], [], []
    groups = sorted({p["group"] for p in pairs})
    rng = random.Random(args.seed)
    rng.shuffle(groups)
    held_groups = set(groups[: max(1, len(groups) // 5)])
    for pair in pairs:
        if pair["goal"]["goal_id"] in unseen:
            unseen_pairs.append(pair)
        elif pair["group"] in held_groups:
            held_pairs.append(pair)
        else:
            train_pairs.append(pair)
    print(
        f"train={len(train_pairs)} held={len(held_pairs)} unseen={len(unseen_pairs)} "
        f"held_groups={sorted(held_groups)}"
    )

    value_index = {v: i for i, v in enumerate(VALUE_LABELS)}

    def tensors(subset: list[dict]):
        texts = [format_input(p["question"], p["goal"], p["utterance"]) for p in subset]
        rel = torch.tensor([1.0 if p["relevant"] else 0.0 for p in subset])
        val = torch.tensor(
            [
                value_index.get(p["value"], value_index["other"]) if p["value"] else -100
                for p in subset
            ]
        )
        val_mask = torch.tensor([p["value"] is not None for p in subset])
        act = torch.tensor(
            [ACT_INDEX[p["act"]] if p["act"] in ACT_INDEX else -100 for p in subset]
        )
        act_mask = torch.tensor([p["act"] in ACT_INDEX for p in subset])
        corr = torch.tensor([1.0 if p["correction"] else 0.0 for p in subset])
        return texts, rel, val, val_mask, act, act_mask, corr

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    from transformers import AutoModel, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=False)
    encoder = AutoModel.from_pretrained(MODEL_ID, trust_remote_code=False).to(device)
    for param in encoder.parameters():
        param.requires_grad = False
    if args.unfreeze_top > 0:
        for layer in encoder.layers[-args.unfreeze_top :]:
            for param in layer.parameters():
                param.requires_grad = True
    with torch.no_grad():
        probe = encode_texts(
            tokenizer, encoder, [format_input("q", {"description": "g"}, "u")], device
        )
    dim = probe.shape[1]
    if args.arch == "bi":
        dim = dim * 4

    def featurize(subset: list[dict]):
        if args.arch == "bi":
            return encode_pair_features(tokenizer, encoder, subset, device)
        texts = [format_input(p["question"], p["goal"], p["utterance"]) for p in subset]
        return encode_texts(tokenizer, encoder, texts, device)

    tr_texts, tr_rel, tr_val, tr_val_m, tr_act, tr_act_m, tr_corr = tensors(train_pairs)
    with torch.no_grad():
        Xtr = featurize(train_pairs)
    head_rel = nn.Linear(dim, 1)
    head_val = nn.Linear(dim, len(VALUE_LABELS))
    head_act = nn.Linear(dim, len(ACTS))
    head_corr = nn.Linear(dim, 1)
    heads = nn.ModuleDict(
        {"rel": head_rel, "val": head_val, "act": head_act, "corr": head_corr}
    )
    n_pos_tr = float(tr_rel.sum())
    n_neg_tr = float(len(tr_rel) - n_pos_tr)
    pos_weight = torch.tensor([n_neg_tr / max(n_pos_tr, 1.0)])
    if args.unfreeze_top > 0:
        heads.to(device)
        tr_rel = tr_rel.to(device)
        tr_val, tr_val_m = tr_val.to(device), tr_val_m.to(device)
        tr_act, tr_act_m, tr_corr = tr_act.to(device), tr_act_m.to(device), tr_corr.to(device)
        pos_weight = pos_weight.to(device)
    if args.unfreeze_top > 0:
        Xtr = None
        optimizer = torch.optim.AdamW(
            [
                {"params": list(heads.parameters()), "lr": args.lr},
                {
                    "params": [p for p in encoder.parameters() if p.requires_grad],
                    "lr": args.encoder_lr,
                },
            ],
            weight_decay=1e-4,
        )
    else:
        optimizer = torch.optim.AdamW(heads.parameters(), lr=args.lr, weight_decay=1e-4)
    bce = nn.BCEWithLogitsLoss()
    bce_rel = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    ce = nn.CrossEntropyLoss(ignore_index=-100)
    heads.train()
    if args.unfreeze_top > 0:
        encoder.train()
    want = {h.strip() for h in args.heads.split(",")}
    for _epoch in range(args.epochs):
        optimizer.zero_grad()
        if args.unfreeze_top > 0:
            if args.arch == "bi":
                raise SystemExit("--arch bi requires frozen encoder in this experiment")
            Xb = encode_train(tokenizer, encoder, tr_texts, device)
        else:
            Xb = Xtr
        loss = bce_rel(head_rel(Xb).squeeze(-1), tr_rel)
        if "val" in want and tr_val_m.any():
            loss = loss + ce(head_val(Xb[tr_val_m]), tr_val[tr_val_m])
        if "act" in want and tr_act_m.any():
            loss = loss + ce(head_act(Xb[tr_act_m]), tr_act[tr_act_m])
        if "corr" in want:
            loss = loss + bce(head_corr(Xb).squeeze(-1), tr_corr)
        loss.backward()
        if args.unfreeze_top > 0 and _epoch == 0:
            norms = [
                p.grad.norm().item()
                for p in encoder.parameters()
                if p.requires_grad and p.grad is not None
            ]
            print(f"encoder grad check: {len(norms)} params, max_norm={max(norms):.2e}")
            assert norms and max(norms) > 0, "no gradient reached the encoder"
        optimizer.step()
    encoder.eval()

    def evaluate(subset: list[dict], name: str) -> dict:
        heads.eval()
        with torch.no_grad():
            texts, rel, val, val_m, act, act_m, corr = tensors(subset)
            if not texts:
                return {"n": 0}
            X = featurize(subset)
            if args.unfreeze_top > 0:
                X = X.to(device)
                rel = rel.to(device)
                val, val_m, act, act_m, corr = (
                    val.to(device),
                    val_m.to(device),
                    act.to(device),
                    act_m.to(device),
                    corr.to(device),
                )
            scores = torch.sigmoid(head_rel(X)).squeeze(-1)
            pred_rel = (scores >= 0.5).float()
            tp = int(((pred_rel == 1) & (rel == 1)).sum())
            fp = int(((pred_rel == 1) & (rel == 0)).sum())
            fn = int(((pred_rel == 0) & (rel == 1)).sum())
            precision = tp / (tp + fp) if tp + fp else 0.0
            recall = tp / (tp + fn) if tp + fn else 0.0
            f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
            # Average precision over the ranked list (threshold-free).
            order = torch.argsort(scores, descending=True)
            ranked = rel[order]
            cum_tp = torch.cumsum(ranked, dim=0)
            precisions = cum_tp / torch.arange(1, len(ranked) + 1).to(rel.device)
            average_precision = (
                float((precisions * ranked).sum() / max(int(ranked.sum()), 1))
                if int(ranked.sum())
                else 0.0
            )
            # Threshold curve F1 @ 0.3/0.5/0.7/0.9.
            curve = {}
            for thr in (0.3, 0.5, 0.7, 0.9):
                pr = (scores >= thr).float()
                t = int(((pr == 1) & (rel == 1)).sum())
                f = int(((pr == 1) & (rel == 0)).sum())
                n = int(((pr == 0) & (rel == 1)).sum())
                p = t / (t + f) if t + f else 0.0
                r = t / (t + n) if t + n else 0.0
                curve[str(thr)] = round(
                    2 * p * r / (p + r) if p + r else 0.0, 3
                )
            out: dict = {
                "n": len(subset),
                "rel_precision": round(precision, 3),
                "rel_recall": round(recall, 3),
                "rel_f1": round(f1, 3),
                "average_precision": round(average_precision, 3),
                "f1_curve": curve,
                "wrong_goal_fp": fp,
                "brier": round(float(((scores - rel) ** 2).mean()), 4),
                "ece": round(_ece(scores, rel), 4),
            }
            if val_m.any():
                pred_val = head_val(X[val_m]).argmax(dim=1)
                out["value_acc"] = round(float((pred_val == val[val_m]).float().mean()), 3)
                out["value_n"] = int(val_m.sum())
            if act_m.any():
                pred_act = head_act(X[act_m]).argmax(dim=1)
                out["act_acc"] = round(float((pred_act == act[act_m]).float().mean()), 3)
            errors = []
            with torch.no_grad():
                for i, pair in enumerate(subset):
                    if bool(pred_rel[i]) != bool(rel[i]):
                        errors.append(
                            {
                                "utterance": pair["utterance"][:100],
                                "goal": pair["goal"]["goal_id"],
                                "true_rel": bool(rel[i]),
                                "pred_rel": bool(pred_rel[i]),
                            }
                        )
                        if len(errors) >= 40:
                            break
            out["errors"] = errors
            print(f"{name}: {json.dumps({k: v for k, v in out.items() if k != 'errors'})}")
            return out

    def _ece(scores, labels, bins: int = 10) -> float:
        err = 0.0
        for b in range(bins):
            lo, hi = b / bins, (b + 1) / bins
            mask = (scores >= lo) & (scores < hi if b < bins - 1 else scores <= hi)
            if int(mask.sum()) == 0:
                continue
            err += abs(float(scores[mask].mean()) - float(labels[mask].mean())) * int(
                mask.sum()
            )
        return err / max(len(scores), 1)

    def calibrate(dev_rows: list[dict]) -> dict:
        """Global threshold + Platt scaling fit on calibration_dev ONLY.

        Never touches eval_fixed. Returns params + dev metrics.
        """
        import torch
        import torch.nn as nn

        pairs = [
            {
                "question": r["question"] or "",
                "goal": r["goal"],
                "utterance": r["utterance"],
                "relevant": bool(r["relevant"]),
                "value": r.get("value"),
                "act": r.get("act"),
                "correction": bool(r.get("correction", False)),
                "group": "calib_dev",
            }
            for r in dev_rows
        ]
        heads.eval()
        with torch.no_grad():
            X = featurize(pairs)
            if args.unfreeze_top > 0:
                X = X.to(device)
            logits = head_rel(X).squeeze(-1)
            y = torch.tensor([1.0 if p["relevant"] else 0.0 for p in pairs])
            if args.unfreeze_top > 0:
                y = y.to(device)
        # Global threshold sweep for best dev F1.
        best_thr, best_f1 = 0.5, -1.0
        for thr in [round(0.05 * i, 2) for i in range(1, 20)]:
            pr = (torch.sigmoid(logits) >= thr).float()
            t = int(((pr == 1) & (y == 1)).sum())
            f = int(((pr == 1) & (y == 0)).sum())
            n = int(((pr == 0) & (y == 1)).sum())
            p = t / (t + f) if t + f else 0.0
            r = t / (t + n) if t + n else 0.0
            f1 = 2 * p * r / (p + r) if p + r else 0.0
            if f1 > best_f1:
                best_f1, best_thr = f1, thr
        # Platt scaling: logistic fit on raw logits.
        platt = nn.Linear(1, 1)
        opt = torch.optim.LBFGS(platt.parameters(), max_iter=100)
        targets = y.unsqueeze(-1)
        feats = logits.detach().unsqueeze(-1)

        def closure():
            opt.zero_grad()
            loss = nn.BCEWithLogitsLoss()(platt(feats), targets)
            loss.backward()
            return loss

        try:
            opt.step(closure)
            with torch.no_grad():
                cal_probs = torch.sigmoid(platt(feats)).squeeze(-1)
            platt_a = float(platt.weight.squeeze())
            platt_b = float(platt.bias.squeeze())
        except Exception:
            cal_probs = torch.sigmoid(logits)
            platt_a, platt_b = 1.0, 0.0
        report = {
            "n": len(pairs),
            "best_threshold": best_thr,
            "best_f1": round(best_f1, 3),
            "platt_a": round(platt_a, 4),
            "platt_b": round(platt_b, 4),
            "brier_raw": round(float(((torch.sigmoid(logits) - y) ** 2).mean()), 4),
            "brier_cal": round(float(((cal_probs - y) ** 2).mean()), 4),
            "ece_raw": round(_ece(torch.sigmoid(logits), y), 4),
            "ece_cal": round(_ece(cal_probs, y), 4),
        }
        print(f"calibration: {json.dumps(report)}")
        return report

    held_report = evaluate(held_pairs, "held")
    unseen_report = evaluate(unseen_pairs, "unseen-goal(diagnostic)")
    fixed_report: dict = {}
    if args.eval_file:
        eval_rows = [
            json.loads(line)
            for line in Path(args.eval_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        eval_pairs = [
            {
                "question": r["question"] or "",
                "goal": r["goal"],
                "utterance": r["utterance"],
                "relevant": bool(r["relevant"]),
                "value": r.get("value"),
                "act": r.get("act"),
                "correction": bool(r.get("correction", False)),
                "group": "eval_fixed",
            }
            for r in eval_rows
        ]
        fixed_report = evaluate(eval_pairs, "eval-fixed")
    else:
        fixed_report = {}
    calib_report: dict = {}
    if args.calib_file:
        calib_report = calibrate(
            [
                json.loads(line)
                for line in Path(args.calib_file).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        )

    out_dir = ARTIFACT_ROOT / args.version
    out_dir.mkdir(parents=True, exist_ok=True)
    torch.save(heads.state_dict(), out_dir / "heads.pt")
    if args.unfreeze_top > 0:
        encoder.save_pretrained(out_dir / "encoder")
    (out_dir / "labels.json").write_text(
        json.dumps(
            {"acts": list(ACTS), "values": list(VALUE_LABELS), "model": "cross-encoder"},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    extra_info: dict = {}
    if args.extra_data:
        extra_bytes = Path(args.extra_data).read_bytes()
        extra_info = {
            "extra_path": args.extra_data,
            "extra_sha256": hashlib.sha256(extra_bytes).hexdigest(),
            "extra_rows": len(extra),
        }
    by_goal: dict[str, int] = {}
    by_act: dict[str, int] = {}
    n_pos = n_neg = n_val = 0
    for pair in train_pairs:
        by_goal[pair["goal"]["goal_id"]] = by_goal.get(pair["goal"]["goal_id"], 0) + 1
        if pair["act"]:
            by_act[pair["act"]] = by_act.get(pair["act"], 0) + 1
        if pair["relevant"]:
            n_pos += 1
        else:
            n_neg += 1
        if pair["value"]:
            n_val += 1
    (out_dir / "metrics.json").write_text(
        json.dumps(
            {
                "dataset_sha256": dataset_sha,
                "extra_data": extra_info,
                "n_total_rows": len(rows),
                "n_train_pairs": len(train_pairs),
                "n_held_pairs": len(held_pairs),
                "n_unseen_pairs": len(unseen_pairs),
                "n_positive": n_pos,
                "n_negative": n_neg,
                "n_value_labels": n_val,
                "n_by_goal": by_goal,
                "n_by_act": by_act,
                "train_groups": sorted({p["group"] for p in train_pairs}),
                "held_groups": sorted({p["group"] for p in held_pairs}),
                "unseen_goals": sorted(unseen),
                "held": held_report,
                "unseen": unseen_report,
                "eval_fixed": fixed_report,
                "calibration": calib_report,
                "model_id": MODEL_ID,
                "seed": args.seed,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (out_dir / "errors.jsonl").write_text(
        "\n".join(
            json.dumps(e, ensure_ascii=False)
            for e in held_report.get("errors", []) + unseen_report.get("errors", [])
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {out_dir}")


if __name__ == "__main__":
    main()
