"""Tests for mixed-audio / background media rejection."""
from __future__ import annotations

import unittest

from conversation_system.policy.resolver import IntentResolver
from conversation_system.agenda.manager import AgendaManager
from conversation_system.domain.fsm_types import CallPhase, FsmEvent
from conversation_system.domain.understanding import (
    ConfidenceBand,
    SpeechAct,
    SttReason,
    TurnUnderstanding,
)
from conversation_system.memory.state import ConversationMemory
from conversation_system.turn.analyzer import is_narrative
from conversation_system.turn.dialogue_relevance import (
    looks_like_hostile_or_unintelligible_bleed,
    looks_like_media_bleed,
    looks_like_overheard_speech,
    should_reject_mixed_capture,
)


class DialogueRelevanceTests(unittest.TestCase):
    def test_live_call_video_transcript_is_media_bleed(self):
        text = (
            "Я хотел посмотреть с вами видео очень круто снято "
            "я без термос смотрел трек"
        )
        self.assertTrue(looks_like_media_bleed(text))
        self.assertFalse(
            is_narrative(
                text,
                last_question="Как вы себя чувствуете сегодня?",
            ))

    def test_real_elder_narrative_still_passes(self):
        text = "Внучка приезжала вчера, мы с ней чай пили и разговаривали"
        self.assertFalse(looks_like_media_bleed(text))
        self.assertFalse(is_narrative(text))
        self.assertTrue(
            is_narrative(
                text,
                current_topic="сон",
                on_table=True,
                last_question="Как вы спали прошлой ночью?",
            ))

    def test_narrative_requires_open_question(self):
        """Long speech before any agenda slot is open is NOT a «granddaughter story»."""
        text = (
            "Переживать эту беседную ночь и чередную. "
            "Вер, слышишь? Умираю я плохо мне."
        )
        self.assertFalse(
            is_narrative(text, on_table=False, last_question=""))

    def test_resolver_blocks_narrative_on_video_bleed(self):
        resolver = IntentResolver()
        mem = ConversationMemory(call_id="bleed1")
        mem.last_question = "Как вы себя чувствуете сегодня?"
        agenda = AgendaManager.from_canonical()
        agenda.on_good_path = True
        agenda.question_open = True
        u = TurnUnderstanding(
            raw_text="стейки с индейки с макароншками",
            clean_text="стейки с индейки с макароншками",
            input_reason=SttReason.NONE,
            speech_act=SpeechAct.NARRATIVE,
            topic_signals=(),
            symptom_focus=None,
            answers_last_control=None,
            confidence_band=ConfidenceBand.HIGH,
            is_narrative=True,
            word_count=5,
        )
        out = resolver.resolve(mem, agenda, u, phase=CallPhase.GOOD_PATH)
        self.assertIn(FsmEvent.E_ECHO, out.events)
        self.assertNotIn(FsmEvent.E_NARRATIVE, out.events)

    def test_off_agenda_stt_reason_maps_to_echo(self):
        resolver = IntentResolver()
        mem = ConversationMemory(call_id="bleed2")
        agenda = AgendaManager.from_canonical()
        u = TurnUnderstanding(
            raw_text="",
            clean_text="",
            input_reason=SttReason.OFF_AGENDA,
            speech_act=SpeechAct.EMPTY,
            topic_signals=(),
            symptom_focus=None,
            answers_last_control=None,
            confidence_band=ConfidenceBand.HIGH,
            is_narrative=False,
            word_count=0,
        )
        out = resolver.resolve(mem, agenda, u, phase=CallPhase.GOOD_PATH)
        self.assertEqual(out.events, (FsmEvent.E_ECHO,))

    def test_should_reject_mixed_capture_on_food_monologue(self):
        q = "Как настроение сегодня?"
        text = (
            "Пелисичками, стейки с индейки с макароншками, "
            "либо с кумбри с картошкой отварной"
        )
        self.assertTrue(should_reject_mixed_capture(text, last_question=q))

    def test_media_with_health_prefix_false_positive_stays_rejected(self):
        text = "Смотрите видео и ставьте больше лайков"
        self.assertTrue(
            should_reject_mixed_capture(
                text,
                last_question="Как настроение сегодня?",
            )
        )

    def test_live_call_garbage_stt_rejected(self):
        q = "Как вы себя чувствуете сегодня?"
        self.assertTrue(
            should_reject_mixed_capture("Як как, у пять.", last_question=q))

    def test_overheard_third_person_monologue_rejected(self):
        q = "Как настроение сегодня?"
        text = "Потом он пошёл в магазин и купил хлеб с молоком"
        self.assertTrue(looks_like_overheard_speech(text))
        self.assertTrue(should_reject_mixed_capture(text, last_question=q))

    def test_elder_family_story_not_overheard(self):
        text = "Внучка приезжала вчера, мы с ней чай пили"
        self.assertFalse(looks_like_overheard_speech(text))

    def test_caller_controls_not_rejected_as_off_agenda(self):
        q = "Как настроение сегодня?"
        for text in (
            "а кто вы такая",
            "вы записываете разговор",
            "я не понял вопрос",
            "я не поняла вопрос",
            "я упал и не могу встать",
            "мне трудно дышать",
            "мне плохо, блять",
        ):
            with self.subTest(text=text):
                self.assertFalse(
                    should_reject_mixed_capture(text, last_question=q))


    def test_live_call_profanity_bleed_rejected(self):
        text = (
            "Неплохо. Сука, тебя вообще что ли кикули, нахуй. "
            "Днем вообще нет, неплохо, блять!"
        )
        self.assertTrue(looks_like_hostile_or_unintelligible_bleed(text))
        self.assertTrue(
            should_reject_mixed_capture(
                text, last_question="Как вы себя чувствуете сегодня?"))
        self.assertFalse(
            is_narrative(
                text, last_question="Как вы себя чувствуете сегодня?"))

    def test_bad_wellness_long_answer_not_narrative(self):
        """Live call e804c9ca3163: «плохо мне по самочувству» → not «Как приятно!»."""
        text = "Плохо, вер, плохо мне, по самочувству, плохо."
        self.assertFalse(
            is_narrative(
                text,
                current_topic="самочувствие",
                on_table=True,
                last_question="Вы чувствуете себя плохо?",
            ))
        from conversation_system.turn.analyzer import TurnAnalyzer
        u = TurnAnalyzer().analyze(
            text,
            last_question="Вы чувствуете себя плохо?",
            current_topic="самочувствие",
            agenda_question_open=True,
            confidence=0.9,
        )
        self.assertFalse(u.is_narrative)
        resolver = IntentResolver()
        mem = ConversationMemory(call_id="bad-wellness")
        mem.last_question = "Вы чувствуете себя плохо?"
        agenda = AgendaManager.from_canonical()
        agenda.on_bad_path = True
        out = resolver.resolve(
            mem, agenda, u, phase=CallPhase.BAD_PATH)
        self.assertNotIn(FsmEvent.E_NARRATIVE, out.events)


if __name__ == "__main__":
    unittest.main()
