"""Structured mission understanding — candidates only, zero EngineState writes.

Generic over GoalDefinition.prompt_hint + answer schema.
No per-mission Python branches (no utilities_/groceries_ special cases).
"""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING

from packages.dialogue_engine.mission import (
    CallMission,
    GoalAnswerCandidate,
    GoalDefinition,
    definition_by_id,
)
from packages.dialogue_engine.semantic_kernel.lexicon import OTHER_PERSON_MARKERS
from packages.dialogue_engine.semantic_kernel.types import Observation, SubjectKind

if TYPE_CHECKING:
    from packages.dialogue_engine.state import EngineState

_YES = re.compile(
    r"(?i)\b(да|ага|угу|конечно|успел\w*|оплатил\w*|сделал\w*|приходил\w*|"
    r"оплачен\w*|заплатил\w*)\b"
)
_NO = re.compile(
    r"(?i)\b(нет|не\s+успел\w*|не\s+оплатил\w*|не\s+надо|не\s+нужн\w*|"
    r"не\s+приходил\w*|не\s+хочу)\b"
)
_UNKNOWN = re.compile(r"(?i)\b(не\s+знаю|хз|забыл\w*|не\s+помню)\b")

# Domain-general problem / degradation reports (not mission-id specific).
_PROBLEM_CLAUSE = re.compile(
    r"(?i)([^.!?;]+(?:\bне\s+работа\w*|\bеле\s+работа\w*|\bпочти\s+не\s+работа\w*|"
    r"\bслома\w*|\bне\s+греет|\bплохо\s+работа\w*|не\s+включа\w*)[^.!?;]*)"
)

_STOPWORDS = frozenset(
    {
        "и",
        "а",
        "но",
        "или",
        "как",
        "вы",
        "себя",
        "на",
        "в",
        "с",
        "у",
        "о",
        "об",
        "ли",
        "ли",
        "сегодня",
        "сейчас",
        "пожалуйста",
        "скажите",
        "нужна",
        "нужно",
        "нужен",
        "успели",
        "можете",
    }
)


def _tokens(text: str) -> set[str]:
    parts = re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", text.lower())
    out: set[str] = set()
    for p in parts:
        if len(p) < 4 or p in _STOPWORDS:
            continue
        # cheap stem: strip common Russian endings
        stem = re.sub(r"(ами|ями|ить|ать|ять|ого|ему|ыми|ых|ов|ев|ей|ой|ие|ия|ию)$", "", p)
        if len(stem) >= 4:
            out.add(stem)
        out.add(p)
    return out


def _enum_value(text: str) -> str | None:
    if _UNKNOWN.search(text):
        return "unknown"
    if _NO.search(text):
        return "no"
    if _YES.search(text):
        return "yes"
    return None


def _overlap_score(utterance: str, hint: str) -> float:
    ut = _tokens(utterance)
    ht = _tokens(hint)
    if not ht:
        return 0.0
    hit = len(ut & ht)
    return hit / max(1, len(ht))


def _evidence_span(text: str, needle_re: re.Pattern[str]) -> str:
    m = needle_re.search(text)
    if m:
        return m.group(0)
    # first clause as weak evidence
    clause = re.split(r"[.!;]", text, maxsplit=1)[0].strip()
    return clause[:120]


def extract_goal_answers(
    text: str,
    *,
    mission: CallMission,
    active_goal_id: str | None,
    engine_state: EngineState | None = None,
) -> tuple[GoalAnswerCandidate, ...]:
    """Map utterance → goal answers using definitions + active question context."""
    raw = text.strip()
    if not raw or not mission.goals:
        return ()

    enum_val = _enum_value(raw)
    candidates: list[GoalAnswerCandidate] = []

    # 1) Active / delivered goal first (strongest context).
    ordered: list[GoalDefinition] = []
    if active_goal_id:
        g = definition_by_id(mission, active_goal_id)
        if g is not None:
            ordered.append(g)
    for gdef in sorted(mission.goals, key=lambda g: g.priority):
        if gdef in ordered:
            continue
        if engine_state is not None:
            runtime = engine_state.goals.get(gdef.goal_id)
            if runtime is not None and runtime.lifecycle.value == "SATISFIED":
                continue
        ordered.append(gdef)

    for gdef in ordered:
        if gdef.answer_type not in {"enum", "bool"}:
            continue
        if enum_val is None:
            continue
        allowed = set(gdef.allowed_values) or {"yes", "no", "unknown"}
        if enum_val not in allowed:
            continue
        # Active goal: accept enum even with weak lexical overlap.
        # Other open goals: require hint overlap so we don't mark groceries from
        # a utilities answer alone.
        overlap = _overlap_score(raw, gdef.prompt_hint or gdef.description)
        is_active = active_goal_id == gdef.goal_id
        if not is_active and overlap < 0.15:
            continue
        conf = 0.92 if is_active else min(0.9, 0.55 + overlap)
        if enum_val == "yes":
            needle = _YES
        elif enum_val == "no":
            needle = _NO
        else:
            needle = _UNKNOWN
        evidence = _evidence_span(raw, needle)
        # Prefer clause that also overlaps hint when present.
        for clause in re.split(r"[.!;]+", raw):
            c = clause.strip()
            if not c:
                continue
            if _overlap_score(c, gdef.prompt_hint or "") >= overlap and _enum_value(c) == enum_val:
                evidence = c
                break
        candidates.append(
            GoalAnswerCandidate(
                goal_id=gdef.goal_id,
                value=enum_val,
                confidence=conf,
                evidence=evidence,
            )
        )
        # One primary enum answer per turn unless multiple hints clearly match.
        if is_active:
            break

    # Deduplicate by goal_id keeping highest confidence.
    best: dict[str, GoalAnswerCandidate] = {}
    for item in candidates:
        prev = best.get(item.goal_id)
        if prev is None or item.confidence > prev.confidence:
            best[item.goal_id] = item
    return tuple(best.values())


def extract_side_observations(
    text: str,
    *,
    goal_answer_evidence: tuple[str, ...] = (),
) -> tuple[Observation, ...]:
    """Generic free-text observations (problems, other-person plans). Not goal-id keyed."""
    raw = text.strip()
    if not raw:
        return ()
    used = {e.lower() for e in goal_answer_evidence if e}
    out: list[Observation] = []

    for m in _PROBLEM_CLAUSE.finditer(raw):
        clause = m.group(1).strip(" ,.-")
        if not clause or clause.lower() in used:
            continue
        # Strip leading conjunctions
        clause = re.sub(r"(?i)^(только|ещё|еще|и|а|но)\s+", "", clause).strip()
        out.append(
            Observation(
                observation_id=f"obs-{uuid.uuid4().hex[:10]}",
                attribute="reported_problem",
                value=clause,
                normalized_value=clause.lower(),
                subject=SubjectKind.SPEAKER,
                confidence=0.85,
                evidence=clause,
                status="candidate",
            )
        )

    # Other-person mention with future/plan verb in same clause.
    for clause in re.split(r"[.!;]+", raw):
        c = clause.strip()
        if not c or c.lower() in used:
            continue
        low = c.lower()
        person = next((p for p in OTHER_PERSON_MARKERS if p in low), None)
        if person is None:
            continue
        if not re.search(r"(?i)обещ\w*|зайд\w*|прид\w*|приед\w*|должен\w*|должн\w*", c):
            continue
        out.append(
            Observation(
                observation_id=f"obs-{uuid.uuid4().hex[:10]}",
                attribute="other_person_plan",
                value=c,
                normalized_value=c.lower(),
                subject=SubjectKind.OTHER_PERSON,
                confidence=0.8,
                evidence=c,
                status="candidate",
            )
        )
    return tuple(out)


def understand_mission_turn(
    text: str,
    *,
    utterance_id: str,
    engine_state: EngineState,
    mission: CallMission | None = None,
) -> tuple[GoalAnswerCandidate, ...]:
    """Production understanding helper for mission goals (no state mutation)."""
    from packages.dialogue_engine.mission_seed import resolve_mission

    resolved = mission or resolve_mission(None)
    # Prefer mission metadata on state when present.
    if engine_state.mission_goal_ids and mission is None:
        # Rebuild thin CallMission from seeded ids is insufficient for hints;
        # caller should pass mission or store definitions. Use attached module cache.
        pass
    active = engine_state.answer_context_slot()
    return extract_goal_answers(
        text,
        mission=resolved,
        active_goal_id=active,
        engine_state=engine_state,
    )
