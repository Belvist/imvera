"""Shared clause segmentation for kernel parsers."""

from __future__ import annotations

import re

# Contrast/comma only — do NOT split on coordinating "и" inside one complaint.
_CLAUSE_SPLIT = re.compile(
    r"\s*(?:[,;.!?…]+|\s+(?:но|однако)\s+|\s+а\s+(?!также)|\s+а\s+также\s+|"
    r"(?<!сейчас)(?<!всё)(?<!все)\s+ещё\s+|(?<!сейчас)(?<!всё)(?<!все)\s+еще\s+)\s*",
    re.I,
)


def clause_bounds(text: str) -> list[tuple[int, int, str]]:
    clauses: list[tuple[int, int, str]] = []
    offset = 0
    lower = text.lower()
    for part in _CLAUSE_SPLIT.split(text):
        part = part.strip()
        if not part:
            continue
        start = lower.find(part.lower(), offset)
        if start < 0:
            start = offset
        end = start + len(part)
        clauses.append((start, end, part))
        offset = end
    return clauses or [(0, len(text), text)]


def clause_for_position(clauses: list[tuple[int, int, str]], pos: int) -> str:
    for start, end, clause in clauses:
        if start <= pos < end:
            return clause
    return clauses[-1][2] if clauses else ""
