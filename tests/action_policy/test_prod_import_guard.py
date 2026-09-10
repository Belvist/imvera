from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROD_FILES = (
    ROOT / "packages/dialogue_engine/reducer.py",
    ROOT / "packages/dialogue_engine/conversation_policy.py",
    ROOT / "packages/voice_runtime/call_actor.py",
)


def _imports_action_policy(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "dialogue_engine.action_policy" in alias.name:
                    found.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if "dialogue_engine.action_policy" in module:
                found.append(module)
    return found


def test_phase1_has_no_production_imports() -> None:
    offenders = {
        str(path.relative_to(ROOT)): imports
        for path in PROD_FILES
        if (imports := _imports_action_policy(path))
    }
    assert offenders == {}


def test_phase1_does_not_wrap_information_gain() -> None:
    policy_dir = ROOT / "packages/dialogue_engine/action_policy"
    offenders = {}
    for path in policy_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "information_gain" in text:
            offenders[str(path.relative_to(ROOT))] = True
    assert offenders == {}
