"""Dialogue Product Pack — opinionated issue plans (MVP behaviour, one brain).

Not a second dialogue engine. ConversationPolicy remains the scheduler;
this pack owns *which* episode step to ask and *how* to say it.
"""

from __future__ import annotations

from packages.dialogue_engine.product.issue_plans import (
    ASSOCIATED_LABELS,
    FAMILY_PLANS,
    MAX_ASKS_PER_FAMILY,
    MAX_CONTENT_ASKS_PER_CALL,
    ProductFamily,
    classify_episode_family,
    plan_steps_for_family,
)
from packages.dialogue_engine.product.known import (
    CallKnownFacts,
    snapshot_call_known,
    step_already_known,
)
from packages.dialogue_engine.product.planner import (
    bump_product_ask,
    call_cap_reached,
    next_product_need,
    product_episode_complete,
    spoken_for_need,
)

__all__ = [
    "ASSOCIATED_LABELS",
    "CallKnownFacts",
    "FAMILY_PLANS",
    "MAX_ASKS_PER_FAMILY",
    "MAX_CONTENT_ASKS_PER_CALL",
    "ProductFamily",
    "bump_product_ask",
    "call_cap_reached",
    "classify_episode_family",
    "next_product_need",
    "plan_steps_for_family",
    "product_episode_complete",
    "snapshot_call_known",
    "spoken_for_need",
    "step_already_known",
]
