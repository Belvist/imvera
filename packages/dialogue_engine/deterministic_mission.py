"""Production deterministic MissionUnderstandingProvider.

Works only from CallMission GoalDefinition data + MissionUnderstandingContext.
No domain/mission-specific Python dictionaries (plumber/meds/groceries/…).

Behaviors inspired by older voice MVP quality (clause split, multi-goal bind,
evidence spans, clarify-when-ambiguous) — not a port of that engine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from packages.dialogue_engine.mission import (
    CallMission,
    GoalAnswerCandidate,
    GoalDefinition,
    GoalDispositionCandidate,
    definition_by_id,
)
from packages.dialogue_engine.mission_understanding import (
    MissionUnderstandingContext,
    MissionUnderstandingRequest,
    StructuredMissionResult,
)

# Language infrastructure only — not domain/mission catalogs.
_BARE_YES = re.compile(r"(?i)^\s*(да|ага|угу)\s*[.!]?\s*$")
_BARE_NO = re.compile(r"(?i)^\s*(нет)\s*[.!]?\s*$")
_BARE_UNKNOWN = re.compile(r"(?i)^\s*(не\s+знаю|не\s+помню)\s*[.!]?\s*$")
_LEADING_YES = re.compile(r"(?i)^\s*(да|ага|угу)\s*[,!.]?\s*")
_LEADING_NO = re.compile(r"(?i)^\s*(нет)\s*[,!.]?\s*")
_LEADING_UNKNOWN = re.compile(r"(?i)^\s*(не\s+знаю|не\s+помню)\s*[,!.]?\s*")
_TOKEN = re.compile(r"[а-яёa-z0-9]+", re.I)
_NEGATION = re.compile(r"(?i)(?<![а-яёa-z])не(?![а-яёa-z])")

# Mission clause split: commas, contrast, sentence ends. Keep offsets for evidence.
_CLAUSE_SPLIT = re.compile(
    r"(?:"
    r"\s*[,;]\s*"
    r"|\s*[.!?]+\s+"
    r"|\s+но\s+"
    r"|\s+однако\s+"
    r"|\s+а\s+(?!также)"
    r"|\s+а\s+также\s+"
    r"|\s+ещё\s+"
    r"|\s+еще\s+"
    r")",
    re.I,
)

_STOPWORDS = frozenset(
    {
        "а",
        "без",
        "бы",
        "в",
        "вам",
        "вас",
        "во",
        "вот",
        "все",
        "всё",
        "вы",
        "да",
        "для",
        "до",
        "его",
        "ее",
        "её",
        "если",
        "есть",
        "еще",
        "ещё",
        "же",
        "за",
        "и",
        "из",
        "или",
        "к",
        "как",
        "когда",
        "ли",
        "мне",
        "меня",
        "мы",
        "на",
        "над",
        "не",
        "нет",
        "но",
        "о",
        "об",
        "он",
        "она",
        "они",
        "от",
        "по",
        "под",
        "после",
        "при",
        "про",
        "с",
        "сейчас",
        "сегодня",
        "так",
        "то",
        "у",
        "уже",
        "это",
        "что",
        "чтобы",
    }
)

_STEM_SUFFIXES = (
    "ивать",
    "ывать",
    "овать",
    "евать",
    "нуть",
    "ться",
    "тся",
    "ешь",
    "ете",
    "ать",
    "ять",
    "ить",
    "еть",
    "ал",
    "ала",
    "али",
    "ил",
    "ила",
    "или",
    "ыл",
    "ыла",
    "ыли",
    "лось",
    "лась",
    "лись",
    "ами",
    "ями",
    "ах",
    "ях",
    "ом",
    "ем",
    "ой",
    "ей",
    "ую",
    "юю",
    "ый",
    "ий",
    "ая",
    "яя",
    "ое",
    "ее",
    "ые",
    "ие",
    "ов",
    "ев",
    "ам",
    "ям",
    "у",
    "ю",
    "а",
    "я",
    "е",
    "и",
    "ы",
    "о",
)

_TERMINAL = frozenset(
    {
        "SATISFIED",
        "DECLINED",
        "SKIPPED",
        "NOT_APPLICABLE",
        "BLOCKED",
    }
)

_MIN_MATCH_SCORE = 1.0
_AMBIGUITY_EPSILON = 0.15


@dataclass(frozen=True)
class _Clause:
    start: int
    end: int
    text: str


def split_mission_clauses(text: str) -> list[_Clause]:
    """Split utterance into semantic clauses with exact evidence spans."""
    raw = text or ""
    if not raw.strip():
        return []
    clauses: list[_Clause] = []
    offset = 0
    lower = raw.lower()
    parts = _CLAUSE_SPLIT.split(raw)
    for part in parts:
        part_stripped = part.strip()
        if not part_stripped:
            continue
        start = lower.find(part_stripped.lower(), offset)
        if start < 0:
            start = raw.find(part_stripped, offset)
        if start < 0:
            start = offset
        end = start + len(part_stripped)
        clauses.append(_Clause(start=start, end=end, text=part_stripped))
        offset = end
    return clauses or [_Clause(0, len(raw), raw.strip())]


def _stem(token: str) -> str:
    t = token.casefold()
    if len(t) <= 3:
        return t
    for suf in _STEM_SUFFIXES:
        if len(t) > len(suf) + 2 and t.endswith(suf):
            return t[: -len(suf)]
    return t


def _content_stems(text: str) -> frozenset[str]:
    stems: set[str] = set()
    for tok in _TOKEN.findall(text or ""):
        low = tok.casefold()
        if low in _STOPWORDS or low.isdigit():
            continue
        if len(low) < 2:
            continue
        stems.add(_stem(low))
    return frozenset(stems)


def _goal_lexicon(gdef: GoalDefinition) -> frozenset[str]:
    parts = [
        gdef.prompt_hint or "",
        gdef.description or "",
        *gdef.aliases,
        *gdef.semantic_hints,
    ]
    return _content_stems(" ".join(parts))


def _score_clause_to_goal(clause: str, gdef: GoalDefinition) -> float:
    lex = _goal_lexicon(gdef)
    if not lex:
        return 0.0
    clause_stems = _content_stems(clause)
    if not clause_stems:
        return 0.0
    overlap = clause_stems & lex
    if not overlap:
        # Substring fall-back: full alias / hint phrase inside clause.
        low = clause.casefold()
        for phrase in (*gdef.aliases, *gdef.semantic_hints, gdef.prompt_hint, gdef.description):
            p = (phrase or "").strip().casefold()
            if len(p) >= 4 and p in low:
                return 1.5
        return 0.0
    # Prefer denser overlap relative to goal lexicon size.
    return float(len(overlap)) + (0.25 * len(overlap) / max(1, len(lex)))


def _negation_near_goal_token(clause: str, gdef: GoalDefinition) -> bool:
    """True when the clause both matches the goal and carries a negation.

    Language-level ``не`` near goal content → polarity no. No domain verb lists.
    """
    if not _NEGATION.search(clause or ""):
        return False
    if _score_clause_to_goal(clause, gdef) < _MIN_MATCH_SCORE:
        return False
    return True


def _match_answer_aliases(clause: str, gdef: GoalDefinition) -> str | None:
    low = clause.casefold()
    hits: list[tuple[int, str]] = []
    for value, phrases in (gdef.answer_aliases or {}).items():
        for phrase in phrases or ():
            p = (phrase or "").strip().casefold()
            if not p:
                continue
            if p in low or _content_stems(p) <= _content_stems(clause):
                hits.append((len(p), value))
    if not hits:
        return None
    hits.sort(key=lambda x: -x[0])
    best_len, best_val = hits[0]
    # Ambiguous aliases of equal strength for different values → refuse.
    rivals = [v for ln, v in hits if ln == best_len and v != best_val]
    if rivals:
        return None
    return best_val


def _bare_polarity(text: str) -> str | None:
    if _BARE_YES.match(text):
        return "yes"
    if _BARE_NO.match(text):
        return "no"
    if _BARE_UNKNOWN.match(text):
        return "unknown"
    return None


def _leading_polarity(text: str) -> tuple[str | None, str]:
    for pattern, value in (
        (_LEADING_UNKNOWN, "unknown"),
        (_LEADING_YES, "yes"),
        (_LEADING_NO, "no"),
    ):
        m = pattern.match(text)
        if m:
            return value, text[m.end() :].strip()
    return None, text


def _allowed_for(gdef: GoalDefinition) -> set[str]:
    if gdef.answer_type == "free_text":
        return set()
    return set(gdef.allowed_values) or {"yes", "no", "unknown"}


def _pick_value_for_clause(
    clause: str,
    gdef: GoalDefinition,
    *,
    inherited_polarity: str | None,
) -> str | None:
    if gdef.answer_type == "free_text":
        text = clause.strip()
        return text if text else None

    allowed = _allowed_for(gdef)
    alias_val = _match_answer_aliases(clause, gdef)
    if alias_val is not None:
        return alias_val if alias_val in allowed else None

    bare = _bare_polarity(clause)
    if bare is not None:
        return bare if bare in allowed else None

    lead, rest = _leading_polarity(clause)
    if lead is not None and not rest:
        return lead if lead in allowed else None

    score = _score_clause_to_goal(clause, gdef)
    if score < _MIN_MATCH_SCORE and inherited_polarity is None:
        # Leading polarity alone may answer delivered goal without content overlap.
        if lead is not None and lead in allowed:
            return lead
        return None

    if _negation_near_goal_token(clause, gdef):
        if "no" in allowed:
            return "no"
        return None

    if score >= _MIN_MATCH_SCORE:
        if "yes" in allowed:
            return "yes"
        return None

    if inherited_polarity is not None and inherited_polarity in allowed:
        return inherited_polarity
    if lead is not None and lead in allowed:
        return lead
    return None


def _unresolved_goal_ids(
    mission: CallMission,
    context: MissionUnderstandingContext | None,
) -> list[str]:
    lifecycle = dict(context.goal_lifecycles) if context is not None else {}
    out: list[str] = []
    for g in mission.goals:
        life = lifecycle.get(g.goal_id, "UNSEEN")
        if life in _TERMINAL:
            continue
        out.append(g.goal_id)
    return out


def _rank_goals_for_clause(
    clause: str,
    mission: CallMission,
    candidate_ids: list[str],
) -> list[tuple[float, GoalDefinition]]:
    ranked: list[tuple[float, GoalDefinition]] = []
    for gid in candidate_ids:
        gdef = definition_by_id(mission, gid)
        if gdef is None:
            continue
        score = _score_clause_to_goal(clause, gdef)
        if score >= _MIN_MATCH_SCORE:
            ranked.append((score, gdef))
    ranked.sort(key=lambda x: (-x[0], x[1].priority, x[1].goal_id))
    return ranked


def _evidence_span(utterance: str, clause: _Clause) -> str:
    span = utterance[clause.start : clause.end]
    return span if span.strip() else clause.text


class DeterministicMissionUnderstandingProvider:
    """Production mission understanding — CallMission data + context only."""

    def understand(self, request: MissionUnderstandingRequest) -> StructuredMissionResult:
        text = (request.text or "").strip()
        if not text:
            return StructuredMissionResult()

        ctx = request.context
        delivered_id = request.delivered_goal_id or (
            ctx.delivered_goal_id if ctx is not None else None
        )
        phase = (
            request.delivered_question_phase
            or (ctx.delivered_question_phase if ctx is not None else None)
            or ""
        ).upper()
        if delivered_id and phase and phase != "DELIVERED":
            delivered_id = None

        unresolved = _unresolved_goal_ids(request.mission, ctx)
        if not unresolved:
            return StructuredMissionResult()

        clauses = split_mission_clauses(text)
        answers: list[GoalAnswerCandidate] = []
        dispositions: list[GoalDispositionCandidate] = []
        bound_goals: set[str] = set()
        used_clause_indexes: set[int] = set()

        utterance_polarity = _bare_polarity(text)
        leading_polarity, after_lead = _leading_polarity(text)
        inherited = utterance_polarity or leading_polarity

        # --- B. First bind answer to DELIVERED goal ---
        if delivered_id and delivered_id in unresolved:
            gdef = definition_by_id(request.mission, delivered_id)
            if gdef is not None:
                bound, disp, used_idx = self._bind_delivered(
                    text=text,
                    clauses=clauses,
                    gdef=gdef,
                    inherited_polarity=inherited,
                    after_lead=after_lead,
                )
                if bound is not None:
                    answers.append(bound)
                    bound_goals.add(delivered_id)
                    if used_idx is not None:
                        used_clause_indexes.add(used_idx)
                elif disp is not None:
                    dispositions.append(disp)

        # --- C. Remaining clauses → other unresolved goals (unambiguous only) ---
        remaining_ids = [g for g in unresolved if g not in bound_goals]
        for idx, clause in enumerate(clauses):
            if idx in used_clause_indexes:
                continue
            if _bare_polarity(clause.text) is not None:
                # Bare polarity already consumed for delivered (or ignored).
                continue
            ranked = _rank_goals_for_clause(clause.text, request.mission, remaining_ids)
            if not ranked:
                continue
            top_score, top_gdef = ranked[0]
            if len(ranked) > 1 and (top_score - ranked[1][0]) < _AMBIGUITY_EPSILON:
                # Ambiguous goal binding → do not guess.
                dispositions.append(
                    GoalDispositionCandidate(
                        goal_id=top_gdef.goal_id,
                        disposition="unclear",
                        confidence=0.55,
                        evidence=_evidence_span(text, clause),
                    )
                )
                used_clause_indexes.add(idx)
                continue
            value = _pick_value_for_clause(
                clause.text,
                top_gdef,
                inherited_polarity=None,
            )
            if value is None:
                dispositions.append(
                    GoalDispositionCandidate(
                        goal_id=top_gdef.goal_id,
                        disposition="unclear",
                        confidence=0.5,
                        evidence=_evidence_span(text, clause),
                    )
                )
                used_clause_indexes.add(idx)
                continue
            answers.append(
                GoalAnswerCandidate(
                    goal_id=top_gdef.goal_id,
                    value=value,
                    confidence=min(0.98, 0.7 + 0.08 * top_score),
                    evidence=_evidence_span(text, clause),
                )
            )
            bound_goals.add(top_gdef.goal_id)
            remaining_ids = [g for g in remaining_ids if g != top_gdef.goal_id]
            used_clause_indexes.add(idx)

        return StructuredMissionResult(
            goal_answers=tuple(answers),
            goal_dispositions=tuple(dispositions),
        )

    def _bind_delivered(
        self,
        *,
        text: str,
        clauses: list[_Clause],
        gdef: GoalDefinition,
        inherited_polarity: str | None,
        after_lead: str,
    ) -> tuple[GoalAnswerCandidate | None, GoalDispositionCandidate | None, int | None]:
        # Bare whole-utterance polarity.
        bare = _bare_polarity(text)
        if bare is not None:
            allowed = _allowed_for(gdef)
            if gdef.answer_type != "free_text" and bare in allowed:
                return (
                    GoalAnswerCandidate(
                        goal_id=gdef.goal_id,
                        value=bare,
                        confidence=0.95,
                        evidence=text.strip(),
                    ),
                    None,
                    0 if clauses else None,
                )

        # Prefer best-matching clause for this delivered goal.
        best_idx = -1
        best_score = 0.0
        for idx, clause in enumerate(clauses):
            score = _score_clause_to_goal(clause.text, gdef)
            if score > best_score:
                best_score = score
                best_idx = idx

        if best_idx >= 0 and best_score >= _MIN_MATCH_SCORE:
            clause = clauses[best_idx]
            # Guard: another goal must not match equally/better unless clearly weaker.
            # (Ambiguity vs other goals checked by caller for multi-bind; here for delivered
            # we still refuse if value cannot be determined.)
            value = _pick_value_for_clause(
                clause.text,
                gdef,
                inherited_polarity=inherited_polarity,
            )
            if value is None and inherited_polarity and not after_lead:
                value = inherited_polarity if inherited_polarity in _allowed_for(gdef) else None
            if value is None and inherited_polarity and best_score >= _MIN_MATCH_SCORE:
                # "Да, мастер приходил" — lead yes + matching content.
                if not _negation_near_goal_token(clause.text, gdef):
                    if inherited_polarity in _allowed_for(gdef):
                        value = inherited_polarity
            if value is None:
                return (
                    None,
                    GoalDispositionCandidate(
                        goal_id=gdef.goal_id,
                        disposition="unclear",
                        confidence=0.55,
                        evidence=_evidence_span(text, clause),
                    ),
                    best_idx,
                )
            return (
                GoalAnswerCandidate(
                    goal_id=gdef.goal_id,
                    value=value,
                    confidence=min(0.98, 0.75 + 0.08 * best_score),
                    evidence=_evidence_span(text, clause),
                ),
                None,
                best_idx,
            )

        # No lexical match: leading/bare polarity alone may still answer delivered enum/bool.
        if inherited_polarity and gdef.answer_type in {"enum", "bool"}:
            allowed = _allowed_for(gdef)
            if inherited_polarity in allowed:
                # Only when remainder is empty or has no competing content answer.
                remainder = after_lead if after_lead else ""
                if not remainder or _bare_polarity(remainder) is not None:
                    evidence = text.strip() if not remainder else (
                        clauses[0].text if clauses else text.strip()
                    )
                    return (
                        GoalAnswerCandidate(
                            goal_id=gdef.goal_id,
                            value=inherited_polarity,
                            confidence=0.9,
                            evidence=evidence,
                        ),
                        None,
                        0 if clauses else None,
                    )
                # Remainder exists but didn't match this goal — polarity alone is weak;
                # if remainder has content stems, treat as unclear rather than guess.
                if _content_stems(remainder):
                    return (
                        None,
                        GoalDispositionCandidate(
                            goal_id=gdef.goal_id,
                            disposition="unclear",
                            confidence=0.5,
                            evidence=remainder[:120],
                        ),
                        None,
                    )
                return (
                    GoalAnswerCandidate(
                        goal_id=gdef.goal_id,
                        value=inherited_polarity,
                        confidence=0.85,
                        evidence=text.strip(),
                    ),
                    None,
                    0 if clauses else None,
                )

        # Free-text delivered: take whole utterance if non-empty and not bare control.
        if gdef.answer_type == "free_text" and text.strip():
            return (
                GoalAnswerCandidate(
                    goal_id=gdef.goal_id,
                    value=text.strip(),
                    confidence=0.8,
                    evidence=text.strip(),
                ),
                None,
                0 if clauses else None,
            )

        return (None, None, None)
