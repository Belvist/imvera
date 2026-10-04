"""Source audit of product/policy need compatibility, not a live acceptance."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--checkout", type=Path, default=ROOT)
    args = parser.parse_args()
    source = args.checkout.resolve()
    sys.path.insert(0, str(source))
    from packages.dialogue_engine.action_policy.need_value import currently_askable_needs
    from packages.dialogue_engine.action_policy.needs import ASKABLE_NEEDS, normalize_attribute
    from packages.dialogue_engine.action_policy.policy import choose, generate_candidates
    from packages.dialogue_engine.action_policy.snapshot import (
        EpisodeSnapshot,
        PolicySnapshot,
        TurnContextView,
    )
    from packages.dialogue_engine.product.issue_plans import FAMILY_PLANS

    snapshot = PolicySnapshot(
        episodes=(EpisodeSnapshot(
            "e1", "symptom", "active", known_attributes=(
                ("duration", "со вчера"), ("current", "active"),
                ("severity", "moderate"), ("functional_impact", "none"),
            ),
        ),),
        active_episode_id="e1", pending_episode_attribute="associated",
        wellness_entry_covered=True,
    )
    context = TurnContextView()
    product_needs = sorted({step for steps in FAMILY_PLANS.values() for step in steps
                            if normalize_attribute(step) not in ASKABLE_NEEDS})
    output = {
        "source_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=source,
        ).decode().strip(),
        "scope": ("static need mapping plus synthetic read-only policy snapshot; "
                  "not actual engine/phone turn"),
        "policy_askable_needs": list(ASKABLE_NEEDS),
        "families": {
            family.value: {
                "product_steps": list(steps),
                "outside_policy_askable_set": [step for step in steps
                                              if normalize_attribute(step) not in ASKABLE_NEEDS],
            } for family, steps in FAMILY_PLANS.items()
        },
        "synthetic_pending_associated": {
            "snapshot": {
                "known_attributes": dict(snapshot.episodes[0].known_attributes),
                "pending_episode_attribute": snapshot.pending_episode_attribute,
                "wellness_entry_covered": snapshot.wellness_entry_covered,
            },
            "outstanding_pending_obligation": snapshot.outstanding_pending_obligation(),
            "candidates": [item.key.label() for item in generate_candidates(snapshot, context)],
            "chosen": choose(snapshot, context).chosen.key.label(),
        },
        "canonical_pending_by_need": {},
    }
    for need in product_needs:
        pending = PolicySnapshot(
            episodes=snapshot.episodes, active_episode_id="e1",
            pending_episode_attribute=need, wellness_entry_covered=True,
        )
        output["canonical_pending_by_need"][need] = {
            "askable": list(currently_askable_needs(pending)),
            "chosen": choose(pending, context).chosen.key.label(),
            "outstanding": pending.outstanding_pending_obligation(),
        }
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
