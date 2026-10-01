"""Production deterministic MissionUnderstandingProvider.

Works only from CallMission GoalDefinition data + MissionUnderstandingContext.
No domain/mission-specific Python dictionaries (plumber/meds/groceries/…).

Enum/bool values require an explicit gate (bare polarity, leading polarity +
delivered context, answer_aliases, or predicate-grounded negation of stems
from GoalDefinition.semantic_hints when non-empty). prompt_hint/description
are ranking/rendering context only — never factual negation polarity.
When semantic_hints is empty, free negative phrases do not become factual no
(bare «нет», answer_aliases, and other already-safe gates still apply).
Topic mention + any «не» is never enough for factual no. Uncertainty is
clause-local: an uncertain clause blocks hard yes/no via inherited/leading
polarity and hard negation; answer_aliases may still bind.

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
# Call-level control (not a goal answer). Imperative / request only —
# past-tense narrative «не звонил» must NOT hang up the call.
_CALL_CONTROL_NO_CALL = re.compile(
    r"(?i)\bне\s+(?:звоните|звони|звонить|звоню)\b"
)
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


def _one_word_alias_stems(gdef: GoalDefinition) -> frozenset[str]:
    """Single-token topic aliases — must not alone ground predicate negation."""
    out: set[str] = set()
    for alias in gdef.aliases or ():
        toks = [
            t.casefold()
            for t in _TOKEN.findall(alias or "")
            if t.casefold() not in _STOPWORDS
            and not t.isdigit()
            and len(t) >= 2
        ]
        if len(toks) == 1:
            out.add(_stem(toks[0]))
    return frozenset(out)


def _predicate_lexicon(gdef: GoalDefinition) -> frozenset[str]:
    """Stems that can ground factual polarity for this goal.

    If ``semantic_hints`` is non-empty: build ONLY from those hints (minus
    one-word topic aliases). ``prompt_hint`` / ``description`` are never
    used for factual negation polarity — only for ranking/rendering.

    If ``semantic_hints`` is empty: return empty — do not guess factual
    ``no`` from free negative phrases. Bare ``нет``, ``answer_aliases``,
    and other already-safe gates remain available outside this path.
    """
    hints = tuple(h for h in (gdef.semantic_hints or ()) if (h or "").strip())
    if not hints:
        return frozenset()
    stems = set(_content_stems(" ".join(hints)))
    stems -= _one_word_alias_stems(gdef)
    return frozenset(stems)


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
    """True only when ``не`` negates a goal PREDICATE stem.

    For every word ``не``, inspect the next 1–2 content tokens/stems. Return
    true only when a negated stem is in the predicate lexicon derived from
    non-empty ``semantic_hints`` (minus topic aliases). Topic alias alone is
    never enough. No domain verb dictionaries.
    """
    pred = _predicate_lexicon(gdef)
    if not pred:
        return False
    tokens = list(_TOKEN.finditer(clause or ""))
    if not tokens:
        return False
    for i, m in enumerate(tokens):
        if m.group(0).casefold() != "не":
            continue
        seen_content = 0
        for j in range(i + 1, len(tokens)):
            low = tokens[j].group(0).casefold()
            if low in _STOPWORDS or low.isdigit() or len(low) < 2:
                continue
            if _stem(low) in pred:
                return True
            seen_content += 1
            if seen_content >= 2:
                break
    return False


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


def _is_uncertainty_only_clause(text: str) -> bool:
    """True when the clause is only an uncertainty cue (e.g. «кажется»)."""
    raw = (text or "").strip()
    if not raw or not _is_uncertainty(raw):
        return False
    stripped = _UNCERTAINTY.sub(" ", raw)
    return not _content_stems(stripped)


def _clause_uncertain(clauses: list[_Clause], idx: int) -> bool:
    """Clause-local uncertainty, including a prior uncertainty-only cue clause.

    Whole-utterance uncertainty must NOT blanket every goal. A cue like
    «Кажется, …» (comma-split) still softens the following content clause.
    """
    if idx < 0 or idx >= len(clauses):
        return False
    if _is_uncertainty(clauses[idx].text):
        return True
    if idx > 0 and _is_uncertainty_only_clause(clauses[idx - 1].text):
        return True
    return False


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


def _wellness_speaker_text(text: str) -> str | None:
    """Speaker-only slice for wellness free_text.

    Other person's complaint («у мужа плохо») must never become the
    speaker's wellness fact. Mixed turns keep only speaker clauses
    («у мужа плохо, а у меня более-менее» → «у меня более-менее»).
    Returns None when no speaker slice exists.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        from packages.dialogue_engine.policy import _is_other_person_only
    except Exception:  # noqa: BLE001
        return raw
    clauses = split_mission_clauses(raw)
    if len(clauses) <= 1:
        if _is_other_person_only(raw):
            return None
        return raw
    kept = [c.text for c in clauses if not _is_other_person_only(c.text)]
    if not kept:
        return None
    if len(kept) == len(clauses):
        return raw
    joined = " ".join(kept).strip()
    joined = re.sub(r"^а\s+", "", joined, flags=re.I).strip()
    return joined or None


def _wellness_grounded(speaker_text: str) -> bool:
    """Wellness free_text is VALID only with grounded meaning.

    Accepts polarity signal, complaint/symptom, or a harvested wellness
    fact. Bare garbage («абракадабра») has none of these and must stay
    UNCLEAR instead of closing the slot.
    """
    raw = (speaker_text or "").strip()
    if not raw:
        return False
    try:
        from packages.dialogue_engine.fast_interpreter import (
            _detect_polarity as _well_pol,
        )
        from packages.dialogue_engine.fast_interpreter import (
            is_nonhealth_evaluation as _well_film,
        )

        # «Мне плохо от фильма»: badness about something else is not a
        # health answer, even though polarity/complaint markers fire.
        if _well_film(raw):
            return False
        if _well_pol(raw) is not None:
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        from packages.dialogue_engine.check_path import (
            _looks_like_complaint as _well_complaint,
        )
        from packages.dialogue_engine.check_path import (
            has_pain_mention as _well_pain,
        )

        if _well_complaint(raw) or _well_pain(raw):
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        from packages.dialogue_engine.issue_mention_extract import (
            extract_goal_facts as _well_facts,
        )

        facts = _well_facts(raw, answer_slot="wellness")
        if any(f.field == "wellness" for f in facts):
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _pick_value_for_clause(
    clause: str,
    gdef: GoalDefinition,
    *,
    inherited_polarity: str | None,
    for_delivered: bool,
    clause_uncertain: bool = False,
) -> str | None:
    """Enum/bool gates only — never topic-mention → yes.

    A. bare polarity (delivered path / bare clause)
    B. leading polarity + delivered context (for_delivered)
    C/D. answer_aliases / allowed-value phrase map from GoalDefinition
    E. linguistic negation of goal predicate → no

    Uncertainty is clause-local: if this clause is uncertain, do not emit
    hard yes/no via inherited/leading polarity or hard negation. Aliases
    (C/D) may still bind.
    """
    if gdef.answer_type == "free_text":
        return None  # free_text handled by dedicated path

    allowed = _allowed_for(gdef)

    # C/D — grounded answer_aliases from mission data (may bind even under uncertainty).
    alias_val = _match_answer_aliases(clause, gdef)
    if alias_val is not None:
        return alias_val if alias_val in allowed else None

    # Question / meta clause must not become a hard enum/bool fact.
    if _is_user_question(clause) or _is_meta(clause):
        return None

    # A — bare polarity clause (whole clause is just да/нет/не знаю).
    bare = _bare_polarity(clause)
    if bare is not None:
        if for_delivered and bare in allowed:
            return bare
        # Future goals must not absorb bare polarity meant for the delivered question.
        return None

    lead, rest = _leading_polarity(clause)

    # E — predicate-grounded negation only (not topic + any «не»).
    # Clause-local uncertainty blocks hard factual no unless alias matched.
    if _negation_near_goal_token(clause, gdef):
        if clause_uncertain:
            return None
        if "no" in allowed:
            return "no"
        return None

    score = _score_clause_to_goal(clause, gdef)

    # B — explicit leading / inherited polarity + unambiguous delivered context.
    # Clause-local uncertainty blocks hard yes/no polarity inheritance.
    if for_delivered:
        if clause_uncertain:
            return None
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
                clause_uncertain=_clause_uncertain(clauses, idx),
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
            # Wellness: context + subject + groundedness. Same «более-менее»
            # after sleep/pain belongs to that question (delivered binding
            # already scopes it); other person's clause never fills speaker
            # wellness; garbage never closes the slot.
            if gdef.goal_id == "wellness":
                speaker = _wellness_speaker_text(stripped)
                if speaker is None or not speaker:
                    return None
                try:
                    from packages.dialogue_engine.fast_interpreter import (
                        is_nonhealth_evaluation as _film_veto,
                    )

                    # Morphology veto beats the learned boundary: film-eval
                    # must not reach the judge as a candidate at all.
                    if _film_veto(speaker):
                        return None
                except Exception:  # noqa: BLE001
                    pass
                if not _wellness_grounded(speaker):
                    # Tier-2 (pilot only): learned answer/skip/garbage boundary
                    # for anchor-misses. `answer` records the user's own words
                    # (polarity resolved at write time; unknown valence falls
                    # back to uncertain there — probe, never the food ladder).
                    # skip/garbage/abstain → None (re-ask, never close).
                    # judge() returns None with the flag off → frozen path
                    # keeps the deterministic behavior above.
                    try:
                        from packages.dialogue_engine.slotclf import (
                            judge as _wellness_judge,
                        )

                        if _wellness_judge("wellness", speaker) != "answer":
                            return None
                    except Exception:  # noqa: BLE001 — fail closed to re-ask
                        return None
                return speaker
            if gdef.source != "daily_check_preset" and gdef.semantic_scope == "general":
                from packages.dialogue_engine.issue_mention_extract import extract_issue_mentions

                # Complaints are an interruption, not a name, shopping list,
                # address etc. Reuse Understand's grounded issue extraction;
                # no mission-specific phrase/verb dictionaries. In mixed
                # answers retain only an exact contiguous non-issue span.
                clauses = split_mission_clauses(stripped)
                kept = [
                    clause for clause in clauses
                    if not extract_issue_mentions(clause.text)
                ]
                if len(kept) != len(clauses):
                    if len(kept) != 1:
                        return None  # Multiple residual spans need a provider.
                    return kept[0].text
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
                    evidence=value,
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
            uncertain = _clause_uncertain(clauses, best_idx)
            value = _pick_value_for_clause(
                clause.text,
                gdef,
                inherited_polarity=inherited_polarity,
                for_delivered=True,
                clause_uncertain=uncertain,
            )
            if value is None and inherited_polarity and best_score >= _MIN_MATCH_SCORE:
                # Leading polarity + matching goal content (gate B).
                # Clause-local uncertainty blocks hard polarity inheritance.
                if not uncertain and not _negation_near_goal_token(clause.text, gdef):
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
