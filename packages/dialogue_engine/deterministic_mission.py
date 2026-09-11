"""Production deterministic MissionUnderstandingProvider.

Works only from CallMission GoalDefinition data + MissionUnderstandingContext.
No domain/mission-specific Python dictionaries (plumber/meds/groceries/…).

Enum/bool values require an explicit gate (bare polarity, leading polarity +
delivered context, answer_aliases, or linguistic negation of the goal
predicate). Topic mention alone is never affirmative.

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

# Generic refusal ≠ factual "нет". No domain/topic refusal dictionaries.
_GENERIC_REFUSAL = re.compile(
    r"(?i)(?:"
    r"\bне\s+хочу\b|"
    r"\bне\s+надо\b|"
    r"\bне\s+буду\b|"
    r"\bне\s+желаю\b|"
    r"\bотказываюсь\b|"
    r"\bоткажусь\b"
    r")"
)
# Call-level control (not a goal answer).
_CALL_CONTROL_NO_CALL = re.compile(r"(?i)\bне\s+звон\w*")
_PAUSE = re.compile(
    r"(?i)\b(подождите|подожди|минуточку|секундочку|погодите)\b"
)
_UNCERTAINTY = re.compile(
    r"(?i)\b("
    r"не\s+знаю|не\s+помню|не\s+уверен\w*|не\s+уверена|"
    r"возможно|наверное|кажется|хз"
    r")\b"
)
_USER_QUESTION = re.compile(
    r"(?i)("
    r"\?|"
    r"\bзачем\b|"
    r"\bпочему\b|"
    r"\bкто\s+вы\b|"
    r"\bа\s+вы\s+кто\b|"
    r"\bчто\s+вам\s+нужн|"
    r"\bчто\s+вы\s+хотите\b|"
    r"\bчто\s+вы\s+спрашив|"
    r"\bзачем\s+вы\b"
    r")"
)
_META_ABOUT_CALL = re.compile(
    r"(?i)("
    r"\bзачем\s+вы\s+(это\s+)?спрашив|"
    r"\bзачем\s+звон|"
    r"\bпочему\s+звон|"
    r"\bкто\s+вы\b|"
    r"\bчто\s+вам\s+нужн"
    r")"
)
_CORRECTION_MARKER = re.compile(
    r"(?i)("
    r"я\s+ошиб(?:ся|лась|лись)|"
    r"\bточнее\b|"
    r"нет[,]?\s*поправлю|"
    r"на\s+самом\s+деле|"
    r"вс[её]-таки|"
    r"\bвернее\b"
    r")"
)

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
# Future (non-delivered) goals need denser overlap than a single topic stem.
_FUTURE_MIN_MATCH_SCORE = 2.0
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


def _has_correction_marker(text: str) -> bool:
    return bool(_CORRECTION_MARKER.search(text or ""))


def _is_generic_refusal(text: str) -> bool:
    """Refusal of answering — not factual polarity, not call-control."""
    raw = (text or "").strip()
    if not raw:
        return False
    if _CALL_CONTROL_NO_CALL.search(raw):
        return False
    if _bare_polarity(raw) == "no":
        return False
    return bool(_GENERIC_REFUSAL.search(raw))


def _is_call_control(text: str) -> bool:
    return bool(_CALL_CONTROL_NO_CALL.search(text or ""))


def _is_pause(text: str) -> bool:
    return bool(_PAUSE.search(text or ""))


def _is_user_question(text: str) -> bool:
    return bool(_USER_QUESTION.search(text or ""))


def _is_meta(text: str) -> bool:
    return bool(_META_ABOUT_CALL.search(text or ""))


def _is_uncertainty(text: str) -> bool:
    return bool(_UNCERTAINTY.search(text or ""))


def _free_text_blocked_reason(text: str) -> str | None:
    """Return why free_text must not accept this utterance, else None."""
    raw = (text or "").strip()
    if not raw:
        return "empty"
    if _is_call_control(raw):
        return "control"
    if _is_generic_refusal(raw):
        return "refusal"
    if _is_pause(raw):
        return "pause"
    if _is_user_question(raw) or _is_meta(raw):
        return "question"
    if _is_uncertainty(raw):
        return "uncertainty"
    return None


def _pick_value_for_clause(
    clause: str,
    gdef: GoalDefinition,
    *,
    inherited_polarity: str | None,
    for_delivered: bool,
) -> str | None:
    """Enum/bool gates only — never topic-mention → yes.

    A. bare polarity (delivered path / bare clause)
    B. leading polarity + delivered context (for_delivered)
    C/D. answer_aliases / allowed-value phrase map from GoalDefinition
    E. linguistic negation of goal predicate → no
    """
    if gdef.answer_type == "free_text":
        return None  # free_text handled by dedicated path

    allowed = _allowed_for(gdef)

    # C/D — grounded answer_aliases from mission data.
    alias_val = _match_answer_aliases(clause, gdef)
    if alias_val is not None:
        return alias_val if alias_val in allowed else None

    # A — bare polarity clause.
    bare = _bare_polarity(clause)
    if bare is not None:
        if for_delivered and bare in allowed:
            return bare
        # Future goals must not absorb bare polarity meant for the delivered question.
        return None

    lead, rest = _leading_polarity(clause)

    # E — unambiguous linguistic negation of the goal predicate.
    if _negation_near_goal_token(clause, gdef):
        if "no" in allowed:
            return "no"
        return None

    score = _score_clause_to_goal(clause, gdef)

    # B — explicit leading / inherited polarity + unambiguous delivered context.
    if for_delivered:
        if lead is not None and not rest and lead in allowed:
            return lead
        polarity = lead if lead is not None else inherited_polarity
        if (
            polarity is not None
            and polarity in allowed
            and score >= _MIN_MATCH_SCORE
            and not _negation_near_goal_token(clause, gdef)
        ):
            return polarity
        # Leading polarity alone with empty/weak remainder — delivered only.
        if lead is not None and lead in allowed and score < _MIN_MATCH_SCORE:
            if not rest or not _content_stems(rest):
                return lead
        return None

    # Future goals: alias (above) or negation (above) only.
    # One topic stem is insufficient; no fabricated yes.
    _ = score  # scored for ranking only; never maps to yes here
    return None


def _lifecycle_map(context: MissionUnderstandingContext | None) -> dict[str, str]:
    if context is None:
        return {}
    return dict(context.goal_lifecycles)


def _candidate_goal_ids(
    mission: CallMission,
    context: MissionUnderstandingContext | None,
    *,
    include_satisfied: bool,
) -> list[str]:
    lifecycle = _lifecycle_map(context)
    out: list[str] = []
    for g in mission.goals:
        life = lifecycle.get(g.goal_id, "UNSEEN")
        if life == "SATISFIED" and include_satisfied:
            out.append(g.goal_id)
            continue
        if life in _TERMINAL:
            continue
        out.append(g.goal_id)
    return out


def _rank_goals_for_clause(
    clause: str,
    mission: CallMission,
    candidate_ids: list[str],
    *,
    min_score: float,
) -> list[tuple[float, GoalDefinition]]:
    ranked: list[tuple[float, GoalDefinition]] = []
    for gid in candidate_ids:
        gdef = definition_by_id(mission, gid)
        if gdef is None:
            continue
        score = _score_clause_to_goal(clause, gdef)
        if score >= min_score:
            ranked.append((score, gdef))
    ranked.sort(key=lambda x: (-x[0], x[1].priority, x[1].goal_id))
    return ranked


def _evidence_span(utterance: str, clause: _Clause) -> str:
    span = utterance[clause.start : clause.end]
    return span if span.strip() else clause.text


def _was_satisfied(context: MissionUnderstandingContext | None, goal_id: str) -> bool:
    return _lifecycle_map(context).get(goal_id) == "SATISFIED"


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

        correction = _has_correction_marker(text)
        candidates = _candidate_goal_ids(
            request.mission, ctx, include_satisfied=correction
        )
        if not candidates:
            return StructuredMissionResult()

        # Call-level control before any goal binding.
        if _is_call_control(text):
            return StructuredMissionResult(control="stop_call")

        # Generic refusal → declined for delivered goal (not factual no).
        if _is_generic_refusal(text):
            dispositions: list[GoalDispositionCandidate] = []
            if delivered_id and delivered_id in candidates:
                dispositions.append(
                    GoalDispositionCandidate(
                        goal_id=delivered_id,
                        disposition="declined",
                        confidence=0.92,
                        evidence=text.strip(),
                    )
                )
            return StructuredMissionResult(goal_dispositions=tuple(dispositions))

        clauses = split_mission_clauses(text)
        answers: list[GoalAnswerCandidate] = []
        dispositions = []
        bound_goals: set[str] = set()
        used_clause_indexes: set[int] = set()

        utterance_polarity = _bare_polarity(text)
        leading_polarity, after_lead = _leading_polarity(text)
        inherited = utterance_polarity or leading_polarity

        # --- B. First bind answer to DELIVERED goal ---
        if delivered_id and delivered_id in candidates:
            gdef = definition_by_id(request.mission, delivered_id)
            if gdef is not None:
                bound, disp, used_idx = self._bind_delivered(
                    text=text,
                    clauses=clauses,
                    gdef=gdef,
                    inherited_polarity=inherited,
                    after_lead=after_lead,
                    is_correction=correction and _was_satisfied(ctx, delivered_id),
                )
                if bound is not None:
                    answers.append(bound)
                    bound_goals.add(delivered_id)
                    if used_idx is not None:
                        used_clause_indexes.add(used_idx)
                elif disp is not None:
                    dispositions.append(disp)
                    if used_idx is not None:
                        used_clause_indexes.add(used_idx)

        # --- C. Remaining clauses → other unresolved / correction goals ---
        remaining_ids = [g for g in candidates if g not in bound_goals]
        for idx, clause in enumerate(clauses):
            if idx in used_clause_indexes:
                continue
            if _bare_polarity(clause.text) is not None:
                continue
            if _is_generic_refusal(clause.text):
                continue
            # Future binding is stricter than delivered: require denser lexical overlap
            # OR alias/negation (checked inside pick). Ranking uses future min score
            # unless an answer_alias hits (score boost via lexicon still needed for rank).
            ranked = _rank_goals_for_clause(
                clause.text,
                request.mission,
                remaining_ids,
                min_score=_MIN_MATCH_SCORE,
            )
            if not ranked:
                continue
            # Prefer alias hits; otherwise require future-strength uniqueness.
            alias_ranked = [
                (s, g)
                for s, g in ranked
                if _match_answer_aliases(clause.text, g) is not None
                or _negation_near_goal_token(clause.text, g)
            ]
            pool = alias_ranked if alias_ranked else [
                (s, g) for s, g in ranked if s >= _FUTURE_MIN_MATCH_SCORE
            ]
            if not pool:
                # Topic mention alone / weak future match → do not fabricate SATISFIED.
                continue
            top_score, top_gdef = pool[0]
            if len(pool) > 1 and (top_score - pool[1][0]) < _AMBIGUITY_EPSILON:
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
                for_delivered=False,
            )
            if value is None and top_gdef.answer_type == "free_text":
                value = self._free_text_value(
                    clause.text,
                    top_gdef,
                    for_delivered=False,
                )
            if value is None:
                # Matched topic without affirmative gate → clarify, do not invent yes.
                if top_gdef.answer_type in {"enum", "bool"}:
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
                    is_correction=correction and _was_satisfied(ctx, top_gdef.goal_id),
                )
            )
            bound_goals.add(top_gdef.goal_id)
            remaining_ids = [g for g in remaining_ids if g != top_gdef.goal_id]
            used_clause_indexes.add(idx)

        user_q: str | None = None
        if _is_user_question(text) or _is_meta(text):
            user_q = text.strip()

        return StructuredMissionResult(
            goal_answers=tuple(answers),
            goal_dispositions=tuple(dispositions),
            user_question=user_q,
        )

    def _free_text_value(
        self,
        text: str,
        gdef: GoalDefinition,
        *,
        for_delivered: bool,
    ) -> str | None:
        blocked = _free_text_blocked_reason(text)
        if blocked is not None:
            return None
        stripped = text.strip()
        if not stripped:
            return None
        if for_delivered:
            return stripped
        # Future free_text: require strong hint/alias — not any non-empty utterance.
        if _match_answer_aliases(stripped, gdef) is not None:
            return stripped
        if _score_clause_to_goal(stripped, gdef) >= _FUTURE_MIN_MATCH_SCORE:
            return stripped
        return None

    def _bind_delivered(
        self,
        *,
        text: str,
        clauses: list[_Clause],
        gdef: GoalDefinition,
        inherited_polarity: str | None,
        after_lead: str,
        is_correction: bool,
    ) -> tuple[GoalAnswerCandidate | None, GoalDispositionCandidate | None, int | None]:
        # Free-text delivered: filter questions / refusal / control / meta / pause.
        if gdef.answer_type == "free_text":
            blocked = _free_text_blocked_reason(text)
            if blocked == "refusal":
                return (
                    None,
                    GoalDispositionCandidate(
                        goal_id=gdef.goal_id,
                        disposition="declined",
                        confidence=0.92,
                        evidence=text.strip(),
                    ),
                    0 if clauses else None,
                )
            if blocked is not None:
                return (None, None, None)
            value = self._free_text_value(text, gdef, for_delivered=True)
            if value is None:
                return (None, None, None)
            return (
                GoalAnswerCandidate(
                    goal_id=gdef.goal_id,
                    value=value,
                    confidence=0.8,
                    evidence=text.strip(),
                    is_correction=is_correction,
                ),
                None,
                0 if clauses else None,
            )

        # A — bare whole-utterance polarity to delivered goal.
        bare = _bare_polarity(text)
        if bare is not None:
            allowed = _allowed_for(gdef)
            if bare in allowed:
                return (
                    GoalAnswerCandidate(
                        goal_id=gdef.goal_id,
                        value=bare,
                        confidence=0.95,
                        evidence=text.strip(),
                        is_correction=is_correction,
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
            value = _pick_value_for_clause(
                clause.text,
                gdef,
                inherited_polarity=inherited_polarity,
                for_delivered=True,
            )
            if value is None and inherited_polarity and best_score >= _MIN_MATCH_SCORE:
                # Leading polarity + matching goal content (gate B).
                if not _negation_near_goal_token(clause.text, gdef):
                    if inherited_polarity in _allowed_for(gdef):
                        value = inherited_polarity
            if value is None:
                # Topic mention without affirmative gate → unclear, not yes.
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
                    is_correction=is_correction,
                ),
                None,
                best_idx,
            )

        # No lexical match: leading/bare polarity alone may still answer delivered enum/bool (A/B).
        if inherited_polarity and gdef.answer_type in {"enum", "bool"}:
            allowed = _allowed_for(gdef)
            if inherited_polarity in allowed:
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
                            is_correction=is_correction,
                        ),
                        None,
                        0 if clauses else None,
                    )
                if _content_stems(remainder):
                    # Remainder exists but did not bind this goal — do not guess.
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
                        is_correction=is_correction,
                    ),
                    None,
                    0 if clauses else None,
                )

        return (None, None, None)
