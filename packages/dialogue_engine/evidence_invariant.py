"""Evidence invariant — grounded symptoms only, no invented body sites."""

from __future__ import annotations

import re

from packages.contracts.semantic import IssueMention, evidence_matches
from packages.dialogue_engine.state import EngineState, IssueEpisode

_BODY_REF = re.compile(
    r"\b(живот\w*|желудк\w*|кишечник\w*|голов\w*|сердц\w*|груд\w*|ух\w*|горл\w*)\w*\b",
    re.I,
)


def known_body_sites(state: EngineState) -> set[str]:
    sites: set[str] = set()
    for ep in state.issue_episodes.values():
        if ep.body_site:
            sites.add(ep.body_site.lower())
        for mention in ep.mentions:
            if mention.body_site:
                sites.add(mention.body_site.lower())
            sites.update(_body_roots_in_quote(mention.evidence.quote))
    return sites


def known_issue_labels(state: EngineState) -> set[str]:
    labels: set[str] = set()
    for ep in state.issue_episodes.values():
        labels.add(ep.primary_label.lower())
        for mention in ep.mentions:
            labels.add(mention.label.lower())
            labels.add(mention.evidence.quote.lower())
    return labels


def _body_roots_in_quote(quote: str) -> set[str]:
    return {m.group(0).lower() for m in _BODY_REF.finditer(quote)}


def body_site_grounded(body_site: str | None, evidence_quote: str) -> bool:
    if not body_site:
        return True
    quote = evidence_quote.lower()
    site = body_site.lower()
    if site in quote:
        return True
    return any(site in root or root.startswith(site[:4]) for root in _body_roots_in_quote(quote))


def sanitize_issue_mention(mention: IssueMention, raw_text: str) -> IssueMention | None:
    """Drop or trim mentions whose label/body_site are not grounded in evidence.quote."""
    if not evidence_matches(raw_text, mention.evidence):
        return None

    quote = mention.evidence.quote.lower()
    label = mention.label
    body_site = mention.body_site

    if body_site and not body_site_grounded(body_site, mention.evidence.quote):
        body_site = None

    label_l = label.lower()
    if "тошн" in quote and ("живот" in label_l or body_site == "живот"):
        label = "тошнота"
        body_site = None
        label_l = label.lower()

    content_tokens = [
        t
        for t in re.findall(r"\w{3,}", label_l)
        if t not in {"боль", "боли", "болит", "болел", "болела"}
    ]
    if content_tokens and not any(tok in quote for tok in content_tokens):
        if not any(tok[:4] in quote for tok in content_tokens if len(tok) >= 4):
            label = mention.evidence.quote.strip()

    return mention.model_copy(update={"label": label, "body_site": body_site})


def question_references_forbidden_site(state: EngineState, question_text: str) -> bool:
    """True when question names a body site absent from confirmed episode evidence."""
    if not state.issue_episodes:
        return False
    known = known_body_sites(state)
    known_quotes = " ".join(
        m.evidence.quote.lower()
        for ep in state.issue_episodes.values()
        for m in ep.mentions
    )
    q = question_text.lower()
    for match in _BODY_REF.finditer(q):
        root = match.group(0).lower()
        if root in known_quotes:
            continue
        if any(
            body_site_grounded(site, root) or body_site_grounded(root, site)
            for site in known
        ):
            continue
        if any(root in site or site in root for site in known):
            continue
        return True
    return False


def episode_has_body_site(episode: IssueEpisode, site: str) -> bool:
    if episode.body_site and episode.body_site.lower() == site.lower():
        return True
    return any(m.body_site and m.body_site.lower() == site.lower() for m in episode.mentions)
