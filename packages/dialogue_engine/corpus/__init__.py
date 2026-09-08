"""Deterministic DialogueEngine regression corpus — >=500 full daily-check dialogues."""

from packages.dialogue_engine.corpus.generator import (
    CORPUS_SEED,
    CORPUS_VERSION,
    generate_corpus,
)
from packages.dialogue_engine.corpus.runner import CorpusRunner, CorpusRunResult
from packages.dialogue_engine.corpus.schema import FullDialogueScenario, WellnessCategory

__all__ = [
    "CORPUS_SEED",
    "CORPUS_VERSION",
    "CorpusRunner",
    "CorpusRunResult",
    "FullDialogueScenario",
    "WellnessCategory",
    "generate_corpus",
]
