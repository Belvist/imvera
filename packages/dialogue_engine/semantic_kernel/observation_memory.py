"""Observation memory — canonical facts with evidence and supersede."""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING

from packages.contracts.semantic import Evidence, IssueMention
from packages.dialogue_engine.semantic_kernel.clauses import clause_bounds, clause_for_position
from packages.dialogue_engine.semantic_kernel.subject_resolver import (
    _subject_for_clause,
    subject_for_issue,
)
from packages.dialogue_engine.semantic_kernel.types import (
    CorrectionRecord,
    Observation,
    RelationType,
    SemanticKernelResult,
    SemanticSpan,
    SpanType,
    SubjectKind,
    TemporalFrame,
)

if TYPE_CHECKING:
    from packages.dialogue_engine.state import EngineState
    from packages.dialogue_engine.turn_understanding import RichUserTurn


def _oid() -> str:
    return f"obs-{uuid.uuid4().hex[:8]}"


def _span_by_id(spans: tuple[SemanticSpan, ...], sid: str) -> SemanticSpan | None:
    return next((s for s in spans if s.span_id == sid), None)


def _targets_for_relation(
    rel_type: RelationType, spans: tuple[SemanticSpan, ...], relations
) -> dict[str, list[SemanticSpan]]:
    out: dict[str, list[SemanticSpan]] = {}
    for rel in relations:
        if rel.type != rel_type:
            continue
        src = _span_by_id(spans, rel.source_span_id)
        tgt = _span_by_id(spans, rel.target_span_id)
        if src and tgt:
            out.setdefault(tgt.span_id, []).append(src)
    return out


def _temporal_from_spans(
    issue: SemanticSpan,
    onset_spans: list[SemanticSpan],
    duration_spans: list[SemanticSpan],
    status_spans: list[SemanticSpan],
    negated: bool,
) -> TemporalFrame:
    temporal_kwargs: dict = {"raw_evidence": issue.text}
    if onset_spans:
        temporal_kwargs["onset"] = onset_spans[0].text
        temporal_kwargs["raw_evidence"] = onset_spans[0].text
        lower = onset_spans[0].text.lower()
        if "сейчас" in lower:
            temporal_kwargs["current"] = True
        if "вчера" in lower or "утром" in lower:
            temporal_kwargs["current"] = False
    if duration_spans:
        temporal_kwargs["duration"] = duration_spans[0].text
    for sspan in status_spans:
        if any(
            w in sspan.text.lower()
            for w in ("прошл", "лучше", "получше", "не болит", "нормально")
        ):
            temporal_kwargs["current"] = False
    if negated:
        temporal_kwargs["current"] = False
    return TemporalFrame(**temporal_kwargs)


def build_observations(result: SemanticKernelResult) -> tuple[Observation, ...]:
    spans = result.spans
    relations = result.relations
    issues = [s for s in spans if s.type == SpanType.ISSUE]
    body_of = _targets_for_relation(RelationType.BODY_OF, spans, relations)
    onset_of = _targets_for_relation(RelationType.ONSET_OF, spans, relations)
    duration_of = _targets_for_relation(RelationType.DURATION_OF, spans, relations)
    severity_of = _targets_for_relation(RelationType.SEVERITY_OF, spans, relations)
    status_of = _targets_for_relation(RelationType.STATUS_OF, spans, relations)

    observations: list[Observation] = []
    clauses = clause_bounds(result.raw_text)
    for issue in issues:
        body_spans = body_of.get(issue.span_id, [])
        body_site = body_spans[0].normalized if body_spans else None
        issue_norm = issue.normalized or issue.text.lower()
        label = f"{body_site} {issue_norm}".strip() if body_site else issue.text
        clause = clause_for_position(clauses, issue.start)
        clause_subject = _subject_for_clause(clause, has_issue=True)
        subject = subject_for_issue(
            issue.span_id,
            relations,
            clause_subject=clause_subject,
        )

        onset_spans = onset_of.get(issue.span_id, [])
        duration_spans = duration_of.get(issue.span_id, [])
        status_spans = status_of.get(issue.span_id, [])
        negated = any(
            rel.type == RelationType.NEGATES and rel.target_span_id == issue.span_id
            for rel in relations
        )
        temporal = _temporal_from_spans(
            issue, onset_spans, duration_spans, status_spans, negated
        )

        observations.append(
            Observation(
                observation_id=_oid(),
                attribute="issue",
                value=label,
                normalized_value=issue_norm,
                body_site=body_site,
                issue_normalized=issue_norm,
                subject=subject,
                temporal=temporal,
                confidence=issue.confidence,
                source_turn_id=result.utterance_id,
                evidence=issue.text,
                status="confirmed",
            )
        )
        for sspan in severity_of.get(issue.span_id, []):
            observations.append(
                Observation(
                    observation_id=_oid(),
                    attribute="severity",
                    value=sspan.text,
                    normalized_value=sspan.normalized,
                    body_site=body_site,
                    issue_normalized=issue_norm,
                    subject=subject,
                    source_turn_id=result.utterance_id,
                    evidence=sspan.text,
                    status="confirmed",
                )
            )
        for sspan in onset_of.get(issue.span_id, []):
            observations.append(
                Observation(
                    observation_id=_oid(),
                    attribute="onset",
                    value=sspan.text,
                    normalized_value=sspan.normalized,
                    body_site=body_site,
                    issue_normalized=issue_norm,
                    subject=subject,
                    temporal=TemporalFrame(onset=sspan.text, raw_evidence=sspan.text),
                    source_turn_id=result.utterance_id,
                    evidence=sspan.text,
                    status="confirmed",
                )
            )
        for sspan in duration_of.get(issue.span_id, []):
            observations.append(
                Observation(
                    observation_id=_oid(),
                    attribute="duration",
                    value=sspan.text,
                    normalized_value=sspan.normalized,
                    body_site=body_site,
                    issue_normalized=issue_norm,
                    subject=subject,
                    temporal=TemporalFrame(duration=sspan.text, raw_evidence=sspan.text),
                    source_turn_id=result.utterance_id,
                    evidence=sspan.text,
                    status="confirmed",
                )
            )
        for sspan in status_of.get(issue.span_id, []):
            current = not any(
                w in sspan.text.lower()
                for w in ("прошл", "лучше", "получше", "не болит", "нормально")
            )
            observations.append(
                Observation(
                    observation_id=_oid(),
                    attribute="current",
                    value=sspan.text,
                    normalized_value=sspan.normalized,
                    body_site=body_site,
                    issue_normalized=issue_norm,
                    subject=subject,
                    temporal=TemporalFrame(current=current, raw_evidence=sspan.text),
                    source_turn_id=result.utterance_id,
                    evidence=sspan.text,
                    status="confirmed",
                )
            )
    return tuple(observations)


def build_reference_observations(
    result: SemanticKernelResult,
    state: EngineState,
) -> tuple[Observation, ...]:
    """Attach temporal/status updates to active episode via REFERS_TO."""
    if not state.active_episode_id:
        return ()
    ep_id = state.active_episode_id
    ep = state.issue_episodes.get(ep_id)
    if ep is None:
        return ()

    body_site = ep.body_site
    issue_norm = ep.primary_label.lower()
    observations: list[Observation] = []
    raw = result.raw_text.strip()
    from packages.dialogue_engine.question_context import utterance_indicates_resolved

    if utterance_indicates_resolved(raw):
        observations.append(
            Observation(
                observation_id=_oid(),
                episode_id=ep_id,
                attribute="current",
                value="resolved",
                normalized_value="resolved",
                body_site=body_site,
                issue_normalized=issue_norm,
                source_turn_id=result.utterance_id,
                evidence=raw,
                status="confirmed",
                temporal=TemporalFrame(current=False, raw_evidence=raw),
            )
        )
        return tuple(observations)

    time_spans = [s for s in result.spans if s.type in (SpanType.TIME, SpanType.DURATION)]
    status_spans = [s for s in result.spans if s.type == SpanType.STATUS]
    severity_spans = [s for s in result.spans if s.type == SpanType.SEVERITY]
    pending = state.pending_episode_attribute

    if pending and not any(r.type == RelationType.REFERS_TO for r in result.relations):
        if pending in ("onset", "duration"):
            from packages.dialogue_engine.issue_memory import extract_grounded_onset_value

            # Only grounded temporal anchors — never fall back to arbitrary TIME spans
            # (e.g. «там» in meta speech).
            value = extract_grounded_onset_value(raw)
            if value:
                attr = pending
                observations.append(
                    Observation(
                        observation_id=_oid(),
                        episode_id=ep_id,
                        attribute=attr,
                        value=value,
                        normalized_value=value.lower(),
                        body_site=body_site,
                        issue_normalized=issue_norm,
                        source_turn_id=result.utterance_id,
                        evidence=value,
                        status="confirmed",
                        temporal=TemporalFrame(
                            onset=value if attr == "onset" else None,
                            duration=value if attr == "duration" else None,
                            raw_evidence=value,
                        ),
                    )
                )
                return tuple(observations)
        if pending == "severity" and severity_spans:
            span = severity_spans[0]
            observations.append(
                Observation(
                    observation_id=_oid(),
                    episode_id=ep_id,
                    attribute="severity",
                    value=span.text,
                    normalized_value=span.normalized,
                    body_site=body_site,
                    issue_normalized=issue_norm,
                    source_turn_id=result.utterance_id,
                    evidence=span.text,
                    status="confirmed",
                )
            )
            return tuple(observations)

    refers = [r for r in result.relations if r.type == RelationType.REFERS_TO]
    if not refers:
        return ()

    from packages.dialogue_engine.issue_memory import extract_grounded_onset_value

    grounded_temporal = extract_grounded_onset_value(raw)
    for span in time_spans:
        # Reject weak TIME tokens («там») unless a grounded temporal anchor exists.
        if not grounded_temporal:
            continue
        gt = grounded_temporal.lower()
        st = span.text.lower()
        if st not in gt and gt not in st:
            # Prefer the grounded clause as the value.
            value = grounded_temporal
        else:
            value = span.text
        attr = "duration" if span.type == SpanType.DURATION else "onset"
        if pending in ("onset", "duration"):
            attr = pending
        observations.append(
            Observation(
                observation_id=_oid(),
                episode_id=ep_id,
                attribute=attr,
                value=value,
                normalized_value=value.lower(),
                body_site=body_site,
                issue_normalized=issue_norm,
                source_turn_id=result.utterance_id,
                evidence=value,
                status="confirmed",
                temporal=TemporalFrame(
                    onset=value if attr == "onset" else None,
                    duration=value if attr == "duration" else None,
                    raw_evidence=value,
                ),
            )
        )

    for span in status_spans:
        current = not any(
            w in span.text.lower()
            for w in ("прошл", "лучше", "получше", "не болит", "нормально")
        )
        observations.append(
            Observation(
                observation_id=_oid(),
                episode_id=ep_id,
                attribute="current",
                value=span.text,
                normalized_value=span.normalized,
                body_site=body_site,
                issue_normalized=issue_norm,
                source_turn_id=result.utterance_id,
                evidence=span.text,
                status="confirmed",
                temporal=TemporalFrame(current=current, raw_evidence=span.text),
            )
        )

    if not observations and result.raw_text.strip():
        lower = result.raw_text.lower()
        if any(w in lower for w in ("час", "день", "дней", "недел", "утр", "вчера", "давно")):
            observations.append(
                Observation(
                    observation_id=_oid(),
                    episode_id=ep_id,
                    attribute="duration",
                    value=result.raw_text.strip(),
                    normalized_value=result.raw_text.strip().lower(),
                    body_site=body_site,
                    issue_normalized=issue_norm,
                    source_turn_id=result.utterance_id,
                    evidence=result.raw_text.strip(),
                    status="confirmed",
                    temporal=TemporalFrame(
                        duration=result.raw_text.strip(),
                        raw_evidence=result.raw_text,
                    ),
                )
            )
    return tuple(observations)


def apply_corrections(
    state: EngineState,
    corrections: tuple[CorrectionRecord, ...],
    new_observations: tuple[Observation, ...],
) -> None:
    store: dict[str, Observation] = dict(state.observations)  # type: ignore[arg-type]
    for obs in new_observations:
        store[obs.observation_id] = obs
    for corr in corrections:
        for oid, obs in list(store.items()):
            if obs.attribute == corr.target and obs.status == "confirmed":
                if corr.old_evidence and corr.old_evidence in obs.evidence:
                    store[oid] = obs.model_copy(update={"status": "superseded"})
        new_id = _oid()
        store[new_id] = Observation(
            observation_id=new_id,
            attribute=corr.target,
            value=corr.new_evidence,
            evidence=corr.new_evidence,
            source_turn_id="",
            status="confirmed",
        )
    state.observations = store  # type: ignore[assignment]


def _episode_key(ep) -> tuple[str | None, str]:
    return (ep.body_site, (ep.primary_label or "").lower())


def _match_episode_for_observation(
    state: EngineState,
    obs: Observation,
    turn: RichUserTurn,
) -> str | None:
    if obs.episode_id:
        return obs.episode_id
    if obs.body_site:
        for ep_id, ep in state.issue_episodes.items():
            if ep.body_site == obs.body_site:
                return ep_id
    if obs.issue_normalized:
        norm = obs.issue_normalized.lower()
        for ep_id, ep in state.issue_episodes.items():
            label = (ep.primary_label or "").lower()
            if norm in label or (ep.body_site and norm.startswith(ep.body_site)):
                return ep_id
    if (
        obs.attribute in ("onset", "duration", "severity", "current")
        and not turn.issue_mentions
        and state.active_episode_id
    ):
        return state.active_episode_id
    return None


def _bind_observations_to_episodes(
    state: EngineState,
    turn: RichUserTurn,
) -> tuple[Observation, ...]:
    bound: list[Observation] = []
    for obs in turn.observations:
        ep_id = _match_episode_for_observation(state, obs, turn)
        if ep_id and obs.episode_id != ep_id:
            bound.append(obs.model_copy(update={"episode_id": ep_id}))
        else:
            bound.append(obs)
    return tuple(bound)


def _apply_bound_observations_to_episodes(
    state: EngineState,
    observations: tuple[Observation, ...],
) -> None:
    """Project only explicitly bound turn observations — no active_episode fallback."""
    for obs in observations:
        if obs.status != "confirmed" or obs.subject != SubjectKind.SPEAKER:
            continue
        if not obs.episode_id:
            continue
        ep = state.issue_episodes.get(obs.episode_id)
        if ep is None:
            continue
        if obs.attribute in ("onset", "duration", "severity", "current"):
            from packages.dialogue_engine.question_context import (
                current_value_indicates_resolved,
                episode_is_resolved,
                utterance_indicates_resolved,
            )

            if episode_is_resolved(ep):
                continue
            if obs.attribute in ("onset", "duration") and utterance_indicates_resolved(
                obs.evidence
            ):
                continue
            if obs.attribute in ("onset", "duration") and ep.known_attributes.get(
                obs.attribute
            ) and obs.value.strip().lower() in ("сейчас", "now"):
                continue
            ep.known_attributes[obs.attribute] = obs.value
            if obs.attribute == "current":
                from packages.dialogue_engine.question_context import (
                    current_value_indicates_resolved,
                    mark_episode_resolved,
                )

                if current_value_indicates_resolved(obs.value):
                    mark_episode_resolved(ep)
        if obs.body_site and not ep.body_site:
            ep.body_site = obs.body_site


def atomic_semantic_apply(state: EngineState, turn: RichUserTurn) -> None:
    """Atomic: episodes first, bind observations, persist, project this turn only."""
    from packages.dialogue_engine.issue_memory import (
        extract_grounded_onset_value,
        ingest_rich_turn,
    )

    ingest_rich_turn(state, turn)
    bound = _bind_observations_to_episodes(state, turn)

    store: dict[str, Observation] = dict(state.observations)  # type: ignore[arg-type]
    for obs in bound:
        if obs.status == "superseded":
            continue
        store[obs.observation_id] = obs
    # Side observations from mission understanding (problems / other-person plans).
    for obs in turn.observations:
        if obs.observation_id not in store and obs.status != "superseded":
            store[obs.observation_id] = obs
    state.observations = store  # type: ignore[assignment]

    if turn.kernel_corrections:
        apply_corrections(state, turn.kernel_corrections, bound)
    _apply_bound_observations_to_episodes(state, bound)
    _apply_mission_goal_answers(state, turn)

    # Same-turn temporal for a new issue: same clause, or sole episode if temporal
    # is not a foreign sleep/topic narrative (e.g. "проснулся в четыре" ≠ throat onset).
    grounded = extract_grounded_onset_value(turn.raw_text)
    if grounded and turn.utterance_id:
        from packages.dialogue_engine.issue_memory import _original_clause_slices

        _FOREIGN_TEMPORAL = re.compile(
            r"проснул|не\s+спал|плохо\s+спал|во\s+сне|разбуд|кошмар",
            re.IGNORECASE,
        )
        clauses = _original_clause_slices(turn.raw_text)
        candidates = [
            ep
            for ep in state.issue_episodes.values()
            if turn.utterance_id in ep.evidence_turn_ids
            and not ep.known_attributes.get("onset")
            and not ep.known_attributes.get("duration")
        ]
        for ep in candidates:
            issue_bits = [
                (m.evidence.quote if m.evidence else "") or m.label
                for m in ep.mentions
            ]
            same_clause = False
            temporal_host = ""
            for clause in clauses:
                cl = clause.lower()
                has_time = grounded.lower() in cl or any(
                    tok in cl for tok in grounded.lower().split()[:3] if len(tok) > 2
                )
                has_issue = any(bit and bit.lower() in cl for bit in issue_bits)
                if has_time:
                    temporal_host = clause
                if has_time and has_issue:
                    same_clause = True
                    break
            if not same_clause and _FOREIGN_TEMPORAL.search(temporal_host or grounded):
                continue
            if same_clause or len(candidates) == 1:
                ep.known_attributes["onset"] = grounded
                if state.pending_episode_attribute in ("onset", "duration"):
                    state.pending_episode_attribute = None
                break


def _apply_mission_goal_answers(state: EngineState, turn: RichUserTurn) -> None:
    """Satisfy/decline GoalState only after deterministic grounding validation."""
    from packages.contracts.enums import SlotStatus
    from packages.dialogue_engine.mission_grounding import (
        filter_grounded_dispositions,
        filter_grounded_goal_answers,
    )
    from packages.dialogue_engine.mission_seed import mission_from_state
    from packages.dialogue_engine.state import GoalLifecycle

    mission = mission_from_state(state)
    satisfied = {
        gid
        for gid, g in state.goals.items()
        if g.lifecycle == GoalLifecycle.SATISFIED
    }
    answers = getattr(turn, "goal_answers", ()) or ()
    grounded = filter_grounded_goal_answers(
        answers,
        mission=mission,
        utterance=turn.raw_text,
        existing_satisfied=satisfied,
    )
    for ans in grounded:
        goal = state.goals.get(ans.goal_id)
        if goal is None:
            continue
        if goal.lifecycle == GoalLifecycle.SATISFIED and not ans.is_correction:
            continue
        evidence_id = f"ev-{turn.utterance_id}-{ans.goal_id}"
        if ans.is_correction and goal.lifecycle == GoalLifecycle.SATISFIED:
            # Supersede prior goal observation values.
            store_pre: dict[str, Observation] = dict(state.observations)  # type: ignore[arg-type]
            for eid in list(goal.evidence_ids):
                prev = store_pre.get(eid)
                if prev is not None and prev.goal_id == ans.goal_id:
                    store_pre[eid] = prev.model_copy(update={"status": "superseded"})
            state.observations = store_pre  # type: ignore[assignment]
        goal.answer = ans.value
        if evidence_id not in goal.evidence_ids:
            goal.evidence_ids.append(evidence_id)
        goal.lifecycle = GoalLifecycle.SATISFIED
        goal.status = SlotStatus.FILLED
        obs_id = f"obs-goal-{ans.goal_id}-{turn.utterance_id}"
        store: dict[str, Observation] = dict(state.observations)  # type: ignore[arg-type]
        store[obs_id] = Observation(
            observation_id=obs_id,
            attribute=ans.goal_id,
            value=ans.value,
            normalized_value=str(ans.value).lower(),
            goal_id=ans.goal_id,
            subject=SubjectKind.SPEAKER,
            confidence=float(ans.confidence),
            source_turn_id=turn.utterance_id,
            evidence=ans.evidence,
            status="confirmed",
        )
        state.observations = store  # type: ignore[assignment]
        if obs_id not in goal.evidence_ids:
            goal.evidence_ids.append(obs_id)
        if ans.goal_id in state.slots:
            state.slots[ans.goal_id] = SlotStatus.FILLED
            state.slot_values[ans.goal_id] = ans.value

    dispositions = filter_grounded_dispositions(
        getattr(turn, "goal_dispositions", ()) or (),
        mission=mission,
        utterance=turn.raw_text,
    )
    for disp in dispositions:
        goal = state.goals.get(disp.goal_id)
        if goal is None or goal.lifecycle == GoalLifecycle.SATISFIED:
            continue
        if disp.disposition == "declined":
            goal.lifecycle = GoalLifecycle.DECLINED
            goal.status = SlotStatus.DECLINED
        elif disp.disposition == "not_applicable":
            goal.lifecycle = GoalLifecycle.NOT_APPLICABLE
        else:
            goal.lifecycle = GoalLifecycle.UNCLEAR
        evidence_id = f"ev-disp-{turn.utterance_id}-{disp.goal_id}"
        if evidence_id not in goal.evidence_ids:
            goal.evidence_ids.append(evidence_id)

    # Non-health needs_help answers from structured episode attributes first.
    for attr in getattr(turn, "episode_attributes", ()) or ():
        if getattr(attr, "attribute", None) != "needs_help":
            continue
        evidence = (getattr(attr, "evidence", "") or "").strip()
        if evidence and evidence.casefold() not in turn.raw_text.casefold():
            continue
        ep_id = getattr(attr, "episode_id", None) or state.active_episode_id
        ep = state.issue_episodes.get(ep_id) if ep_id else None
        if ep is None or ep.kind != "other":
            continue
        value = str(getattr(attr, "value", "") or "").strip()
        if value not in {"self_ok", "needs_help", "unknown"}:
            continue
        ep.known_attributes["needs_help"] = value
        ep.status = "resolved"
        state.pending_episode_attribute = None

    # Non-health needs_help answers from free text on pending attribute (fallback only).
    if state.pending_episode_attribute == "needs_help" and state.active_episode_id:
        ep = state.issue_episodes.get(state.active_episode_id)
        if ep is not None and ep.kind == "other" and "needs_help" not in ep.known_attributes:
            low = turn.raw_text.lower()
            if any(
                tok in low
                for tok in (
                    "справл",
                    "сам",
                    "не надо",
                    "не нужн",
                    "пока",
                    "нужна",
                    "нужно",
                    "помо",
                )
            ):
                value = "self_ok"
                if any(tok in low for tok in ("нужна", "нужно", "помог", "помош")):
                    value = "needs_help"
                if any(tok in low for tok in ("справл", "сам", "не надо", "не нужн")):
                    value = "self_ok"
                ep.known_attributes["needs_help"] = value
                ep.status = "resolved"
                state.pending_episode_attribute = None

    # Target presence answers.
    dq = state.delivered_question
    if dq is not None and dq.intent == "ask_target_person":
        low = turn.raw_text.lower()
        if any(w in low for w in ("передаю", "сейчас дам", "минутку", "сейчас")):
            state.target_presence = "confirmed"
        elif any(w in low for w in ("нет", "спит", "не может", "ушла", "уехал", "нету", "нема")):
            state.target_presence = "unavailable"




def persist_turn_observations(state: EngineState, turn: RichUserTurn) -> None:
    """Deprecated alias — use atomic_semantic_apply."""
    atomic_semantic_apply(state, turn)


def observations_to_issue_mentions(
    observations: tuple[Observation, ...],
    raw_text: str,
) -> tuple[IssueMention, ...]:
    """Compatibility projection for existing IssueEpisode ingest."""
    severity_by_key: dict[tuple[str | None, str], str] = {}
    for obs in observations:
        if obs.status == "superseded" or obs.attribute != "severity":
            continue
        if obs.subject != SubjectKind.SPEAKER:
            continue
        severity_by_key[(obs.body_site, obs.issue_normalized)] = obs.value

    mentions: list[IssueMention] = []
    primary_set = False
    for obs in observations:
        if obs.status == "superseded":
            continue
        if obs.subject not in (SubjectKind.SPEAKER,):
            continue
        if obs.attribute != "issue":
            continue
        body_site = obs.body_site
        severity = severity_by_key.get((body_site, obs.issue_normalized))
        start = raw_text.lower().find(obs.evidence.lower())
        if start < 0:
            start = 0
        end = min(len(raw_text), start + len(obs.evidence))
        role = "primary" if not primary_set else "independent"
        primary_set = True
        temporal = "now"
        status = "active"
        if obs.temporal.current is False:
            status = "resolved"
            temporal = "past"
        elif obs.temporal.onset:
            temporal = "past" if "вчера" in obs.temporal.onset.lower() else "now"
        label = obs.value
        if body_site and body_site not in label.lower():
            label = f"{body_site} {obs.issue_normalized or obs.normalized_value}".strip()
        mentions.append(
            IssueMention(
                mention_id=f"im-{obs.observation_id[-8:]}",
                kind="symptom",
                label=label[:60],
                role=role,
                body_site=body_site,
                temporal_scope=temporal,
                status=status,
                onset=obs.temporal.onset or obs.temporal.duration,
                severity=severity,
                evidence=Evidence(start=start, end=end, quote=raw_text[start:end] or obs.evidence),
            )
        )
    return tuple(mentions)


def merge_legacy_mentions(
    kernel_mentions: tuple[IssueMention, ...],
    legacy_mentions: tuple[IssueMention, ...],
) -> tuple[IssueMention, ...]:
    """Legacy may only fill gaps — kernel meaning always wins."""
    if not legacy_mentions:
        return kernel_mentions
    if not kernel_mentions:
        return legacy_mentions

    merged = list(kernel_mentions)
    kernel_keys = {
        (m.body_site or "", m.label.lower()) for m in kernel_mentions
    }
    for legacy in legacy_mentions:
        key = (legacy.body_site or "", legacy.label.lower())
        if key in kernel_keys:
            continue
        if any(
            legacy.label.lower() in k.label.lower() or k.label.lower() in legacy.label.lower()
            for k in kernel_mentions
        ):
            continue
        merged.append(legacy)
        kernel_keys.add(key)
    return tuple(merged)
