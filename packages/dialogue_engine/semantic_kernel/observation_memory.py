"""Observation memory — canonical facts with evidence and supersede."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from packages.contracts.semantic import Evidence, IssueMention
from packages.dialogue_engine.semantic_kernel.subject_resolver import (
    _clause_bounds,
    _clause_for_position,
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
    clauses = _clause_bounds(result.raw_text)
    for issue in issues:
        body_spans = body_of.get(issue.span_id, [])
        body_site = body_spans[0].normalized if body_spans else None
        issue_norm = issue.normalized or issue.text.lower()
        label = f"{body_site} {issue_norm}".strip() if body_site else issue.text
        clause = _clause_for_position(clauses, issue.start)
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

    refers = [r for r in result.relations if r.type == RelationType.REFERS_TO]
    if not refers:
        return ()

    body_site = ep.body_site
    issue_norm = ep.primary_label.lower()
    observations: list[Observation] = []

    time_spans = [s for s in result.spans if s.type in (SpanType.TIME, SpanType.DURATION)]
    status_spans = [s for s in result.spans if s.type == SpanType.STATUS]

    for span in time_spans:
        attr = "duration" if span.type == SpanType.DURATION else "onset"
        observations.append(
            Observation(
                observation_id=_oid(),
                episode_id=ep_id,
                attribute=attr,
                value=span.text,
                normalized_value=span.normalized,
                body_site=body_site,
                issue_normalized=issue_norm,
                source_turn_id=result.utterance_id,
                evidence=span.text,
                status="confirmed",
                temporal=TemporalFrame(
                    onset=span.text if attr == "onset" else None,
                    duration=span.text if attr == "duration" else None,
                    raw_evidence=span.text,
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


def persist_turn_observations(state: EngineState, turn: RichUserTurn) -> None:
    """Canonical observation memory — source of truth before IssueEpisode projection."""
    if turn.observations:
        store: dict[str, Observation] = dict(state.observations)  # type: ignore[arg-type]
        for obs in turn.observations:
            if obs.status == "superseded":
                continue
            store[obs.observation_id] = obs
        state.observations = store  # type: ignore[assignment]
    if turn.kernel_corrections:
        apply_corrections(state, turn.kernel_corrections, turn.observations)
    _project_observations_to_episodes(state)


def _project_observations_to_episodes(state: EngineState) -> None:
    """Compatibility projection: canonical observations → IssueEpisode.known_attributes."""
    store: dict[str, Observation] = state.observations  # type: ignore[assignment]
    for obs in store.values():
        if obs.status != "confirmed" or obs.subject != SubjectKind.SPEAKER:
            continue
        ep_id = obs.episode_id or state.active_episode_id
        if not ep_id:
            continue
        ep = state.issue_episodes.get(ep_id)
        if ep is None:
            continue
        if obs.attribute in ("onset", "duration", "severity", "current"):
            ep.known_attributes[obs.attribute] = obs.value
        if obs.body_site and not ep.body_site:
            ep.body_site = obs.body_site


def observations_to_issue_mentions(
    observations: tuple[Observation, ...],
    raw_text: str,
) -> tuple[IssueMention, ...]:
    """Compatibility projection for existing IssueEpisode ingest."""
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
                onset=obs.temporal.onset,
                severity=obs.value if obs.attribute == "severity" else None,
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
