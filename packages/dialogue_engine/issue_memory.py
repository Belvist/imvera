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
    r"\b(давно|дня|дней|недел\w*|месяц\w*|час\w*|утр\w*|вчерашн\w*|вчера|сегодня|"
    r"второй\s+день|третий\s+день|пару\s+дней|несколько|с\s+утра|"
    r"со?\s+вчерашн\w*|уже\s+\w+\s+дн|в\s+четыре|в\s+\d+|"
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
    current = _infer_current_from_mention(mention)
    if current:
        attrs["current"] = current
    if mention.kind == "sleep_problem":
        label = (mention.label or "").lower()
        if any(x in label for x in ("плох", "бессон", "не спал")):
            attrs["quality"] = "poor"
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


_PRESENT_SYMPTOM = re.compile(
    r"\b(болит|ноет|давит|ломит|кружит|тошнит)\b",
    re.I,
)
_PAST_SYMPTOM = re.compile(
    r"\b(болел[аио]?|ныл[аио]?|давил[аио]?|тошнил[аио]?)\b",
    re.I,
)


def _infer_current_from_mention(mention: IssueMention) -> str | None:
    """Present-tense complaint ⇒ current=active; past-only ⇒ ask trend later."""
    if mention.status in ("improving", "resolved"):
        return mention.status
    quote = f"{getattr(mention.evidence, 'quote', '') or ''} {mention.label or ''}"
    if _PRESENT_SYMPTOM.search(quote):
        return "active"
    if _PAST_SYMPTOM.search(quote):
        return None
    if mention.status == "active":
        return "active"
    return None


def _merge_mention(episode: IssueEpisode, mention: IssueMention, turn_id: str) -> None:
    episode.mentions.append(mention)
    if turn_id not in episode.evidence_turn_ids:
        episode.evidence_turn_ids.append(turn_id)
    if mention.onset:
        episode.known_attributes["onset"] = mention.onset
    if mention.severity:
        episode.known_attributes["severity"] = mention.severity
    current = _infer_current_from_mention(mention)
    if current:
        episode.known_attributes["current"] = current
    if mention.kind == "sleep_problem":
        label = (mention.label or "").lower()
        if any(x in label for x in ("плох", "бессон", "не спал")):
            episode.known_attributes.setdefault("quality", "poor")


def _find_episode_for_mention(state: EngineState, mention: IssueMention) -> str | None:
    key = (mention.body_site or mention.label).lower()
    for ep_id, ep in state.issue_episodes.items():
        if ep.body_site and ep.body_site.lower() == key:
            return ep_id
        if ep.primary_label.lower() == mention.label.lower():
            return ep_id
    return None


_ASSOCIATED_SECONDARY_LABELS = frozenset(
    {"тошнота", "тошнит", "головокружение", "слабость", "усталость"}
)


def _headache_episode_id(state: EngineState) -> str | None:
    for ep_id, ep in state.issue_episodes.items():
        label = (ep.primary_label or "").lower()
        if ep.body_site == "голова" or "голов" in label:
            return ep_id
    return None


def _dedupe_primary_mentions(mentions: tuple[IssueMention, ...]) -> tuple[IssueMention, ...]:
    """Kernel often emits two primaries for one body site (живот болит + боль в животе)."""
    seen_sites: set[str] = set()
    seen_primaries: set[str] = set()
    out: list[IssueMention] = []
    for mention in mentions:
        if mention.body_site and mention.role in ("primary", "independent"):
            if mention.body_site in seen_sites:
                continue
            seen_sites.add(mention.body_site)
        elif mention.role in ("primary", "independent"):
            label = (mention.label or "").lower()
            if label in seen_primaries:
                continue
            seen_primaries.add(label)
        out.append(mention)
    return tuple(out)


def finalize_episode_if_complete(ep: IssueEpisode) -> None:
    """Close episode when product pack obligations are met so it cannot be re-activated."""
    from packages.dialogue_engine.question_context import episode_is_resolved
    from packages.dialogue_engine.state import EngineState

    if episode_is_resolved(ep):
        return
    family = ep.known_attributes.get("_product_family")
    if family:
        shim = EngineState(call_id="finalize")
        shim.issue_episodes = {ep.episode_id: ep}
        from packages.dialogue_engine.product.planner import product_episode_complete

        # Attach episode as active so pending checks don't block falsely.
        shim.active_episode_id = ep.episode_id
        if product_episode_complete(shim, ep):
            ep.status = "resolved"
        return
    from packages.dialogue_engine.question_context import episode_obligations_satisfied

    if episode_obligations_satisfied(ep):
        ep.status = "resolved"


def _merge_associated_episode_groups(
    groups: list[tuple[IssueMention, list[IssueMention]]],
) -> list[tuple[IssueMention, list[IssueMention]]]:
    """One primary episode per turn — nausea/dizziness stay associated with headache."""
    if len(groups) <= 1:
        return groups
    primary, associated = groups[0]
    primary_label = (primary.label or "").lower()
    merged = list(associated)
    rest: list[tuple[IssueMention, list[IssueMention]]] = []
    for sec_primary, sec_assoc in groups[1:]:
        sec_label = (sec_primary.label or "").lower()
        headache_primary = "голов" in primary_label or primary.body_site == "голова"
        secondary_associated = (
            sec_primary.role in ("associated", "independent")
            and sec_label in _ASSOCIATED_SECONDARY_LABELS
        )
        if headache_primary and secondary_associated:
            merged.append(sec_primary)
            merged.extend(sec_assoc)
        else:
            rest.append((sec_primary, sec_assoc))
    return [(primary, merged)] + rest


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


def _background_slot_issue_override(turn: RichUserTurn, answer_slot: str) -> bool:
    """Keep issue mentions that should redirect focus (e.g. headache at sleep slot)."""
    if not turn.issue_mentions:
        return False
    for mention in turn.issue_mentions:
        label = (mention.label or "").lower()
        if mention.kind == "symptom" and (
            "голов" in label
            or mention.body_site in ("голова", "живот", "горло")
        ):
            return True
        if answer_slot == "sleep" and mention.kind == "sleep_problem":
            return False
    return False


_FATIGUE_DIMENSION = re.compile(r"усталост\w*\s+есть", re.I)


def _mention_is_unrelated_dimension_answer(
    state: EngineState,
    mention: IssueMention,
    raw_text: str,
) -> bool:
    """Sleep/fatigue dimension phrases are not new episodes during unrelated episode probe."""
    if not state.pending_episode_attribute or not state.active_episode_id:
        return False
    active = state.issue_episodes.get(state.active_episode_id)
    if active is None:
        return False
    n = raw_text.strip()
    label = (mention.label or "").lower()
    if _FATIGUE_DIMENSION.fullmatch(n.rstrip(".!?")):
        return True
    if mention.kind == "sleep_problem" and active.kind != "sleep_problem":
        return True
    if active.body_site and mention.body_site != active.body_site:
        if any(token in label for token in ("устал", "сон", "спал", "бодр")):
            return True
    return False


def _mention_is_topic_dimension_answer(
    state: EngineState,
    mention: IssueMention,
) -> bool:
    """Fatigue/sleep answers during topic Q&A are not parallel IssueEpisodes."""
    if not state.active_topic or not is_topic_slot(state.answer_context_slot() or ""):
        return False
    label = (mention.label or "").lower()
    if state.active_topic == TopicFamily.SLEEP:
        if mention.kind == "sleep_problem":
            return True
        if any(token in label for token in ("устал", "сон", "спал", "бодр")):
            return True
    if state.active_topic == TopicFamily.ABDOMINAL_PAIN:
        if mention.body_site == "живот" or "живот" in label:
            return True
    return False


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


def filter_rich_turn_mentions(state: EngineState, turn: RichUserTurn) -> RichUserTurn:
    """Drop dimension-only mentions that must not become parallel episodes."""
    from packages.dialogue_engine.question_context import utterance_indicates_resolved

    if state.pending_episode_attribute and state.active_episode_id:
        if utterance_indicates_resolved(turn.raw_text):
            return turn.model_copy(update={"issue_mentions": ()})
    if not turn.issue_mentions:
        return turn

    active = get_active_episode(state)
    # Sleep pack: daytime fatigue answers belong to sleep episode, not new «устаю».
    if active is not None and (
        active.kind == "sleep_problem"
        or "сон" in (active.primary_label or "").lower()
        or "спал" in (active.primary_label or "").lower()
    ):
        fatigue_labels = ("устал", "устаю", "усталость", "сонлив", "слаб")
        kept: list[IssueMention] = []
        absorbed = False
        for mention in turn.issue_mentions:
            label = (mention.label or "").lower()
            if any(tok in label for tok in fatigue_labels) or mention.kind == "sleep_problem":
                if state.pending_episode_attribute == "daytime_impact" or not active.known_attributes.get(
                    "daytime_impact"
                ):
                    active.known_attributes["daytime_impact"] = turn.raw_text.strip()
                    if state.pending_episode_attribute == "daytime_impact":
                        state.pending_episode_attribute = None
                    absorbed = True
                continue
            kept.append(mention)
        if absorbed or len(kept) != len(turn.issue_mentions):
            turn = turn.model_copy(update={"issue_mentions": tuple(kept)})
            if not turn.issue_mentions:
                return turn

    if state.pending_episode_attribute and state.active_episode_id:
        filtered = [
            m
            for m in turn.issue_mentions
            if not _mention_is_unrelated_dimension_answer(state, m, turn.raw_text)
        ]
        if len(filtered) != len(turn.issue_mentions):
            return turn.model_copy(update={"issue_mentions": tuple(filtered)})
    return turn


def ingest_rich_turn(state: EngineState, turn: RichUserTurn) -> IngestResult:
    result = IngestResult()
    answer_slot = state.answer_context_slot()
    if (
        answer_slot in ("mood", "sleep", "plans")
        and turn.answers_pending_question
        and not _background_slot_issue_override(turn, answer_slot)
    ):
        turn = turn.model_copy(update={"issue_mentions": ()})
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

    answer_slot = state.answer_context_slot()
    if is_topic_slot(answer_slot) and state.active_topic:
        if answered_episode_id and answered_attribute:
            _fill_pending_attribute_for_episode(
                state,
                turn,
                answered_episode_id,
                answered_attribute,
            )
        elif turn.answers_pending_question:
            _fill_pending_attribute_from_answer(state, turn)
        if turn.issue_mentions:
            filtered: list[IssueMention] = []
            for mention in turn.issue_mentions:
                if _mention_is_topic_dimension_answer(state, mention):
                    continue
                probe = _episode_from_mention(mention, turn.utterance_id)
                if _episode_handled_by_topic_flow(state, probe):
                    continue
                filtered.append(mention)
            if filtered:
                turn = turn.model_copy(update={"issue_mentions": tuple(filtered)})
            else:
                return result
        else:
            return result

    if turn.issue_mentions and state.pending_episode_attribute and state.active_episode_id:
        filtered_dim = [
            m
            for m in turn.issue_mentions
            if not _mention_is_unrelated_dimension_answer(state, m, turn.raw_text)
        ]
        if len(filtered_dim) != len(turn.issue_mentions):
            turn = turn.model_copy(update={"issue_mentions": tuple(filtered_dim)})

    # While answering a pending episode attribute: keep focus. Secondary
    # symptoms (тошнота…) attach to the answered/headache episode; new body
    # sites may queue as pending — never steal active mid-answer.
    if (
        answered_episode_id
        and answered_attribute
        and turn.issue_mentions
    ):
        kept_mentions: list[IssueMention] = []
        for mention in turn.issue_mentions:
            label = (mention.label or "").strip().lower()
            if _find_episode_for_mention(state, mention):
                kept_mentions.append(mention)
                continue
            if mention.role == "associated" or label in _ASSOCIATED_SECONDARY_LABELS:
                target_id = _headache_episode_id(state) or answered_episode_id
                target = state.issue_episodes.get(target_id)
                if target is not None:
                    assoc = mention.model_copy(update={"role": "associated"})
                    _merge_mention(target, assoc, turn.utterance_id)
                continue
            if mention.body_site or (
                label and label not in {"болит", "боль", "ноет", "ломит", "давит"}
            ):
                kept_mentions.append(mention)
        turn = turn.model_copy(update={"issue_mentions": tuple(kept_mentions)})

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

    mentions = _dedupe_primary_mentions(turn.issue_mentions)
    groups = _merge_associated_episode_groups(_group_episode_mentions(mentions))
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
        hold_focus = bool(answered_episode_id)
        if defer_focus or hold_focus:
            focus_id = answered_episode_id if hold_focus else state.active_episode_id
            for ep_id in created:
                ep = state.issue_episodes[ep_id]
                if _episode_handled_by_topic_flow(state, ep):
                    continue
                if focus_id and ep_id == focus_id:
                    continue
                if ep_id not in state.pending_episode_ids:
                    state.pending_episode_ids.append(ep_id)
            if hold_focus and answered_episode_id:
                state.active_episode_id = answered_episode_id
                if answered_episode_id in state.pending_episode_ids:
                    state.pending_episode_ids = [
                        eid
                        for eid in state.pending_episode_ids
                        if eid != answered_episode_id
                    ]
            result.activated = state.active_episode_id
        else:
            if (
                state.active_episode_id
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
    from packages.dialogue_engine.question_context import (
        mark_episode_resolved,
        utterance_indicates_resolved,
    )

    if utterance_indicates_resolved(turn.raw_text):
        mark_episode_resolved(ep)
        state.pending_episode_attribute = None
        if state.active_episode_id == episode_id:
            activate_next_pending_episode(state)
        return
    # «Не знаю» / «не помню» = valid skip for this attribute — never hang the call.
    if _UNKNOWN_ATTRIBUTE_ANSWER.search(_norm(turn.raw_text)):
        ep.known_attributes[attribute] = "unknown"
        _maybe_clear_pending_attribute(state, episode_id, attribute)
        finalize_episode_if_complete(ep)
        return
    exclude = _mention_exclusion_clauses(turn)
    if attribute == "onset":
        value = extract_grounded_onset_value(turn.raw_text, exclude_clauses=exclude)
        if value:
            ep.known_attributes["onset"] = value
            _maybe_infer_current_active_from_temporal_answer(ep, turn.raw_text)
            _maybe_clear_pending_attribute(state, episode_id, attribute)
            finalize_episode_if_complete(ep)
        return
    if attribute == "severity":
        value = extract_grounded_severity_value(turn.raw_text, exclude_clauses=exclude)
        if value:
            ep.known_attributes["severity"] = value
            _maybe_clear_pending_attribute(state, episode_id, attribute)
            finalize_episode_if_complete(ep)
        return
    if attribute == "duration":
        value = extract_grounded_onset_value(turn.raw_text, exclude_clauses=exclude)
        if value:
            ep.known_attributes["duration"] = value
            _maybe_infer_current_active_from_temporal_answer(ep, turn.raw_text)
            _maybe_clear_pending_attribute(state, episode_id, attribute)
            finalize_episode_if_complete(ep)
        return
    raw = turn.raw_text.strip().lower()
    if attribute == "current" and raw:
        if utterance_indicates_resolved(turn.raw_text):
            mark_episode_resolved(ep)
            if state.active_episode_id == episode_id:
                activate_next_pending_episode(state)
        elif any(x in raw for x in ("бол", "да", "ещё", "еще")):
            ep.known_attributes["current"] = "active"
        else:
            ep.known_attributes["current"] = turn.raw_text.strip()
        _maybe_clear_pending_attribute(state, episode_id, attribute)
        return
    if attribute in {"pattern", "quality", "daytime_impact", "intake", "barrier",
                     "intensity", "social_context", "status_today", "associated"} and raw:
        ep.known_attributes[attribute] = turn.raw_text.strip()
        _maybe_clear_pending_attribute(state, episode_id, attribute)
        finalize_episode_if_complete(ep)
        return
    if attribute == "needs_help" and raw:
        if any(x in raw for x in ("не нуж", "сам", "сама", "справля", "нет", "неа")):
            ep.known_attributes["needs_help"] = "self_ok"
        elif any(x in raw for x in ("нужн", "помо", "да", "хочу")):
            ep.known_attributes["needs_help"] = "needs_help"
        else:
            ep.known_attributes["needs_help"] = turn.raw_text.strip()
        _maybe_clear_pending_attribute(state, episode_id, attribute)
        finalize_episode_if_complete(ep)
        return


def _maybe_infer_current_active_from_temporal_answer(ep: IssueEpisode, text: str) -> None:
    """Temporal-only answer to when/current compound ⇒ still active unless improved."""
    from packages.dialogue_engine.question_context import utterance_indicates_resolved

    if ep.known_attributes.get("current"):
        return
    if utterance_indicates_resolved(text):
        return
    ep.known_attributes["current"] = "active"


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
    from packages.dialogue_engine.question_context import episode_obligations_satisfied

    return episode_obligations_satisfied(ep)


def _needs_severity(ep: IssueEpisode) -> bool:
    label = ep.primary_label.lower()
    if ep.body_site in ("голова", "живот", "горло", "колено", "зуб", "шея", "спина", "ухо"):
        return True
    return any(
        tok in label
        for tok in (
            "голов",
            "боль",
            "болит",
            "ноет",
            "ломит",
            "давит",
            "тянет",
            "колен",
            "зуб",
            "горл",
            "шея",
            "спин",
        )
    )


def has_abdominal_episode(state: EngineState) -> bool:
    for ep in state.issue_episodes.values():
        if ep.body_site == "живот" or "живот" in ep.primary_label.lower():
            return True
    return False
