"""20 technical family templates — FSM event trajectories over daily-check."""

from __future__ import annotations

from packages.dialogue_engine.corpus.schema import (
    CorpusStep,
    DeferLastSpeak,
    DeliverPlayout,
    DeliverPlayoutDuplicate,
    ExpectSlot,
    ExpectSpeakIntent,
    ExpectTerminal,
    SlotAnswers,
    StaleLastSpeak,
    UserStep,
)


def _wellness_phase(
    answer: str,
    *,
    next_intent: str = "important_to_share",
    extra_before: tuple[CorpusStep, ...] = (),
    extra_after: tuple[CorpusStep, ...] = (),
) -> tuple[CorpusStep, ...]:
    steps: list[CorpusStep] = [
        *extra_before,
        UserStep(text=answer),
        ExpectSlot(slot="wellness"),
        ExpectSpeakIntent(intent=next_intent),
        DeliverPlayout(),
        *extra_after,
    ]
    return tuple(steps)


def _closing_from_share(
    answers: SlotAnswers,
    share_answer: str = "Ничего.",
) -> tuple[CorpusStep, ...]:
    return (
        UserStep(text=share_answer),
        ExpectSpeakIntent(intent="summary"),
        DeliverPlayout(include_summary=True),
        UserStep(text=answers.goodbye),
        ExpectSpeakIntent(intent="goodbye_confirm"),
        DeliverPlayout(),
        UserStep(text=answers.confirm),
        ExpectTerminal(intent="goodbye_final"),
    )


def _mandatory_slot_phase(
    slot: str,
    answer: str,
    *,
    next_intent: str,
) -> tuple[CorpusStep, ...]:
    return (
        UserStep(text=answer),
        ExpectSlot(slot=slot),
        ExpectSpeakIntent(intent=next_intent),
        DeliverPlayout(),
    )


def _mandatory_closing(answers: SlotAnswers) -> tuple[CorpusStep, ...]:
    return (
        UserStep(text=answers.plans),
        ExpectSlot(slot="plans"),
        ExpectSpeakIntent(intent="summary"),
        DeliverPlayout(include_summary=True),
        UserStep(text=answers.goodbye),
        ExpectSpeakIntent(intent="goodbye_confirm"),
        DeliverPlayout(),
        UserStep(text=answers.confirm),
        ExpectTerminal(intent="goodbye_final"),
    )


def build_family_steps(
    family: str,
    answers: SlotAnswers,
    *,
    wellness_category: str = "good",
) -> tuple[CorpusStep, ...]:
    """Return full step sequence for a family + lexical answers."""
    a = answers
    base_wellness = _wellness_phase(a.wellness)
    closing = _closing_from_share(a)

    if family == "clean_short":
        return (*base_wellness, *closing)

    if family == "clean_long":
        long_wellness = _wellness_phase(f"Да, {a.wellness} В целом всё стабильно.")
        return (*long_wellness, *closing)

    if family == "colloquial":
        return (
            UserStep(text=a.wellness),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="important_to_share"),
            DeliverPlayout(),
            *_closing_from_share(a),
        )

    if family == "paraphrase":
        return (
            UserStep(text=f"Скажу так: {a.wellness}"),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="important_to_share"),
            DeliverPlayout(),
            UserStep(text="Нет, больше ничего."),
            ExpectSpeakIntent(intent="summary"),
            DeliverPlayout(include_summary=True),
            UserStep(text=a.goodbye),
            ExpectSpeakIntent(intent="goodbye_confirm"),
            DeliverPlayout(),
            UserStep(text=a.confirm),
            ExpectTerminal(intent="goodbye_final"),
        )

    if family == "contextual":
        return (
            UserStep(text=f"{a.wellness.rstrip('.')}, вроде."),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="important_to_share"),
            DeliverPlayout(),
            *_closing_from_share(a),
        )

    if family == "self_correction":
        correction = {
            "good": "Плохо… хотя нет, хорошо.",
            "normal": "Плохо… хотя нет, нормально.",
            "so_so": "Хорошо… хотя нет, так себе.",
            "okay": "Плохо… хотя нет, пойдёт.",
            "bad": "Хорошо… хотя нет, плохо.",
        }.get(wellness_category, "Плохо… хотя нет, нормально.")
        return (
            UserStep(text=correction),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="important_to_share"),
            DeliverPlayout(),
            *_closing_from_share(a),
        )

    if family == "repair_allo":
        return (
            UserStep(text=a.wellness),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="important_to_share"),
            DeliverPlayout(),
            UserStep(text="Алло, слышишь?"),
            ExpectSpeakIntent(intent="repair_repeat"),
            DeliverPlayout(),
            *_closing_from_share(a),
        )

    if family == "repair_repeat":
        return (
            UserStep(text=a.wellness),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="important_to_share"),
            DeliverPlayout(),
            UserStep(text="Повтори вопрос."),
            ExpectSpeakIntent(intent="repair_repeat"),
            DeliverPlayout(),
            *_closing_from_share(a),
        )

    if family == "repair_what":
        return (
            UserStep(text=a.wellness),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="important_to_share"),
            DeliverPlayout(),
            UserStep(text="Что?"),
            ExpectSpeakIntent(intent="repair_repeat"),
            DeliverPlayout(),
            *_closing_from_share(a),
        )

    if family == "backchannel":
        return (
            UserStep(text=a.wellness),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="important_to_share"),
            DeliverPlayout(),
            UserStep(text="ага"),
            UserStep(text="Ничего."),
            ExpectSpeakIntent(intent="summary"),
            DeliverPlayout(include_summary=True),
            UserStep(text=a.goodbye),
            ExpectSpeakIntent(intent="goodbye_confirm"),
            DeliverPlayout(),
            UserStep(text=a.confirm),
            ExpectTerminal(intent="goodbye_final"),
        )

    if family == "off_topic_once":
        return (
            UserStep(text=a.wellness),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="important_to_share"),
            DeliverPlayout(),
            UserStep(text="А погода какая?"),
            ExpectSpeakIntent(intent="summary"),
            DeliverPlayout(include_summary=True),
            UserStep(text=a.goodbye),
            ExpectSpeakIntent(intent="goodbye_confirm"),
            DeliverPlayout(),
            UserStep(text=a.confirm),
            ExpectTerminal(intent="goodbye_final"),
        )

    if family == "unclear_once":
        return (
            UserStep(text=a.wellness),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="important_to_share"),
            DeliverPlayout(),
            UserStep(text="ммм"),
            ExpectSpeakIntent(intent="summary"),
            DeliverPlayout(include_summary=True),
            UserStep(text=a.goodbye),
            ExpectSpeakIntent(intent="goodbye_confirm"),
            DeliverPlayout(),
            UserStep(text=a.confirm),
            ExpectTerminal(intent="goodbye_final"),
        )

    if family == "silence_once":
        return (
            UserStep(text=a.wellness),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="important_to_share"),
            DeliverPlayout(),
            UserStep(text="ммм"),
            ExpectSpeakIntent(intent="summary"),
            DeliverPlayout(include_summary=True),
            UserStep(text=a.goodbye),
            ExpectSpeakIntent(intent="goodbye_confirm"),
            DeliverPlayout(),
            UserStep(text=a.confirm),
            ExpectTerminal(intent="goodbye_final"),
        )

    if family == "delayed_answer":
        return (
            UserStep(text=a.wellness, delayed=True),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="important_to_share"),
            DeliverPlayout(),
            *_closing_from_share(a),
        )

    if family == "interrupted_question":
        return (
            UserStep(text=a.wellness),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="important_to_share"),
            UserStep(text="Ничего."),
            ExpectSpeakIntent(intent="summary"),
            DeliverPlayout(include_summary=True),
            UserStep(text=a.goodbye),
            ExpectSpeakIntent(intent="goodbye_confirm"),
            DeliverPlayout(),
            UserStep(text=a.confirm),
            ExpectTerminal(intent="goodbye_final"),
        )

    if family == "stale_speak":
        return (
            UserStep(text=a.wellness),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="important_to_share"),
            DeliverPlayout(),
            UserStep(text="Ничего."),
            ExpectSpeakIntent(intent="summary"),
            DeferLastSpeak(),
            UserStep(text="ага"),
            StaleLastSpeak(),
            DeliverPlayout(include_summary=True),
            UserStep(text=a.goodbye),
            ExpectSpeakIntent(intent="goodbye_confirm"),
            DeliverPlayout(),
            UserStep(text=a.confirm),
            ExpectTerminal(intent="goodbye_final"),
        )

    if family == "stale_timer":
        return (
            UserStep(text=a.wellness, delayed=True),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="important_to_share"),
            DeliverPlayout(),
            *_closing_from_share(a),
        )

    if family == "duplicate_playout":
        return (
            UserStep(text=a.wellness),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="important_to_share"),
            DeliverPlayout(),
            DeliverPlayoutDuplicate(),
            *_closing_from_share(a),
        )

    if family == "long_processing":
        return (
            UserStep(text=a.wellness, delayed=True),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="important_to_share"),
            DeliverPlayout(),
            *_closing_from_share(a),
        )

    if family == "full_mixed":
        return (
            UserStep(text=a.wellness),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="important_to_share"),
            DeliverPlayout(),
            UserStep(text="ага"),
            UserStep(text="Алло?"),
            ExpectSpeakIntent(intent="repair_repeat"),
            DeliverPlayout(),
            *_closing_from_share(a),
        )

    raise ValueError(f"unknown family: {family}")
