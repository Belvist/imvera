"""Conversation policy — single scheduler for next-turn decisions."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import StrEnum

from packages.contracts.enums import SlotStatus
from packages.dialogue_engine import questions
from packages.dialogue_engine.evidence_invariant import question_references_forbidden_site
from packages.dialogue_engine.issue_memory import (
    activate_next_pending_episode,
    episode_complete,
    get_active_episode,
)
from packages.dialogue_engine.question_context import QuestionNeed
from packages.dialogue_engine.response_plan import ResponsePlan
from packages.dialogue_engine.state import (
    BackgroundGoalCoverage,
    CheckPath,
    EngineState,
    SuspendedObligation,
)
from packages.dialogue_engine.turn_understanding import RichUserTurn


class ConversationObligation(StrEnum):
    SAFETY = "safety"
    CONTROL = "control"
    REPAIR = "repair"
    ANSWER_USER_QUESTION = "answer_user_question"
    HANDLE_CORRECTION = "handle_correction"
    ACKNOWLEDGE_IMPORTANT_FACT = "acknowledge_important_fact"
    CONTINUE_ACTIVE_EPISODE = "continue_active_episode"
    RESUME_PENDING_EPISODE = "resume_pending_episode"
    RESUME_SUSPENDED = "resume_suspended"
    IMPORTANT_TO_SHARE = "important_to_share"
    FOLLOW_USER_THREAD = "follow_user_thread"
    BACKGROUND_GOAL = "background_goal"
    SUMMARY_CLOSE = "summary_close"
    NEVER_SILENT = "never_silent"


@dataclass(frozen=True)
class TurnContext:
    turn: RichUserTurn | None = None
    newly_filled_slots: tuple[str, ...] = ()
    user_text: str = ""
    answer_slot: str | None = None
    clarify: bool = False
    answer_not_recalled: bool = False


@dataclass(frozen=True)
class PolicyDecision:
    """Legacy adapter — prefer ResponsePlan from schedule_next_action."""

    obligation: ConversationObligation
    text: str = ""
    intent: str = ""
    slot: str | None = None
    marks_question: bool = False
    suspend: SuspendedObligation | None = None
    control: str | None = None
    episode_id: str | None = None
    semantic_need: QuestionNeed | None = None
    thread_mode: str | None = None


_IMPORTANT_TO_SHARE_QUESTION = questions._ITS_QUESTION_VARIANTS[0]


def _is_important_to_share_decline(text: str) -> bool:
    """Soft «nothing more» answers to the closing add-anything question."""
    import re

    low = text.lower().strip().rstrip(".!?")
    if not low:
        return False
    if low in (
        "нет",
        "неа",
        "ничего",
        "не",
        "всё",
        "все",
        "нет ничего",
        "пока всё",
        "пока все",
        "не знаю",
        "не помню",
        "хз",
    ):
        return True
    strong = (
        "нечего добавить",
        "не хочу добавить",
        "ничего добавить",
        "сказал уже",
        "сказала уже",
        "я ж сказал",
        "я же сказал",
        "я уже сказал",
        "на этом всё",
        "на этом все",
        "больше нечего",
        "уже всё сказал",
        "уже все сказал",
    )
    if any(m in low for m in strong):
        return True
    # «больше ничего» is decline only when not a meta question about Vera asking more.
    if "больше ничего" in low and not any(
        x in low for x in ("спроси", "хотите", "слушаете", "это всё?", "это все?")
    ):
        return True
    soft_no = (
        "вроде бы нет",
        "вроде нет",
        "да нет",
        "да вроде нет",
        "ничего такого",
        "уже всё",
        "уже все",
    )
    if any(m in low for m in soft_no):
        return True
    if re.search(r"\bнет\b", low) and any(
        x in low for x in ("вроде", "больше", "ничего", "толком")
    ):
        return True
    if re.search(r"^(так\s+)?вроде\s+(бы\s+)?вс[её](\s+нормально)?\.?$", low):
        return True
    return False


def _record_important_share(state: EngineState, text: str) -> None:
    note = text.strip()
    if not note:
        return
    state.observations["important_to_share"] = note


def _classify_important_to_share_answer(
    turn: RichUserTurn | None,
    raw: str,
    state: EngineState | None = None,
) -> str:
    """Semantic class for ITS answers — raw text alone is never a recorded fact."""
    from packages.dialogue_engine.semantic_kernel.reference_resolver import (
        is_exclusive_topic_reference,
    )

    if _is_important_to_share_decline(raw):
        return "DECLINE"
    if turn is not None:
        if turn.control not in ("none", ""):
            return "CONTROL"
        if turn.dialogue_act == "repair":
            return "REPAIR"
        if turn.user_question:
            return "USER_QUESTION_OR_META"
        if turn.issue_mentions or turn.goal_facts or turn.correction:
            return "NEW_GROUNDED_INFORMATION"
        if _mentions_medication(raw or ""):
            return "NEW_GROUNDED_INFORMATION"
        if turn.dialogue_act in ("unclear", "backchannel"):
            return "UNCLEAR"
        if (
            turn.dialogue_act == "answer"
            and turn.answers_pending_question
            and not turn.needs_clarification
            and not turn.kernel_ambiguities
            and not turn.risk_candidates
            and not turn.observations
            and not turn.episode_attributes
            and is_exclusive_topic_reference(
                raw, turn.semantic_spans, turn.semantic_relations, state,
            )
        ):
            return "TOPIC_COMPLETE"
    if _mentions_medication(raw or ""):
        return "NEW_GROUNDED_INFORMATION"
    # Meaningful text without grounded extraction → not a share note.
    return "UNCLEAR"


# The listening move, as a pair: the listener clause is an acknowledgement the
# renderer may replace with a grounded reaction, the invitation is the move.
_ITS_META_LISTEN_ACK = "Я вас слушаю."
_ITS_META_LISTEN_QUESTION = (
    "Если хотите, можете сказать, что ещё для вас сейчас важно."
)
_ITS_META_LISTEN = f"{_ITS_META_LISTEN_ACK} {_ITS_META_LISTEN_QUESTION}"

def _mentions_medication(raw: str) -> bool:
    """Tablets/meds mention is grounded family info (live fs-a7bffaf1).

    Medication is a frozen ProductFamily (status_today) with spoken text in
    the pack — losing it into UNCLEAR listen-water + partial is abandonment.
    """
    global _MEDICATION_RE
    if _MEDICATION_RE is None:
        import re as _re

        _MEDICATION_RE = _re.compile(
            r"(таблет|лекар|препарат|медикамент|капл\w*\s+в\s+глаза|"
            r"покапа\w*\s+в\s+глаза|"
            r"от\s+давления|от\s+сердца|для\s+давления)",
            _re.I,
        )
    return bool(_MEDICATION_RE.search(raw or ""))


def capture_suspended_obligation(state: EngineState) -> SuspendedObligation | None:
    ep = get_active_episode(state)
    if ep and state.pending_episode_attribute:
        return SuspendedObligation(
            kind="episode_question",
            episode_id=ep.episode_id,
            attribute=state.pending_episode_attribute,
            slot=f"episode_{ep.episode_id}_{state.pending_episode_attribute}",
            intent=f"episode_{ep.episode_id}_{state.pending_episode_attribute}",
        )
    if state.delivered_question:
        return SuspendedObligation(
            kind="slot_question",
            slot=state.delivered_question.slot,
            intent=state.delivered_question.intent,
        )
    return None


def episode_question_for_attribute(ep, attribute: str) -> tuple[str, str]:
    """Spoken + intent from Dialogue Product Pack (MVP-quality copy)."""
    from packages.dialogue_engine.product import spoken_for_need
    from packages.dialogue_engine.state import EngineState

    # Pack needs state for family cache; build a minimal shim when called without.
    # Call sites that have EngineState should prefer spoken_for_need(state, ep, attr).
    state = EngineState(call_id="pack-speak")
    return spoken_for_need(state, ep, attribute)


def episode_question_for_attribute_with_state(state, ep, attribute: str) -> tuple[str, str]:
    from packages.dialogue_engine.product import spoken_for_need

    return spoken_for_need(state, ep, attribute)


def _missing_question_need(state: EngineState, ep) -> QuestionNeed | None:
    """Product pack owns next step — not information_gain scoring."""
    from packages.dialogue_engine.product import next_product_need

    # Other person's episode: no speaker-directed probes from ANY path.
    if getattr(ep, "subject", "unknown") == "other_person":
        return None
    return next_product_need(state, ep)


def _missing_attribute(state: EngineState, ep) -> str | None:
    need = _missing_question_need(state, ep)
    return need.attribute if need else None


def _all_episodes_resolved(state: EngineState) -> bool:
    if state.active_episode_id:
        ep = state.issue_episodes.get(state.active_episode_id)
        if ep and ep.status != "resolved":
            return False
    for eid in state.pending_episode_ids:
        ep = state.issue_episodes.get(eid)
        if ep and ep.status != "resolved":
            return False
    if state.issue_episodes:
        return all(ep.status == "resolved" for ep in state.issue_episodes.values())
    return True


def _has_open_episodes(state: EngineState) -> bool:
    # Other person's episodes never block the speaker's flow (recorded only).
    def _open(eid: str | None) -> bool:
        ep = state.issue_episodes.get(eid or "")
        return bool(
            ep and ep.status != "resolved" and ep.subject != "other_person"
        )

    if _open(state.active_episode_id):
        return True
    return any(_open(eid) for eid in state.pending_episode_ids)
    return False


def _is_coverage_debris(turn: RichUserTurn, domain: str | None = None) -> bool:
    """STT debris / off-topic one-liners carry nothing to record.

    Slot-aware: food/med verbs («успели», «принял», «поела») and yes/no are
    valid answers on nutrition/medication slots (live 780904ae «Успел.»).
    """
    if turn.goal_facts:
        return False
    text = (turn.raw_text or "").strip()
    if not text:
        return True
    low = text.lower().rstrip(".!?")
    if low in {"да", "нет", "неа"}:
        return False
    if domain in ("nutrition", "medication"):
        from packages.dialogue_engine.reluctance import _SHORT_CONTENT_VERBS

        if _SHORT_CONTENT_VERBS.search(text):
            return False
    from packages.dialogue_engine.coverage import (
        _MEDICATION_MARKERS,
        _MOOD_MARKERS,
        _NUTRITION_MARKERS,
        _SLEEP_MARKERS,
    )
    from packages.dialogue_engine.fast_interpreter import _detect_polarity
    from packages.dialogue_engine.issue_memory import (
        extract_grounded_onset_value,
        extract_grounded_severity_value,
    )

    try:
        if _detect_polarity(text) in ("positive", "negative"):
            return False
    except Exception:  # noqa: BLE001
        pass
    if (
        _MEDICATION_MARKERS.search(text)
        or _NUTRITION_MARKERS.search(text)
        or _SLEEP_MARKERS.search(text)
        or _MOOD_MARKERS.search(text)
    ):
        return False
    if (
        extract_grounded_onset_value(text) is not None
        or extract_grounded_severity_value(text) is not None
    ):
        return False
    return len(text.split()) <= 4


def _apply_coverage_reply(state: EngineState, context: TurnContext) -> ResponsePlan | None:
    """Consume heard routine answers once, before either selector can defer them.

    A story/question suspends the obligation. A local refusal drops that topic
    without manufacturing a health answer. Clinical/safety owners still win.
    """
    domain, turn = state.pending_coverage_domain, context.turn
    if state.red_state_pending or state.risk_handling or state.check_path == CheckPath.URGENT:
        return None
    if (domain and (context.answer_not_recalled or getattr(turn, "not_recalled", False))
            and state.last_user_delivered_slot in {domain, f"background_{domain}"}):
        # Unknown discharges this question; it does not establish an outcome.
        # Semantic-path unknowns can arrive here without a RichUserTurn.
        state.observations[f"coverage_{domain}_unknown"] = context.user_text or (
            turn.raw_text if turn is not None else ""
        )
        state.pending_coverage_domain = None
        return None
    if turn is None:
        return None
    from packages.dialogue_engine.coverage import nutrition_reply_record
    from packages.dialogue_engine.discourse import listening_question_pending

    # A volunteered intake answer can satisfy coverage before the meal question
    # is ever asked. No clinical/consent fact is inferred from this record.
    food = nutrition_reply_record(
        turn, answering=domain == "nutrition"
        and state.last_user_delivered_slot == "background_nutrition"
        and not listening_question_pending(state),
    )
    if food is not None:
        state.coverage_records["nutrition"] = food
        state.observations["coverage_nutrition"] = food.source_text
    if not domain:
        return None
    if turn.issue_mentions or turn.control not in ("", "none") or turn.correction:
        state.pending_coverage_domain = None
        return None
    if (turn.user_question or turn.dialogue_act == "repair"
            or state.red_state_pending or state.risk_handling or _has_open_episodes(state)):
        return None
    from packages.dialogue_engine.semantic_kernel.controls import is_local_question_refusal

    if is_local_question_refusal(turn.raw_text):
        state.observations[f"coverage_{domain}_declined"] = turn.raw_text.strip()
        state.pending_coverage_domain = None
        return None
    if listening_question_pending(state):
        return None
    from packages.dialogue_engine.coverage import (
        classify_medication_screen,
        coverage_reply_quote,
    )

    quote = coverage_reply_quote(turn, domain)
    if quote is not None and quote.casefold().strip().rstrip(".!?…") in {
        "да", "нет", "неа", "конечно",
    } and state.last_user_delivered_slot not in {domain, f"background_{domain}"}:
        # A planned question cannot borrow a bare answer to an older heard
        # question. Lexical volunteered facts remain independent of delivery.
        return None
    screen = classify_medication_screen(quote or "") if domain == "medication" else "unclear"
    if domain == "medication" and not state.medication_asked and screen == "takes_meds":
        state.medication_asked = True
        return ResponsePlan(
            obligation=ConversationObligation.BACKGROUND_GOAL,
            action="speak", mandatory_question=_medication_today_text(state),
            intent="background_medication_today", slot="background_medication", marks_question=True,
        )
    if screen == "refused":
        state.observations[f"coverage_{domain}_declined"] = turn.raw_text.strip()
        state.pending_coverage_domain = None
        return None
    if quote is None and screen not in ("no_meds", "already_took"):
        # Source-grounded discourse owns the floor. Even a lengthy answer act
        # cannot turn photographs or a family story into a food/meds answer.
        if (state.current_thread_label == "рассказ"
                and state.thread_last_utterance_id == turn.utterance_id):
            return None
        if _is_coverage_debris(turn, domain):
            state.pending_coverage_domain = None
        return None
    state.observations[f"coverage_{domain}"] = quote or turn.raw_text.strip()
    state.last_answered_domain = domain
    state.pending_coverage_domain = None
    return None


def _mark_slot_coverage(state: EngineState, slot: str, coverage: BackgroundGoalCoverage) -> None:
    state.set_background_goal_coverage(slot, coverage)


def _medication_today_text(state: EngineState) -> str:
    import zlib

    from packages.dialogue_engine.coverage import MEDICATION_TODAY_TEXTS

    idx = zlib.crc32(((state.call_id or "") + ":meds").encode()) % len(
        MEDICATION_TODAY_TEXTS
    )
    return MEDICATION_TODAY_TEXTS[idx]


def _sync_background_coverage_from_fills(state: EngineState, filled: tuple[str, ...]) -> None:
    for slot in filled:
        if slot in state.background_goal_status:
            _mark_slot_coverage(state, slot, BackgroundGoalCoverage.ANSWERED)


def _next_background_goal(state: EngineState) -> str | None:
    if not _routine_ladder_allowed(state):
        return None
    from packages.dialogue_engine.policy import can_ask_slot

    order = ("mood", "sleep", "plans")
    if state.slots.get("wellness") == SlotStatus.OPEN:
        order = ("wellness", "mood", "sleep", "plans")
    for slot in order:
        # Coverage filler already asked once — never re-ask declined (no quiz).
        if slot == "mood" and "mood" in state.coverage_asked_domains:
            continue
        if slot == "sleep" and "sleep" in state.coverage_asked_domains:
            continue
        if not state.background_goal_needs_attention(slot):
            continue
        if not can_ask_slot(state, slot):
            _mark_slot_coverage(state, slot, BackgroundGoalCoverage.SKIPPED)
            continue
        return slot
    return None


def _episode_plan(
    state: EngineState,
    ep,
    need: QuestionNeed,
    *,
    bridge: str = "",
) -> ResponsePlan | None:
    text, intent = episode_question_for_attribute_with_state(state, ep, need.attribute)
    if question_references_forbidden_site(state, text):
        return None
    # Lowercase only when bridge is a mid-sentence lead-in ("… —"), not a full sentence.
    if bridge.rstrip().endswith("—") and text and text[0].isupper():
        text = text[0].lower() + text[1:]
    return ResponsePlan(
        obligation=ConversationObligation.CONTINUE_ACTIVE_EPISODE,
        action="speak",
        episode_id=ep.episode_id,
        question_needs=[need],
        intent=intent,
        slot=intent,
        mandatory_question=text if not need.is_compound else "",
        acknowledge=bridge,
        marks_question=True,
    )


def _next_episode_plan(state: EngineState) -> ResponsePlan | None:
    """Pick one next episode question — product pack is completion authority."""
    from packages.dialogue_engine.product import call_cap_reached, product_episode_complete

    if call_cap_reached(state):
        return None
    bridge_next = False
    prev_ep = None
    guard = 0
    while guard < 8:
        guard += 1
        ep = get_active_episode(state)
        if ep is None:
            ep = activate_next_pending_episode(state)
            if ep is not None:
                bridge_next = True
        if ep is None:
            return None
        # Pack owns completion. Legacy episode_complete alone must not skip pack steps
        # (e.g. sleep «плохо спал» used to jump to ITS without pattern/daytime).
        # Other person's complaint: recorded, never interrogated — advance
        # past it without speaker-directed probes (reviewer item 2).
        if ep.subject == "other_person":
            activate_next_pending_episode(state)
            bridge_next = True
            continue
        if ep.status == "resolved" or product_episode_complete(state, ep):
            from packages.dialogue_engine.issue_memory import finalize_episode_if_complete

            finalize_episode_if_complete(ep)
            if ep.status != "resolved":
                ep.status = "resolved"
            prev_ep = ep
            activate_next_pending_episode(state)
            bridge_next = True
            continue

        need = _missing_question_need(state, ep)
        if need is None:
            from packages.dialogue_engine.issue_memory import finalize_episode_if_complete

            finalize_episode_if_complete(ep)
            if ep.status != "resolved":
                ep.status = "resolved"
            prev_ep = ep
            activate_next_pending_episode(state)
            bridge_next = True
            continue

        bridge = _bridge_ack_for_episode(ep, prev_ep) if bridge_next else ""
        return _episode_plan(state, ep, need, bridge=bridge)
    return None


def _wellness_entry_covered(state: EngineState) -> bool:
    if state.slots.get("wellness") != SlotStatus.OPEN:
        return True
    status = state.background_goal_status.get("wellness", BackgroundGoalCoverage.UNSEEN)
    if status in (
        BackgroundGoalCoverage.ANSWERED,
        BackgroundGoalCoverage.COVERED_FROM_SPEECH,
    ):
        return True
    # Mood/sleep already answered after opening also counts as entry coverage.
    for slot in ("mood", "sleep"):
        st = state.background_goal_status.get(slot, BackgroundGoalCoverage.UNSEEN)
        if st in (
            BackgroundGoalCoverage.ANSWERED,
            BackgroundGoalCoverage.COVERED_FROM_SPEECH,
        ):
            return True
        if state.slots.get(slot) == SlotStatus.FILLED:
            return True
    return False


_VOLUNTEERED_ACK_DOMAINS = ("nutrition", "sleep")

_DISTRESS_MARKERS = re.compile(
    r"(очень\s+плохо|(?<!не\s)\bплохо\b|ужасн\w*|не\s+могу|невыносим\w*|"
    r"умира\w*|помогите|кошмар\w*|страшно|очень\s+болит|сильно\s+болит|"
    r"болит\s+сильно|помира\w*|нет\s+сил|болезненн\w*)",
    re.I,
)
# Ambiguous fatigue (external audit 2026-09-29): «Надоело всё» is not
# self-harm — explicit forms go RED via safety patterns — but answering it
# with a cold form is inhumane. ITS questions after a fatigue turn carry
# an empathy prefix. Never a standalone (speech-discipline gate).
_FATIGUE_MARKERS = re.compile(
    r"(?:"
    r"\bнадоел[ои]?\b\s*(?:вс[её]|так|жить|болеть|таблетки)?|"
    r"\bнадоели\b|"
    r"\bустал[аои]?\b\s*(?:так|всё|все|жить)?|"
    r"\bжизнь\s+не\s+мила\b"
    r")",
    re.I,
)
_FATIGUE_ACK = "Понимаю."


def _has_fatigue_markers(text: str) -> bool:
    return bool(_FATIGUE_MARKERS.search(text or ""))


def _has_distress_markers(text: str) -> bool:
    return bool(_DISTRESS_MARKERS.search(text or ""))


def _volunteered_ack(state: EngineState) -> str:
    """Acknowledge a volunteered topic once before moving on (live 30a2a638:
    «покушала» → silence about food felt wrong). Asked domains excluded —
    only volunteered ones get the ack.

    Returns the acknowledgement as its own clause: the renderer owns the
    surface and composes it with the question (see realization.py).
    """
    if state.volunteered_ack_done:
        return ""
    from packages.dialogue_engine.coverage import covered_domains

    covered = covered_domains(state)
    asked = state.coverage_asked_domains
    for domain in _VOLUNTEERED_ACK_DOMAINS:
        if domain in covered and domain not in asked:
            from packages.dialogue_engine.realization import _current_record, reaction_clause

            if _current_record(state, domain) is not None:
                state.volunteered_ack_done = True
                return reaction_clause(state, (domain,))
    return ""


def _turn_reports_fresh_negative(turn) -> bool:
    """This turn carries a fresh negative wellness signal.

    Early-close (reluctance) must yield to it: «Нет, мне плохо» at summary
    is a health report, not consent to hang up. Scoped to this turn only —
    an old probed negative must not block a later tired close.
    """
    if turn is None:
        return False
    for fact in turn.goal_facts or ():
        if fact.field == "wellness" and fact.value in ("negative", "uncertain"):
            return True
    return False


def _its_pair(state: EngineState, user_text: str = "") -> tuple[str, str]:
    """(acknowledgement, question) for an ITS turn.

    The transition acknowledgement and the question travel as separate fields
    so the renderer owns the surface (and may replace a content-free transition
    with a grounded reaction). Fatigue empathy outranks the neutral transition.
    """
    ack, question = questions.its_question_and_ack(state)
    if user_text and _has_fatigue_markers(user_text):
        ack = _FATIGUE_ACK
    return ack, question


def _important_to_share_plan(
    state: EngineState, user_text: str = ""
) -> ResponsePlan | None:
    if state.important_to_share_asked or state.important_to_share_resolved:
        return None
    if _has_open_episodes(state):
        return None
    if state.red_state_pending:
        return None
    if not _wellness_entry_covered(state):
        return None
    _its_ack_text, _its_question_text = _its_pair(state, user_text)
    return ResponsePlan(
        obligation=ConversationObligation.IMPORTANT_TO_SHARE,
        action="speak",
        transition_ack=_its_ack_text,
        mandatory_question=_its_question_text,
        intent="important_to_share",
        slot="important_to_share",
        marks_question=True,
    )


def _probe_plan(state: EngineState, *, clarify: bool = False) -> ResponsePlan | None:
    if not state.probe_phase:
        return None
    # Issues own the turn — probe is compatibility context only.
    if _has_open_episodes(state):
        return None
    phase = state.probe_phase
    return ResponsePlan(
        obligation=ConversationObligation.CONTINUE_ACTIVE_EPISODE,
        action="speak",
        question_needs=[QuestionNeed.for_attribute(phase)],
        slot=f"probe_{phase}",
        intent=f"probe_{phase}",
        marks_question=True,
        clarification=clarify,
    )


def _topic_plan(state: EngineState) -> ResponsePlan | None:
    from packages.dialogue_engine.topic_tracker import next_topic_prompt, topic_slot

    prompt = next_topic_prompt(state)
    if prompt is None:
        return None
    return ResponsePlan(
        obligation=ConversationObligation.ACKNOWLEDGE_IMPORTANT_FACT,
        action="speak",
        intent=prompt.intent,
        slot=topic_slot(prompt.family),
        mandatory_question=questions.topic_question(prompt.intent),
        marks_question=True,
    )




def _background_goal_plan(
    state: EngineState,
    *,
    filled: tuple[str, ...] = (),
) -> ResponsePlan | None:
    slot = _next_background_goal(state)
    if slot is None:
        return None
    _mark_slot_coverage(state, slot, BackgroundGoalCoverage.ASKED)
    return ResponsePlan(
        obligation=ConversationObligation.BACKGROUND_GOAL,
        action="speak",
        acknowledge_facts=list(filled),
        next_slot=slot,
        intent=f"check_{slot}",
        slot=slot,
        marks_question=True,
    )


def _summary_plan(state: EngineState, *, acknowledge: str = "") -> ResponsePlan:
    return ResponsePlan(
        obligation=ConversationObligation.SUMMARY_CLOSE,
        action="close_summary",
        close_reason="complete",
        marks_question=False,
        acknowledge=acknowledge,
    )


_MEDICATION_RE = None


def _correction_plan(state: EngineState, turn: RichUserTurn) -> ResponsePlan:
    ep = get_active_episode(state)
    if ep is None and turn.issue_mentions:
        from packages.dialogue_engine.issue_memory import _find_episode_for_mention

        ep_id = _find_episode_for_mention(state, turn.issue_mentions[0])
        if ep_id:
            state.active_episode_id = ep_id
            ep = state.issue_episodes[ep_id]
    label = ep.primary_label if ep else ""
    ack = f"Да, вы говорили, что {label}." if ep else "Понимаю."
    need = None
    if ep:
        pending = state.pending_episode_attribute
        need = (
            QuestionNeed.for_attribute(pending)
            if pending
            else _missing_question_need(state, ep)
        )
    if ep and need:
        q_plan = _episode_plan(state, ep, need)
        if q_plan:
            q_plan.obligation = ConversationObligation.HANDLE_CORRECTION
            q_plan.acknowledge = ack
            return q_plan
    return ResponsePlan(
        obligation=ConversationObligation.HANDLE_CORRECTION,
        action="speak",
        acknowledge=ack,
        mandatory_question="Расскажите, пожалуйста, чуть подробнее.",
        intent="episode_correction_ack",
        marks_question=True,
    )


def _grounded_ack_for_mentions(
    turn: RichUserTurn, state: EngineState | None = None, *, clarifying: bool = True,
) -> str:
    if not turn.issue_mentions:
        return ""
    speaker_mentions = [
        m for m in turn.issue_mentions if getattr(m, "subject", "unknown") != "other_person"
    ]
    labels = [(m.label or "").strip().lower() for m in speaker_mentions if m.label]
    from packages.dialogue_engine.issue_memory import clinical_issue_concept

    active_pain = [m for m in speaker_mentions
                   if getattr(m, "status", "unknown") not in ("improving", "resolved")
                   and clinical_issue_concept(m.label) == "pain"]
    has_head = any(m.body_site == "голова" or "голов" in m.label.lower() for m in active_pain)
    has_belly = any(m.body_site == "живот" or "живот" in m.label.lower() for m in active_pain)
    has_nausea = any("тошн" in x for x in labels)
    if not clarifying and any(getattr(m, "status", "unknown") != "active"
                              for m in speaker_mentions):
        return questions.reported_symptoms_ack(tuple(m.label for m in speaker_mentions))
    # Multi-complaint: warm acknowledgment of the whole picture (not «Понимаю, болит»).
    if has_head and (has_belly or has_nausea):
        parts: list[str] = ["головная боль"]
        if has_belly:
            parts.append("боль в животе")
        if has_nausea:
            parts.append("тошнота")
        if len(parts) == 3:
            joined = f"{parts[0]}, {parts[1]} и {parts[2]}"
        else:
            joined = " и ".join(parts)
        return (
            f"Поняла вас. {joined[0].upper() + joined[1:]} — "
            + ("это неприятно, давайте уточним по порядку." if clarifying else "это неприятно.")
        )
    if has_belly and has_nausea:
        tail = ", давайте уточним по порядку." if clarifying else "."
        return "Поняла вас. Живот и тошнота — это неприятно" + tail
    _any_primary = [
        m
        for m in speaker_mentions
        if m.role in ("primary", "independent", "unknown")
    ]
    candidates = list(_any_primary or speaker_mentions)
    if not candidates:
        return ""
    # Prefer a speakable label: skip bare verbs and broken glue when a
    # fuller mention of the same complaint exists («голова боль» next to
    # «головная боль» must not win the acknowledgment).
    speakable = [
        m
        for m in candidates
        if not _is_bare_verb_label(m.label or "")
        and not _is_broken_glue_label(m.label or "")
    ]
    primary = next((m for m in speakable if (m.body_site or "").strip()),
                   next(iter(speakable or candidates)))
    label = (primary.label or "").strip().rstrip(".")
    if (
        label
        and len(label) > 4
        and not _is_bare_verb_label(label)
        and not _is_broken_glue_label(label)
    ):
        spoken_label = label[0].upper() + label[1:]
        ack = questions.episode_ack(
            _episode_ack_kind(turn, primary),
            spoken_label,
            turn_seq=_utterance_seq(turn),
            clarifying=clarifying,
            conversational=getattr(primary, "status", "unknown") == "active",
            additional_labels=tuple(
                m.label for m in speakable
                if m is not primary and getattr(m, "status", "unknown") == "active"
            ) if getattr(primary, "status", "unknown") == "active" else (),
        )
        raw = getattr(turn, "raw_text", "") or ""
        if raw and _has_fatigue_markers(raw) and "Понимаю" not in ack:
            ack = f"{_FATIGUE_ACK} {ack}"
        if state is not None and ack:
            from packages.dialogue_engine.discourse import normalize_signature

            state.last_ack_signature = normalize_signature(ack)
        return ack
    raw = getattr(turn, "raw_text", "") or ""
    if raw and _has_fatigue_markers(raw):
        return f"{_FATIGUE_ACK} Тяжело."
    return _BARE_ACK_ROTATION[_utterance_seq(turn) % len(_BARE_ACK_ROTATION)]


def _episode_ack_kind(turn: RichUserTurn, mention) -> str:
    """Which acknowledgment fits what actually happened (not a phrase list).

    improving → the elder says it eased; strong → they already said it
    hurts badly; answer → they replied to Vera's own question; new →
    they reported a symptom for the first time.
    """
    status = str(getattr(mention, "status", "") or "").lower()
    raw = str(getattr(turn, "raw_text", "") or "")
    from packages.dialogue_engine.question_context import utterance_indicates_resolved
    from packages.dialogue_engine.semantic_kernel.clauses import clause_bounds, clause_for_position

    evidence = getattr(mention, "evidence", None)
    clause = clause_for_position(clause_bounds(raw), evidence.start) if evidence else raw
    # «Утром поболел» infers past/unknown-current, not actual improvement.
    if status == "resolved" or (status == "improving" and utterance_indicates_resolved(clause)):
        return "improving"
    severity = str(getattr(mention, "severity", "") or "")
    if (severity and _STRONG_PAIN.search(severity)) or _STRONG_PAIN.search(clause):
        return "strong"
    if getattr(turn, "answers_pending_question", False):
        return "answer"
    return "new"


_STRONG_PAIN = re.compile(
    r"(сильн|очень|невыносим|ужасн|нестерпим|адск|не\s+могу\s+терпеть)",
    re.I,
)


def _prev_episode_reported_strong_pain(prev) -> bool:
    """True when the episode we switch away from just grounded strong pain."""
    if prev is None:
        return False
    from packages.dialogue_engine.issue_memory import clinical_issue_concept

    if clinical_issue_concept(prev.primary_label, getattr(prev, "canonical_key", "")) != "pain":
        return False
    severity = str((prev.known_attributes or {}).get("severity", ""))
    return bool(severity and _STRONG_PAIN.search(severity))


def _bridge_ack_for_episode(ep, prev=None) -> str:
    """Warm bridge when switching to a pending episode — never repeat «когда началось»."""
    if _prev_episode_reported_strong_pain(prev):
        # Never answer «Сильно [болит]» with «Хорошо» — acknowledge the pain
        # first, then ask the next episode's question (collects, cares).
        return questions.strong_pain_transition(ep.body_site or "", ep.kind, ep.primary_label)
    label = (ep.primary_label or "").strip()
    return questions.episode_transition(
        (ep.body_site or "").strip(), ep.kind,
        label if not _is_bare_verb_label(label) else "",
    )


# Last-resort fallback when a turn has content but no speakable label.
# Listener-honest by design: claiming «Поняла вас» about something not
# understood is dishonest — «Слушаю вас» tells the truth and the clarifying
# question that follows does the work. (Speech-discipline gate bans the old
# «Поняла вас.»/«Хорошо, поняла вас.» standalones.)
_BARE_ACK_ROTATION = ("Слушаю вас.", "Поняла вас.", "Я вас слушаю.")
_BRIDGE_ACK_ROTATION = ("Хорошо.", "Поняла вас.", "Так, поняла вас.")


def _utterance_seq(turn) -> int:
    import re

    m = re.search(r"(\d+)$", str(getattr(turn, "utterance_id", "") or ""))
    return int(m.group(1)) if m else 0


_BARE_VERBS = frozenset(
    {
        "болит",
        "болят",
        "ноет",
        "ноют",
        "тянет",
        "колет",
        "давит",
        "ломит",
        "тошнит",
        "болеть",
        "ныть",
        "тянуть",
        "колоть",
        "давить",
        "ломить",
        "тошнить",
        "беспокоить",
        "беспокоит",
    }
)

# Body sites whose bare glue with «боль» is ungrammatical
# («голова боль» — never render; «голова болит» is fine).
_BROKEN_GLUE_SITES = frozenset(
    {
        "голова",
        "живот",
        "нога",
        "ноги",
        "рука",
        "руки",
        "спина",
        "грудь",
        "сердце",
        "горло",
        "ухо",
        "уши",
        "зуб",
        "зубы",
        "поясница",
        "колено",
        "плечо",
        "шея",
    }
)


def _is_broken_glue_label(label: str) -> bool:
    """True for ungrammatical site+боль glue («голова боль»)."""
    words = [w.strip(".,!?").lower() for w in label.split()]
    words = [w for w in words if w]
    return (
        len(words) == 2
        and words[0] in _BROKEN_GLUE_SITES
        and words[1] in ("боль", "боли")
    )


def _is_verb_phrase_label(label: str) -> bool:
    """True for a «<site> <pain verb>» label (the generic-body-site form).

    Such a label is a clause, not a noun phrase: it must be spoken as a
    clause, never after «Про».
    """
    words = [w.strip(".,!?").lower() for w in (label or "").split()]
    words = [w for w in words if w]
    return len(words) >= 2 and words[-1] in _BARE_VERBS


def _is_bare_verb_label(label: str) -> bool:
    """True when the label is a bare verb without topic (would render
    broken 'Про болит'). Such mentions must not drive topic questions."""
    words = [w.strip(".,!?").lower() for w in label.split()]
    words = [w for w in words if w]
    if not words:
        return True
    return all(w in _BARE_VERBS or w in ("и", "а") for w in words)


def _turn_is_easing(turn: RichUserTurn) -> bool:
    """Easing/resolution reports belong to the improving path, never to a
    thread follow-up («полегче» → «а что там самое главное?» interrogates)."""
    from packages.dialogue_engine.question_context import _RESOLVED_UTTERANCE

    if any(
        str(getattr(m, "status", "") or "").lower() in ("improving", "resolved")
        for m in (turn.issue_mentions or ())
    ):
        return True
    return bool(_RESOLVED_UTTERANCE.search(turn.raw_text or ""))


def _turn_is_nonhealth_eval(turn: RichUserTurn) -> bool:
    """Film/dream/joke evaluations with health words stay owned by the
    clarify path («плохо от фильма» → redirect to self, live catch)."""
    from packages.dialogue_engine.fast_interpreter import (
        is_nonhealth_evaluation as _film,
    )

    return bool(_film((turn.raw_text or "").strip()))


def _turn_is_unprobed_negative_wellness(state: EngineState) -> bool:
    """Vague-negative wellness with no concern yet belongs to the
    concern-probe net (same ownership as the safety net below): a thread
    follow-up here would swallow a clinical probe."""
    try:
        record = state.slot_records.get("wellness")
    except Exception:  # noqa: BLE001
        return False
    if record is None or (state.wellness_concern or "").strip():
        return False
    return str(getattr(record, "polarity", "") or "") in ("negative", "uncertain")


def _delivered_is_free(state: EngineState) -> bool:
    """True when no specific answer is pending: nothing delivered, or the
    generic opening wellness (the 'free' state where a story may lead)."""
    delivered = getattr(state, "delivered_question", None)
    if delivered is None:
        return True
    return (getattr(delivered, "slot", "") or "") == "wellness"


def resume_after_user_thread(state: EngineState) -> ResponsePlan:
    """Resume a real unanswered goal, without calling a story a health answer."""
    state.thread_reply_finished = True
    if state.slots.get("wellness") == SlotStatus.OPEN:
        return ResponsePlan(
            obligation=ConversationObligation.BACKGROUND_GOAL,
            acknowledge=questions.thread_return_ack(),
            mandatory_question=questions.thread_wellness_return(),
            intent="resume_after_thread", slot="wellness", marks_question=True,
        )
    plan = _schedule_next_action_legacy(state, TurnContext())
    if plan.action in ("speak", "close_summary") and not plan.acknowledge:
        plan.acknowledge = questions.thread_return_ack()
    return plan


def _schedule_next_action_legacy(state: EngineState, turn_context: TurnContext) -> ResponsePlan:
    """Canonical legacy scheduler — mutates EngineState; owns real ResponsePlan."""
    from packages.dialogue_engine.mission_flow import is_custom_mission, schedule_custom_mission

    if is_custom_mission(state):
        custom = schedule_custom_mission(state, turn_context)
        if custom is not None:
            return custom

    turn = turn_context.turn
    filled = turn_context.newly_filled_slots
    clarify = turn_context.clarify
    _sync_background_coverage_from_fills(state, filled)

    if turn and turn.dialogue_act == "repair":
        from packages.dialogue_engine.question_context import repair_question_text

        slot = state.answer_context_slot() or "wellness"
        explanation = questions.requests_question_explanation(turn.raw_text)
        repair_text = repair_question_text(state, slot, explain=explanation)
        return ResponsePlan(
            obligation=ConversationObligation.REPAIR,
            action="speak",
            mandatory_question=questions.repair_response(repair_text, explanation=explanation),
            intent="repair_repeat",
            slot=slot,
            marks_question=False,
        )

    if turn and turn.control not in ("none", ""):
        return ResponsePlan(
            obligation=ConversationObligation.CONTROL,
            action="control",
            control=turn.control,
        )

    # Personal thread selection belongs exclusively to ActionPolicy v10 via
    # DecisionRouter. There is no second bounded follow-up ladder here.
    # Find-out ladder for an answer that contributed NOTHING (no fill, no
    # facts, no mentions — «Непонятно.», debris): try to find out, each time
    # differently — hint, then concrete options — then record unknown
    # EXPLICITLY and move on. Never slide into the ladder with health
    # unknown (live fs-d99db688), never hang up on confusion. Bounded: 3.
    if (
        turn is not None
        and state.check_path != CheckPath.URGENT
        and not _has_open_episodes(state)
        and state.slots.get("wellness") == SlotStatus.OPEN
        and state.first_user_turn_received
        and not turn.issue_mentions
        and not turn.goal_facts
        and not turn.user_question
        and turn.control in ("none", "")
    ):
        from packages.dialogue_engine.runtime import coverage_ladder_enabled as _ladder

        if _ladder():
            from packages.dialogue_engine.fast_interpreter import (
                is_nonhealth_evaluation as _film_clarify,
            )

            attempt = state.slot_unclear_counts.get("wellness", 0) + 1
            state.slot_unclear_counts["wellness"] = attempt
            state.wellness_clarify_asked = True
            if attempt == 1:
                # Heard, but off-topic («фильм плохой»): acknowledge and
                # redirect to self instead of lying «не расслышала».
                _raw = (turn.raw_text or "").strip()
                _ack = ""
                if _film_clarify(_raw) and len(_raw.split()) >= 2:
                    # Heard? No — it was off-topic. The receipt is its own
                    # field so the renderer may answer with a grounded
                    # reaction instead of a bare «Понятно.».
                    _ack = "Понятно."
                    _q = "А вы сами как себя чувствуете — хорошо или не очень?"
                else:
                    _q = (
                        "Простите, не расслышала. Как вы себя чувствуете — "
                        "хорошо или не очень?"
                    )
                return ResponsePlan(
                    obligation=ConversationObligation.NEVER_SILENT,
                    action="speak",
                    acknowledge=_ack,
                    mandatory_question=_q,
                    intent="clarify_wellness",
                    slot="wellness",
                    marks_question=True,
                )
            if attempt == 2:
                return ResponsePlan(
                    obligation=ConversationObligation.NEVER_SILENT,
                    action="speak",
                    mandatory_question=(
                        "Скажите просто: хорошо, нормально или плохо?"
                    ),
                    intent="clarify_wellness",
                    slot="wellness",
                    marks_question=True,
                )
            from packages.dialogue_engine.state import GoalLifecycle

            goal = state.goals.get("wellness")
            if goal is not None:
                goal.lifecycle = GoalLifecycle.UNCLEAR
                goal.status = SlotStatus.UNRESOLVED
            state.slots["wellness"] = SlotStatus.UNRESOLVED
            _mark_slot_coverage(
                state, "wellness", BackgroundGoalCoverage.SKIPPED
            )
            state.observations["wellness_unknown"] = (turn.raw_text or "").strip()
            state.slot_unclear_counts.pop("wellness", None)
            return ResponsePlan(
                obligation=ConversationObligation.NEVER_SILENT,
                action="speak",
                mandatory_question=(
                    "Не получается разобрать, я это запишу. Продолжим?"
                ),
                intent="wellness_unknown",
                slot="wellness",
                marks_question=False,
            )
    if turn is not None and state.check_path != CheckPath.URGENT:
        from packages.dialogue_engine.reluctance import note_reluctance, wants_early_close
        from packages.dialogue_engine.runtime import coverage_ladder_enabled

        note_reluctance(
            state,
            turn,
            answer_slot=state.answer_context_slot(),
            cooperative_fill=bool(filled),
        )
        # Never soothe-close while clarifying red («Отстань» on «умираю»
        # escalates via the probe ladder, not a warm summary).
        if state.red_state_pending:
            pass
        elif (
            coverage_ladder_enabled()
            and wants_early_close(state)
            and not _has_open_episodes(state)
            and not _turn_reports_fresh_negative(turn)
        ):
            return _summary_plan(state)
        elif (
            coverage_ladder_enabled()
            and wants_early_close(state)
            and state.reluctance_score >= 10
            and not _turn_reports_fresh_negative(turn)
        ):
            # Explicit finish-now: close even with open threads, facts kept.
            return _summary_plan(state)

    if turn and turn.user_question and not turn.answers_pending_question:
        from packages.dialogue_engine.mission_flow import answer_user_question_text

        suspend = capture_suspended_obligation(state)
        listening = (
            state.current_thread_label in {"рассказ", "вопрос"}
            and not _has_open_episodes(state)
            and not state.pending_episode_attribute
            and not state.probe_phase
            and not _turn_is_unprobed_negative_wellness(state)
            and state.thread_last_statement and not state.thread_reply_finished
        )
        return ResponsePlan(
            obligation=ConversationObligation.ANSWER_USER_QUESTION,
            action="speak",
            answer_user_question=answer_user_question_text(turn.user_question, state=state),
            intent="answer_user_question",
            marks_question=False,
            suspend=suspend,
            thread_mode="listen" if listening else None,
        )

    if turn and turn.correction:
        return _correction_plan(state, turn)

    if state.suspended_obligation and turn and not turn.user_question:
        suspended = state.suspended_obligation
        state.suspended_obligation = None
        if suspended.kind == "episode_question" and suspended.episode_id:
            state.active_episode_id = suspended.episode_id
            state.pending_episode_attribute = suspended.attribute
        resumed = _next_episode_plan(state)
        if resumed:
            resumed.obligation = ConversationObligation.RESUME_SUSPENDED
            return resumed
        bg = _background_goal_plan(state, filled=filled)
        if bg:
            bg.obligation = ConversationObligation.RESUME_SUSPENDED
            return bg

    if turn and turn.issue_mentions:
        # Acute turns replace the delivered background question before this
        # branch can return. Its pending filler must not steal the next answer.
        state.pending_coverage_domain = None
        if state.important_to_share_asked and not state.important_to_share_resolved:
            state.important_to_share_resolved = True
        ack = _grounded_ack_for_mentions(turn, state)
        # Cross-call continuity (corroboration only): a grounded current
        # mention matching the previous call's episode digest is marked as
        # reopened — the returning complaint is not interrogated as brand
        # new, and the family sees было→стало. Past alone never fires.
        if state.prior_call_context:
            from packages.dialogue_engine.check_path import past_site_matches

            _sites = {
                (getattr(m, "body_site", "") or "").strip().lower()
                for m in (turn.issue_mentions or [])
            }
            _labels = [
                (getattr(m, "label", "") or "").strip().lower()
                for m in (turn.issue_mentions or [])
            ]
            _reopened = past_site_matches(
                state.prior_call_context, sites=_sites, labels=_labels
            )
            if _reopened and not state.observations.get("past_episode_reopened"):
                state.observations["past_episode_reopened"] = _reopened
                # Spoken past: a fresh recurrence of a past complaint is
                # acknowledged out loud as returning — never as brand new.
                # Easing reports (improving/resolved) keep their own ack.
                _recurrence = any(
                    str(getattr(m, "status", "") or "").lower()
                    not in ("improving", "resolved")
                    for m in (turn.issue_mentions or [])
                )
                if _recurrence:
                    from packages.dialogue_engine.discourse import (
                        normalize_signature,
                    )

                    ack = (
                        f"Снова {_reopened}? В прошлый раз тоже было — "
                        "записала, слушаю."
                    )
                    state.last_ack_signature = normalize_signature(ack)
        next_q = _next_episode_plan(state)
        if next_q:
            # Keep pack bridge when switching episodes; don't overwrite with parrot ack.
            if ack and not (next_q.acknowledge or "").strip():
                next_q.acknowledge = ack
            next_q.obligation = ConversationObligation.ACKNOWLEDGE_IMPORTANT_FACT
            return next_q

    if _has_open_episodes(state) and turn is not None:
        pending = state.pending_episode_attribute
        if pending in ("onset", "duration", "severity", "current"):
            from packages.dialogue_engine.issue_memory import (
                extract_grounded_onset_value,
                extract_grounded_severity_value,
            )

            grounded = False
            if pending in ("onset", "duration"):
                grounded = extract_grounded_onset_value(turn.raw_text) is not None
            elif pending == "severity":
                grounded = extract_grounded_severity_value(turn.raw_text) is not None
            else:
                grounded = bool(turn.issue_mentions) or turn.answers_pending_question
            if (
                not grounded
                and not turn.issue_mentions
                and _classify_important_to_share_answer(turn, turn.raw_text)
                in ("USER_QUESTION_OR_META", "UNCLEAR", "REPAIR")
            ):
                next_q = _next_episode_plan(state)
                if next_q:
                    next_q.acknowledge = "Я вас слушаю."
                    return next_q
                return ResponsePlan(
                    obligation=ConversationObligation.NEVER_SILENT,
                    action="speak",
                    acknowledge=_ITS_META_LISTEN_ACK,
                    mandatory_question=_ITS_META_LISTEN_QUESTION,
                    intent="listen_open",
                    marks_question=True,
                )

    if _has_open_episodes(state):
        from packages.dialogue_engine.issue_memory import finalize_episode_if_complete
        from packages.dialogue_engine.policy import can_ask_slot

        next_q = None
        for _ in range(8):
            next_q = _next_episode_plan(state)
            if next_q is None:
                break
            if next_q.slot and not can_ask_slot(state, next_q.slot):
                # Exhausted episode probe — skip attribute, never hang up mid-call.
                # Never fabricate values ("unknown" is not an answer).
                ep = get_active_episode(state)
                if (ep is not None and next_q.question_needs
                        and any(state.issue_episodes.get(eid) is not None
                                and state.issue_episodes[eid].subject != "other_person"
                                and state.issue_episodes[eid].status != "resolved"
                                for eid in state.pending_episode_ids)):
                    # Confusion about one need must not abandon the other
                    # complaints. Discharge this exhausted question with the
                    # person's actual quote, never a fabricated clinical value.
                    need = next_q.question_needs[0]
                    answer_quote = turn.raw_text if turn else turn_context.user_text
                    if not need.is_compound and answer_quote.strip():
                        ep.unanswered_attributes[need.attribute] = answer_quote
                        state.pending_episode_attribute = None
                        next_q = None
                        continue
                if ep is not None:
                    finalize_episode_if_complete(ep)
                state.pending_episode_attribute = None
                if ep is not None and episode_complete(ep):
                    activate_next_pending_episode(state)
                next_q = None
                continue
            break
        if next_q:
            return next_q

    if turn and turn.dialogue_act == "backchannel":
        return ResponsePlan(action="none")

    if state.check_path == CheckPath.URGENT and not state.red_state_pending:
        return ResponsePlan(
            obligation=ConversationObligation.SAFETY,
            action="close_urgent",
        )

    probe = _probe_plan(state, clarify=clarify)
    if probe:
        return probe

    topic = _topic_plan(state)
    if topic:
        return topic

    bare_unheard = (
        not state.last_user_delivered_slot
        and (turn_context.user_text or getattr(turn, "raw_text", "")).casefold().strip()
        .rstrip(".!?…") in {"да", "нет", "неа"}
    )
    if (state.pending_coverage_domain and (state.thread_reply_finished or bare_unheard)
            and _routine_ladder_allowed(state)
            and not _has_open_episodes(state)):
        # Resume the same unanswered need after a finished story or a reply
        # that could not bind to an unheard question. A grounded active thread
        # has already been selected by ActionPolicy, before this legacy path.
        from packages.dialogue_engine.coverage import domain_question

        domain = state.pending_coverage_domain
        previous = state.delivered_question or state.playing_question
        text, intent, slot = domain_question(domain, variant=0)
        if previous is not None and text in previous.text:
            text, intent, slot = domain_question(domain, variant=1)
        if domain == "medication" and state.medication_asked:
            text, intent = _medication_today_text(state), "background_medication_today"
        return ResponsePlan(
            obligation=ConversationObligation.BACKGROUND_GOAL,
            action="speak", thread_mode="resume" if state.thread_reply_finished else None,
            mandatory_question=text,
            intent=intent, slot=slot, marks_question=True,
        )

    if state.important_to_share_asked and not state.important_to_share_resolved:
        raw = ""
        if turn and turn.raw_text.strip():
            raw = turn.raw_text.strip()
        elif turn_context.user_text.strip():
            raw = turn_context.user_text.strip()
        if not raw:
            _ack_text, _question_text = _its_pair(state)
            return ResponsePlan(
                obligation=ConversationObligation.IMPORTANT_TO_SHARE,
                action="speak",
                transition_ack=_ack_text,
                mandatory_question=_question_text,
                intent="important_to_share",
                slot="important_to_share",
                marks_question=True,
            )
        its_class = _classify_important_to_share_answer(turn, raw, state)
        # Fresh negative inside a decline («Нет, мне плохо») is a health
        # report, not consent to close: fall through to the safety net.
        if its_class in ("DECLINE", "TOPIC_COMPLETE") and not _turn_reports_fresh_negative(turn):
            state.important_to_share_resolved = True
            # Full check-in when the mission requires background goals:
            # ask OPEN mood/sleep/plans (all other guards inside).
            # A short call ends only when nothing is left open.
            if state.mandatory_background_goals or state.required_background_goals:
                bg = _background_goal_plan(state, filled=filled)
                if bg:
                    return bg
            # Soft «не знаю» / «нет» after a real check-in → warm recorded close.
            soft = (raw or "").strip().lower().rstrip(".!?")
            if soft in {"не знаю", "не помню", "хз"}:
                return _summary_plan(state)
            return _summary_plan(state)
        if its_class == "NEW_GROUNDED_INFORMATION":
            state.important_to_share_resolved = True
            next_q = _next_episode_plan(state)
            if next_q:
                next_q.acknowledge = "Поняла."
                return next_q
            # Issue was grounded — never treat raw text as ITS share note / close.
            if turn and turn.issue_mentions:
                if _has_open_episodes(state):
                    return ResponsePlan(
                        obligation=ConversationObligation.CONTINUE_ACTIVE_EPISODE,
                        action="speak",
                        mandatory_question="Расскажите подробнее, пожалуйста.",
                        intent="episode_followup",
                        marks_question=True,
                    )
                return _summary_plan(state)
            _record_important_share(state, raw)
            # Frozen MEDICATION family: mention → one status_today followup
            # (pack text exists). Do not swallow into summary/partial.
            if _mentions_medication(raw or "") and not state.medication_asked:
                state.medication_asked = True
                return ResponsePlan(
                    obligation=ConversationObligation.CONTINUE_ACTIVE_EPISODE,
                    action="speak",
                    mandatory_question=(
                        "Поняла. Вы сегодня приняли лекарство, "
                        "которое обычно должны принять?"
                    ),
                    intent="medication_status_today",
                    slot="important_to_share",
                    marks_question=True,
                )
            # Same full check-in rule as the DECLINE branch above.
            if state.mandatory_background_goals or state.required_background_goals:
                bg = _background_goal_plan(state, filled=filled)
                if bg:
                    return bg
            return _summary_plan(state, acknowledge=questions.shared_information_ack())
        if its_class in ("USER_QUESTION_OR_META", "REPAIR", "UNCLEAR", "CONTROL"):
            # Do not resolve ITS — keep conversation open.
            return ResponsePlan(
                obligation=ConversationObligation.IMPORTANT_TO_SHARE,
                action="speak",
                acknowledge=_ITS_META_LISTEN_ACK,
                mandatory_question=_ITS_META_LISTEN_QUESTION,
                intent="important_to_share_listen",
                slot="important_to_share",
                marks_question=True,
            )

    # Safety net (path-independent): negative wellness with no concern on
    # record and nothing acute open MUST probe the concern first — routine
    # ladder (meds/food) may never precede it (live fs-5324e8b6 asked meds
    # right after «Плохо.»). Ladder: probe → options → urgent-unspecified.
    # A twice-vague critical caller escalates with concern unknown (never a
    # «не получилось узнать» partial on red). Runs also on URGENT check path
    # while red_state_pending (clarifying WHAT before the close).
    # A fresh negative re-arms the net even after ITS was asked: the probe
    # below fires on the record, which the reducer just updated.
    if not _has_open_episodes(state) and (
        not state.important_to_share_asked or _turn_reports_fresh_negative(turn)
    ):
        _concern_bits = " ".join(
            x
            for x in [
                state.wellness_concern or "",
                state.observations.get("important_to_share") or "",
            ]
            if x
        )
        if _concern_bits.strip() and state.red_state_pending:
            state.red_state_pending = False
        # Restated complaint re-opens a declined concern («я же говорю,
        # ...плохо мне» after «поел» declined it — live fs-a1dca80c): one
        # sharper probe instead of sliding silently into the ladder.
        _declined = state.observations.get("concern_declined") == "1"
        if _declined and turn is not None:
            from packages.dialogue_engine.check_path import _looks_like_complaint
            from packages.dialogue_engine.protocol.acts import lift_forbids

            if _looks_like_complaint(turn.raw_text or ""):
                state.observations.pop("concern_declined", None)
                state.concern_probe_count = max(state.concern_probe_count, 1)
                lift_forbids(state)
                _declined = False
        # Movie/news defuse (live: «умираю» from a film): strong non-medical
        # context + no symptom anywhere → not a medical red. Clear pending,
        # note the mood, rejoin the normal flow (asked, not assumed).
        if state.red_state_pending and turn is not None and not _has_open_episodes(state):
            from packages.dialogue_engine.coverage import _MOOD_MARKERS

            _raw_low = (turn.raw_text or "").lower()
            if re.search(
                r"\b(фильм\w*|кино|передач\w*|сериал\w*|новост\w*|"
                r"во\s+сне|снил\w*|приснил\w*|сказк\w*)\b",
                _raw_low,
            ) and not turn.issue_mentions:
                from packages.dialogue_engine.check_path import _PAIN

                if not _PAIN.search(turn.raw_text or "") and not _MOOD_MARKERS.search(
                    turn.raw_text or ""
                ):
                    _defuse_red_state(
                        state, "defused-non-medical"
                    )
                elif _MOOD_MARKERS.search(turn.raw_text or ""):
                    _defuse_red_state(state, "defused-mood")
        # Read AFTER defuse (it may have withdrawn the red wellness record).
        _well = state.slot_records.get("wellness")
        _well_text = ""
        if _well is not None:
            _well_text = (_well.source_text or state.slot_values.get("wellness", "") or "")
        # Ambivalent/uncertain wellness that still names feeling bad
        # («нормально, но плохо», live fs-a1dca80c went to food!) counts as
        # negative for probing: polarity alone misses it on the live path.
        # Uncertain-middle («более-менее», «так себе», «средне») names no
        # disease but proves no absence of complaints → probe concern first,
        # never the routine ladder.
        _bad_markers = re.search(
            r"(плох|бол|тошн|кружи|дурно|мутит|тяжел|скверно|отвратительн|"
            r"паршив|хреново|фигово|дерьмово|гнусно|мерзко|погано|кошмарно|"
            r"не\s+очень|так\s+себе)",
            _well_text.lower(),
        )
        # Health concern only: a plain ITS note («Дома буду») is not a
        # concern and must not stand the net down (live: «мне плохо» at
        # summary slid to goodbye because ITS was already asked).
        _health_concern = (state.wellness_concern or "").strip()
        _episode_concern_known = any(
            ep.subject == "speaker" and ep.evidence_turn_ids and ep.mentions
            for ep in state.issue_episodes.values()
        )
        # Completed questioning does not erase the complaint. A fresh vague
        # deterioration can still need its own concern clarification.
        _known_concern_covers_turn = _episode_concern_known and (
            not _turn_reports_fresh_negative(turn) or bool(turn and turn.issue_mentions)
        )
        _negative_no_concern = (
            _well is not None
            and (
                _well.polarity == "negative"
                or _well.polarity == "uncertain"
                or (_well.polarity is None and _bad_markers)
            )
            and not _health_concern
            and not _declined
            and not _known_concern_covers_turn
        ) or (state.red_state_pending and not _concern_bits.strip())
        if _negative_no_concern and (
            state.check_path != CheckPath.URGENT or state.red_state_pending
        ):
            from packages.dialogue_engine.protocol.acts import is_forbidden

            # CDK Step 2: forbids from acts. concern_probe ban skips every
            # probe branch below (decline fallthrough). pain_site_probe
            # ban (e.g. after WELLNESS_OK) skips only the site-listing
            # options variant — a plain "что беспокоит" stays allowed so
            # genuine deterioration still probes (live battery).
            _concern_banned = is_forbidden(state, "concern_probe")
            _pain_banned = is_forbidden(state, "pain_site_probe")
            if state.concern_probe_count >= 2:
                # Twice vague on red — escalate unspecified, honestly marked.
                # BUT a calm substantive non-complaint («Пойдёт.») declines
                # the concern instead (live fs-a1dca80c); only refusal/vent
                # («Отстань», hostile, debris) escalates from here.
                _force = True
                _raw_turn = turn.raw_text if turn is not None else ""
                # Semantic path carries no RichUserTurn: fall back to the
                # scheduled user text so calm/hostile distinction still runs.
                _raw = _raw_turn or (turn_context.user_text or "")
                from packages.dialogue_engine.check_path import (
                    complaint_without_negation,
                )

                if (
                    getattr(state, "last_protocol_act", "") == "WELLNESS_SO_SO"
                    and _raw.strip()
                    and not complaint_without_negation(_raw)
                ):
                    # CDK Step 3: only ever vague (no complaint, no hostility
                    # below) — decline, never force-close-urgent on mush.
                    from packages.dialogue_engine.reluctance import _IRRITATION

                    if not _IRRITATION.search(_raw):
                        _force = False
                        state.observations["concern_declined"] = "1"
                        state.red_state_pending = False
                if _force and _raw.strip():
                    from packages.dialogue_engine.reluctance import (
                        _DONT_KNOW,
                        _FINISH_NOW,
                        _IRRITATION,
                    )

                    _cant_say = _DONT_KNOW.match(_raw.strip()) or re.search(
                        r"не\s+могу\s+сказать", _raw, re.I
                    )
                    if (
                        not complaint_without_negation(_raw)
                        and not _FINISH_NOW.search(_raw)
                        and not _IRRITATION.search(_raw)
                        and not _cant_say
                    ):
                        _force = False
                if _force and not _concern_banned:
                    state.observations["concern_status"] = "unspecified"
                    state.red_state_pending = False
                    return ResponsePlan(
                        obligation=ConversationObligation.SAFETY,
                        action="close_urgent",
                    )
                state.observations["concern_declined"] = "1"
                state.red_state_pending = False
            elif state.concern_probe_count == 1:
                from packages.dialogue_engine.check_path import (
                    apply_concern_answer,
                )
                from packages.dialogue_engine.protocol.acts import (
                    declines_open_concern_probe,
                )

                _raw1 = (
                    getattr(turn, "raw_text", "")
                    or (turn_context.user_text or "")
                )
                if _raw1.strip() and declines_open_concern_probe(state, _raw1):
                    # Decline of the open probe (denial shapes or bare
                    # "I'm fine") — accept and move on (live fs-6e3abff0);
                    # vague/refusal still gets ONE options ask below.
                    apply_concern_answer(state, _raw1)
                    state.observations["concern_declined"] = "1"
                    state.red_state_pending = False
                else:
                    if _concern_banned:
                        state.observations["concern_declined"] = "1"
                        state.red_state_pending = False
                    elif _pain_banned:
                        # Site listing banned, plain probe allowed.
                        state.concern_probe_count = 2
                        return ResponsePlan(
                            obligation=ConversationObligation.NEVER_SILENT,
                            action="speak",
                            mandatory_question=questions.probe_question("concern", state=state),
                            intent="probe_concern",
                            slot="wellness",
                            marks_question=True,
                        )
                    else:
                        state.concern_probe_count = 2
                        return ResponsePlan(
                            obligation=ConversationObligation.NEVER_SILENT,
                            action="speak",
                            mandatory_question=(
                                "Скажите, что болит — голова, сердце, "
                                "живот? Или что случилось?"
                            ),
                            intent="probe_concern_options",
                            # slot=None: the per-slot reserve cap already spent two
                            # wellness asks; this ladder is slot-independent anyway.
                            slot=None,
                            marks_question=True,
                        )
            else:
                if _concern_banned:
                    state.observations["concern_declined"] = "1"
                    state.red_state_pending = False
                    state.concern_probe_count = 0
                    _q = ""
                else:
                    state.concern_probe_count = 1
                    _q = questions.probe_question("concern", state=state)
                if _q:
                    _turn_text = turn.raw_text if turn is not None else ""
                    _empathy = ""
                    if _has_distress_markers(_turn_text):
                        # Live fs-2d8153a8: «очень плохо» → bare «Что беспокоит».
                        # Name the pain first, then ask — pools intact.
                        _empathy = "Сочувствую."
                    return ResponsePlan(
                        obligation=ConversationObligation.NEVER_SILENT,
                        action="speak",
                        acknowledge=_empathy,
                        mandatory_question=_q,
                        intent="probe_concern",
                        slot="wellness",
                        marks_question=True,
                    )
                # Forbidden: declined, rejoin the ladder below.

    # Adaptive coverage (not a questionnaire): when nothing acute is open
    # but the minimum (3 exchanges / 3 domains) is unmet, ask ONE next
    # uncovered baseline domain — volunteered topics are never re-asked,
    # declined ones are never repeated. Tired clients skip straight to ITS.
    # ADR-014 exception, flagged: IMVERA_COVERAGE_LADDER=1 (default frozen).
    if (
        not _has_open_episodes(state)
        and state.check_path != CheckPath.URGENT
        and state.reluctance_score < 2
        and not state.red_state_pending
    ):
        from packages.dialogue_engine.coverage import (
            coverage_met,
            domain_question,
            scored_next_domain,
        )
        from packages.dialogue_engine.product import call_cap_reached
        from packages.dialogue_engine.runtime import coverage_ladder_enabled

        if (
            coverage_ladder_enabled()
            and not coverage_met(state)
            and not call_cap_reached(state)
            and _routine_ladder_allowed(state)
        ):
            # Utility-scored coverage (Cut D start): the person's own topic
            # wins over line position («спал плохо» → sleep next, never
            # nutrition-by-default). Ties → FILLER_ORDER. No re-ask of debris.
            _turn = turn_context.turn
            _last_text = turn_context.user_text or (
                _turn.raw_text if _turn is not None else ""
            )
            _domain = scored_next_domain(state, _last_text)
            if _domain is not None:
                import zlib

                state.coverage_asked_domains.add(_domain)
                state.pending_coverage_domain = _domain
                _variant = zlib.crc32((state.call_id or "").encode()) % 2
                _text, _intent, _slot = domain_question(_domain, variant=_variant)
                return ResponsePlan(
                    obligation=ConversationObligation.BACKGROUND_GOAL,
                    action="speak",
                    acknowledge=_volunteered_ack(state),
                    mandatory_question=_text,
                    intent=_intent,
                    slot=_slot,
                    marks_question=True,
                )

    its = _important_to_share_plan(
        state, getattr(turn, "raw_text", "") or turn_context.user_text
    )
    if its:
        return its

    bg = _background_goal_plan(state, filled=filled)
    if bg:
        return bg

    if not _has_open_episodes(state) or _all_episodes_resolved(state):
        if _next_background_goal(state) is None:
            if not state.important_to_share_resolved:
                if state.first_user_turn_received:
                    _ack_text, _question_text = _its_pair(
                        state, getattr(turn, "raw_text", "") or turn_context.user_text
                    )
                    return ResponsePlan(
                        obligation=ConversationObligation.IMPORTANT_TO_SHARE,
                        action="speak",
                        transition_ack=_ack_text,
                        mandatory_question=_question_text,
                        intent="important_to_share",
                        slot="important_to_share",
                        marks_question=True,
                    )
            return _summary_plan(state)

    if _has_open_episodes(state) and not _all_episodes_resolved(state):
        # No episode plan materialized (ask caps exhausted on confusion):
        # never re-ask an answered slot, never hang up on confusion.
        # Warm summary with what IS known (partial episode data kept,
        # nothing fabricated); the user can still add after it.
        return _summary_plan(state)

    return ResponsePlan(
        obligation=ConversationObligation.NEVER_SILENT,
        action="speak",
        mandatory_question=questions.slot_question("wellness", state=state),
        intent="clarify_wellness",
        slot="wellness",
        marks_question=True,
    )


_REFUSAL_ACK = (
    "Поняла, не буду больше спрашивать.",
    "Хорошо, больше не спрашиваю.",
    "Поняла, оставлю вас в покое.",
)


def _elder_asked_to_stop(
    state: EngineState, turn_context: TurnContext
) -> ResponsePlan | None:
    """«Не беспокой меня» must stop the routine question ladders.

    Warm acknowledgement, no question. Safety and grounding outrank
    politeness: a symptom reported after a refusal still reaches ISSUE_SITE
    through the normal paths, because the refusal predicate never matches a
    complaint. The farewell stays available so the elder can end the call.
    """
    from packages.dialogue_engine.check_path import is_politeness_refusal

    turn = turn_context.turn
    raw = getattr(turn, "raw_text", "") or ""
    if raw and is_politeness_refusal(raw):
        if not getattr(state, "elder_asked_to_stop", False):
            state.elder_asked_to_stop = True
            # Consent transition as a separate fact (ADR-024 outcome data):
            # the withdrawal moment must be traceable independently of the
            # final call_outcome, so a future ranker can learn sequences
            # like consent=DECLINED -> silence -> call DECLINED. First
            # refusal wins; later quotes don't overwrite the moment.
            state.observations["consent_declined"] = raw.strip()[:160]
    if not getattr(state, "elder_asked_to_stop", False):
        return None
    # Only silence the routine ladders while nothing is being reported.
    if turn is not None and getattr(turn, "issue_mentions", None):
        return None
    ack = _REFUSAL_ACK[_utterance_seq(turn) % len(_REFUSAL_ACK)]
    return ResponsePlan(
        obligation=ConversationObligation.NEVER_SILENT,
        action="speak",
        mandatory_question=ack,
        intent="ack_refusal",
        marks_question=False,
    )


def _speech_equivalent_quote(value: str) -> str:
    return value.strip().rstrip(".!?…").casefold()


def _turn_has_accepted_episode_value(state: EngineState, turn: RichUserTurn) -> bool:
    """A filled clinical answer is not an invitation to interrogate its wording."""
    ep = get_active_episode(state)
    if ep is None or not turn.answers_pending_question:
        return False
    from packages.dialogue_engine.issue_memory import (
        extract_grounded_duration_value,
        extract_grounded_severity_value,
    )

    degree = extract_grounded_severity_value(turn.raw_text)
    duration = extract_grounded_duration_value(turn.raw_text)
    return bool(
        (degree and _speech_equivalent_quote(degree)
         == _speech_equivalent_quote(str(ep.known_attributes.get("severity", ""))))
        or (duration and any(duration.casefold() in str(ep.known_attributes.get(k, "")).casefold()
                             for k in ("duration", "onset")))
    )


def _requested_episode_plan(state: EngineState, ctx: TurnContext) -> ResponsePlan | None:
    """Follow an evidenced topic request without answering the interrupted probe."""
    turn = ctx.turn
    if (
        turn is None or turn.dialogue_act != "question" or turn.control not in ("none", "")
        or turn.issue_mentions or turn.goal_facts or turn.correction
        or state.safety_mode == "red" or state.risk_handling or state.red_state_pending
        or state.check_path == CheckPath.URGENT
    ):
        return None
    from packages.dialogue_engine.product import product_episode_complete
    from packages.dialogue_engine.semantic_kernel.reference_resolver import requested_episode
    from packages.dialogue_engine.semantic_kernel.types import RelationType

    target = requested_episode(turn.raw_text, state)
    if target is None or not any(
        r.type == RelationType.REFERS_TO and r.target_span_id == target
        for r in turn.semantic_relations
    ):
        return None
    ep = state.issue_episodes[target]
    if product_episode_complete(state, ep):
        return None
    need = _missing_question_need(state, ep)
    if need is None:
        return None
    # Keep the previous episode's facts and missing attributes in the existing
    # queue. Custom mission's suspended goal remains owned by mission_flow.
    old = state.active_episode_id
    if old and old != target and old not in state.pending_episode_ids:
        state.pending_episode_ids.insert(0, old)
    state.pending_episode_ids = [eid for eid in state.pending_episode_ids if eid != target]
    state.active_episode_id = target
    state.pending_episode_attribute = None
    return _episode_plan(state, ep, need, bridge=questions.requested_episode_ack(
        ep.body_site or "", ep.kind, ep.primary_label,
    ))


def schedule_next_action(state: EngineState, turn_context: TurnContext) -> ResponsePlan:
    """Thin routing wrapper via DecisionRouter.

    Shadow/soft/policy scope = conversation_scheduler only. Outer guards
    (safety/control/repair/timer) are owned by the reducer and bypass this path.
    Exactly one authoritative scheduler mutates/returns per invocation.
    """
    from packages.dialogue_engine.decision_router import route_schedule_next_action

    refusal = _elder_asked_to_stop(state, turn_context)
    if refusal is not None:
        return refusal
    requested = _requested_episode_plan(state, turn_context)
    if requested is not None:
        return requested

    coverage = _apply_coverage_reply(state, turn_context)
    if coverage is not None:
        return coverage

    answered_episode_id = state.active_episode_id
    from packages.dialogue_engine.mission_flow import (
        answer_user_question_text,
        is_conversation_navigation,
    )

    turn = turn_context.turn
    navigation = bool(
        turn and turn.user_question and is_conversation_navigation(turn.user_question)
        and turn.control in ("none", "") and not turn.correction
        and not turn.issue_mentions and not turn.risk_candidates
        and state.safety_mode != "red" and not state.risk_handling
        and not state.red_state_pending and state.check_path != CheckPath.URGENT
    )
    selection_context = turn_context
    if navigation:
        # Resolve only the navigation obligation, then invoke the same owner
        # exactly once. The original canonical turn/evidence remains intact.
        selection_context = replace(turn_context, turn=turn.model_copy(update={
            "user_question": None, "dialogue_act": "answer", "answers_pending_question": False,
        }))
    plan = route_schedule_next_action(
        state,
        selection_context,
        legacy=_schedule_next_action_legacy,
    )
    if navigation and plan.action == "speak" and not plan.control and not plan.safety_class:
        plan.answer_user_question = answer_user_question_text(turn.user_question, state=state)
    ordinary_response = (
        ((plan.action == "speak" and plan.marks_question)
         or (plan.action == "close_summary" and not state.summary_delivered))
        and not plan.control and not plan.safety_class
        and state.safety_mode != "red" and not state.risk_handling
        and not state.red_state_pending
        and state.check_path != CheckPath.URGENT
    )
    if ordinary_response:
        _acknowledge_accepted_report(state, turn_context, plan)
    if ordinary_response and not plan.acknowledge:
        if turn_context.newly_filled_slots:
            plan.acknowledge_facts = list(turn_context.newly_filled_slots)
        _acknowledge_accepted_episode_answer(state, turn_context, plan, answered_episode_id)
        _acknowledge_accepted_relief(state, turn_context, plan)
    if (
        turn_context.answer_not_recalled
        and plan.action == "speak"
        and plan.marks_question
        and not plan.control
        and not plan.safety_class
        and state.safety_mode != "red"
        and not state.risk_handling
        and not state.red_state_pending
    ):
        plan.acknowledgement_kind = "not_recalled"
    # «А что ты спрашивал?» — answer with the last asked question, then
    # continue the plan (never steamroll a question-back into summary).
    # Topic-aware: «...про лекарства?» quotes the meds question, not just
    # the latest one (live 6298a1a3).
    turn = turn_context.turn
    if (
        plan.action == "speak"
        and turn is not None
        and turn.user_question
        and _asks_what_was_asked(turn.user_question)
        and state.asked_history
    ):
        plan.answer_user_question = (
            f"Я спрашивала: «{_history_about(state, turn.user_question)}»."
        )
    return plan


def _acknowledge_accepted_report(
    state: EngineState, ctx: TurnContext, plan: ResponsePlan,
) -> None:
    """React to persisted speaker reports even when no clinical probe remains."""
    turn = ctx.turn
    if (
        turn is None or turn.control not in ("none", "") or turn.user_question
        or turn.correction or turn.not_recalled or plan.acknowledgement_kind
        or plan.acknowledge not in ("", "Поняла.", "Хорошо.", "Хорошо, записала.")
        or plan.obligation in (ConversationObligation.REPAIR, ConversationObligation.CONTROL,
                               ConversationObligation.HANDLE_CORRECTION)
    ):
        return
    from packages.dialogue_engine.issue_memory import _find_episode_for_mention

    accepted = []
    for mention in turn.issue_mentions:
        ep_id = _find_episode_for_mention(state, mention)
        ep = state.issue_episodes.get(ep_id or "")
        if (mention.subject == "speaker" and ep is not None and ep.subject == "speaker"
                and turn.utterance_id in ep.evidence_turn_ids):
            accepted.append(mention)
    if accepted:
        grounded = turn.model_copy(update={"issue_mentions": tuple(accepted)})
        plan.acknowledge = _grounded_ack_for_mentions(
            grounded, state, clarifying=bool(plan.question_needs),
        )


def _acknowledge_accepted_relief(
    state: EngineState, ctx: TurnContext, plan: ResponsePlan,
) -> None:
    """Clinical resolution needs a confirmed current-turn observation."""
    turn = ctx.turn
    if (turn is None or turn.issue_mentions or turn.user_question or turn.correction
            or turn.control not in ("none", "") or plan.acknowledgement_kind):
        return
    for obs in state.observations.values():
        ep = state.issue_episodes.get(getattr(obs, "episode_id", "") or "")
        if (getattr(obs, "source_turn_id", None) == turn.utterance_id
                and getattr(obs, "attribute", None) == "current"
                and getattr(obs, "status", None) == "confirmed"
                and getattr(obs, "subject", None) == "speaker"
                and getattr(obs, "value", None) == "resolved"
                and ep is not None and ep.subject == "speaker"
                and ep.known_attributes.get("current") == "resolved"):
            plan.acknowledgement_kind = "current_relief"
            return


def _acknowledge_accepted_episode_answer(
    state: EngineState, ctx: TurnContext, plan: ResponsePlan, episode_id: str | None,
) -> None:
    """Speech intent follows an accepted value, never a coarse answer vote."""
    turn = ctx.turn
    if (
        turn is None or turn.issue_mentions or turn.user_question or turn.correction
        or turn.not_recalled or plan.acknowledgement_kind
        or not (
            (ctx.answer_slot or "").startswith("episode_")
            or ctx.answer_slot in ("probe_duration", "probe_severity")
            or (ctx.answer_slot is None and turn.answers_pending_question)
        )
    ):
        return
    ep = state.issue_episodes.get(episode_id or "")
    if ep is None or ep.subject == "other_person":
        return
    from packages.dialogue_engine.issue_memory import (
        extract_grounded_duration_value,
        extract_grounded_severity_value,
    )

    duration = extract_grounded_duration_value(turn.raw_text)
    if duration and any(
        duration.casefold() in str(ep.known_attributes.get(key, "")).casefold()
        for key in ("onset", "duration")
    ):
        plan.acknowledgement_kind = "temporal_answer"
        plan.acknowledgement_value = duration
        return
    severity = extract_grounded_severity_value(turn.raw_text)
    accepted = ep.known_attributes.get("severity", "")
    if not severity or _speech_equivalent_quote(severity) != _speech_equivalent_quote(accepted):
        return
    if _STRONG_PAIN.search(severity):
        plan.acknowledgement_kind = "strong_answer"
    elif re.search(r"\bтерпим\w*\b", severity, re.I):
        plan.acknowledgement_kind = "tolerable_answer"
    else:
        from packages.dialogue_engine.semantic_kernel.span_parser import tolerance_severity_spans

        degrees = tolerance_severity_spans(severity)
        if degrees:
            plan.acknowledgement_kind = (
                "tolerable_answer" if degrees[0].normalized == "терпимо" else "strong_answer"
            )
    if plan.acknowledgement_kind == "strong_answer":
        from packages.dialogue_engine.issue_memory import clinical_issue_concept

        if clinical_issue_concept(ep.primary_label, ep.canonical_key) != "pain":
            plan.acknowledgement_kind = None
            plan.acknowledge = questions.severity_answer_ack(strong=True, pain=False)


def _defuse_red_state(state: EngineState, marker: str) -> None:
    """Roll back a false red alarm (movie/news context, investigated).

    The red cry referred to fiction, not health: clear pending, downgrade
    the check path, and withdraw the poisoned wellness record (explicitly
    marked, never silently). Without this, every later close escalates on
    stale «умираю» evidence.
    """
    from packages.contracts.enums import SlotStatus

    state.red_state_pending = False
    state.observations["concern_status"] = marker
    state.check_path = CheckPath.STANDARD
    state.slots["wellness"] = SlotStatus.OPEN
    state.slot_records.pop("wellness", None)
    state.slot_values.pop("wellness", None)


_TOPIC_HINTS = (
    (("лекарств", "таблет", "препарат"), ("лекарств", "таблет", "приняли", "принимаете")),
    (("поесть", "покушать", "попить", "еда", "аппетит"), ("поесть", "покушать", "попить")),
    (("спал", "сон", "выспал"), ("спал", "спали", "выспал")),
    (("настроен", "тревожит", "беспокоит"), ("настроен", "тревожит")),
)


def _routine_ladder_allowed(state: EngineState) -> bool:
    """Bulletproof guard AT the point of asking: routine questions (food /
    meds / mood / sleep) only on explicitly positive wellness.

    The probe net above should intercept first, but live fs-e8164316 proved
    a path exists where it doesn't fire — this guard closes it regardless
    of polarity bookkeeping on any entry path. Closed by default: missing
    record (garbage rejected, question still OPEN) never allows the ladder.
    Uncertain-middle («более-менее») also blocks — it needs a concern probe.
    """
    if state.red_state_pending:
        return False
    _well = state.slot_records.get("wellness")
    if _well is None:
        return False
    if _well.polarity == "positive":
        return True
    if _well.polarity == "negative":
        return False
    if _well.polarity == "uncertain":
        return False
    # None: allow only when the text carries no bad markers.
    _text = (
        _well.source_text or state.slot_values.get("wellness", "") or ""
    ).lower()
    return not re.search(
        r"(плох|бол|тошн|кружи|дурно|мутит|тяжел|скверно|отвратительн|"
        r"паршив|хреново|фигово|дерьмово|гнусно|мерзко|погано|кошмарно|"
        r"не\s+очень|так\s+себе)",
        _text,
    )


def _history_about(state: EngineState, user_question: str) -> str:
    low = (user_question or "").lower()
    for synonyms, markers in _TOPIC_HINTS:
        if any(s in low for s in synonyms):
            for past in reversed(state.asked_history):
                pl = past.lower()
                if any(m in pl for m in markers):
                    return past
    return state.asked_history[-1]


_ASKED_ABOUT_ASKED = re.compile(
    r"(что\s+ты\s+спрашивал\w*|что\s+вы\s+спрашивали|"
    r"о\s+ч[её]м\s+ты\s+спрашивал\w*|что\s+ты\s+сейчас\s+спросил\w*|"
    r"что\s+за\s+вопрос)",
    re.I,
)


def _asks_what_was_asked(user_question: str) -> bool:
    return bool(_ASKED_ABOUT_ASKED.search(user_question or ""))


def resume_episode_obligation(state: EngineState) -> PolicyDecision | None:
    """Compatibility adapter for legacy call sites."""
    plan = _next_episode_plan(state)
    if plan is None:
        return None
    from packages.dialogue_engine.response_plan import composed_text, render_response_plan

    rendered = render_response_plan(plan, state)
    return PolicyDecision(
        obligation=ConversationObligation.CONTINUE_ACTIVE_EPISODE,
        text=composed_text(rendered),
        intent=rendered.intent,
        slot=rendered.slot,
        marks_question=rendered.marks_question,
        episode_id=plan.episode_id,
        semantic_need=plan.question_needs[0] if plan.question_needs else None,
        thread_mode=plan.thread_mode,
    )


def decide_conversation_policy(
    state: EngineState,
    turn: RichUserTurn,
) -> PolicyDecision | None:
    """Legacy entry — delegates to schedule_next_action."""
    from packages.dialogue_engine.response_plan import composed_text, render_response_plan

    plan = schedule_next_action(
        state,
        TurnContext(turn=turn, user_text=turn.raw_text),
    )
    if plan.action == "none":
        return None
    if plan.action == "control":
        return PolicyDecision(
            obligation=ConversationObligation.CONTROL,
            control=plan.control,
        )
    rendered = render_response_plan(plan, state)
    text = composed_text(rendered)
    if not text and plan.obligation != ConversationObligation.CONTROL:
        return None
    return PolicyDecision(
        obligation=plan.obligation or ConversationObligation.NEVER_SILENT,
        text=text,
        intent=rendered.intent,
        slot=rendered.slot,
        marks_question=rendered.marks_question,
        suspend=plan.suspend if isinstance(plan.suspend, SuspendedObligation) else None,
        control=plan.control,
        episode_id=plan.episode_id,
        semantic_need=plan.question_needs[0] if plan.question_needs else None,
        thread_mode=plan.thread_mode,
    )


# Backward compat for question_context import
_attribute_question = episode_question_for_attribute
