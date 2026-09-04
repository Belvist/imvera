"""Architecture contract — forbidden imports and module boundaries."""
from __future__ import annotations

import ast
import unittest
from pathlib import Path


_REPO = Path(__file__).resolve().parents[2]
_GOLDEN = _REPO / "golden_path"

_FORBIDDEN_IMPORT_PREFIXES = (
    "telephony.conversation_system",
    "telephony.core.dialogue",
    "conversation_system",
)


def _iter_python_files(root: Path) -> list[Path]:
    skip = {"tests", "traces", "__pycache__"}
    files: list[Path] = []
    for path in root.rglob("*.py"):
        if any(part in skip for part in path.parts):
            continue
        files.append(path)
    return files


def _imported_modules(source: str) -> list[str]:
    tree = ast.parse(source)
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


class ArchitectureContractTests(unittest.TestCase):
    def test_golden_path_has_no_legacy_conversation_imports(self) -> None:
        violations: list[str] = []
        for path in _iter_python_files(_GOLDEN):
            rel = path.relative_to(_REPO)
            for mod in _imported_modules(path.read_text(encoding="utf-8")):
                for forbidden in _FORBIDDEN_IMPORT_PREFIXES:
                    if mod == forbidden or mod.startswith(forbidden + "."):
                        violations.append(f"{rel}: import {mod}")
        self.assertEqual(violations, [], "forbidden legacy imports in golden_path")

    def test_architecture_contract_doc_exists(self) -> None:
        doc = _REPO / "docs" / "CONVERSATION_ARCHITECTURE.md"
        self.assertTrue(doc.is_file(), "docs/CONVERSATION_ARCHITECTURE.md missing")

    def test_architecture_contract_documents_layers(self) -> None:
        doc = _REPO / "docs" / "CONVERSATION_ARCHITECTURE.md"
        body = doc.read_text(encoding="utf-8")
        for phrase in (
            "WHAT HAPPENED",
            "WHAT IS TRUE NOW",
            "WHAT TO DO NEXT",
            "HOW TO SAY IT",
            "MAY THIS BE SAID",
        ):
            self.assertIn(phrase, body)


if __name__ == "__main__":
    unittest.main()
