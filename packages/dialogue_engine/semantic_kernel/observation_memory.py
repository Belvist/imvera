"""Observation memory — canonical facts with evidence and supersede."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from packages.contracts.semantic import Evidence, IssueMention
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


def build_observations(result: SemanticKernelResult) -> tuple[Observation, ...]:
    spans = result.spans
    relations = result.relations
    issues = [s for s in spans if s.type == SpanType.ISSUE]
    body_of = _targets_for_relation(RelationType.BODY_OF, spans, relations)
    onset_of = _targets_for_relation(RelationType.ONSET_OF, spans, relations)
    duration_of = _targets_for_relation(RelationType.DURATION_OF, spans, relations)
    severity_of = _targets_for_relation(RelationType.SEVERITY_OF, spans, relations)
    status_of = _targets_for_relation(RelationType.STATUS_OF, spans, relations)

    subject = SubjectKind.SPEAKER
    for rel in relations:
        if rel.type == RelationType.SUBJECT_OF:
            subject = SubjectKind.OTHER_PERSON
            break

    observations: list[Observation] = []
    for issue in issues:
        body_spans = body_of.get(issue.span_id, [])
        body_site = body_spans[0].normalized if body_spans else ""
        label = f"{body_site} {issue.normalized}".strip() if body_site else issue.text

        temporal = TemporalFrame(raw_evidence=issue.text)
        onset_spans = onset_of.get(issue.span_id, [])
        duration_spans = duration_of.get(issue.span_id, [])
        status_spans = status_of.get(issue.span_id, [])
        temporal_kwargs: dict = {"raw_evidence": issue.text}
        if onset_spans:
            temporal_kwargs["onset"] = onset_spans[0].text
            temporal_kwargs["raw_evidence"] = onset_spans[0].text
            if "сейчас" in onset_spans[0].text.lower():
                temporal_kwargs["current"] = True
            if "вчера" in onset_spans[0].text.lower() or "утром" in onset_spans[0].text.lower():
                temporal_kwargs["current"] = False
        if duration_spans:
            temporal_kwargs["duration"] = duration_spans[0].text
        for sspan in status_spans:
            if any(
                w in sspan.text.lower()
                for w in ("прошл", "лучше", "получше", "не болит", "нормально")
            ):
                temporal_kwargs["current"] = False
        temporal = TemporalFrame(**temporal_kwargs)

        negated = any(
            rel.type == RelationType.NEGATES and rel.target_span_id == issue.span_id
            for rel in relations
        )
        if negated:
            temporal_kwargs = dict(temporal.model_dump())
            temporal_kwargs["current"] = False
            temporal = TemporalFrame(**temporal_kwargs)

        observations.append(
            Observation(
                observation_id=_oid(),
                attribute="issue",
                value=label,
                normalized_value=issue.normalized,
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
                    subject=subject,
                    source_turn_id=result.utterance_id,
                    evidence=sspan.text,
                    status="confirmed",
                )
            )
    return tuple(observations)


def apply_corrections(
    state: EngineState,
    corrections: tuple[CorrectionRecord, ...],
    new_observations: tuple[Observation, ...],
) -> None:
    if not hasattr(state, "observations"):
        state.observations = {}  # type: ignore[attr-defined]
    store: dict[str, Observation] = state.observations  # type: ignore[attr-defined]
    for obs in new_observations:
        store[obs.observation_id] = obs
    for corr in corrections:
        for oid, obs in list(store.items()):
            if obs.attribute == corr.target and obs.status == "confirmed":
                if corr.old_evidence and corr.old_evidence in obs.evidence:
                    store[oid] = obs.model_copy(update={"status": "superseded"})
        store[_oid()] = Observation(
            observation_id=_oid(),
            attribute=corr.target,
            value=corr.new_evidence,
            evidence=corr.new_evidence,
            source_turn_id="",
            status="confirmed",
        )


def observations_to_issue_mentions(
    observations: tuple[Observation, ...],
    raw_text: str,
) -> tuple[IssueMention, ...]:
    """Compatibility projection for existing IssueEpisode ingest."""
    mentions: list[IssueMention] = []
    primary_set = False
    for obs in observations:
        if obs.status == "superseded" or obs.subject != SubjectKind.SPEAKER:
            continue
        if obs.attribute != "issue":
            continue
        body_site = None
        parts = obs.normalized_value.split()
        if parts:
            body_site = parts[0] if len(parts[0]) > 2 else None
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
        mentions.append(
            IssueMention(
                mention_id=f"im-{obs.observation_id[-8:]}",
                kind="symptom",
                label=obs.value[:60],
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
