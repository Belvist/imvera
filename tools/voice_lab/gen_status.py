"""Generate docs/STATUS.json from verifiable repo sources only.

Every value is read from the working tree: git HEAD/branch/tree state, the
CI workflow file, tracked string constants, and on-disk artifacts. Test
counts are never fabricated — this script does not run the suite, so
``tests.status`` is always ``"not_run"``.

Also writes models/semantic_nlp/<latest>/MANIFEST.json recording head.pt
sha256 + seed.jsonl sha256 + training commit (skip with --no-manifest).
"""

import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CI_YML = REPO / ".github" / "workflows" / "ci.yml"
SHADOW_CONFIG = REPO / "packages" / "dialogue_engine" / "action_policy_shadow_config.py"
CORPUS_GENERATOR = REPO / "packages" / "dialogue_engine" / "corpus" / "generator.py"
SEED = REPO / "packages" / "dialogue_engine" / "semantic_nlp" / "seed.jsonl"
NLP_ROOT = REPO / "models" / "semantic_nlp"


def run(cmd: list[str]) -> str:
    out = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, check=True)
    return out.stdout.strip()


def str_constant(path: Path, name: str) -> str:
    """Read a module-level ``NAME = "..."`` without importing the module."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value.value
    raise ValueError(f"{name} not found as string constant in {path}")


def ci_jobs() -> list[str]:
    """Top-level job names from ci.yml (two-space-indented keys under jobs:)."""
    jobs: list[str] = []
    in_jobs = False
    for line in CI_YML.read_text(encoding="utf-8").splitlines():
        if line == "jobs:":
            in_jobs = True
            continue
        if not in_jobs:
            continue
        stripped = line.strip()
        if (
            line.startswith("  ")
            and not line.startswith("   ")
            and stripped.endswith(":")
            and not stripped.startswith("#")
        ):
            jobs.append(stripped[:-1])
    return jobs


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def latest_nlp_version() -> str:
    versions = sorted(p.name for p in NLP_ROOT.iterdir() if p.is_dir() and p.name.startswith("v"))
    if not versions:
        raise ValueError(f"no version dirs in {NLP_ROOT}")
    return versions[-1]


def build_status(write_manifest: bool) -> dict:
    head_sha = run(["git", "rev-parse", "HEAD"])
    branch = run(["git", "branch", "--show-current"])
    tree_clean = run(["git", "status", "--porcelain"]) == ""
    seed_rel = SEED.relative_to(REPO).as_posix()
    training_commit = run(["git", "log", "--format=%H", "-1", "--", seed_rel])

    nlp_version = latest_nlp_version()
    artifact = NLP_ROOT / nlp_version
    artifact_rel = artifact.relative_to(REPO).as_posix()
    metrics_path = artifact / "metrics.json"
    labels_path = artifact / "labels.json"
    head_pt = artifact / "head.pt"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    acts = labels.get("acts", []) if isinstance(labels, dict) else []

    seed_info = {
        "path": seed_rel,
        "sha256": sha256_file(SEED),
        "lines": len(SEED.read_bytes().splitlines()),
        "training_commit": training_commit,
    }
    head_info = {"sha256": sha256_file(head_pt), "bytes": head_pt.stat().st_size}
    manifest_rel = f"{artifact_rel}/MANIFEST.json"
    manifest = {
        "generated_by": "tools/voice_lab/gen_status.py",
        "generated_at_head": head_sha,
        "artifact": artifact_rel,
        "head_pt": head_info,
        "seed": seed_info,
        "metrics": f"{artifact_rel}/metrics.json",
        "labels": f"{artifact_rel}/labels.json",
    }
    if write_manifest:
        (artifact / "MANIFEST.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )

    return {
        "generated_by": "tools/voice_lab/gen_status.py",
        "git": {"head_sha": head_sha, "branch": branch, "tree_clean": tree_clean},
        "ci": {"workflow": ".github/workflows/ci.yml", "jobs": ci_jobs()},
        "action_policy": {
            "frozen_policy_sha": str_constant(SHADOW_CONFIG, "FROZEN_POLICY_SHA"),
            "policy_version": str_constant(SHADOW_CONFIG, "POLICY_VERSION"),
            "source": "packages/dialogue_engine/action_policy_shadow_config.py",
        },
        "corpus": {
            "version": str_constant(CORPUS_GENERATOR, "CORPUS_VERSION"),
            "source": "packages/dialogue_engine/corpus/generator.py:CORPUS_VERSION",
        },
        "semantic_nlp": {
            "version": nlp_version,
            "artifact_dir": artifact_rel,
            "model_id": metrics.get("model_id"),
            "metrics_file": f"{artifact_rel}/metrics.json",
            "held_acc": metrics.get("held_acc"),
            "train_acc": metrics.get("train_acc"),
            "n_train": metrics.get("n_train"),
            "n_held": metrics.get("n_held"),
            "labels_acts": len(acts),
            "head_pt": head_info,
            "seed": seed_info,
        },
        "tests": {
            "status": "not_run",
            "reason": "generator does not execute the suite; run pytest separately",
        },
        "manifest": manifest_rel,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="docs/STATUS.json")
    parser.add_argument("--no-manifest", action="store_true")
    args = parser.parse_args()

    status = build_status(write_manifest=not args.no_manifest)
    out_path = REPO / args.output
    out_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_path.relative_to(REPO).as_posix()}")
    if not args.no_manifest:
        print(f"wrote {status['manifest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
