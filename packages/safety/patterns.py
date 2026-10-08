"""Single source of safety patterns and guards (P0 audit fix).

Two detectors (`dialogue_engine.check_path` for the engine hijack,
`safety.rules` for the legacy SafetyEngine) import from here. One fix
lands in both. Guards order per clause: third-party → negation → past.
Imperative help calls (помогите/спасите/вызовите скорую) bypass the
past guard but never the negation guard.
"""

from __future__ import annotations

import re

# Shared surface for an explicit breathing difficulty, in either word order.
# The existing clause guards, not this lexical fragment, own attribution/time.
BREATHING_DIFFICULTY = r"(?:трудно|тяжело)\s+дышать|дышать\s+(?:трудно|тяжело)"

# Negation immediately before the match ("я не упала", "не падала").
_NEGATION = re.compile(r"(?:\bне\b|\bни\b|\bникогда\b)[\s,]*$", re.I)

# Past markers ("упала вчера" is history, not an emergency now).
_PAST = re.compile(
    r"\b(вчера|позавчера|на\s+прошлой\s+неделе|раньше|давно|"
    r"на\s+днях|в\s+прошлом\s+году)\b",
    re.I,
)

# Present-tense distress keeps urgency despite a past marker
# ("упала вчера, лежу не могу встать").
_PRESENT_DISTRESS = re.compile(
    r"\b(сейчас|лежу|не\s+могу|плохо|болит|кровь|помогите|спасите)\b",
    re.I,
)

# Third party without self ("муж упал" is not the caller's fall).
_THIRD_PARTY = re.compile(
    r"\b(сосед\w*|внук\w*|внучк\w*|дочь|дочер\w*|дочк\w*|сын\w*|мама|папа|"
    r"брат\w*|сестр\w*|родственник\w*|муж(?:а|у|ем|е)?|жен(?:а|у|ы|е|ой)|"
    r"супруг\w*|ему|ей|им)\b",
    re.I,
)
_SELF = re.compile(r"\b(я|мне|меня|у\s+меня)\b", re.I)

# Explicit request for help: the user asked — no false-alarm doubt.
EXPLICIT_HELP_REQUEST = re.compile(
    r"\b(помогите|спасите|вызывайте\s+скор\w*|вызови(те)?\s+скор\w*|"
    r"вызвали\s+скор\w*|вызвать\s+скор\w*|вызов\w*\s+скор\w*|срочн\w*)\b",
    re.I,
)

# Imperatives bypass the past guard (help needed now by definition).
_IMPERATIVE_HELP = EXPLICIT_HELP_REQUEST

_CLAUSE_SPLIT = re.compile(r"[,;]|\s+но\s+|\s+а\s+", re.I)


def split_clauses(text: str) -> list[str]:
    parts = _CLAUSE_SPLIT.split((text or "").lower().strip())
    return [p.strip() for p in parts if p.strip()]


def _negated(clause: str, start: int) -> bool:
    prefix = clause[:start].rstrip()
    if _NEGATION.search(prefix):
        return True
    tokens = prefix.split()
    if tokens and tokens[-1] in ("не", "ни", "никогда"):
        return True
    return len(tokens) >= 2 and tokens[-2] == "не"


def match_guarded(pattern: re.Pattern[str], text: str) -> re.Match[str] | None:
    """First match surviving third-party / negation / past guards."""
    for clause in split_clauses(text):
        clause_help = _IMPERATIVE_HELP.search(clause) is not None
        for match in pattern.finditer(clause):
            if _THIRD_PARTY.search(clause) and not _SELF.search(clause):
                continue
            if _negated(clause, match.start()):
                continue
            if not clause_help:
                past = _PAST.search(clause)
                if past and not _PRESENT_DISTRESS.search(clause):
                    continue
            return match
    return None


def is_third_party_only(clause: str) -> bool:
    return bool(_THIRD_PARTY.search(clause)) and not bool(_SELF.search(clause))


def is_negated_at(clause: str, match_start: int) -> bool:
    return _negated(clause, match_start)


def is_past_without_present(clause: str) -> bool:
    return bool(_PAST.search(clause)) and not bool(_PRESENT_DISTRESS.search(clause))


def is_negated_match(text: str, match_start: int) -> bool:
    for clause in split_clauses(text):
        if match_start < len(clause):
            return _negated(clause, match_start)
    return False
