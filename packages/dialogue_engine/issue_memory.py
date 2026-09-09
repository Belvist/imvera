"""Generic issue episode memory — active/pending/evidence from RichUserTurn."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from packages.contracts.semantic import IssueMention
from packages.dialogue_engine.state import EngineState, IssueEpisode
from packages.dialogue_engine.turn_understanding import RichUserTurn


@dataclass
class IngestResult:
    episodes_touched: list[str] = field(default_factory=list)
    activated: str | None = None


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
    if mention.status in ("improving", "resolved", "active"):
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


def ingest_rich_turn(state: EngineState, turn: RichUserTurn) -> IngestResult:
    result = IngestResult()
    if turn.correction:
        _apply_correction(state, turn)

    if not turn.issue_mentions:
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
        if state.active_episode_id and state.active_episode_id not in created:
            if state.active_episode_id not in state.pending_episode_ids:
                state.pending_episode_ids.append(state.active_episode_id)
        state.active_episode_id = created[0]
        for ep_id in created[1:]:
            if ep_id != state.active_episode_id and ep_id not in state.pending_episode_ids:
                state.pending_episode_ids.append(ep_id)
        result.activated = state.active_episode_id
        result.episodes_touched = created
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


def _fill_pending_attribute_from_answer(state: EngineState, turn: RichUserTurn) -> None:
    if not state.active_episode_id or turn.answers_pending_question:
        return
    ep = state.issue_episodes.get(state.active_episode_id)
    if ep is None:
        return
    raw = turn.raw_text.strip().lower()
    pending = state.pending_episode_attribute
    if pending == "onset" and raw:
        ep.known_attributes["onset"] = turn.raw_text.strip()
        state.pending_episode_attribute = None
        return
    if pending == "severity" and raw:
        ep.known_attributes["severity"] = turn.raw_text.strip()
        state.pending_episode_attribute = None
        return
    if pending == "current" and raw:
        if any(x in raw for x in ("не бол", "прошл", "легче", "лучше", "нет")):
            ep.known_attributes["current"] = "resolved"
        elif any(x in raw for x in ("бол", "да", "ещё", "еще")):
            ep.known_attributes["current"] = "active"
        else:
            ep.known_attributes["current"] = turn.raw_text.strip()
        state.pending_episode_attribute = None


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
