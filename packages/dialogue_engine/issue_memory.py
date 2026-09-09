"""Generic issue episode memory — active/pending/evidence from RichUserTurn."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from packages.contracts.semantic import IssueMention
from packages.dialogue_engine.state import EngineState, IssueEpisode
from packages.dialogue_engine.topic_tracker import (
    _DURATION_MARKERS,
    TopicFamily,
    _norm,
    is_topic_slot,
)
from packages.dialogue_engine.turn_understanding import RichUserTurn

_UNKNOWN_ATTRIBUTE_ANSWER = re.compile(
    r"\b(не\s+знаю|не\s+помню|затрудня\w*(?:\s+сказ\w*)?|"
    r"не\s+могу\s+сказ|сложно\s+сказ|не\s+уверен\w*|не\s+скажу)\b",
    re.I,
)
_TEMPORAL_ANCHOR = re.compile(
    r"\b(давно|дня|дней|недел\w*|месяц\w*|час\w*|утр\w*|вчера|сегодня|"
    r"второй\s+день|третий\s+день|пару\s+дней|несколько|с\s+утра|"
    r"уже\s+\w+\s+дн|в\s+четыре|в\s+\d+|"
    r"с\s+десят\w*|с\s+\d+)\b",
    re.I,
)
_SEVERITY_ANCHOR = re.compile(
    r"\b(сильн\w*|терпим\w*|слаб\w*|невыносим\w*)\b",
    re.I,
)


@dataclass
class IngestResult:
    episodes_touched: list[str] = field(default_factory=list)
    activated: str | None = None


def _original_clause_slices(raw_text: str) -> list[str]:
    """Split user text into clauses without destroying original casing."""
    raw = raw_text.strip()
    raw = re.sub(r"[.!?]+$", "", raw)
    parts = re.split(r"\s*,\s*|\s*;\s*", raw)
    out: list[str] = []
    for part in parts:
        subs = re.split(r"\s+и\s+", part.strip(), maxsplit=0)
        out.extend(s.strip() for s in subs if s.strip())
    return out or [raw_text.strip()]


def _clause_excluded(clause: str, exclude_clauses: tuple[str, ...]) -> bool:
    c = _norm(clause)
    for excluded in exclude_clauses:
        e = _norm(excluded)
        if e and (e in c or c in e):
            return True
    return False


def extract_grounded_onset_value(
    raw_text: str,
    *,
    exclude_clauses: tuple[str, ...] = (),
) -> str | None:
    """Return onset only when a clause contains a grounded temporal anchor."""
    clauses = _original_clause_slices(raw_text) or [raw_text.strip()]
    for clause in clauses:
        text = clause.strip()
        if not text:
            continue
        if _clause_excluded(text, exclude_clauses):
            continue
        n = _norm(text)
        if _UNKNOWN_ATTRIBUTE_ANSWER.search(n):
            continue
        if _TEMPORAL_ANCHOR.search(n) or _DURATION_MARKERS.search(n):
            if len(clauses) == 1:
                return raw_text.strip().rstrip(",;")
            return text.rstrip(",;")
    return None


def extract_grounded_severity_value(
    raw_text: str,
    *,
    exclude_clauses: tuple[str, ...] = (),
) -> str | None:
    """Return severity only when a clause contains a grounded severity marker."""
    clauses = _original_clause_slices(raw_text) or [raw_text.strip()]
    for clause in clauses:
        text = clause.strip()
        if not text:
            continue
        if _clause_excluded(text, exclude_clauses):
            continue
        n = _norm(text)
        if _UNKNOWN_ATTRIBUTE_ANSWER.search(n):
            continue
        match = _SEVERITY_ANCHOR.search(n)
        if match:
            if len(clauses) == 1:
                return raw_text.strip().rstrip(",;")
            start, end = match.span()
            return text[start:end]
    return None


def _mention_exclusion_clauses(turn: RichUserTurn) -> tuple[str, ...]:
    return tuple(m.evidence.quote for m in turn.issue_mentions if m.evidence.quote)


def _maybe_clear_pending_attribute(
    state: EngineState,
    episode_id: str,
    attribute: str,
) -> None:
    if state.pending_episode_attribute == attribute:
        state.pending_episode_attribute = None


def _new_episode_id() -> str:
    return f"ep-{uuid.uuid4().hex[:8]}"


def _episode_from_mention(mention: IssueMention, turn_id: str) -> IssueEpisode:
    attrs: dict[str, str] = {}
    if mention.onset:
        attrs["onset"] = mention.onset
    if mention.severity:
        attrs["severity"] = mention.severity
    if mention.status in ("improving", "resolved"):
        attrs["current"] = mention.status
    return IssueEpisode(
        episode_id=_new_episode_id(),
        primary_label=mention.label,
        kind=mention.kind,
        body_site=mention.body_site,
        mentions=[mention],
        evidence_turn_ids=[turn_id],
        known_attributes=attrs,
        status="open" if mention.status not in ("resolved",) else "resolved",
    )


def _merge_mention(episode: IssueEpisode, mention: IssueMention, turn_id: str) -> None:
    episode.mentions.append(mention)
    if turn_id not in episode.evidence_turn_ids:
        episode.evidence_turn_ids.append(turn_id)
    if mention.onset:
        episode.known_attributes["onset"] = mention.onset
    if mention.severity:
        episode.known_attributes["severity"] = mention.severity
    if mention.status in ("improving", "resolved"):
        episode.known_attributes["current"] = mention.status


def _find_episode_for_mention(state: EngineState, mention: IssueMention) -> str | None:
    key = (mention.body_site or mention.label).lower()
    for ep_id, ep in state.issue_episodes.items():
        if ep.body_site and ep.body_site.lower() == key:
            return ep_id
        if ep.primary_label.lower() == mention.label.lower():
            return ep_id
    return None


def _group_episode_mentions(
    mentions: tuple[IssueMention, ...],
) -> list[tuple[IssueMention, list[IssueMention]]]:
    if not mentions:
        return []
    groups: list[tuple[IssueMention, list[IssueMention]]] = []
    current_primary: IssueMention | None = None
    associated: list[IssueMention] = []
    for mention in mentions:
        if mention.role == "associated" and current_primary is not None:
            associated.append(mention)
            continue
        if current_primary is not None:
            groups.append((current_primary, associated))
            associated = []
        current_primary = mention
    if current_primary is not None:
        groups.append((current_primary, associated))
    return groups


def _episode_handled_by_topic_flow(state: EngineState, ep: IssueEpisode) -> bool:
    """Topic-tracked families stay on Phase 1 topic flow — not pending episodes."""
    label = ep.primary_label.lower()
    if ep.body_site == "живот" or "живот" in label:
        return (
            TopicFamily.ABDOMINAL_PAIN in state.pending_topics
            or state.active_topic == TopicFamily.ABDOMINAL_PAIN
            or TopicFamily.ABDOMINAL_PAIN in state.topic_evidence
        )
    return False


def ingest_rich_turn(state: EngineState, turn: RichUserTurn) -> IngestResult:
    result = IngestResult()
    answered_episode_id = (
        state.active_episode_id
        if turn.answers_pending_question and state.pending_episode_attribute
        else None
    )
    answered_attribute = (
        state.pending_episode_attribute if answered_episode_id else None
    )

    if turn.correction:
        _apply_correction(state, turn)
        if answered_episode_id and answered_attribute:
            _fill_pending_attribute_for_episode(
                state,
                turn,
                answered_episode_id,
                answered_attribute,
            )
        return result

    if not turn.issue_mentions:
        if answered_episode_id and answered_attribute:
            _fill_pending_attribute_for_episode(
                state,
                turn,
                answered_episode_id,
                answered_attribute,
            )
        else:
            _fill_pending_attribute_from_answer(state, turn)
        return result

    groups = _group_episode_mentions(turn.issue_mentions)
    created: list[str] = []
    for primary, associated in groups:
        existing = _find_episode_for_mention(state, primary)
        if existing:
            ep = state.issue_episodes[existing]
            _merge_mention(ep, primary, turn.utterance_id)
            for extra in associated:
                _merge_mention(ep, extra, turn.utterance_id)
            created.append(existing)
        else:
            ep = _episode_from_mention(primary, turn.utterance_id)
            for extra in associated:
                _merge_mention(ep, extra, turn.utterance_id)
            state.issue_episodes[ep.episode_id] = ep
            created.append(ep.episode_id)

    if created:
        defer_focus = bool(
            is_topic_slot(state.answer_context_slot()) and state.active_topic is not None
        )
        if defer_focus:
            for ep_id in created:
                ep = state.issue_episodes[ep_id]
                if _episode_handled_by_topic_flow(state, ep):
                    continue
                if ep_id not in state.pending_episode_ids:
                    state.pending_episode_ids.append(ep_id)
        else:
            if (
                answered_episode_id
                and state.active_episode_id
                and state.active_episode_id not in created
                and state.active_episode_id not in state.pending_episode_ids
            ):
                state.pending_episode_ids.append(state.active_episode_id)
            state.active_episode_id = created[0]
            for ep_id in created[1:]:
                if ep_id != state.active_episode_id and ep_id not in state.pending_episode_ids:
                    state.pending_episode_ids.append(ep_id)
            result.activated = state.active_episode_id
        result.episodes_touched = created
    if answered_episode_id and answered_attribute:
        _fill_pending_attribute_for_episode(
            state,
            turn,
            answered_episode_id,
            answered_attribute,
        )
    elif turn.answers_pending_question:
        _fill_pending_attribute_from_answer(state, turn)
    return result


def _apply_correction(state: EngineState, turn: RichUserTurn) -> None:
    for mention in turn.issue_mentions:
        ep_id = _find_episode_for_mention(state, mention)
        if ep_id:
            state.active_episode_id = ep_id
            if ep_id in state.pending_episode_ids:
                state.pending_episode_ids.remove(ep_id)
            _merge_mention(state.issue_episodes[ep_id], mention, turn.utterance_id)
            return
    if turn.issue_mentions:
        ep = _episode_from_mention(turn.issue_mentions[0], turn.utterance_id)
        state.issue_episodes[ep.episode_id] = ep
        state.active_episode_id = ep.episode_id


def _fill_pending_attribute_for_episode(
    state: EngineState,
    turn: RichUserTurn,
    episode_id: str,
    attribute: str,
) -> None:
    if not turn.answers_pending_question:
        return
    ep = state.issue_episodes.get(episode_id)
    if ep is None:
        return
    exclude = _mention_exclusion_clauses(turn)
    if attribute == "onset":
        value = extract_grounded_onset_value(turn.raw_text, exclude_clauses=exclude)
        if value:
            ep.known_attributes["onset"] = value
            _maybe_clear_pending_attribute(state, episode_id, attribute)
        return
    if attribute == "severity":
        value = extract_grounded_severity_value(turn.raw_text, exclude_clauses=exclude)
        if value:
            ep.known_attributes["severity"] = value
            _maybe_clear_pending_attribute(state, episode_id, attribute)
        return
    raw = turn.raw_text.strip().lower()
    if attribute == "current" and raw:
        if any(x in raw for x in ("не бол", "прошл", "легче", "лучше", "нет")):
            ep.known_attributes["current"] = "resolved"
        elif any(x in raw for x in ("бол", "да", "ещё", "еще")):
            ep.known_attributes["current"] = "active"
        else:
            ep.known_attributes["current"] = turn.raw_text.strip()
        _maybe_clear_pending_attribute(state, episode_id, attribute)


def _fill_pending_attribute_from_answer(state: EngineState, turn: RichUserTurn) -> None:
    if not state.active_episode_id or not turn.answers_pending_question:
        return
    if not state.pending_episode_attribute:
        return
    _fill_pending_attribute_for_episode(
        state,
        turn,
        state.active_episode_id,
        state.pending_episode_attribute,
    )


def get_active_episode(state: EngineState) -> IssueEpisode | None:
    if not state.active_episode_id:
        return None
    return state.issue_episodes.get(state.active_episode_id)


def activate_next_pending_episode(state: EngineState) -> IssueEpisode | None:
    state.active_episode_id = None
    state.pending_episode_attribute = None
    while state.pending_episode_ids:
        candidate = state.pending_episode_ids.pop(0)
        ep = state.issue_episodes.get(candidate)
        if ep and ep.status != "resolved":
            state.active_episode_id = candidate
            return ep
    return None


def episode_complete(ep: IssueEpisode) -> bool:
    if ep.status == "resolved":
        return True
    if ep.kind == "symptom":
        if "onset" not in ep.known_attributes:
            return False
        if _needs_severity(ep) and "severity" not in ep.known_attributes:
            return False
        if ep.body_site == "живот" and "current" not in ep.known_attributes:
            return False
        return True
    return "onset" in ep.known_attributes or ep.kind == "sleep_problem"


def _needs_severity(ep: IssueEpisode) -> bool:
    label = ep.primary_label.lower()
    return "голов" in label or "боль" in label


def has_abdominal_episode(state: EngineState) -> bool:
    for ep in state.issue_episodes.values():
        if ep.body_site == "живот" or "живот" in ep.primary_label.lower():
            return True
    return False
