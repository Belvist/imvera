"""Discourse memory — the thread of the conversation (single owner).

Stores bounded, verbatim statements with their accepted utterance identity.
These are discourse context, not verified medical or family facts. Clinical
mentions, facts and control retain their own owners. ActionPolicy reads this
context; the reducer activates listening only after audible completion.
Unrelated turns age a topic; substantive listening replies do not.
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
THREAD_QUESTION_INTENTS = frozenset({"thread_followup", "thread_continue"})
_BARE_EVALUATIONS = frozenset({"хорошо", "плохо", "нормально", "неплохо", "так себе"})


def _floor_feedback(text: str) -> bool:
    """Feedback is not a new story anchor or an evidenced health assertion."""
    from packages.dialogue_engine.fast_interpreter import _POSITIVE, _normalize_core
    from packages.dialogue_engine.semantic_kernel.morphology import normalize_text

    core = _normalize_core(text)
    if _POSITIVE.fullmatch(core) or core in _BARE_EVALUATIONS or core in {
        "да", "ага", "угу", "понимаю", "правильно", "понятно", "ясно", "ладно", "конечно",
    }:
        return True
    words = frozenset(normalize_text(core).split())
    if words & {"слушать", "понимать"} and words <= {
        "я", "вы", "ты", "слушать", "понимать", "да", "ну",
    }:
        return True
    return bool(words & {"говорить", "сказать"} and words <= {
        "я", "же", "уже", "говорить", "сказать", "нормально", "хорошо",
        "правильно", "всё", "все", "это", "ну", "да",
    })


def _floor_handoff(text: str) -> bool:
    from packages.dialogue_engine.semantic_kernel.morphology import normalize_text

    words = frozenset(normalize_text(text).split())
    return bool(words & {"всё", "все"} and words <= {
        "всё", "все", "я", "говорить", "сказать", "уже", "правильно", "вот",
        "и", "ну", "это", "пока", "на", "этот",
    })


def listening_question_pending(state) -> bool:
    delivered = getattr(state, "delivered_question", None)
    heard = bool(getattr(state, "thread_heard_listening_id", ""))
    current = bool(
        getattr(state, "thread_listening_id", "")
        and getattr(state, "thread_listening_delivered", False)
        and not state.thread_reply_finished
    )
    token = heard or (getattr(state, "current_thread_label", "") == "рассказ" and current)
    return token or getattr(delivered, "intent", "") in THREAD_QUESTION_INTENTS


def is_listening_evaluation(state, text: str) -> bool:
    if not listening_question_pending(state):
        return False
    # The same floor meaning must govern both fact admission and discourse.
    # Explicit domain predicates still belong to their evidence owner.
    return _floor_feedback(text)



def _listening_reply(state, turn, raw: str) -> bool:
    """The delivered invitation, rather than an old health slot, owns this answer."""
    if not listening_question_pending(state) or state.thread_reply_finished:
        return False
    if (
        getattr(turn, "control", "none") not in ("none", "")
        or getattr(turn, "correction", False)
        or getattr(turn, "user_question", None)
        or getattr(turn, "issue_mentions", ())
        or getattr(turn, "goal_facts", ())
        or getattr(turn, "goal_answers", ())
        or getattr(turn, "risk_candidates", ())
    ):
        return False
    low = raw.lower().rstrip(".!?…")
    finished = _floor_handoff(raw) or bool(getattr(turn, "not_recalled", False)) or low in (
        "нет", "неа", "не знаю", "не помню", "ничего", "больше нечего добавить",
    )
    if not finished and (
        getattr(turn, "dialogue_act", "") != "answer" or not raw or len(raw) > 2048
    ):
        return False
    state.thread_last_utterance_id = turn.utterance_id
    if not finished and not _floor_feedback(raw):
        state.thread_last_statement = raw[:200]
    # A genuinely heard answer may also yield the floor. The next accepted
    # continuation becomes the person's thread, without inventing a fact.
    state.current_thread_label = "рассказ"
    state.thread_reply_turn_id = turn.utterance_id
    state.thread_reply_finished = finished
    state.current_thread_turns = 0
    return True

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


def _story_after_coverage_answer(state, turn, raw: str) -> str:
    """A separately asserted story after a routine answer, never a long-answer guess.

    «Да, поела. А вчера дочь приезжала…» contains two purposes. The first
    remains coverage evidence; the second is discourse evidence. No facts or
    clinical episodes are written here and no additional model is invoked.
    """
    domain = getattr(state, "pending_coverage_domain", None)
    if (not domain or getattr(turn, "issue_mentions", ())
            or getattr(turn, "user_question", None)):
        return ""
    from packages.dialogue_engine.coverage import coverage_reply_quote
    from packages.dialogue_engine.deterministic_mission import split_mission_clauses
    from packages.dialogue_engine.fast_interpreter import _detect_polarity
    from packages.dialogue_engine.issue_mention_extract import extract_goal_facts

    if coverage_reply_quote(turn, domain) is None:
        return ""
    for clause in split_mission_clauses(raw):
        text = clause.text
        scoped = turn.model_copy(update={"raw_text": text, "goal_facts": ()})
        if (coverage_reply_quote(scoped, domain) or extract_goal_facts(text)
                or _detect_polarity(text)):
            continue
        if len(text.split()) >= 3 and not any(_speech_owned_elsewhere(text)):
            from packages.dialogue_engine.semantic_kernel.lexicon import has_other_person

            if has_other_person(text) and _OTHER_HEALTH.search(text):
                continue
            # Keep one contiguous, attributable suffix; do not splice clauses
            # into a story the person never actually told.
            return raw[clause.start:][:200]
    return ""


def update_discourse(state, turn) -> None:
    """Single reducer-invoked discourse writer, including bounded context."""
    _update_discourse(state, turn)
    _remember_personal_statement(state, turn)


def _remember_personal_statement(state, turn) -> None:
    from packages.dialogue_engine.state import DiscourseStatement

    if getattr(turn, "correction", False):
        # Until corrected narrative references have their own grounded binding,
        # never retrieve an older statement as the corrected version.
        state.thread_statements.clear()
        return
    raw = (getattr(turn, "raw_text", "") or "").strip()
    uid = getattr(turn, "utterance_id", "") or ""
    quote = state.thread_last_statement.strip()
    if (
        state.current_thread_label != "рассказ" or state.thread_last_utterance_id != uid
        or not raw or not uid or not state.call_id
        or len(uid) > 128 or len(state.call_id) > 128
        or not quote or quote not in raw
        or getattr(turn, "control", "none") not in ("none", "")
        or getattr(turn, "user_question", None) or getattr(turn, "not_recalled", False)
        or getattr(turn, "issue_mentions", ()) or getattr(turn, "risk_candidates", ())
        or _floor_feedback(raw) or _floor_handoff(raw)
    ):
        return
    from packages.dialogue_engine.semantic_kernel.controls import is_local_question_refusal

    if is_local_question_refusal(raw):
        return
    end = raw.find(quote) + len(quote)
    if end < len(raw) and raw[end].isalnum() and quote[-1].isalnum():
        # Keep an exact excerpt but never cut the spoken quote inside a word.
        quote = quote.rsplit(" ", 1)[0] if " " in quote else ""
    if not quote:
        return
    record = DiscourseStatement(call_id=state.call_id, utterance_id=uid,
                               text=quote, turn_number=state.turn_seq)
    previous = [item for item in state.thread_statements
                if item.call_id == state.call_id and item.utterance_id != uid]
    state.thread_statements = (previous + [record])[-6:]


def recall_personal_statement(state, question_words: frozenset[str]) -> str | None:
    """Read-only topical literal recall; never rescue clinical/mission facts."""
    from packages.dialogue_engine.semantic_kernel.lexicon import (
        BODY_SITE_LEMMAS,
        ISSUE_VERB_LEMMAS,
        MEDICATION_WORDS,
        SENSATION_NOUNS,
    )
    from packages.dialogue_engine.semantic_kernel.morphology import normalize_text

    if question_words & (BODY_SITE_LEMMAS | ISSUE_VERB_LEMMAS
                         | MEDICATION_WORDS | SENSATION_NOUNS):
        return None
    functional = {
        "а", "и", "ну", "как", "какой", "что", "вы", "ты", "я", "мой", "наш", "у", "в",
        "про", "об", "о", "на", "сегодня", "сейчас", "себя", "дело", "это", "этот",
        "говорить", "рассказывать", "рассказать", "сказать", "сообщать", "помнить", "разговор",
        "же", "вот", "ли", "мочь",
    }
    anchors = question_words - functional
    entries = [item for item in state.thread_statements
               if item.call_id == state.call_id and item.utterance_id and item.text.strip()]
    if not anchors:
        # A retained old story must not masquerade as the latest medical answer.
        if state.current_thread_label != "рассказ" or not entries:
            return None
        last = entries[-1]
        return last.text if state.thread_last_statement.startswith(last.text) else None
    for item in reversed(entries):
        words = frozenset(normalize_text(item.text).split())
        if anchors <= words:
            return item.text
    return None


def _update_discourse(state, turn) -> None:
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
        if (
            user_question and listening_question_pending(state)
            and getattr(turn, "control", "none") in ("none", "")
            and not getattr(turn, "correction", False)
            and not getattr(turn, "issue_mentions", ())
            and not getattr(turn, "risk_candidates", ())
        ):
            from packages.dialogue_engine.mission_flow import is_conversation_navigation

            if is_conversation_navigation(user_question):
                # The user gives the floor back. No clinical/background fact
                # is inferred, and the existing selector chooses the next need.
                state.thread_reply_finished = True
                state.thread_reply_turn_id = turn.utterance_id
                state.thread_last_utterance_id = turn.utterance_id
        if _listening_reply(state, turn, raw):
            return
        from packages.dialogue_engine.semantic_kernel.controls import (
            is_local_question_refusal,
            wants_to_continue_talking,
        )

        if (
            is_local_question_refusal(raw) and wants_to_continue_talking(raw)
            and not mentions and not facts and not user_question
            and getattr(turn, "control", "none") in ("none", "")
            and not getattr(turn, "risk_candidates", ())
        ):
            # The refusal's goal disposition keeps its existing semantic owner;
            # a separately explicit wish to talk determines only the floor.
            state.current_thread_label = "рассказ"
            state.current_thread_turns = 0
            state.thread_last_statement = raw[:200]
            state.thread_last_utterance_id = turn.utterance_id
            state.thread_reply_turn_id = ""
            state.thread_reply_finished = False
            return
        engaged = _engaged_with_pending(state, raw, raw_lower)
        if engaged:
            story = _story_after_coverage_answer(state, turn, raw)
            if story:
                state.current_thread_label = "рассказ"
                state.current_thread_turns = 0
                state.thread_last_statement = story
                state.thread_last_utterance_id = turn.utterance_id
                state.thread_reply_turn_id = ""
                state.thread_reply_finished = False
                return
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
            # A side question suspends, rather than erases, the person's story.
            if state.current_thread_label == "рассказ" and state.thread_last_statement:
                return
            if state.current_thread_label != "вопрос":
                state.current_thread_label = "вопрос"
                state.current_thread_turns = 0
            else:
                state.current_thread_turns = 0
            state.thread_last_statement = raw[:200]
            state.thread_last_utterance_id = turn.utterance_id
            state.thread_reply_turn_id = ""
            state.thread_reply_finished = False
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
                    not state.open_hook
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
            and not _floor_feedback(raw)
            and len(words) >= 3
            and content
            and len(raw) <= 2048
        ):
            if _continues(words, state):
                state.current_thread_turns = 0
            else:
                state.current_thread_label = "рассказ"
                state.current_thread_turns = 0
            state.thread_last_statement = raw[:200]
            state.thread_last_utterance_id = turn.utterance_id
            state.thread_reply_turn_id = ""
            state.thread_reply_finished = False
            if not state.open_hook and raw:
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
            state.open_hook = ""
            state.open_hook_used = False
            state.thread_followup_count = 0
            state.thread_reply_turn_id = ""
            state.thread_reply_finished = False
            state.thread_consumed_reply_id = ""
            state.thread_last_statement = ""
            state.thread_last_utterance_id = ""
            state.thread_listening_id = ""
            state.thread_listening_text = ""
            state.thread_listening_delivered = False
            state.thread_listening_generation = 0
            state.thread_heard_listening_id = ""
            state.thread_heard_listening_generation = 0
            state.thread_heard_listening_text = ""


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
