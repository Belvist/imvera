from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROD_FILES = (
    ROOT / "packages/dialogue_engine/reducer.py",
    ROOT / "packages/dialogue_engine/conversation_policy.py",
    ROOT / "packages/voice_runtime/call_actor.py",
)


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.append(node.module)
    return found


def _imports_action_policy(path: Path) -> list[str]:
    return [
        module
        for module in _imported_modules(path)
        if "dialogue_engine.action_policy" in module
    ]


def test_phase1_has_no_production_imports() -> None:
    offenders = {
        str(path.relative_to(ROOT)): imports
        for path in PROD_FILES
        if (imports := _imports_action_policy(path))
    }
    assert offenders == {}


def test_phase1_does_not_import_legacy_information_gain_policy() -> None:
    policy_dir = ROOT / "packages/dialogue_engine/action_policy"
    forbidden = "packages.dialogue_engine.semantic_kernel.information_gain"
    offenders: dict[str, list[str]] = {}
    for path in policy_dir.glob("*.py"):
        matches = [
            module
            for module in _imported_modules(path)
            if module == forbidden or module.startswith(f"{forbidden}.")
        ]
        if matches:
            offenders[str(path.relative_to(ROOT))] = matches
    assert offenders == {}
