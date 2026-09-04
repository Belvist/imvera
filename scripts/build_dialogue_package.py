#!/usr/bin/env python3
"""Split telephony/core/dialogue.py into telephony/core/dialogue/ package."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "telephony" / "core"
SRC = CORE / "dialogue.py"
PKG = CORE / "dialogue"


def lines(start: int, end: int) -> str:
    all_lines = SRC.read_text(encoding="utf-8").splitlines(keepends=True)
    return "".join(all_lines[start - 1 : end])


def write(path: Path, header: str, body: str) -> None:
    path.write_text(header + body, encoding="utf-8")


def main() -> int:
    if not SRC.is_file():
        print(f"missing {SRC}")
        return 1
    if PKG.exists():
        shutil.rmtree(PKG)
    PKG.mkdir()

    write(
        PKG / "variety.py",
        '"""Process-level phrase variety ring for cross-call rotation."""\n'
        "from __future__ import annotations\n\n"
        "import collections\n"
        "import threading\n\n",
        lines(68, 74),
    )

    write(
        PKG / "cleaners.py",
        '"""STT transcript cleaning and short-answer recovery."""\n'
        "from __future__ import annotations\n\n"
        "import re\n\n",
        lines(77, 251),
    )

    write(
        PKG / "classifiers.py",
        '"""Text classifiers for FSM event routing."""\n'
        "from __future__ import annotations\n\n"
        "import re\n\n"
        "from core.dialogue.cleaners import short_real_answer\n\n",
        lines(1419, 1557),
    )

    write(
        PKG / "prompts.py",
        '"""VERA persona prompts, constants, and LLM output cleaning."""\n'
        "from __future__ import annotations\n\n"
        "import os\n"
        "import re\n\n"
        "from core.conversation.pools import GREETING_POOL\n\n",
        lines(1283, 1417),
    )

    write(
        PKG / "skill_state.py",
        '"""Compact SKILL.state snapshot for LLM context."""\n'
        "from __future__ import annotations\n\n"
        "from dataclasses import dataclass, field\n"
        "from typing import TYPE_CHECKING\n\n"
        "if TYPE_CHECKING:\n"
        "    from core.dialogue.agent import Agent\n\n",
        lines(1196, 1270),
    )

    fsm_header = (
        '"""DialogueFSM — formal wellness-call state machine."""\n'
        "from __future__ import annotations\n\n"
        "import random\n"
        "import re\n\n"
        "from core.conversation.compose import (\n"
        "    _already_asked_agenda_topic,\n"
        "    build_agenda_intent,\n"
        "    build_cleared_intent,\n"
        "    build_narrative_intent,\n"
        "    build_resume_intent,\n"
        "    build_side_question_intent,\n"
        "    build_symptom_intent,\n"
        "    build_wrap_intent,\n"
        "    cleared_spoken,\n"
        "    extract_symptom_focus,\n"
        "    greeting_spoken,\n"
        "    heard_spoken,\n"
        "    remember_symptom,\n"
        "    symptom_fallback,\n"
        "    topic_fallback,\n"
        "    wrap_fallback,\n"
        ")\n"
        "from core.conversation.danger import pick_danger_reply\n"
        "from core.conversation.flags import (\n"
        "    agenda_topic_allows_llm,\n"
        "    llm_side_questions_enabled,\n"
        ")\n"
        "from core.conversation.goals import (\n"
        "    CONCISE_SKIP_TOPICS,\n"
        "    GOOD_PATH_FOLLOWUP_TOPICS,\n"
        "    TOPIC_KEYS,\n"
        ")\n"
        "from core.conversation.pools import STAY_OBSERVANT_ACKS, SYMPTOM_CHECKS\n"
        "from core.dialogue.classifiers import (\n"
        "    _ALLO_RE,\n"
        "    _is_closing,\n"
        "    _is_closing_direct,\n"
        "    _is_meta_confusion,\n"
        "    _is_refusal,\n"
        "    _is_text_question,\n"
        ")\n"
        "from core.dialogue.cleaners import short_real_answer\n"
        "from core.dialogue.prompts import BAD_WORDS\n"
        "from core.fsm import StateMachine\n"
        "from core.safety_engine import Observation, SafetyEngine\n\n"
    )
    write(PKG / "fsm.py", fsm_header, lines(278, 1193))

    agent_header = (
        '"""Agent — turn-based MVERA conversational controller."""\n'
        "from __future__ import annotations\n\n"
        "import collections\n"
        "import os\n"
        "import random\n"
        "import re\n\n"
        "from core.conversation.compose import (\n"
        "    MINIMAL_FALLBACK,\n"
        "    _already_asked_agenda_topic,\n"
        "    build_agenda_intent,\n"
        "    build_cleared_intent,\n"
        "    cleared_spoken,\n"
        "    greeting_spoken,\n"
        "    heard_spoken,\n"
        "    build_narrative_intent,\n"
        "    build_resume_intent,\n"
        "    build_side_question_intent,\n"
        "    build_symptom_intent,\n"
        "    build_wrap_intent,\n"
        "    extract_symptom_focus,\n"
        "    remember_symptom,\n"
        "    symptom_fallback,\n"
        "    topic_fallback,\n"
        "    wrap_fallback,\n"
        ")\n"
        "from core.conversation.engine import ConversationEngine\n"
        "from core.conversation.flags import (\n"
        "    agenda_topic_allows_llm,\n"
        "    llm_side_questions_enabled,\n"
        ")\n"
        "from core.conversation.goals import (\n"
        "    AGENDA as CHECKIN_AGENDA,\n"
        "    CONCISE_SKIP_TOPICS,\n"
        "    GOOD_PATH_FOLLOWUP_TOPICS,\n"
        "    TOPIC_KEYS,\n"
        ")\n"
        "from core.conversation.greeting import (\n"
        "    format_elder_spoken_name,\n"
        "    pick_scheduled_greeting,\n"
        ")\n"
        "from core.conversation.guards import (\n"
        "    reply_looks_broken,\n"
        "    reply_looks_hallucinated,\n"
        "    reply_too_similar,\n"
        "    same_topic_question,\n"
        "    too_close_to_spoken,\n"
        ")\n"
        "from core.conversation.pools import (\n"
        "    GREETING_POOL,\n"
        "    MINIMAL_FALLBACKS,\n"
        "    SCHEDULED_GREETING_POOL,\n"
        "    SYMPTOM_FALLBACK_POOLS,\n"
        "    TOPIC_FALLBACK_POOLS,\n"
        "    WRAP_FALLBACKS,\n"
        "    STAY_OBSERVANT_ACKS,\n"
        "    SYMPTOM_CHECKS,\n"
        ")\n"
        "from core.dialogue.classifiers import (\n"
        "    _GENERIC_AGENDA_MATCH_KEYS,\n"
        "    _is_closing,\n"
        "    _is_closing_direct,\n"
        "    _is_refusal,\n"
        "    _is_text_question,\n"
        "    _skips_stt_confirm,\n"
        ")\n"
        "from core.dialogue.cleaners import clean_transcript, short_real_answer\n"
        "from core.dialogue.fsm import DialogueFSM\n"
        "from core.dialogue.prompts import (\n"
        "    BAD_WORDS,\n"
        "    DISTRESS_WORDS,\n"
        "    HELP_WORDS,\n"
        "    MED_WORDS,\n"
        "    MVERA_GREETING,\n"
        "    OK_WORDS,\n"
        "    VERA_LLM_ID,\n"
        "    VERA_LLM_URL,\n"
        "    VERA_SCENARIOS,\n"
        "    VERA_SYSTEM_PROMPT,\n"
        "    _clean_llm,\n"
        "    _feminize_self,\n"
        ")\n"
        "from core.dialogue.skill_state import SkillState\n"
        "from core.dialogue.variety import _RECENT_LOCK, _RECENT_SPOKEN\n"
        "from core.safety_engine import SafetyEngine\n\n"
    )
    write(PKG / "agent.py", agent_header, lines(1559, 2702))

    init = '''"""Dialogue engine package — MVERA state machine and VERA persona."""

from core.dialogue.agent import Agent
from core.dialogue.classifiers import (
    _is_closing,
    _is_closing_direct,
    _is_meta_confusion,
    _is_refusal,
    _is_text_question,
    _skips_stt_confirm,
)
from core.dialogue.cleaners import clean_transcript, short_real_answer
from core.dialogue.fsm import DialogueFSM
from core.dialogue.prompts import (
    BAD_WORDS,
    DISTRESS_WORDS,
    HELP_WORDS,
    MED_WORDS,
    MVERA_GREETING,
    OK_WORDS,
    VERA_LLM_ID,
    VERA_LLM_URL,
    VERA_SCENARIOS,
    VERA_SYSTEM_PROMPT,
    _clean_llm,
    _feminize_self,
)
from core.dialogue.skill_state import SkillState
from core.dialogue.variety import _RECENT_LOCK, _RECENT_SPOKEN
from core.conversation.guards import (
    reply_looks_broken,
    reply_looks_hallucinated,
)

__all__ = [
    "Agent",
    "DialogueFSM",
    "SkillState",
    "MVERA_GREETING",
    "VERA_SYSTEM_PROMPT",
    "VERA_SCENARIOS",
    "VERA_LLM_ID",
    "VERA_LLM_URL",
    "OK_WORDS",
    "BAD_WORDS",
    "DISTRESS_WORDS",
    "MED_WORDS",
    "HELP_WORDS",
    "clean_transcript",
    "short_real_answer",
    "_clean_llm",
    "_feminize_self",
    "reply_looks_broken",
    "reply_looks_hallucinated",
    "_RECENT_SPOKEN",
    "_RECENT_LOCK",
    "_is_closing",
    "_is_closing_direct",
    "_is_meta_confusion",
    "_is_refusal",
    "_is_text_question",
    "_skips_stt_confirm",
]
'''
    write(PKG / "__init__.py", "", init)

    backup = CORE / "dialogue_monolith.py.bak"
    shutil.copy2(SRC, backup)
    SRC.unlink()
    print(f"split OK -> {PKG} (backup {backup})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
