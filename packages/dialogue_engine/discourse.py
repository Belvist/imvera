"""Discourse memory — the thread of the conversation (single owner).

Writes `current_thread_*`, `open_hook`, `open_hook_used` on EngineState
from verified semantics only: issue mentions, grounded goal facts, the
person's own question. Never from free text, garbage, or silence.

Readers: FOLLOW_USER_THREAD branch in conversation_policy (stay on the
person's topic instead of jumping back to the ladder), hook follow-up
speech built from the person's own words. Decay: 3 uncontinued turns
clear the thread; a hook is consumed once.
"""

from __future__ import annotations

import re

_WS = re.compile(r"\s+")

# goal field -> short speakable thread label.
_FACT_THREAD_LABELS = {
    "mood": "настроение",
    "sleep": "сон",
    "plans": "планы",
    "medication": "лекарства",
    "nutrition": "еда",
    "wellness": "самочувствие",
}

_THREAD_DECAY_TURNS = 3
_HOOK_MAX_CHARS = 70
_HOOK_MIN_WORDS = 2

# Reactive-led turns answer the pending question («Да, дочь
# раскладывает», «Постоянно нет, только иногда») — they belong to the
# ladder, never to the thread. First two words: affirmations, denials,
# and bare «не».
_REACTIVE_LEAD = re.compile(
    r"^(да|нет|не|ага|угу|конечно|неа|ну\s+да|да-да|не-а)\b", re.I
)

# Wellness-state words excluded from delivered-question overlap (they
# match everything: «хорошо посидели» is not about «всё хорошо?»).
_WELLNESS_STOP = frozenset(
    {
        "хорошо",
        "плохо",
        "нормально",
        "обычно",
        "сегодня",
        "сейчас",
        "очень",
        "такое",
        "такая",
        "такой",
        "себя",
        "чувствуете",
        "чувствую",
        "более",
        "менее",
        "себе",
    }
)


def _content_words(text: str) -> set[str]:
    return {
        w.strip(".,!?…").lower()
        for w in (text or "").split()
        if len(w.strip(".,!?…")) >= 5
    } - _WELLNESS_STOP


def _engaged_with_pending(state, raw: str, raw_lower: str) -> bool:
    """True when the turn works on the delivered question: affirmation-led
    or sharing content words with it. Such turns advance the ladder —
    they must not plant hooks or reset the thread."""
    if _REACTIVE_LEAD.search(raw_lower):
        return True
    _first_two = " ".join(raw_lower.split()[:2])
    if re.search(r"\b(да|нет|не|ага|угу|конечно|неа)\b", _first_two):
        return True
    delivered = getattr(state, "delivered_question", None)
    dq_text = (getattr(delivered, "text", "") or "") if delivered else ""
    if not dq_text:
        return False
    return bool(_content_words(raw) & _content_words(dq_text))

# Health-state predicates: with another person present, the turn reports
# THEIR state («муж плохо спал») — not the elder's topic.
_OTHER_HEALTH = re.compile(
    r"спал|спит|спят|сон|сна|заснул|бессонни|болит|болел|температур"
    r"|давлен|кашля|насморк|плохо\s+себе|самочувств|болен|больна|болеет",
    re.I,
)


def normalize_signature(text: str) -> str:
    """Normalized question/ack signature for repeat checks."""
    return _WS.sub(" ", (text or "").strip().lower().rstrip(".!?"))[:120]


def _mention_thread_label(mention) -> str:
    site = (getattr(mention, "body_site", "") or "").strip().lower()
    if site:
        return site
    label = (getattr(mention, "label", "") or "").strip().lower().rstrip("., ")
    return label[:60]


def update_discourse(state, turn) -> None:
    """Single writer of thread/hook fields. Never raises; never writes
    from garbage — a turn with no mentions, facts, or question only ages
    the thread."""
    try:
        mentions = [
            m
            for m in (getattr(turn, "issue_mentions", None) or ())
            if (getattr(m, "subject", "unknown") or "unknown") != "other_person"
        ]
        facts = list(getattr(turn, "goal_facts", None) or ())
        user_question = (getattr(turn, "user_question", None) or "").strip()
        raw = (getattr(turn, "raw_text", None) or "").strip()
        raw_lower = raw.lower()
        engaged = _engaged_with_pending(state, raw, raw_lower)
        if engaged:
            _age(state, raw.split())
            return

        if mentions:
            label = _mention_thread_label(mentions[0])
            if label and label == state.current_thread_label:
                state.current_thread_turns = 0
            elif label:
                state.current_thread_label = label
                state.current_thread_turns = 0
            return

        if user_question:
            if state.current_thread_label != "вопрос":
                state.current_thread_label = "вопрос"
                state.current_thread_turns = 0
            else:
                state.current_thread_turns = 0
            return

        _easing, _nohealth = _speech_owned_elsewhere(raw)
        if facts:
            if (getattr(facts[0], "subject", "") or "") == "other":
                return
            field = (getattr(facts[0], "field", "") or "").strip().lower()
            label = _FACT_THREAD_LABELS.get(field, "")
            if label:
                if label == state.current_thread_label:
                    state.current_thread_turns = 0
                else:
                    state.current_thread_label = label
                    state.current_thread_turns = 0
                # Hook: the person's own words, once. Only from a
                # substantive span — never from one-word answers, easing
                # reports, or non-health evaluations (owned elsewhere).
                if (
                    (not state.open_hook or state.open_hook_used)
                    and not _easing
                    and not _nohealth
                ):
                    words = raw.split()
                    if len(words) >= _HOOK_MIN_WORDS and len(raw) <= 200:
                        hook = raw[:_HOOK_MAX_CHARS].strip()
                        if hook and hook.lower() not in ("да", "нет", "ага", "угу"):
                            state.open_hook = hook
                            state.open_hook_used = False
            return

        # Substantive statement the extractors could not type (act-level
        # verified: kernel called it an answer, not garbage). The most
        # human content lives here («внучка приезжала») — it must start
        # a thread, not fall into the void. Quoted back verbatim, so the
        # speech stays grounded in their exact words.
        act = (getattr(turn, "dialogue_act", "") or "").strip().lower()
        control = (getattr(turn, "control", "") or "").strip().lower()
        try:
            from packages.dialogue_engine.semantic_kernel.lexicon import (
                has_other_person as _has_other,
            )

            _other = bool(_has_other(raw))
        except Exception:  # noqa: BLE001 — lexicon missing: keep the turn
            _other = False
        words = raw.split()
        content = [w for w in words if len(w.strip(".,!?…")) >= 5]
        # Someone else's health state («муж плохо спал») is a report, not
        # the elder's topic — it must not become Vera's thread. An event
        # with the elder inside («внучка приезжала, посидели») is.
        # Health-routed turns (any issue_mentions) stay owned by that path.
        _other_health = bool(
            _other and _OTHER_HEALTH.search(raw_lower) if _other else False
        )
        if (
            act == "answer"
            and control in ("none", "")
            and not getattr(turn, "correction", False)
            and not getattr(turn, "issue_mentions", None)
            and not _other_health
            and not _easing
            and not _nohealth
            and len(words) >= 3
            and content
            and len(raw) <= 200
        ):
            if _continues(words, state):
                state.current_thread_turns = 0
            else:
                state.current_thread_label = "рассказ"
                state.current_thread_turns = 0
            if (not state.open_hook or state.open_hook_used) and raw:
                hook = raw[:_HOOK_MAX_CHARS].strip()
                if hook:
                    state.open_hook = hook
                    state.open_hook_used = False
            return

        # No verified content: age the thread, never steer by free text.
        _age(state, words)
    except Exception:  # noqa: BLE001 — discourse never breaks a turn
        return


def _speech_owned_elsewhere(raw: str) -> tuple[bool, bool]:
    """True/True when easing reports / non-health evaluations own the turn.

    Shared with the scheduler guards: a hook planted here would fire a
    follow-up that interrogates instead of hearing, so plant nothing.
    Never raises (lazy imports, abstain on failure)."""
    easing = False
    try:
        from packages.dialogue_engine.question_context import (
            _RESOLVED_UTTERANCE as _EASING_RE,
        )

        easing = bool(_EASING_RE.search(raw or ""))
    except Exception:  # noqa: BLE001
        pass
    nohealth = False
    try:
        from packages.dialogue_engine.fast_interpreter import (
            is_nonhealth_evaluation as _film,
        )

        nohealth = bool(_film((raw or "").strip()))
    except Exception:  # noqa: BLE001
        pass
    return easing, nohealth


def _age(state, words: list[str]) -> None:
    """Age a live thread on turns that belong elsewhere (answers, debris)."""
    if not state.current_thread_label:
        return
    if _continues(words, state):
        state.current_thread_turns = 0
    else:
        state.current_thread_turns += 1
        if state.current_thread_turns >= _THREAD_DECAY_TURNS:
            state.current_thread_label = ""
            state.current_thread_turns = 0


def _continues(words: list[str], state) -> bool:
    """True when this turn overlaps the live thread (same topic continues)."""
    label = (state.current_thread_label or "").strip().lower()
    if not label:
        return False
    low_words = [w.strip(".,!?…").lower() for w in words]
    if label != "рассказ" and label != "вопрос":
        return label in low_words or any(label in w for w in low_words)
    hook_words = {
        w.strip(".,!?…").lower()
        for w in (state.open_hook or "").split()
        if len(w.strip(".,!?…")) >= 5
    }
    return bool(hook_words and hook_words.intersection(low_words))
