"""Qwen3-4B phrase-generation sampling profiles — Mac dev, single model only."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from golden_path.planner import PlannerAction

# Canonical profile after phrase-quality bench (override via env).
VERA_DIALOGUE_GENERATION_PROFILE = os.environ.get(
    "MOSS_LLM_GENERATION_PROFILE", "vera_deterministic"
).strip() or "vera_deterministic"


@dataclass(frozen=True)
class GenerationProfile:
    name: str
    label: str
    temperature: float
    top_p: float
    top_k: int
    min_p: float
    repetition_penalty: float
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "min_p": self.min_p,
            "repetition_penalty": self.repetition_penalty,
            "description": self.description,
        }


# Preset A — close to Qwen3 non-thinking recommendations (HF model card).
PRESET_QWEN3_OFFICIAL = GenerationProfile(
    name="qwen3_official",
    label="Preset A — Qwen3 non-thinking official-ish",
    temperature=0.7,
    top_p=0.8,
    top_k=20,
    min_p=0.0,
    repetition_penalty=1.0,
    description="Official non-thinking sampling baseline for Qwen3.",
)

# Preset B — more deterministic for voice obedience.
PRESET_VERA_DETERMINISTIC = GenerationProfile(
    name="vera_deterministic",
    label="Preset B — Vera deterministic",
    temperature=0.45,
    top_p=0.85,
    top_k=20,
    min_p=0.05,
    repetition_penalty=1.05,
    description="Lower temperature, tighter for ACTION obedience.",
)

# Preset C — balanced default.
PRESET_VERA_BALANCED = GenerationProfile(
    name="vera_balanced",
    label="Preset C — Vera balanced",
    temperature=0.55,
    top_p=0.88,
    top_k=25,
    min_p=0.03,
    repetition_penalty=1.02,
    description="Balanced naturalness vs obedience.",
)

PROFILES: dict[str, GenerationProfile] = {
    PRESET_QWEN3_OFFICIAL.name: PRESET_QWEN3_OFFICIAL,
    PRESET_VERA_DETERMINISTIC.name: PRESET_VERA_DETERMINISTIC,
    PRESET_VERA_BALANCED.name: PRESET_VERA_BALANCED,
}

BENCH_PROFILE_ORDER: tuple[str, ...] = (
    PRESET_QWEN3_OFFICIAL.name,
    PRESET_VERA_DETERMINISTIC.name,
    PRESET_VERA_BALANCED.name,
)

# Voice output token budgets (phrase renderer, not essay).
MAX_TOKENS_BY_ACTION: dict[str, int] = {
    PlannerAction.ACK_ONLY.value: 25,
    PlannerAction.WAIT.value: 20,
    PlannerAction.ASK_SLOT.value: 45,
    PlannerAction.HANDLE_CORRECTION.value: 40,
    PlannerAction.REPAIR.value: 40,
    PlannerAction.HANDLE_REFUSAL.value: 35,
    PlannerAction.HANDLE_FATIGUE.value: 35,
    PlannerAction.ANSWER_USER.value: 60,
    PlannerAction.CLOSE.value: 35,
    PlannerAction.GREET.value: 45,
    PlannerAction.SAFETY.value: 50,
}

DEFAULT_MAX_TOKENS = 48


def max_tokens_for_action(action: str) -> int:
    return MAX_TOKENS_BY_ACTION.get(action, DEFAULT_MAX_TOKENS)


def load_generation_profile(name: str | None = None) -> GenerationProfile:
    key = (name or VERA_DIALOGUE_GENERATION_PROFILE).strip()
    if key not in PROFILES:
        return PRESET_VERA_BALANCED
    return PROFILES[key]


def active_profile_name() -> str:
    return load_generation_profile().name
