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
    FireTimerExpired,
    SlotAnswers,
    StaleLastSpeak,
    UserStep,
)


def _slot_phase(
    slot: str,
    answer: str,
    *,
    next_intent: str,
    extra_before: tuple[CorpusStep, ...] = (),
    extra_after: tuple[CorpusStep, ...] = (),
) -> tuple[CorpusStep, ...]:
    steps: list[CorpusStep] = [
        *extra_before,
        UserStep(text=answer),
        ExpectSlot(slot=slot),
        ExpectSpeakIntent(intent=next_intent),
        DeliverPlayout(),
        *extra_after,
    ]
    return tuple(steps)


def _closing_phase(answers: SlotAnswers) -> tuple[CorpusStep, ...]:
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
    base_wellness = _slot_phase("wellness", a.wellness, next_intent="check_mood")
    mood = _slot_phase("mood", a.mood, next_intent="check_sleep")
    sleep = _slot_phase("sleep", a.sleep, next_intent="check_plans")
    closing = _closing_phase(a)

    if family == "clean_short":
        return (*base_wellness, *mood, *sleep, *closing)

    if family == "clean_long":
        long_wellness = _slot_phase(
            "wellness",
            f"Да, {a.wellness} В целом всё стабильно.",
            next_intent="check_mood",
        )
        long_mood = _slot_phase(
            "mood",
            f"Настроение {a.mood.lower().rstrip('.')}, в целом нормально.",
            next_intent="check_sleep",
        )
        return (*long_wellness, *long_mood, *sleep, *closing)

    if family == "colloquial":
        return (
            UserStep(text=a.wellness),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="check_mood"),
            DeliverPlayout(),
            UserStep(text=a.mood),
            ExpectSlot(slot="mood"),
            ExpectSpeakIntent(intent="check_sleep"),
            DeliverPlayout(),
            *sleep,
            *closing,
        )

    if family == "paraphrase":
        return (
            UserStep(text=f"Скажу так: {a.wellness}"),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="check_mood"),
            DeliverPlayout(),
            UserStep(text=f"Если коротко — {a.mood.lower().rstrip('.')}."),
            ExpectSlot(slot="mood"),
            ExpectSpeakIntent(intent="check_sleep"),
            DeliverPlayout(),
            UserStep(text=f"По сну: {a.sleep.lower().rstrip('.')}."),
            ExpectSlot(slot="sleep"),
            ExpectSpeakIntent(intent="check_plans"),
            DeliverPlayout(),
            UserStep(text=f"Планы такие: {a.plans.lower().rstrip('.')}."),
            ExpectSlot(slot="plans"),
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
            ExpectSpeakIntent(intent="check_mood"),
            DeliverPlayout(),
            UserStep(text=f"{a.mood.rstrip('.')}, наверное."),
            ExpectSlot(slot="mood"),
            ExpectSpeakIntent(intent="check_sleep"),
            DeliverPlayout(),
            *sleep,
            *closing,
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
            ExpectSpeakIntent(intent="check_mood"),
            DeliverPlayout(),
            *mood,
            *sleep,
            *closing,
        )

    if family == "repair_allo":
        return (
            UserStep(text=a.wellness),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="check_mood"),
            DeliverPlayout(),
            UserStep(text="Алло, слышишь?"),
            ExpectSpeakIntent(intent="repair_repeat"),
            DeliverPlayout(),
            UserStep(text=a.mood),
            ExpectSlot(slot="mood"),
            ExpectSpeakIntent(intent="check_sleep"),
            DeliverPlayout(),
            *sleep,
            *closing,
        )

    if family == "repair_repeat":
        return (
            UserStep(text=a.wellness),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="check_mood"),
            DeliverPlayout(),
            UserStep(text="Повтори вопрос."),
            ExpectSpeakIntent(intent="repair_repeat"),
            DeliverPlayout(),
            UserStep(text=a.mood),
            ExpectSlot(slot="mood"),
            ExpectSpeakIntent(intent="check_sleep"),
            DeliverPlayout(),
            *sleep,
            *closing,
        )

    if family == "repair_what":
        return (
            UserStep(text=a.wellness),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="check_mood"),
            DeliverPlayout(),
            UserStep(text="Что?"),
            ExpectSpeakIntent(intent="repair_repeat"),
            DeliverPlayout(),
            UserStep(text=a.mood),
            ExpectSlot(slot="mood"),
            ExpectSpeakIntent(intent="check_sleep"),
            DeliverPlayout(),
            *sleep,
            *closing,
        )

    if family == "backchannel":
        return (
            UserStep(text=a.wellness),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="check_mood"),
            DeliverPlayout(),
            UserStep(text="ага"),
            UserStep(text=a.mood),
            ExpectSlot(slot="mood"),
            ExpectSpeakIntent(intent="check_sleep"),
            DeliverPlayout(),
            *sleep,
            *closing,
        )

    if family == "off_topic_once":
        return (
            UserStep(text=a.wellness),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="check_mood"),
            DeliverPlayout(),
            UserStep(text="А погода какая?"),
            ExpectSpeakIntent(intent="clarify_mood"),
            DeliverPlayout(),
            UserStep(text=a.mood),
            ExpectSlot(slot="mood"),
            ExpectSpeakIntent(intent="check_sleep"),
            DeliverPlayout(),
            *sleep,
            *closing,
        )

    if family == "unclear_once":
        return (
            UserStep(text=a.wellness),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="check_mood"),
            DeliverPlayout(),
            UserStep(text="ммм"),
            ExpectSpeakIntent(intent="clarify_mood"),
            DeliverPlayout(),
            UserStep(text=a.mood),
            ExpectSlot(slot="mood"),
            ExpectSpeakIntent(intent="check_sleep"),
            DeliverPlayout(),
            *sleep,
            *closing,
        )

    if family == "silence_once":
        return (
            UserStep(text=a.wellness),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="check_mood"),
            DeliverPlayout(),
            FireTimerExpired(timer_id="wait-mood"),
            ExpectSpeakIntent(intent="clarify_mood"),
            DeliverPlayout(),
            UserStep(text=a.mood),
            ExpectSlot(slot="mood"),
            ExpectSpeakIntent(intent="check_sleep"),
            DeliverPlayout(),
            *sleep,
            *closing,
        )

    if family == "delayed_answer":
        return (
            UserStep(text=a.wellness, delayed=True),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="check_mood"),
            DeliverPlayout(),
            *mood,
            *sleep,
            *closing,
        )

    if family == "interrupted_question":
        return (
            UserStep(text=a.wellness),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="check_mood"),
            # Playout pending — answer still accepted via playing_question.
            UserStep(text=a.mood),
            ExpectSlot(slot="mood"),
            ExpectSpeakIntent(intent="check_sleep"),
            DeliverPlayout(),
            *sleep,
            *closing,
        )

    if family == "stale_speak":
        return (
            UserStep(text=a.wellness),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="check_mood"),
            DeliverPlayout(),
            *mood,
            *sleep,
            UserStep(text=a.plans),
            ExpectSlot(slot="plans"),
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
            UserStep(text=a.wellness),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="check_mood"),
            DeliverPlayout(),
            FireTimerExpired(timer_id="wait-mood-stale"),
            UserStep(text=a.mood),
            ExpectSlot(slot="mood"),
            ExpectSpeakIntent(intent="check_sleep"),
            DeliverPlayout(),
            *sleep,
            *closing,
        )

    if family == "duplicate_playout":
        return (
            UserStep(text=a.wellness),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="check_mood"),
            DeliverPlayout(),
            DeliverPlayoutDuplicate(),
            *mood,
            *sleep,
            *closing,
        )

    if family == "long_processing":
        return (
            UserStep(text=a.wellness, delayed=True),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="check_mood"),
            DeliverPlayout(),
            *mood,
            *sleep,
            *closing,
        )

    if family == "full_mixed":
        return (
            UserStep(text=a.wellness),
            ExpectSlot(slot="wellness"),
            ExpectSpeakIntent(intent="check_mood"),
            DeliverPlayout(),
            UserStep(text="ага"),
            UserStep(text="Алло?"),
            ExpectSpeakIntent(intent="repair_repeat"),
            DeliverPlayout(),
            UserStep(text=a.mood),
            ExpectSlot(slot="mood"),
            ExpectSpeakIntent(intent="check_sleep"),
            DeliverPlayout(),
            *sleep,
            *closing,
        )

    raise ValueError(f"unknown family: {family}")
