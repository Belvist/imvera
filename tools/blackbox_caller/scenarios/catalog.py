"""Deterministic 500-scenario catalog — 5 wellness × 20 families × 5 variants."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

CORPUS_VERSION = "1.0.0"
CORPUS_SEED = 42

WellnessCategory = Literal["good", "normal", "so_so", "okay", "bad"]

WELLNESS_CATEGORIES: tuple[WellnessCategory, ...] = (
    "good",
    "normal",
    "so_so",
    "okay",
    "bad",
)

FAMILIES: tuple[str, ...] = (
    "clean_short",
    "clean_long",
    "colloquial",
    "paraphrase",
    "multi_slot",
    "mixed_sentiment",
    "self_correction",
    "later_correction",
    "repair_allo",
    "repeat_request",
    "backchannel",
    "off_topic",
    "unclear_once",
    "silence_once",
    "delayed_answer",
    "interrupted_question",
    "stale_speak",
    "stale_timer",
    "long_processing",
    "full_mixed",
)

# phrase_id → manifest key in tests/assets/blackbox_voice/manifest.json
WELLNESS_PHRASE: dict[WellnessCategory, tuple[str, ...]] = {
    "good": (
        "wellness_good_01",
        "wellness_good_02",
        "wellness_good_03",
        "wellness_good_04",
        "wellness_good_05",
    ),
    "normal": (
        "wellness_normal_01",
        "wellness_normal_02",
        "wellness_normal_03",
        "wellness_normal_04",
        "wellness_normal_05",
    ),
    "so_so": (
        "wellness_so_so_01",
        "wellness_so_so_02",
        "wellness_so_so_03",
        "wellness_so_so_04",
        "wellness_so_so_05",
    ),
    "okay": (
        "wellness_okay_01",
        "wellness_okay_02",
        "wellness_okay_03",
        "wellness_okay_04",
        "wellness_okay_05",
    ),
    "bad": (
        "wellness_bad_01",
        "wellness_bad_02",
        "wellness_bad_03",
        "wellness_bad_04",
        "wellness_bad_05",
    ),
}

MOOD_PHRASES = ("mood_positive_01", "mood_neutral_01", "mood_negative_01", "mood_uncertain_01")
SLEEP_PHRASES = ("sleep_good_01", "sleep_normal_01", "sleep_bad_01", "sleep_short_01")
PLANS_PHRASES = (
    "plans_home_01",
    "plans_walk_01",
    "plans_doctor_01",
    "plans_none_01",
    "plans_uncertain_01",
)
GOODBYE_PHRASES = ("goodbye_01", "goodbye_confirm_01")


@dataclass
class ScenarioStep:
    action: str
    phrase_id: str = ""
    delay_ms: int = 0
    wait_s: float = 0.0
    tags: list[str] = field(default_factory=list)


@dataclass
class BlackboxScenario:
    id: str
    wellness_category: WellnessCategory
    family: str
    variant: int
    tags: list[str]
    steps: list[ScenarioStep]
    expected_intents: list[str]
    skip_if_missing_assets: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _pick(pool: tuple[str, ...], key: str) -> str:
    idx = int(hashlib.sha256(key.encode()).hexdigest(), 16) % len(pool)
    return pool[idx]


def _base_turns(
    scenario_id: str,
    category: WellnessCategory,
    family: str,
    variant: int,
) -> list[ScenarioStep]:
    key = f"{CORPUS_SEED}:{scenario_id}"
    wellness = WELLNESS_PHRASE[category][variant]
    mood = _pick(MOOD_PHRASES, key + ":mood")
    sleep = _pick(SLEEP_PHRASES, key + ":sleep")
    plans = _pick(PLANS_PHRASES, key + ":plans")
    steps: list[ScenarioStep] = [
        ScenarioStep(action="wait_bot_finish", wait_s=45.0),
    ]

    if family == "multi_slot":
        steps.append(
            ScenarioStep(
                action="play_wav",
                phrase_id="multi_slot_so_so_sleep_plans",
                tags=["multi_slot"],
            )
        )
        steps.append(ScenarioStep(action="wait_bot_finish", wait_s=30.0))
        steps.append(ScenarioStep(action="play_wav", phrase_id=mood))
        steps.append(ScenarioStep(action="wait_bot_finish", wait_s=30.0))
        steps.append(ScenarioStep(action="play_wav", phrase_id="goodbye_01"))
        steps.append(ScenarioStep(action="wait_bot_finish", wait_s=25.0))
        steps.append(ScenarioStep(action="play_wav", phrase_id="goodbye_confirm_01"))
        steps.append(ScenarioStep(action="wait_bot_finish", wait_s=30.0))
        return steps

    if family == "repair_allo":
        steps.extend(
            [
                ScenarioStep(action="play_wav", phrase_id=wellness),
                ScenarioStep(action="wait_bot_finish", wait_s=30.0),
                ScenarioStep(action="play_wav", phrase_id="repair_allo_01"),
                ScenarioStep(action="wait_bot_finish", wait_s=30.0),
                ScenarioStep(action="play_wav", phrase_id=mood),
                ScenarioStep(action="wait_bot_finish", wait_s=30.0),
                ScenarioStep(action="play_wav", phrase_id=sleep),
                ScenarioStep(action="wait_bot_finish", wait_s=30.0),
                ScenarioStep(action="play_wav", phrase_id=plans),
                ScenarioStep(action="wait_bot_finish", wait_s=30.0),
                ScenarioStep(action="play_wav", phrase_id="goodbye_01"),
                ScenarioStep(action="wait_bot_finish", wait_s=25.0),
                ScenarioStep(action="play_wav", phrase_id="goodbye_confirm_01"),
                ScenarioStep(action="wait_bot_finish", wait_s=30.0),
            ]
        )
        return steps

    if family == "interrupted_question" or family == "barge_in_during_opening":
        steps.append(
            ScenarioStep(
                action="barge_in",
                phrase_id=wellness,
                delay_ms=500,
            )
        )
        steps.extend(
            [
                ScenarioStep(action="wait_bot_finish", wait_s=30.0),
                ScenarioStep(action="play_wav", phrase_id=mood),
                ScenarioStep(action="wait_bot_finish", wait_s=30.0),
                ScenarioStep(action="play_wav", phrase_id=sleep),
                ScenarioStep(action="wait_bot_finish", wait_s=30.0),
                ScenarioStep(action="play_wav", phrase_id=plans),
                ScenarioStep(action="wait_bot_finish", wait_s=30.0),
                ScenarioStep(action="play_wav", phrase_id="goodbye_01"),
                ScenarioStep(action="wait_bot_finish", wait_s=25.0),
                ScenarioStep(action="play_wav", phrase_id="goodbye_confirm_01"),
                ScenarioStep(action="wait_bot_finish", wait_s=30.0),
            ]
        )
        return steps

    if scenario_id == "contextual_horosho_wellness_vs_plans":
        steps.extend(
            [
                ScenarioStep(action="play_wav", phrase_id=WELLNESS_PHRASE[category][variant]),
                ScenarioStep(action="wait_bot_finish", wait_s=30.0),
                ScenarioStep(action="play_wav", phrase_id=_pick(MOOD_PHRASES, key + ":mood")),
                ScenarioStep(action="wait_bot_finish", wait_s=30.0),
                ScenarioStep(action="play_wav", phrase_id=_pick(SLEEP_PHRASES, key + ":sleep")),
                ScenarioStep(action="wait_bot_finish", wait_s=30.0),
                ScenarioStep(action="play_wav", phrase_id="contextual_horosho_plans"),
                ScenarioStep(action="wait_bot_finish", wait_s=30.0),
                ScenarioStep(action="play_wav", phrase_id=_pick(PLANS_PHRASES, key + ":plans")),
                ScenarioStep(action="wait_bot_finish", wait_s=45.0),
                ScenarioStep(action="play_wav", phrase_id="goodbye_01"),
                ScenarioStep(action="wait_bot_finish", wait_s=25.0),
                ScenarioStep(action="play_wav", phrase_id="goodbye_confirm_01"),
                ScenarioStep(action="wait_bot_finish", wait_s=30.0),
            ]
        )
        return steps

    if family == "backchannel":
        steps.extend(
            [
                ScenarioStep(action="play_wav", phrase_id=wellness),
                ScenarioStep(action="wait_bot_finish", wait_s=30.0),
                ScenarioStep(action="play_wav", phrase_id="backchannel_01"),
                ScenarioStep(action="wait_bot_finish", wait_s=15.0),
                ScenarioStep(action="play_wav", phrase_id=mood),
            ]
        )
    else:
        steps.extend(
            [
                ScenarioStep(action="play_wav", phrase_id=wellness),
                ScenarioStep(action="wait_bot_finish", wait_s=30.0),
                ScenarioStep(action="play_wav", phrase_id=mood),
                ScenarioStep(action="wait_bot_finish", wait_s=30.0),
                ScenarioStep(action="play_wav", phrase_id=sleep),
                ScenarioStep(action="wait_bot_finish", wait_s=30.0),
                ScenarioStep(action="play_wav", phrase_id=plans),
            ]
        )

    steps.extend(
        [
            ScenarioStep(action="wait_bot_finish", wait_s=45.0),
            ScenarioStep(action="play_wav", phrase_id="goodbye_01"),
            ScenarioStep(action="wait_bot_finish", wait_s=25.0),
            ScenarioStep(action="play_wav", phrase_id="goodbye_confirm_01"),
            ScenarioStep(action="wait_bot_finish", wait_s=30.0),
        ]
    )
    return steps


def generate_catalog() -> list[BlackboxScenario]:
    scenarios: list[BlackboxScenario] = []
    for category in WELLNESS_CATEGORIES:
        for family in FAMILIES:
            for variant in range(5):
                sid = f"{category}-{family}-{variant:02d}"
                tags = [category, family]
                if category == "so_so" and family == "multi_slot" and variant == 0:
                    sid = "multi_slot_so_so_sleep_plans"
                if category == "good" and family == "paraphrase" and variant == 0:
                    sid = "contextual_horosho_wellness_vs_plans"
                    tags = ["contextual_horosho", "mandatory", category, family]
                if category == "good" and family == "interrupted_question" and variant == 0:
                    sid = "barge_in_during_opening"
                    tags = ["barge_in", "mandatory", category, family]
                if family == "multi_slot":
                    tags.append("multi_slot")
                if family == "interrupted_question" and "barge_in" not in tags:
                    tags.append("barge_in")
                steps = _base_turns(sid, category, family, variant)
                expected = [
                    "opening",
                    "check_mood",
                    "check_sleep",
                    "check_plans",
                    "summary",
                    "goodbye_final",
                ]
                if family == "multi_slot":
                    expected = ["opening", "check_mood", "summary", "goodbye_final"]
                scenarios.append(
                    BlackboxScenario(
                        id=sid,
                        wellness_category=category,
                        family=family,
                        variant=variant,
                        tags=tags,
                        steps=steps,
                        expected_intents=expected,
                    )
                )
    return scenarios


def live_daily_branch_scenarios() -> list[BlackboxScenario]:
    """10 explicit live daily-check branches — wellness probes enabled in CallActor."""

    def _steps_from_phrases(phrases: list[str]) -> list[ScenarioStep]:
        steps: list[ScenarioStep] = [ScenarioStep(action="wait_bot_finish", wait_s=45.0)]
        for pid in phrases:
            steps.append(ScenarioStep(action="play_wav", phrase_id=pid))
            steps.append(ScenarioStep(action="wait_bot_finish", wait_s=30.0))
        steps.extend(
            [
                ScenarioStep(action="play_wav", phrase_id="goodbye_01"),
                ScenarioStep(action="wait_bot_finish", wait_s=25.0),
                ScenarioStep(action="play_wav", phrase_id="goodbye_confirm_01"),
                ScenarioStep(action="wait_bot_finish", wait_s=30.0),
            ]
        )
        return steps

    def _scenario(
        sid: str,
        tags: list[str],
        phrase_path: list[str],
        expected: list[str],
        category: WellnessCategory = "good",
    ) -> BlackboxScenario:
        return BlackboxScenario(
            id=sid,
            wellness_category=category,
            family="live_branch",
            variant=0,
            tags=["live_branch", *tags],
            steps=_steps_from_phrases(phrase_path),
            expected_intents=expected,
            skip_if_missing_assets=True,
        )

    return [
        _scenario(
            "live-branch-01-clean-good",
            ["standard"],
            ["wellness_good_01", "mood_positive_01", "sleep_good_01", "plans_walk_01"],
            ["opening", "check_mood", "check_sleep", "check_plans", "summary", "goodbye_final"],
        ),
        _scenario(
            "live-branch-02-bad-probe",
            ["negative_probe"],
            [
                "wellness_bad_01",
                "wellness_bad_02",
                "wellness_bad_03",
                "mood_negative_01",
                "sleep_bad_01",
                "plans_home_01",
            ],
            [
                "opening",
                "probe_concern",
                "probe_duration",
                "check_mood",
                "check_sleep",
                "check_plans",
                "summary",
                "goodbye_final",
            ],
            category="bad",
        ),
        _scenario(
            "live-branch-03-pain-short",
            ["pain_short"],
            ["wellness_normal_01", "sleep_bad_01", "plans_none_01"],
            ["opening", "probe_pain_night", "check_plans", "summary", "goodbye_final"],
            category="normal",
        ),
        _scenario(
            "live-branch-04-repair-kakoe",
            ["repair"],
            [
                "wellness_bad_01",
                "repair_allo_01",
                "mood_negative_01",
                "sleep_bad_01",
                "plans_home_01",
            ],
            ["opening", "probe_concern", "repair_repeat", "check_mood", "summary", "goodbye_final"],
            category="bad",
        ),
        _scenario(
            "live-branch-05-plans-colloquial",
            ["plans_colloquial"],
            ["wellness_good_01", "mood_positive_01", "sleep_good_01", "plans_none_01"],
            ["opening", "check_mood", "check_sleep", "check_plans", "summary", "goodbye_final"],
        ),
        _scenario(
            "live-branch-06-negative-chain",
            ["negative_chain"],
            [
                "wellness_bad_01",
                "wellness_bad_02",
                "wellness_bad_03",
                "mood_negative_01",
                "sleep_bad_01",
                "plans_none_01",
            ],
            [
                "opening",
                "probe_concern",
                "probe_duration",
                "check_mood",
                "summary",
                "goodbye_final",
            ],
            category="bad",
        ),
        _scenario(
            "live-branch-07-backchannel",
            ["backchannel"],
            [
                "wellness_good_01",
                "backchannel_01",
                "mood_positive_01",
                "sleep_good_01",
                "plans_walk_01",
            ],
            ["opening", "check_mood", "check_sleep", "check_plans", "summary", "goodbye_final"],
        ),
        _scenario(
            "live-branch-08-so-so",
            ["so_so"],
            ["wellness_so_so_01", "mood_uncertain_01", "sleep_normal_01", "plans_uncertain_01"],
            ["opening", "check_mood", "check_sleep", "check_plans", "summary", "goodbye_final"],
            category="so_so",
        ),
        _scenario(
            "live-branch-09-doctor-plans",
            ["plans_doctor"],
            ["wellness_normal_01", "mood_neutral_01", "sleep_normal_01", "plans_doctor_01"],
            ["opening", "check_mood", "check_sleep", "check_plans", "summary", "goodbye_final"],
            category="normal",
        ),
        _scenario(
            "live-branch-10-mixed-good",
            ["mixed"],
            ["wellness_good_03", "mood_positive_01", "sleep_good_01", "plans_walk_01"],
            ["opening", "check_mood", "check_sleep", "check_plans", "summary", "goodbye_final"],
        ),
    ]


def catalog_size() -> int:
    return len(generate_catalog())


def write_catalog_json(path: Path) -> int:
    scenarios = generate_catalog()
    payload = {
        "corpus_version": CORPUS_VERSION,
        "corpus_seed": CORPUS_SEED,
        "total": len(scenarios),
        "scenarios": [s.to_dict() for s in scenarios],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(scenarios)
