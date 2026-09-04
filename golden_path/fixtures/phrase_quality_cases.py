"""50-action phrase quality dataset for Qwen3-4B renderer bench (single model)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from golden_path.analyzer import AnswerType
from golden_path.planner import PlannerAction
from golden_path.slots import SlotName, SlotStatus, default_slot_map
from golden_path.state import ConversationState


@dataclass
class PhraseQualityCase:
    case_id: str
    category: str
    user_message: str
    action: PlannerAction
    slot: SlotName | None = None
    answer_type: AnswerType | None = None
    state_overrides: dict[str, Any] = field(default_factory=dict)

    def build_state(self) -> ConversationState:
        state = ConversationState(session_id=f"bench-{self.case_id}")
        state.greeted = True
        state.slot_statuses = default_slot_map()
        for key, value in self.state_overrides.items():
            if key == "slot_statuses" and isinstance(value, dict):
                for sk, sv in value.items():
                    state.slot_statuses[SlotName(sk)] = SlotStatus(sv)
            elif key == "facts" and isinstance(value, dict):
                state.facts.update(value)
            elif hasattr(state, key):
                setattr(state, key, value)
        return state


def _answered(*slots: str) -> dict[str, str]:
    return {s: SlotStatus.ANSWERED.value for s in slots}


def build_phrase_quality_cases() -> list[PhraseQualityCase]:
    cases: list[PhraseQualityCase] = []

    def add(
        cid: str,
        cat: str,
        user: str,
        action: PlannerAction,
        slot: SlotName | None = None,
        answer_type: AnswerType | None = None,
        **overrides: Any,
    ) -> None:
        cases.append(
            PhraseQualityCase(
                case_id=cid,
                category=cat,
                user_message=user,
                action=action,
                slot=slot,
                answer_type=answer_type,
                state_overrides=overrides,
            )
        )

    # ASK wellness (3)
    for i, user in enumerate(("нормально", "терпимо", "ничего особенного"), 1):
        add(
            f"ask_wellness_{i}",
            "ASK_WELLNESS",
            user,
            PlannerAction.ASK_SLOT,
            SlotName.MOOD,
            slot_statuses=_answered("wellness"),
            pending_slot=SlotName.WELLNESS,
        )

    # ASK mood (3)
    for i, user in enumerate(("настроение хорошее", "спокойное", "ровное"), 1):
        add(
            f"ask_mood_{i}",
            "ASK_MOOD",
            user,
            PlannerAction.ASK_SLOT,
            SlotName.SLEEP,
            slot_statuses=_answered("wellness", "mood"),
        )

    # ASK sleep (3)
    for i, user in enumerate(("спал хорошо", "проснулся отдохнувшим", "средне"), 1):
        add(
            f"ask_sleep_{i}",
            "ASK_SLEEP",
            user,
            PlannerAction.ASK_SLOT,
            SlotName.PLANS,
            slot_statuses=_answered("wellness", "mood", "sleep"),
        )

    # ASK plans (3)
    for i, user in enumerate(
        ("внуки приедут", "ничего особенного", "погуляю"), 1
    ):
        add(
            f"ask_plans_{i}",
            "ASK_PLANS",
            user,
            PlannerAction.ASK_SLOT,
            SlotName.PLANS,
            slot_statuses=_answered("wellness", "mood", "sleep"),
            pending_slot=SlotName.PLANS,
        )

    # ACK narrative (3)
    for i, user in enumerate(
        (
            "внучка приезжала, мы чай пили и разговаривали",
            "соседка заходила, помогла с покупками",
            "утром гулял в парке, было приятно",
        ),
        1,
    ):
        add(
            f"ack_narrative_{i}",
            "ACK_NARRATIVE",
            user,
            PlannerAction.ACK_ONLY,
            slot_statuses=_answered("wellness"),
        )

    # WAIT (3)
    for i, user in enumerate(("секундочку", "подождите", "минутку, вспомню"), 1):
        add(f"wait_{i}", "WAIT", user, PlannerAction.WAIT)

    # FATIGUE (3)
    for i, user in enumerate(
        ("я устал уже отвечать", "хватит вопросов", "не хочу больше отвечать"),
        1,
    ):
        add(f"fatigue_{i}", "FATIGUE", user, PlannerAction.HANDLE_FATIGUE)

    # REFUSAL (3)
    for i, (user, slot) in enumerate(
        (
            ("не хочу про настроение", SlotName.MOOD),
            ("давайте не будем про сон", SlotName.SLEEP),
            ("не буду говорить о планах", SlotName.PLANS),
        ),
        1,
    ):
        add(
            f"refusal_{i}",
            "REFUSAL",
            user,
            PlannerAction.HANDLE_REFUSAL,
            slot,
            pending_slot=slot,
        )

    # CORRECTION (3) — prior symptom only; bench applies analyzer before fallback.
    _correction_prior = (
        {"symptom": "head"},
        {"symptom": "leg"},
        {"symptom": "head"},
    )
    for i, user in enumerate(
        ("нет, не голова, спина", "не нога, а колено", "я имел в виду давление"),
        1,
    ):
        add(
            f"correction_{i}",
            "CORRECTION",
            user,
            PlannerAction.HANDLE_CORRECTION,
            facts=_correction_prior[i - 1],
        )

    # REPAIR (3)
    for i, user in enumerate(("что вы спросили?", "повторите", "не понял"), 1):
        add(
            f"repair_{i}",
            "REPAIR",
            user,
            PlannerAction.REPAIR,
            pending_question="Как вы спали этой ночью?",
            last_assistant_text="Как вы спали этой ночью?",
            pending_slot=SlotName.SLEEP,
        )

    # WHY_CALLING (3)
    for i, user in enumerate(
        ("зачем вы звоните?", "почему вы мне звоните?", "для чего этот звонок?"),
        1,
    ):
        add(
            f"why_{i}",
            "WHY_CALLING",
            user,
            PlannerAction.ANSWER_USER,
            answer_type=AnswerType.WHY_CALLING,
            pending_slot=SlotName.SLEEP,
        )

    # IDENTITY (3)
    for i, user in enumerate(("кто вы?", "как вас зовут?", "вы кто такая?"), 1):
        add(
            f"identity_{i}",
            "IDENTITY",
            user,
            PlannerAction.ANSWER_USER,
            answer_type=AnswerType.IDENTITY,
        )

    # PRIVACY (3)
    for i, user in enumerate(
        (
            "кто увидит мои ответы?",
            "кому вы передаёте информацию?",
            "это конфиденциально?",
        ),
        1,
    ):
        add(
            f"privacy_{i}",
            "PRIVACY",
            user,
            PlannerAction.ANSWER_USER,
            answer_type=AnswerType.PRIVACY,
        )

    # SIDE QUESTION RESUME (4)
    for i, user in enumerate(
        (
            "а зачем вы вообще звоните?",
            "кстати, кто вы?",
            "почему вы звоните мне?",
            "что такое имвера?",
        ),
        1,
    ):
        at = AnswerType.WHY_CALLING if "зачем" in user or "почему" in user else AnswerType.IDENTITY
        add(
            f"side_q_{i}",
            "SIDE_QUESTION_RESUME",
            user,
            PlannerAction.ANSWER_USER,
            answer_type=at,
            slot_statuses=_answered("wellness", "mood"),
            pending_slot=SlotName.SLEEP,
        )

    # Resolved symptom (3)
    for i, user in enumerate(
        ("голове уже легче", "таблетка помогла", "стало лучше"), 1
    ):
        add(
            f"resolved_{i}",
            "RESOLVED_SYMPTOM",
            user,
            PlannerAction.ASK_SLOT,
            SlotName.MOOD,
            slot_statuses=_answered("wellness"),
            facts={"symptom": "head", "improvement": "yes"},
        )

    # Long story (3)
    for i, user in enumerate(
        (
            "вчера внучка приезжала, картошки привезла, а вечером колено заболело",
            "утром ходил в аптеку, потом отдыхал, к вечеру стало легче",
            "дочь звонила, мы долго говорили, потом немного устал",
        ),
        1,
    ):
        add(
            f"long_{i}",
            "LONG_STORY",
            user,
            PlannerAction.ACK_ONLY,
            facts={"symptom": "knee" if i == 1 else ""},
        )

    # CLOSE (1)
    add(
        "close_1",
        "CLOSE",
        "до свидания",
        PlannerAction.CLOSE,
        slot_statuses=_answered("wellness", "mood", "sleep", "plans"),
    )

    return cases[:50]


PHRASE_QUALITY_CASES: tuple[PhraseQualityCase, ...] = tuple(build_phrase_quality_cases())


def apply_bench_user_analysis(case: PhraseQualityCase, state: ConversationState) -> None:
    """Run analyzer + state reduce for correction fixtures (honest bench path)."""
    if case.action != PlannerAction.HANDLE_CORRECTION:
        return
    from golden_path.analyzer import analyze_turn

    analysis = analyze_turn(case.user_message, state)
    state.reduce_user_turn(
        case.user_message,
        analysis.kind.value,
        analysis.facts,
    )
