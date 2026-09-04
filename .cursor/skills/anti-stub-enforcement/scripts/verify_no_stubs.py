#!/usr/bin/env python3
"""Static scan for stub patterns in production Python code.

Exits 0 when clean, 1 when violations are found.
Used by Makefile target `verify-stubs` and CI pre-commit hooks.

Scans: telephony/, voice_runtime/, scripts/ (excluding tests by default).
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]

DEFAULT_SCAN_ROOTS = (
    ROOT / "telephony",
    ROOT / "voice_runtime",
    ROOT / "scripts",
)

SKIP_DIR_NAMES = {
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "qwen-venv",
    "nemotron-venv",
    "site-packages",
    "node_modules",
    "asset",
    "piper_voices",
    "refs",
}

DEFERRED_MARKERS = re.compile(
    r"#\s*(TODO|FIXME|STUB|PLACEHOLDER)\b",
    re.IGNORECASE,
)

HANDWAVE_MARKERS = re.compile(
    r"(rest of implementation|implement (?:business )?logic later|insert calculation here)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    code: str
    detail: str


def _iter_python_files(roots: tuple[Path, ...], include_tests: bool) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            parts = path.parts
            if any(part in SKIP_DIR_NAMES for part in parts):
                continue
            if not include_tests and ("tests" in parts or parts[-1].startswith("test_")):
                continue
            files.append(path)
    return sorted(files)


def _class_is_informal_abc(node: ast.ClassDef) -> bool:
    if any(isinstance(base, ast.Name) and base.id == "ABC" for base in node.bases):
        return True
    if any(
        isinstance(base, ast.Attribute) and base.attr == "ABC"
        for base in node.bases
    ):
        return True
    doc = ast.get_docstring(node) or ""
    if "abstract" in doc.lower():
        return True
    methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if not methods:
        return False
    nie_count = 0
    for method in methods:
        if _function_raises_not_implemented(method):
            nie_count += 1
    return nie_count == len(methods) and len(methods) >= 2


def _function_raises_not_implemented(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Raise) and isinstance(child.exc, ast.Name):
            if child.exc.id == "NotImplementedError":
                return True
    return False


def _has_abstractmethod_decorator(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == "abstractmethod":
            return True
        if isinstance(dec, ast.Attribute) and dec.attr == "abstractmethod":
            return True
    return False


def _body_is_stub_only(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    if _has_abstractmethod_decorator(node):
        return False
    body = [stmt for stmt in node.body if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Constant)]
    # keep docstring-only expr stripped above — re-check
    real_body = []
    for stmt in node.body:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
            continue
        real_body.append(stmt)
    if not real_body:
        return True
    if len(real_body) == 1:
        stmt = real_body[0]
        if isinstance(stmt, ast.Pass):
            return True
        if isinstance(stmt, ast.Raise) and isinstance(stmt.exc, ast.Name):
            if stmt.exc.id == "NotImplementedError":
                return True
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            if stmt.value.value is ...:
                return True
    return False


ALLOWED_HOLLOW_NAMES = frozenset({"log_message", "close"})


def _pass_has_explanatory_comment(text: str, node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    lines = text.splitlines()
    for stmt in node.body:
        if isinstance(stmt, ast.Pass) and stmt.lineno >= 2:
            prev = lines[stmt.lineno - 2].strip()
            if prev.startswith("#"):
                return True
    return False


def _line_has_noqa(text: str, lineno: int) -> bool:
    lines = text.splitlines()
    idx = lineno - 1
    if 0 <= idx < len(lines) and "noqa" in lines[idx]:
        return True
    if 0 <= idx + 1 < len(lines) and "noqa" in lines[idx + 1]:
        return True
    return False


def _scan_ast(path: Path, tree: ast.AST, text: str) -> list[Violation]:
    violations: list[Violation] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            informal_abc = _class_is_informal_abc(node)
            for item in node.body:
                if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if informal_abc or _has_abstractmethod_decorator(item):
                    continue
                if item.name in ALLOWED_HOLLOW_NAMES:
                    continue
                if _body_is_stub_only(item) and not _pass_has_explanatory_comment(text, item):
                    violations.append(
                        Violation(
                            path=path,
                            line=item.lineno,
                            code="HOLLOW_FUNCTION",
                            detail=f"function `{item.name}` has stub-only body (pass/NotImplemented/...)",
                        )
                    )
                elif _function_raises_not_implemented(item):
                    violations.append(
                        Violation(
                            path=path,
                            line=item.lineno,
                            code="NOT_IMPLEMENTED",
                            detail=f"concrete function `{item.name}` raises NotImplementedError",
                        )
                    )

        if isinstance(node, ast.Try):
            try_lineno = node.lineno
            for handler in node.handlers:
                if handler.type is None:
                    continue
                if len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass):
                    if _line_has_noqa(text, handler.lineno) or _line_has_noqa(text, try_lineno):
                        continue
                    violations.append(
                        Violation(
                            path=path,
                            line=handler.lineno,
                            code="SWALLOWED_EXCEPTION",
                            detail="except block silently passes",
                        )
                    )

    return violations


def _scan_text(path: Path, text: str) -> list[Violation]:
    violations: list[Violation] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if DEFERRED_MARKERS.search(line):
            violations.append(
                Violation(
                    path=path,
                    line=lineno,
                    code="DEFERRED_MARKER",
                    detail=line.strip(),
                )
            )
        if HANDWAVE_MARKERS.search(line):
            violations.append(
                Violation(
                    path=path,
                    line=lineno,
                    code="HANDWAVE",
                    detail=line.strip(),
                )
            )
    return violations


def scan_files(paths: list[Path]) -> list[Violation]:
    all_violations: list[Violation] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            all_violations.append(
                Violation(path=path, line=0, code="READ_ERROR", detail=str(exc))
            )
            continue
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            all_violations.append(
                Violation(
                    path=path,
                    line=exc.lineno or 0,
                    code="SYNTAX_ERROR",
                    detail=str(exc),
                )
            )
            continue
        all_violations.extend(_scan_ast(path, tree, text))
        all_violations.extend(_scan_text(path, text))
    return all_violations


BASELINE_PATH = Path(__file__).resolve().parent.parent / "baseline.txt"


def _violation_key(v: Violation) -> str:
    rel = v.path.relative_to(ROOT) if v.path.is_relative_to(ROOT) else v.path
    return f"{rel}:{v.line}:{v.code}"


def _load_baseline(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    keys: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            keys.add(line)
    return keys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect stub patterns in production Python.")
    parser.add_argument(
        "--include-tests",
        action="store_true",
        help="Also scan telephony/tests and voice_runtime test files",
    )
    parser.add_argument(
        "--no-baseline",
        action="store_true",
        help="Fail on all violations, ignore baseline.txt legacy allowlist",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Rewrite baseline.txt with current violations (use after fixing legacy)",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Optional paths to scan (default: telephony, voice_runtime, scripts)",
    )
    args = parser.parse_args(argv)

    if args.paths:
        roots = tuple(Path(p).resolve() for p in args.paths)
    else:
        roots = DEFAULT_SCAN_ROOTS

    skip_tests = not args.include_tests
    files = _iter_python_files(roots, include_tests=not skip_tests)
    violations = scan_files(files)

    if args.update_baseline:
        BASELINE_PATH.write_text(
            "\n".join(sorted(_violation_key(v) for v in violations)) + ("\n" if violations else ""),
            encoding="utf-8",
        )
        print(f"Updated baseline: {len(violations)} violation(s) in {BASELINE_PATH}")
        return 0

    baseline = set() if args.no_baseline else _load_baseline(BASELINE_PATH)
    new_violations = [v for v in violations if _violation_key(v) not in baseline]

    if not violations:
        print(f"OK: {len(files)} file(s) scanned, no stub violations.")
        return 0

    if not new_violations:
        print(
            f"OK: {len(files)} file(s) scanned; "
            f"{len(violations)} legacy baseline violation(s), 0 new."
        )
        return 0

    print(
        f"FAIL: {len(new_violations)} NEW stub violation(s) "
        f"({len(violations)} total, {len(violations) - len(new_violations)} in baseline) "
        f"in {len(files)} file(s):\n"
    )
    for v in new_violations:
        rel = v.path.relative_to(ROOT) if v.path.is_relative_to(ROOT) else v.path
        print(f"  {rel}:{v.line} [{v.code}] {v.detail}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
