"""Check captured public SDK invariants and exact source hashes, not prose scores."""

import hashlib
import json
from pathlib import Path

folder = Path(__file__).resolve().parent
root = folder.parents[2]
checks = {}
for mode in ("legacy", "shadow", "policy"):
    captured = json.loads((folder / f"after-{mode}.json").read_text())
    turns = captured["transcripts"]
    current = {
        "no_sdk_errors": captured["failed_turns"] == 0,
        "source_hashes_match": all(
            hashlib.sha256((root / "packages/dialogue_engine" / name).read_bytes()).hexdigest()
            == digest
            for name, digest in captured["source_hashes"].items()
        ),
        "sleep_correction_kept": turns["correction"][1]["slots"]["sleep"]["source_turn_id"]
        == "u-2",
        "late_detail_kept": turns["late_summary"][-1]["slots"]["sleep"]["source_turn_id"] == "u-3",
        "foreign_history_conditional_not_revisions": all(
            turns[name][-1]["slots"]["sleep"]["source_turn_id"] == "u-1"
            for name in ("foreign", "historical", "conditional")
        ),
        "other_complaint_cannot_overwrite_sleep": turns["different_complaint"][-1]["slots"][
            "sleep"
        ]["source_turn_id"]
        == "u-2",
        "history_cannot_fill_daily_sleep": "sleep"
        not in turns["open_historical_sleep"][0]["slots"],
        "long_sleep_is_bounded_source": len(turns["long_sleep"][0]["slots"]["sleep"]["value"])
        <= 500,
        "urgent_and_stop_still_close": turns["safety"][-1]["closed"]
        and turns["stop"][-1]["closed"],
        "urgent_has_direct_help_not_delivery_promise": all(
            "112" in speech["text"] and "передам" not in speech["text"]
            for speech in turns["safety"][-1]["speaks"]
        ),
    }
    for name in ("unknown_onset", "declined_onset"):
        row = turns[name][-1]
        current[name + "_does_not_reask_or_invent_time"] = (
            row["pending_episode_attribute"] not in {"onset", "duration", "temporal"}
            and any(ep["unanswered_attributes"] for ep in row["episodes"].values())
            and all(
                not ep["known_attributes"].get("onset")
                and not ep["known_attributes"].get("duration")
                for ep in row["episodes"].values()
            )
        )
    if mode == "policy":
        episode = list(turns["functional_answer"][-1]["episodes"].values())
        current["single_complaint_all_volunteered_details_and_functional_answer"] = (
            len(episode) == 1
            and episode[0]["known_attributes"]["onset"] == "вчера"
            and episode[0]["known_attributes"]["severity"] == "терпимо"
            and episode[0]["known_attributes"]["functional_impact"] == "Могу делать обычные дела."
            and turns["functional_answer"][-1]["pending_episode_attribute"] is None
        )
    checks[mode] = current

legacy = json.loads((folder / "after-legacy.json").read_text())["transcripts"]
shadow = json.loads((folder / "after-shadow.json").read_text())["transcripts"]
checks["shadow_preserves_legacy_speech"] = all(
    [row.get("speaks") for row in legacy[case]] == [row.get("speaks") for row in shadow[case]]
    for case in legacy
)
flat = [
    value
    for group in checks.values()
    for value in (group.values() if isinstance(group, dict) else (group,))
]
(folder / "capture-checks.json").write_text(
    json.dumps(
        {
            "scope": "captured SDK/source invariants only; no phone/audio/Core receipt",
            "checks": checks,
            "passed": sum(flat),
            "total": len(flat),
        },
        indent=2,
    )
    + "\n"
)
assert all(flat), checks
print(f"capture checks: {sum(flat)}/{len(flat)} PASS")
