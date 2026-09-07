"""IMVERA domain vocabulary for STT biasing (ADR-003 + wellness script)."""

from __future__ import annotations

# Domain vocabulary for post-ASR normalization / critical-term matching.
# GigaAM has no hotword biasing API — mlx_qwen path passes these to `hotwords`.
IMVERA_HOTWORDS: list[str] = [
    # Wellness / daily check
    "хорошо",
    "нормально",
    "не очень",
    "плохо",
    "нехорошо",
    "чувствую себя хорошо",
    "чувствую себя плохо",
    "голова болит",
    "устал",
    "слабость",
    # Mood / sleep / plans
    "настроение",
    "спал нормально",
    "спала плохо",
    "дома",
    # Safety-critical (ADR-003)
    "упала",
    "упал",
    "не могу встать",
    "помогите",
    "скорая",
    "мне плохо",
    "голова кружится",
    "вызывайте скорую",
]

# ADR-003 primary recall targets — used for critical_terms in STT response.
IMVERA_CRITICAL_TERMS: tuple[str, ...] = (
    "упала",
    "упал",
    "не могу встать",
    "помогите",
    "голова кружится",
    "мне плохо",
    "скорая",
)
