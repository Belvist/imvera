"""Product planner — next QuestionNeed from frozen family plans + caps."""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.dialogue_engine.product.issue_plans import (
    MAX_ASKS_PER_FAMILY,
    MAX_CONTENT_ASKS_PER_CALL,
    ProductFamily,
    call_has_temporal_answer,
    classify_episode_family,
    plan_steps_for_family,
)
from packages.dialogue_engine.product.known import step_already_known
from packages.dialogue_engine.product.spoken import intent_for, spoken_question
from packages.dialogue_engine.question_context import QuestionNeed, attribute_need_satisfied

if TYPE_CHECKING:
    from packages.dialogue_engine.state import EngineState, IssueEpisode


def _ensure_family(state: EngineState, ep: IssueEpisode) -> ProductFamily:
    stored = ep.known_attributes.get("_product_family")
    if stored in {f.value for f in ProductFamily}:
        return ProductFamily(stored)
    family = classify_episode_family(ep)
    ep.known_attributes["_product_family"] = family.value
    return family


def asks_for_family(state: EngineState, family: ProductFamily) -> int:
    return int(state.product_asks_by_family.get(family.value, 0))


def content_asks(state: EngineState) -> int:
    return int(state.product_content_asks or 0)


def bump_product_ask(state: EngineState, family: ProductFamily) -> None:
    key = family.value
    state.product_asks_by_family[key] = asks_for_family(state, family) + 1
    state.product_content_asks = content_asks(state) + 1


def call_cap_reached(state: EngineState) -> bool:
    return content_asks(state) >= MAX_CONTENT_ASKS_PER_CALL


def family_cap_reached(state: EngineState, family: ProductFamily) -> bool:
    return asks_for_family(state, family) >= MAX_ASKS_PER_FAMILY


def _past_oriented_temporal(ep: IssueEpisode) -> bool:
    """True when evidence is past/morning-resolved style → need «а сейчас» trend."""
    blob = " ".join(
        [
            str(ep.known_attributes.get("onset") or ""),
            str(ep.known_attributes.get("duration") or ""),
            ep.primary_label or "",
            *(m.evidence.quote or "" for m in ep.mentions if m.evidence),
            *(m.label or "" for m in ep.mentions),
        ]
    ).lower()
    return any(
        x in blob
        for x in (
            "болела",
            "болел",
            "болело",
            "вчера",
            "вчерашн",
            "на утро",
            "утром болел",
            "утром болела",
        )
    )


def _steps_for(state: EngineState, ep: IssueEpisode, family: ProductFamily) -> tuple[str, ...]:
    if family == ProductFamily.HEADACHE:
        # Past/morning «болела» → ask trend (current), then associated if still open.
        if _past_oriented_temporal(ep):
            return ("duration", "current", "associated")
        # Present «болит» → when + severity + associated (nausea), MVP-like.
        return ("duration", "severity", "associated")
    return plan_steps_for_family(
        family,
        call_has_temporal=call_has_temporal_answer(state),
    )


def _step_satisfied(state: EngineState, ep: IssueEpisode, family: ProductFamily, step: str) -> bool:
    """Product-level satisfaction — pack rules, not raw attribute presence alone.

    Order of authority:
    1) episode resolved → all steps done
    2) known.py skip (already said / call-level temporal) → done
    3) attribute fills + ask marks for soft clarifications
    """
    from packages.dialogue_engine.question_context import (
        current_value_indicates_resolved,
        episode_is_resolved,
    )

    if episode_is_resolved(ep):
        return True

    # Explicit refusal to date the symptom («дальше/пропусти»): temporal
    # steps are done without a value — advance, never re-ask, never invent.
    if step in ("onset", "duration") and ep.known_attributes.get("_temporal_skipped"):
        return True

    # Do not re-ask what the caller already told us (or call-level temporal for abdomen).
    if step_already_known(state, ep, step, family=family.value):
        # associated: mentions alone are handled inside step_already_known as False
        # until a real answer lands — keep ask-once path below.
        if step != "associated":
            return True

    if step == "associated":
        # Must ask once (MVP associated). Mentions alone do not close the need —
        # we still clarify whether nausea/etc. continues now.
        val = ep.known_attributes.get("associated")
        if val and val not in {"already_mentioned"}:
            return True
        if f"_product_asked:{step}" in ep.known_attributes:
            return state.pending_episode_attribute != "associated"
        return False

    if step == "current" and family in {
        ProductFamily.HEADACHE,
        ProductFamily.ABDOMINAL,
    }:
        val = ep.known_attributes.get("current")
        if not val:
            return False
        # Inferred «improving» is not an answer: one real current check is
        # still owed (spec 12) unless the step was already asked once.
        if str(val) == "improving" and f"_product_asked:{step}" not in ep.known_attributes:
            return False
        if current_value_indicates_resolved(str(val)) or str(val) in {
            "resolved",
            "improving",
        }:
            return True
        if str(val) == "active":
            if family == ProductFamily.ABDOMINAL:
                if f"_product_asked:{step}" not in ep.known_attributes:
                    return False
                return state.pending_episode_attribute != "current"
            if _past_oriented_temporal(ep):
                return f"_product_asked:{step}" in ep.known_attributes and (
                    state.pending_episode_attribute != "current"
                )
            return True
        return True

    if step in ("onset", "duration") and family == ProductFamily.HEADACHE:
        return attribute_need_satisfied(ep, "onset") or attribute_need_satisfied(
            ep, "duration"
        )
    return attribute_need_satisfied(ep, step)


def _pending_unanswered(state: EngineState, ep: IssueEpisode, family: ProductFamily) -> bool:
    if state.active_episode_id != ep.episode_id:
        return False
    pending = state.pending_episode_attribute
    if not pending:
        return False
    return not _step_satisfied(state, ep, family, pending)


def product_episode_complete(state: EngineState, ep: IssueEpisode) -> bool:
    """True when pack says stop probing this episode."""
    from packages.dialogue_engine.question_context import (
        episode_is_resolved,
        episode_obligations_satisfied,
    )

    if episode_is_resolved(ep):
        return True
    # Frozen contract (ADR-014): obligations-satisfied means enough grounded
    # facts — stop probing even if product plan steps remain. Product probing
    # (associated, sleep pattern/daytime) beyond this point needs an ADR;
    # it must not override the frozen completion gates.
    if episode_obligations_satisfied(ep):
        return True
    family = _ensure_family(state, ep)
    if _pending_unanswered(state, ep, family):
        return False
    if call_cap_reached(state) or family_cap_reached(state, family):
        return True
    for step in _steps_for(state, ep, family):
        if not _step_satisfied(state, ep, family, step):
            return False
    return True


def next_product_need(state: EngineState, ep: IssueEpisode) -> QuestionNeed | None:
    """Owner of next episode question — plan order, not information_gain scoring."""
    from packages.dialogue_engine.question_context import episode_is_resolved

    if episode_is_resolved(ep):
        return None

    family = _ensure_family(state, ep)

    pending = state.pending_episode_attribute
    if pending and state.active_episode_id == ep.episode_id:
        if not _step_satisfied(state, ep, family, pending):
            return QuestionNeed.for_attribute(pending)

    if call_cap_reached(state) or family_cap_reached(state, family):
        return None

    for step in _steps_for(state, ep, family):
        if _step_satisfied(state, ep, family, step):
            continue
        return QuestionNeed.for_attribute(step)
    return None


def spoken_for_need(
    state: EngineState,
    ep: IssueEpisode,
    attribute: str,
) -> tuple[str, str]:
    family = _ensure_family(state, ep)
    text = spoken_question(family, attribute, ep)
    intent = intent_for(family, attribute, ep.episode_id)
    return text, intent
