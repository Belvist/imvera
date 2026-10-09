"""Generic issue episode memory — active/pending/evidence from RichUserTurn."""

from __future__ import annotations

import logging
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

_log = logging.getLogger("dialogue.second_tier")

_UNKNOWN_ATTRIBUTE_ANSWER = re.compile(
    r"\b(не\s+знаю|не\s+помню|затрудня\w*(?:\s+сказ\w*)?|"
    r"не\s+могу\s+сказ|сложно\s+сказ|не\s+уверен\w*|не\s+скажу)\b",
    re.I,
)
# Site-less bare verbs are echoes, not complaints («болеть» inside
# «не помню, во сколько начала болеть»). Shared by the answering-path
# filter and the creation gate below.
_SITELESS_BARE_LABELS = frozenset(
    {
        "болит",
        "болят",
        "боль",
        "ноет",
        "ноют",
        "ломит",
        "давит",
        "тянет",
        "колет",
        "тошнит",
        "болеть",
        "ныть",
        "ломить",
        "давить",
        "тянуть",
        "колоть",
        "тошнить",
        "беспокоит",
        "беспокоить",
    }
)


def _is_ghost_primary(mention, raw_text: str = "") -> bool:
    """Site-less bare verb with real episodes around: echo, not a complaint.

    «Ещё/также/опять» marks a NEW lead («ещё болит» must be probed, frozen
    contract test_pack_multi_symptom_reaches_its_without_hangup) — never echo.
    """
    if (getattr(mention, "body_site", "") or "").strip():
        return False
    if (getattr(mention, "label", "") or "").strip().lower() not in _SITELESS_BARE_LABELS:
        return False
    if _NEW_LEAD_MARKER.search(raw_text or ""):
        return False
    return True


_NEW_LEAD_MARKER = re.compile(
    r"\b(ещё|еще|также|кроме\s+того|дополнительно|опять|снова)\b",
    re.I,
)


_TEMPORAL_ANCHOR = re.compile(
    r"\b(давно|раньше|дня|дней|недел\w*|месяц\w*|час\w*|минут\w*|минуту|полчаса|"
    r"утр\w*|вчерашн\w*|вчера|позавчерашн\w*|позавчера|позапозавчера|"
    r"позапрошл\w*|сегодня|сейчас|уже|назад|только\s+что|"
    r"понедельн\w*|вторник\w*|сред\w*|четверг\w*|пятниц\w*|суббот\w*|воскресен\w*|"
    r"вечер\w*|ноч\w*|дн[её]м|"
    r"второй\s+день|третий\s+день|пару\s+дней|несколько|с\s+утра|"
    r"со?\s+вчерашн\w*|уже\s+\w+\s+дн|в\s+четыре|в\s+\d+|"
    r"с\s+десят\w*|с\s+\d+|\bч\b|\bмин\b|\b\d{1,2}:\d{2}\b|"
    r"(в|на|к|с)\s+(час|два|две|три|четыре|пять|шесть|семь|восемь|девять|десять|"
    r"одиннадцать|двенадцать)(\s+(часов|часа|утра|дня|вечера|ночи))?)\b",
    re.I,
)
# Event-anchored onset answers: "после того как покушал", "после еды/обеда",
# "как покушал, так и заболело". A meal/event anchor IS a grounded temporal
# answer to "когда началось" — the engine must accept it, not only
# "утром/вечером". Bare meal verbs without после/как stay ungrounded.
_AFTER_EVENT_ANCHOR = re.compile(
    r"после\s+(того\s+как\b|еды\b|еду\b|обед\w*|ужин\w*|завтрак\w*|"
    r"при[её]м\w*\s+пищи|таблет\w*|лекарств\w*|прогул\w*|работы\b|"
    r"сна\b|покушал\w*|поел\w*)|"
    r"\bкак\s+(покушал\w*|поел\w*|пообедал\w*|поужинал\w*|позавтракал\w*|"
    r"приш[её]л\w*|проснул\w*|встал\w*)",
    re.I,
)
_SEVERITY_ANCHOR = re.compile(
    r"\b(сильн\w*|терпим\w*|слаб\w*|невыносим\w*|нестерпим\w*|пойд[её]т|сойд[её]т|"
    r"чуть|немного|средне|очень|ужасн\w*|страшн\w*|кошмарн\w*|жутк\w*|"
    r"дико\b|едва|еле|слегка|порядком)\b",
    re.I,
)
# A negated degree («не сильно», «не очень») is not a severity value.
_SEVERITY_NEGATED = re.compile(r"\b(не|ни)\s*$", re.I)
# Local pain-verb test for the out-of-order recorder (importing the shared
# _PAIN_VERB here would cycle through issue_mention_extract at module load).
_PAIN_VERB_LOCAL = re.compile(
    r"\b(бол(?!ее(?:\b|-))\w*|ноет\w*|ломит\w*|давит\w*|беспоко\w*|тян\w*)\b",
    re.I,
)
# Explicit skip of the temporal probe («давай дальше», «пропусти») — not an
# answer, but a refusal to date the symptom. Counts double toward the
# anti-loop divert so a single skip moves on instead of re-asking.
_SKIP_TEMPORAL = re.compile(
    r"\b(дальше|давай\s+дальше|пропусти|пропустим|"
    r"следующий\s+вопрос|не\s+важно|неважно|не\s+помню\s+когда|"
    r"не\s+помню\s*,?\s*во\s+сколько|не\s+знаю\s*,?\s*когда|"
    r"не\s+могу\s+сказать\s*,?\s*когда|не\s+могу\s+вспомнить\s*,?\s*когда)\b",
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


def _other_person_clause(clause: str) -> bool:
    from packages.dialogue_engine.semantic_kernel.subject_resolver import _subject_for_clause

    return _subject_for_clause(clause, has_issue=False).value == "other_person"


_HEDGE_PREFIX = re.compile(
    r"^(?:я\s+)?не\s+знаю\s*[,.]?\s*"
    r"|^(?:я\s+)?не\s+помню\s*[,.]?\s*"
    r"|^где-то\s+|^где\s+то\s+|^наверное\s+|^наверно\s+|^точнее\s+не\s+скажу\s*[,.]?\s*",
    re.I,
)


# Clock times / day parts (twin of observation_memory._TIME_OF_DAY — kept
# local: issue_memory cannot import observation_memory at module load).
_CLOCK_TIME = re.compile(
    r"\b(вечер\w*|ноч\w*|утр\w*|дн[её]м|"
    r"\d{1,2}:\d{2}|"
    r"(в|к)\s+\d+\b|"
    r"\b\d+\s+час\w*\s+(вечера|утра|дня|ночи)\b)",
    re.I,
)

_TEMPORAL_COMPLEMENTS = frozenset({
    "это", "оно", "так", "уже", "около", "примерно", "почти", "всего", "вот",
    "длиться", "продолжаться", "тянуться", "боль",
})
_CLOCK_COMPLEMENTS = _TEMPORAL_COMPLEMENTS | frozenset({
    "в", "во", "к", "с", "со", "у", "я", "час", "быть", "начаться", "начинаться",
    "появиться", "начало", "один", "два", "три", "четыре", "пять", "шесть", "семь",
    "восемь", "девять", "десять", "одиннадцать", "двенадцать",
    "как", "будто", "бы", "понятно", "на", "что", "то", "чувствовать",
    "подняться", "подниматься", "повыситься", "повышаться",
})


def _clock_answer_has_episode_owner(text: str, spans) -> bool:
    """A bare/deictic clock answers this episode; another predicate owns its time.

    Use the quantity guard's normalized-complement rule after removing the
    actual temporal spans. A medication or plan predicate must not borrow the
    pending clinical question merely because it contains a clock/day part.
    """
    from packages.dialogue_engine.semantic_kernel.morphology import normalize_token
    from packages.dialogue_engine.semantic_kernel.types import SpanType

    ranges = [(m.start(), m.end()) for m in _CLOCK_TIME.finditer(text)]
    ranges.extend((s.start, s.end) for s in spans
                  if s.type in (SpanType.TIME, SpanType.DURATION, SpanType.UNCERTAINTY,
                                SpanType.ISSUE, SpanType.BODY_SITE))
    rest = "".join(char if not any(start <= i < end for start, end in ranges) else " "
                   for i, char in enumerate(text))
    return all(normalize_token(token) in _CLOCK_COMPLEMENTS
               for token in re.findall(r"[а-яёa-z]+", rest, flags=re.I))


def _duration_span_is_clock_time(text: str, span) -> bool:
    """A quantity is part of the named clock, not a separate elapsed duration."""
    if any(span.start < match.end() and match.start() < span.end
           for match in _CLOCK_TIME.finditer(text)):
        return True
    # The parser types word-number clock hours («двенадцать часов вечера»)
    # as DURATION too. The immediately following genitive day part dates
    # that quantity; another quantity later in the clause remains independent.
    return bool(re.match(r"\s+(?:вечера|утра|дня|ночи)\b", text[span.end:], re.I))


def _strip_uncertainty_hedge(text: str) -> str:
    """Remove leading uncertainty hedges («не знаю, где-то ...»).

    A hedge is not content, but it must not poison content either: «Я не
    знаю, где-то 12 часов вечера» answers with 12 часов вечера. Bare
    hedges («Не знаю.») strip to empty and stay unknown downstream.
    """
    prev = None
    cur = (text or "").strip()
    while prev != cur:
        prev = cur
        cur = _HEDGE_PREFIX.sub("", cur).strip()
    return cur


def extract_grounded_onset_value(
    raw_text: str,
    *,
    exclude_clauses: tuple[str, ...] = (),
) -> str | None:
    """Return onset only when a clause contains a grounded temporal anchor."""
    clauses = _original_clause_slices(raw_text) or [raw_text.strip()]
    for clause in clauses:
        text = _strip_uncertainty_hedge(clause.strip())
        if not text:
            continue
        if _clause_excluded(text, exclude_clauses) or _other_person_clause(text):
            continue
        n = _norm(text)
        if _UNKNOWN_ATTRIBUTE_ANSWER.search(n):
            continue
        # A clock is a time point, but still needs this episode as its owner.
        _has_clock_time = bool(_CLOCK_TIME.search(n))
        if (
            _TEMPORAL_ANCHOR.search(n)
            or _DURATION_MARKERS.search(n)
            or _AFTER_EVENT_ANCHOR.search(n)
        ):
            from packages.dialogue_engine.semantic_kernel.span_parser import parse_spans
            from packages.dialogue_engine.semantic_kernel.types import SpanType

            spans = parse_spans(text)
            has_issue = any(s.type == SpanType.ISSUE for s in spans)
            if (_has_clock_time and not _AFTER_EVENT_ANCHOR.search(n)
                    and not _clock_answer_has_episode_owner(text, spans)):
                continue
            if (not _has_clock_time
                    and any(s.type == SpanType.DURATION for s in spans)
                    and not has_issue
                    and not extract_grounded_duration_value(text)):
                # A bare quantity about medication/plans is not this
                # episode's onset merely because the temporal question is open.
                # Clock answers passed their predicate ownership guard above.
                continue
            if len(clauses) == 1:
                # Single clause: keep the raw form byte-stable (the clause
                # splitter eats trailing periods); return the de-hedged
                # text only when a hedge was actually removed.
                if text != clause.strip():
                    return text.rstrip(",;")
                return raw_text.strip().rstrip(",;")
            return text.rstrip(",;")
    return None


def extract_grounded_severity_value(
    raw_text: str,
    *,
    exclude_clauses: tuple[str, ...] = (),
) -> str | None:
    """Return severity only when a clause contains a grounded severity marker."""
    from packages.dialogue_engine.semantic_kernel.span_parser import tolerance_severity_spans

    tolerance = tolerance_severity_spans(raw_text)
    clauses = _original_clause_slices(raw_text) or [raw_text.strip()]
    for clause in clauses:
        text = _strip_uncertainty_hedge(clause.strip())
        if not text:
            continue
        if _clause_excluded(text, exclude_clauses) or _other_person_clause(text):
            continue
        n = _norm(text)
        if _UNKNOWN_ATTRIBUTE_ANSWER.search(n):
            continue
        for degree in tolerance:
            if degree.text in text:
                return degree.text
        for match in _SEVERITY_ANCHOR.finditer(n):
            # A negated degree («не сильно», «не очень беспокоит») answers
            # the opposite — never record it as a severity value. Later
            # matches in the same clause still count («не сильно, а очень»).
            if _SEVERITY_NEGATED.search(n[: match.start()].rstrip(" ,—-")):
                continue
            if len(clauses) == 1:
                if text != clause.strip():
                    return text.rstrip(",;")
                return raw_text.strip().rstrip(",;")
            start, end = match.span()
            return text[start:end]
    return None


def extract_grounded_duration_value(
    raw_text: str, *, exclude_clauses: tuple[str, ...] = (),
) -> str | None:
    """A quantity answering this episode, without another predicate owner.

    Bare time or a deictic continuation belongs to the pending episode;
    «две недели принимаю таблетки / буду дома» does not. This conservative
    boundary is for out-of-order evidence, not a general activity parser.
    """
    from packages.dialogue_engine.semantic_kernel.morphology import normalize_token
    from packages.dialogue_engine.semantic_kernel.span_parser import parse_spans
    from packages.dialogue_engine.semantic_kernel.types import SpanType

    for clause in _original_clause_slices(raw_text):
        clause = _strip_uncertainty_hedge(clause.strip())
        if not clause:
            continue
        if _clause_excluded(clause, exclude_clauses) or _UNKNOWN_ATTRIBUTE_ANSWER.search(clause):
            continue
        for span in parse_spans(clause):
            if span.type != SpanType.DURATION:
                continue
            rest = clause[:span.start] + " " + clause[span.end:]
            tokens = re.findall(r"[а-яёa-z]+", rest, flags=re.I)
            if all(normalize_token(token) in _TEMPORAL_COMPLEMENTS for token in tokens):
                return span.text
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


def _canonical_label(label: str | None, stored: str | None) -> str:
    from packages.dialogue_engine.semantic_kernel.morphology import normalize_text

    key = (stored or "").strip()
    if key:
        return key.lower()
    return normalize_text(label or "")


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
        canonical_key=_canonical_label(mention.label, getattr(mention, "canonical_key", "")),
        kind=mention.kind,
        body_site=mention.body_site,
        subject=(getattr(mention, "subject", "") or "unknown").strip().lower() or "unknown",
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
    # Subject: merge never downgrades a known subject to unknown.
    _msub = (getattr(mention, "subject", "") or "").strip().lower()
    if _msub in ("speaker", "other_person") and episode.subject == "unknown":
        episode.subject = _msub
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


def clinical_issue_concept(label: str, canonical_key: str = "") -> str:
    """Same-site pain paraphrases share an owner; tremor is a different issue."""
    key = _canonical_label(label, canonical_key)
    if re.search(r"\b(?:тряс\w*|тряст\w*|дрож\w*)\b", key, re.I):
        return "tremor"
    if re.search(
        r"\b(?:(?:по|при|за|раз)?бол\w*|побалива\w*|боль|ноет|ноют|ныть|лом\w*)\b",
        key, re.I,
    ):
        return "pain"
    from packages.dialogue_engine.semantic_kernel.lexicon import (
        BODY_SITE_LEMMAS,
        SENSATION_ADJECTIVES,
    )

    # Reference projections can repeat an anatomical subject. It does not
    # change the clinical predicate («горло першит» / «горло горло першит»).
    return " ".join(SENSATION_ADJECTIVES.get(token, token)
                    for token in key.split() if token not in BODY_SITE_LEMMAS)


def _find_episode_for_mention(state: EngineState, mention: IssueMention) -> str | None:
    site = (mention.body_site or "").lower()
    key = _canonical_label(mention.label, getattr(mention, "canonical_key", ""))
    concept = clinical_issue_concept(mention.label, key)
    # Prefer the active owner for a restated answer, but never match by
    # anatomy alone: pain, tremor and another person's symptoms are distinct.
    ids = list(state.issue_episodes)
    if state.active_episode_id in ids:
        ids.remove(state.active_episode_id)
        ids.insert(0, state.active_episode_id)
    for ep_id in ids:
        ep = state.issue_episodes[ep_id]
        if (mention.subject in ("speaker", "other_person")
                and ep.subject in ("speaker", "other_person") and mention.subject != ep.subject):
            continue
        if site and ep.body_site and ep.body_site.lower() != site:
            continue
        if (not site and ep.body_site
                and key != _canonical_label(ep.primary_label, ep.canonical_key)):
            # «Ещё болит» is a fresh vague lead, not evidence that it is
            # the previously discussed headache/abdomen.
            continue
        if concept == clinical_issue_concept(ep.primary_label, ep.canonical_key):
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
    seen_sites: set[tuple[str, str]] = set()
    seen_primaries: set[str] = set()
    out: list[IssueMention] = []
    for mention in mentions:
        if mention.body_site and mention.role in ("primary", "independent"):
            label = _canonical_label(mention.label, getattr(mention, "canonical_key", ""))
            site_key = (mention.body_site, clinical_issue_concept(mention.label, label))
            if site_key in seen_sites:
                continue
            seen_sites.add(site_key)
        elif mention.role in ("primary", "independent"):
            label = _canonical_label(mention.label, getattr(mention, "canonical_key", ""))
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
    """Keep issue mentions that should redirect focus (spec: a new complaint
    inside any background answer switches to the symptom — never swallowed
    by the mood/sleep/plans slot)."""
    if not turn.issue_mentions:
        return False
    for mention in turn.issue_mentions:
        if mention.kind == "symptom":
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
                pending_daytime = state.pending_episode_attribute == "daytime_impact"
                if pending_daytime or not active.known_attributes.get("daytime_impact"):
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
                label and label not in _SITELESS_BARE_LABELS
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
        elif _is_ghost_primary(primary, turn.raw_text) and state.issue_episodes:
            # Live fs-8a64bac9: bare «болеть» echo inside a refusal spawned a
            # ghost episode that stole the floor («когда это началось» for
            # nothing). With real episodes around, echoes don't create.
            continue
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
    # Subject correction («нет, я про мужа», «это у мужа, не у меня»):
    # reassign the active episode to the other person and stop probing
    # the speaker about someone else's pain.
    try:
        from packages.dialogue_engine.semantic_kernel.subject_resolver import (
            OTHER_PERSON_MARKERS,
        )

        _low = (turn.raw_text or "").lower()
        if any(m in _low for m in OTHER_PERSON_MARKERS):
            _ep = get_active_episode(state)
            if _ep is None:
                # Unknown subjects cannot be probed, but a subsequent explicit
                # correction can resolve their uniquely unresolved report.
                candidates = [ep for ep in state.issue_episodes.values()
                              if ep.subject == "unknown" and ep.status != "resolved"]
                if len(candidates) == 1:
                    _ep = candidates[0]
            if _ep is not None:
                _ep.subject = "other_person"
                state.active_episode_id = _ep.episode_id
                if turn.utterance_id not in _ep.evidence_turn_ids:
                    _ep.evidence_turn_ids.append(turn.utterance_id)
                if state.pending_episode_attribute:
                    state.pending_episode_attribute = None
                return
    except Exception:  # noqa: BLE001 — corrections must never break ingest
        pass
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


def _record_out_of_order_value(
    state: EngineState,
    ep: IssueEpisode,
    turn: RichUserTurn,
    pending: str,
    exclude: tuple[str, ...],
) -> bool:
    """Record a grounded answer that arrived for a step other than the pending one.

    «Сильно.» while «сейчас ещё беспокоит?» is open is a real severity answer.
    Dropping it made the current probe repeat verbatim and lost the evidence
    (live fs-4d8f5a8b, hard-battery `abdominal`). Probe order is a product
    plan; evidence is the elder's words — consume the evidence.

    Degree and explicit DURATION spans are independent evidence. Generic
    current answers («Сейчас не беспокоит.») are never borrowed as temporal
    values, and recorded values are never overwritten.
    """
    # Explicit quantities have their own semantic type; a generic current
    # answer must never become a duration just because another step is open.
    duration = extract_grounded_duration_value(turn.raw_text, exclude_clauses=exclude)
    if duration:
        ep.known_attributes.setdefault("duration", duration)
    if pending == "severity":
        return False
    if (ep.known_attributes or {}).get("severity"):
        return False
    raw = (turn.raw_text or "").strip()
    # Out-of-order grab is only safe for a bare degree answer («Сильно.»,
    # «Очень.») or a turn that actually talks about pain («Ужасно болит
    # голова»). Otherwise a degree word about something else («Очень
    # боюсь.») would be misfiled as pain severity.
    bare = len(re.findall(r"[а-яёa-z]+", raw, flags=re.I)) <= 3
    if not bare and not _PAIN_VERB_LOCAL.search(raw):
        return False
    value = extract_grounded_severity_value(turn.raw_text, exclude_clauses=exclude)
    if not value:
        return False
    ep.known_attributes["severity"] = value
    finalize_episode_if_complete(ep)
    return True


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
    from packages.dialogue_engine.check_path import is_other_person_health_frame

    if is_other_person_health_frame(turn.raw_text):
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
    # «Не знаю» / «не помню» is not an answer: no write, no pending change
    # (frozen: onset stays None and pending stays open). Falls through to the
    # per-attribute extractors below, which write only grounded values.
    exclude = _mention_exclusion_clauses(turn)
    _record_out_of_order_value(state, ep, turn, attribute, exclude)
    if attribute == "onset":
        value = extract_grounded_onset_value(turn.raw_text, exclude_clauses=exclude)
        if value:
            ep.known_attributes["onset"] = value
            state.slot_unclear_counts.pop(f"episode_{attribute}_ungrounded", None)
            _maybe_clear_pending_attribute(state, episode_id, attribute)
            finalize_episode_if_complete(ep)
        else:
            # Second tier BEFORE counting ungrounded: the classifier boundary
            # generalizes to unseen paraphrases (no per-incident regex).
            if _second_tier_judgement(state, ep, episode_id, attribute, turn):
                return
            # Anti-loop: 2 ungrounded answers in a row → drop temporal pending
            # (no fabrication) so the next turn asks severity/current, not the
            # same «когда началось» a 3rd time (live c436546b/87312170/a8964347).
            # Explicit «дальше/пропусти» counts double: one skip moves on.
            key = f"episode_{attribute}_ungrounded"
            step = 2 if _SKIP_TEMPORAL.search(turn.raw_text) else 1
            count = state.slot_unclear_counts.get(key, 0) + step
            state.slot_unclear_counts[key] = count
            if count >= 2:
                state.slot_unclear_counts.pop(key, None)
                _maybe_clear_pending_attribute(state, episode_id, attribute)
                if step >= 2:
                    # Explicit refusal («не помню когда», «дальше»): temporal
                    # is done for this episode — advance, never re-arm.
                    # Plain double-garbage keeps the old bail-to-summary path
                    # (test_episode_confusion_never_fabricates_nor_hangs_up).
                    _mark_temporal_asked(state, ep)
        return
    if attribute == "severity":
        value = extract_grounded_severity_value(turn.raw_text, exclude_clauses=exclude)
        if value:
            ep.known_attributes["severity"] = value
            _maybe_clear_pending_attribute(state, episode_id, attribute)
            finalize_episode_if_complete(ep)
        else:
            _second_tier_judgement(state, ep, episode_id, attribute, turn)
        return
    if attribute == "duration":
        value = extract_grounded_onset_value(turn.raw_text, exclude_clauses=exclude)
        if value:
            # «С 10 утра» names the interval's start and remains a literal
            # duration answer. «12 часов вечера» only names a clock point.
            clock_point = bool(_CLOCK_TIME.search(value)) and not re.match(
                r"^со?\s+", value, re.I,
            )
            target_attribute = "onset" if clock_point else "duration"
            ep.known_attributes[target_attribute] = value
            state.slot_unclear_counts.pop(f"episode_{attribute}_ungrounded", None)
            _maybe_clear_pending_attribute(state, episode_id, attribute)
            finalize_episode_if_complete(ep)
        else:
            if _second_tier_judgement(state, ep, episode_id, attribute, turn):
                return
            key = f"episode_{attribute}_ungrounded"
            step = 2 if _SKIP_TEMPORAL.search(turn.raw_text) else 1
            count = state.slot_unclear_counts.get(key, 0) + step
            state.slot_unclear_counts[key] = count
            if count >= 2:
                state.slot_unclear_counts.pop(key, None)
                _maybe_clear_pending_attribute(state, episode_id, attribute)
                if step >= 2:
                    _mark_temporal_asked(state, ep)
        return
    raw = turn.raw_text.strip().lower()
    if attribute == "functional_impact":
        from packages.dialogue_engine.mission_grounding import current_speaker_clauses
        from packages.dialogue_engine.semantic_kernel.morphology import normalize_text
        from packages.dialogue_engine.semantic_kernel.observation_memory import _predicate_tense

        heard_need = state.last_user_delivered_need
        if (raw.rstrip(".!?…") in {"да", "нет"} and heard_need is not None
                and heard_need.attributes == (attribute,)
                and state.last_user_delivered_episode_id == episode_id):
            # Literal polarity answers this actually heard yes/no need only;
            # acknowledgement tokens and planned/cancelled questions do not.
            ep.known_attributes[attribute] = turn.raw_text.strip()
            _maybe_clear_pending_attribute(state, episode_id, attribute)
            return
        for clause in current_speaker_clauses(turn.raw_text):
            words = set(normalize_text(clause.text).split())
            # The heard functional question supplies the referent; the literal
            # response still needs a capability/activity predicate of its own.
            if (_predicate_tense(clause.text) not in {"past", "futr"}
                    and words & {"мочь", "делать", "ходить", "встать", "справляться", "мешать"}):
                ep.known_attributes[attribute] = clause.text
                _maybe_clear_pending_attribute(state, episode_id, attribute)
                return
        return
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


def _second_tier_judgement(
    state: EngineState,
    ep: IssueEpisode,
    episode_id: str,
    attribute: str,
    turn: RichUserTurn,
) -> bool:
    """Slot-classifier second tier (pilot only) when anchors miss.

    answer → record the user's OWN words (capped), advance. skip → skip
    markers, advance, no value. garbage/None → False (existing path runs).
    This is the anti-patch mechanism: unseen paraphrases generalize via the
    boundary instead of per-incident regex.
    """
    from packages.dialogue_engine.slotclf import judge

    # A slot classifier/personal phrase memory may propose an answer, but
    # cannot move an explicitly different symptom/domain into this attribute.
    # First-tier extractors above already consumed any grounded valid value.
    if turn.issue_mentions or any(f.field != "wellness" for f in turn.goal_facts):
        return False
    from packages.dialogue_engine.semantic_kernel.span_parser import parse_spans
    from packages.dialogue_engine.semantic_kernel.types import SpanType

    duration_spans = [s for s in parse_spans(turn.raw_text) if s.type == SpanType.DURATION]
    if duration_spans and (
        attribute == "severity" or not extract_grounded_duration_value(turn.raw_text)
    ):
        return False

    grounded_value = turn.raw_text.strip()[:80]
    if attribute in ("onset", "duration"):
        grounded_value = extract_grounded_onset_value(turn.raw_text)
    elif attribute == "severity":
        grounded_value = extract_grounded_severity_value(turn.raw_text)

    # Tier 1.5 — personal memory (this client's trusted resolutions only).
    client_id = getattr(state, "client_id", "")
    if client_id:
        from packages.dialogue_engine.caller_memory import resolve as _mem_resolve

        _mem = _mem_resolve(client_id, attribute, turn.raw_text)
        if _mem == "answer" and grounded_value:
            ep.known_attributes[attribute] = grounded_value
            state.slot_unclear_counts.pop(f"episode_{attribute}_ungrounded", None)
            _maybe_clear_pending_attribute(state, episode_id, attribute)
            finalize_episode_if_complete(ep)
            return True
        if _mem == "skip":
            key = f"episode_{attribute}_ungrounded"
            state.slot_unclear_counts[key] = (
                state.slot_unclear_counts.get(key, 0) + 2
            )
            state.slot_unclear_counts.pop(key, None)
            _maybe_clear_pending_attribute(state, episode_id, attribute)
            if attribute in ("onset", "duration"):
                _mark_temporal_asked(state, ep)
            return True

    verdict = judge(attribute, turn.raw_text)
    # Cut A4: observability for the Cut B decision (attribute+verdict only,
    # no raw text — PII stays out of logs).
    _log.info(
        "second_tier attribute=%s verdict=%s",
        attribute,
        verdict,
    )
    if verdict == "answer":
        if not grounded_value:
            _log.info("second_tier attribute=%s accepted=False reason=untyped_answer", attribute)
            return False
        if client_id:
            # Learn in process: high-confidence global resolution becomes a
            # personal hypothesis (trusted after 3 consistent hits).
            from packages.dialogue_engine.caller_memory import record as _mem_record
            from packages.dialogue_engine.slotclf import judge_proba

            if (judge_proba(attribute, turn.raw_text) or 0.0) >= 0.8:
                _mem_record(client_id, attribute, turn.raw_text, "answer")
        ep.known_attributes[attribute] = grounded_value
        state.slot_unclear_counts.pop(f"episode_{attribute}_ungrounded", None)
        _maybe_clear_pending_attribute(state, episode_id, attribute)
        finalize_episode_if_complete(ep)
        return True
    if verdict == "skip":
        if client_id:
            from packages.dialogue_engine.caller_memory import record as _mem_record
            from packages.dialogue_engine.slotclf import judge_proba

            if (judge_proba(attribute, turn.raw_text) or 0.0) >= 0.8:
                _mem_record(client_id, attribute, turn.raw_text, "skip")
        key = f"episode_{attribute}_ungrounded"
        count = state.slot_unclear_counts.get(key, 0) + 2
        state.slot_unclear_counts[key] = count
        if count >= 2:
            state.slot_unclear_counts.pop(key, None)
            _maybe_clear_pending_attribute(state, episode_id, attribute)
            if attribute in ("onset", "duration"):
                _mark_temporal_asked(state, ep)
        return True
    return False


def _mark_temporal_asked(state: EngineState, ep: IssueEpisode) -> None:
    """Honest ask telemetry after an explicit temporal skip (no values)."""
    from packages.dialogue_engine.product import bump_product_ask, classify_episode_family

    try:
        family = classify_episode_family(ep)
        for attr in ("onset", "duration"):
            mark = f"_product_asked:{attr}"
            if mark not in ep.known_attributes:
                ep.known_attributes[mark] = "1"
                bump_product_ask(state, family)
        # Explicit refusal to date the symptom — the planner must advance
        # to severity/current, never re-ask onset (no value fabricated).
        ep.known_attributes["_temporal_skipped"] = "1"
    except Exception:  # noqa: BLE001 — telemetry must never break dialogue
        pass


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
