"""Evidence invariant — no invented body sites or symptoms."""

from __future__ import annotations

from packages.dialogue_engine.state import EngineState, IssueEpisode


def _normalized_tokens(text: str) -> set[str]:
    return {t.lower() for t in text.split() if t}


def known_body_sites(state: EngineState) -> set[str]:
    sites: set[str] = set()
    for ep in state.issue_episodes.values():
        if ep.body_site:
            sites.add(ep.body_site.lower())
        for mention in ep.mentions:
            if mention.body_site:
                sites.add(mention.body_site.lower())
    return sites


def known_issue_labels(state: EngineState) -> set[str]:
    labels: set[str] = set()
    for ep in state.issue_episodes.values():
        labels.add(ep.primary_label.lower())
        for mention in ep.mentions:
            labels.add(mention.label.lower())
    return labels


def body_site_allowed(state: EngineState, body_site: str) -> bool:
    site = body_site.lower()
    return site in known_body_sites(state)


def question_references_forbidden_site(state: EngineState, question_text: str) -> bool:
    """True when question names a body site the user never mentioned."""
    q = question_text.lower()
    forbidden_sites = ("живот", "желудок", "кишечник", "сердце", "ухо")
    known = known_body_sites(state)
    for site in forbidden_sites:
        if site in q and site not in known:
            return True
    return False


def episode_has_body_site(episode: IssueEpisode, site: str) -> bool:
    if episode.body_site and episode.body_site.lower() == site.lower():
        return True
    return any(m.body_site and m.body_site.lower() == site.lower() for m in episode.mentions)
