"""Phase 1 unit tests: TurnAnalyzer, Memory, AgendaManager, Wellness, Pools."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conversation_system.agenda.manager import AgendaManager
from conversation_system.agenda.topics import (
    CANONICAL_AGENDA_TOPICS,
    FAMILY_TOPIC_LABEL,
    TOPIC_BAD_SYMPTOM,
    TOPIC_CLOSING,
    TOPIC_GOOD_PROBE,
    TOPIC_RECORD_NOTIFY,
    TOPIC_WELLNESS,
)
from conversation_system.domain.understanding import (
    FamilyQuestion,
    MemoryPatch,
    SpeechAct,
    SttReason,
)
from conversation_system.domain.wellness import WellnessBand, classify_wellness
from conversation_system.memory.state import ConversationMemory
from conversation_system.reply.pools import (
    GREETING_POOL,
    GOODBYE_CRITICAL_POOL,
    GOODBYE_MEDIUM_POOL,
    TimeOfDay,
    goodbye_pool_for_band,
    pool_counts,
    time_of_day_from_hour,
)
from conversation_system.turn._cleaners import (
    clean_transcript,
    is_phone_social_short,
    short_real_answer,
    wellness_short_answer,
)
from conversation_system.turn._classifiers import (
    is_closing,
    is_closing_direct,
    is_refusal,
    is_text_question,
)
from conversation_system.turn.analyzer import (
    TurnAnalyzer,
    answers_wellness,
    extract_symptom_focus,
    mentions_symptom,
    matches_topic,
    symptom_resolved,
)
from conversation_system.safety.bridge import SafetyBridge
from core.safety_engine import SafetyEngine


class CleanersTests(unittest.TestCase):
    def test_short_real_answer_da_homophone(self):
        self.assertEqual(short_real_answer("та"), "да")

    def test_short_real_answer_net_spsibo(self):
        self.assertEqual(short_real_answer("нет спасибо"), "помощь не нужна")

    def test_allo_is_not_wellness_short(self):
        self.assertEqual(short_real_answer("алло"), "алло")
        self.assertTrue(is_phone_social_short("алло"))
        self.assertIsNone(wellness_short_answer("алло"))
        self.assertFalse(answers_wellness("алло"))

    def test_horosho_is_wellness_short(self):
        self.assertEqual(wellness_short_answer("хорошо"), "всё хорошо")
        self.assertTrue(answers_wellness("хорошо"))

    def test_clean_transcript_drops_english_junk(self):
        self.assertIsNone(clean_transcript("thanks for watching"))

    def test_clean_transcript_keeps_russian_phrase(self):
        self.assertEqual(
            clean_transcript("всё нормально, спасибо"),
            "всё нормально, спасибо",
        )

    def test_clean_transcript_recovers_short_da(self):
        self.assertEqual(clean_transcript("ага"), "да")


class ClassifiersTests(unittest.TestCase):
    def test_closing_direct_davay_poka(self):
        self.assertTrue(is_closing_direct("давай, пока"))

    def test_closing_do_svidaniya(self):
        self.assertTrue(is_closing("до свидания"))

    def test_refusal_net_spasibo(self):
        self.assertTrue(is_refusal("нет, спасибо"))

    def test_refusal_not_bare_net(self):
        self.assertFalse(is_refusal("нет, не сейчас хорошо"))

    def test_text_question_with_mark(self):
        self.assertTrue(is_text_question("Как вы себя чувствуете?"))

    def test_text_question_chto_to_not_question(self):
        self.assertFalse(is_text_question("что-то болит"))


class WellnessTests(unittest.TestCase):
    def test_classify_good(self):
        self.assertEqual(classify_wellness("всё хорошо"), WellnessBand.GOOD)

    def test_classify_bad(self):
        self.assertEqual(classify_wellness("плохо, голова болит"), WellnessBand.BAD)

    def test_classify_critical_upal(self):
        self.assertEqual(classify_wellness("я упал"), WellnessBand.CRITICAL)

    def test_classify_medium(self):
        self.assertEqual(classify_wellness("ну так себе"), WellnessBand.MEDIUM)

    def test_classify_unknown_empty(self):
        self.assertEqual(classify_wellness(""), WellnessBand.UNKNOWN)


class PoolsTests(unittest.TestCase):
    def test_greeting_pool_minimum_five(self):
        self.assertGreaterEqual(len(GREETING_POOL), 5)

    def test_all_greetings_ask_wellness(self):
        for g in GREETING_POOL:
            low = g.lower()
            self.assertTrue(
                "как вы" in low or "как у вас" in low or "как себя" in low,
                msg=g,
            )

    def test_goodbye_pools_minimum_five(self):
        counts = pool_counts()
        self.assertGreaterEqual(counts["goodbye_bad"], 5)
        self.assertGreaterEqual(counts["goodbye_critical"], 5)
        self.assertGreaterEqual(counts["goodbye_medium"], 5)
        self.assertGreaterEqual(counts["record_notify"], 5)

    def test_goodbye_good_by_time_of_day(self):
        morning = goodbye_pool_for_band(WellnessBand.GOOD, hour=8)
        evening = goodbye_pool_for_band(WellnessBand.GOOD, hour=19)
        night = goodbye_pool_for_band(WellnessBand.GOOD, hour=23)
        self.assertTrue(any("дня" in g.lower() or "утра" in g.lower() for g in morning))
        self.assertTrue(any("вечер" in g.lower() for g in evening))
        self.assertTrue(any("ноч" in g.lower() or "снов" in g.lower() for g in night))

    def test_goodbye_critical_fast_close_text(self):
        for phrase in GOODBYE_CRITICAL_POOL:
            low = phrase.lower()
            self.assertIn("запис", low)
            self.assertIn("выздоравл", low)

    def test_goodbye_medium_warns_relatives(self):
        for phrase in GOODBYE_MEDIUM_POOL:
            low = phrase.lower()
            self.assertIn("запис", low)
            self.assertTrue(
                "выздоравл" in low or "родн" in low or "приложен" in low,
                msg=phrase,
            )

    def test_no_promise_to_call_in_pools(self):
        forbidden = ("вызову", "позвоню", "отправлю", "скорую вызову")
        from conversation_system.reply.pools import (
            BAD_SYMPTOM_PROBE_POOL,
            GOOD_PROBE_POOL,
            RECORD_NOTIFY_POOL,
            GOODBYE_BAD_POOL,
        )
        all_phrases = (
            list(GREETING_POOL)
            + list(GOOD_PROBE_POOL)
            + list(BAD_SYMPTOM_PROBE_POOL)
            + list(RECORD_NOTIFY_POOL)
            + list(GOODBYE_BAD_POOL)
            + list(GOODBYE_CRITICAL_POOL)
            + list(GOODBYE_MEDIUM_POOL)
        )
        for phrase in all_phrases:
            low = phrase.lower()
            for bad in forbidden:
                self.assertNotIn(bad, low, msg=f"{bad} in {phrase}")

    def test_time_of_day_buckets(self):
        self.assertEqual(time_of_day_from_hour(8), TimeOfDay.MORNING)
        self.assertEqual(time_of_day_from_hour(14), TimeOfDay.DAY)
        self.assertEqual(time_of_day_from_hour(20), TimeOfDay.EVENING)
        self.assertEqual(time_of_day_from_hour(1), TimeOfDay.NIGHT)


class AnalyzerSpeechActTests(unittest.TestCase):
    def setUp(self):
        self.analyzer = TurnAnalyzer(safety_engine=SafetyEngine())

    def test_empty_echo_reason(self):
        u = self.analyzer.analyze("", reason="echo", confidence=0.9)
        self.assertEqual(u.speech_act, SpeechAct.EMPTY)
        self.assertEqual(u.input_reason, SttReason.ECHO)

    def test_greeting_classification(self):
        u = self.analyzer.analyze("Здравствуйте", confidence=0.9)
        self.assertEqual(u.speech_act, SpeechAct.GREETING)

    def test_alo_phone_check_is_greeting(self):
        for text in ("алло", "ало", "Ало", "алле"):
            u = self.analyzer.analyze(text, confidence=0.9)
            self.assertEqual(
                u.speech_act,
                SpeechAct.GREETING,
                msg=text,
            )

    def test_closing_direct_classification(self):
        u = self.analyzer.analyze("давай пока", confidence=0.9)
        self.assertEqual(u.speech_act, SpeechAct.CLOSING_DIRECT)

    def test_side_question_classification(self):
        u = self.analyzer.analyze("Кто ты?", confidence=0.9)
        self.assertEqual(u.speech_act, SpeechAct.QUESTION)

    def test_symptom_classification(self):
        u = self.analyzer.analyze("голова болит", confidence=0.9)
        self.assertEqual(u.speech_act, SpeechAct.SYMPTOM)
        self.assertTrue(u.mentions_symptom)
        self.assertEqual(u.symptom_focus, "голова")

    def test_narrative_long_story(self):
        text = (
            "Внучка приезжала, мы чай пили на кухне и долго разговаривали "
            "про старые фотографии и соседей"
        )
        u = self.analyzer.analyze(
            text,
            confidence=0.9,
            current_topic="сон",
            agenda_question_open=True,
        )
        self.assertTrue(u.is_narrative)

    def test_low_confidence_band(self):
        u = self.analyzer.analyze("нормально", confidence=0.4)
        self.assertEqual(u.confidence_band.value, "low")

    def test_high_confidence_band(self):
        u = self.analyzer.analyze("нормально", confidence=0.91)
        self.assertEqual(u.confidence_band.value, "high")

    def test_safety_engine_signal_on_upal(self):
        bridge = SafetyBridge(SafetyEngine())
        mem = ConversationMemory(call_id="safety-upal")
        u = self.analyzer.analyze("я упал", confidence=0.9)
        result = bridge.process(mem, u, phase="listen", stt_confidence=0.9)
        self.assertIn(result.verdict.kind, ("possible_red", "confirmed_red"))

    def test_analyzer_does_not_observe_safety_engine(self):
        """TurnAnalyzer must not feed SafetyEngine — only SafetyBridge does."""
        engine = SafetyEngine()
        analyzer = TurnAnalyzer(safety_engine=engine)
        analyzer.analyze(
            "голова болит",
            confidence=0.9,
            last_question="Как настроение?",
        )
        self.assertEqual(engine.state, "NONE")
        self.assertFalse(engine.awaiting_confirmation)

    def test_symptom_resolved_otpustilo(self):
        self.assertTrue(symptom_resolved("стало легче", clearing=True))

    def test_extract_symptom_focus_serdce(self):
        self.assertEqual(extract_symptom_focus("болит сердце"), "сердце")

    def test_matches_topic_son(self):
        self.assertTrue(matches_topic("поспала хорошо", "сон"))

    def test_affirmation_short_da(self):
        u = self.analyzer.analyze("да", confidence=0.9)
        self.assertEqual(u.speech_act, SpeechAct.AFFIRMATION)


class MemoryTests(unittest.TestCase):
    def test_apply_add_fact_dedupes(self):
        mem = ConversationMemory()
        mem.apply(MemoryPatch(add_fact="приняла лекарства"))
        mem.apply(MemoryPatch(add_fact="приняла лекарства"))
        self.assertEqual(mem.facts, ["приняла лекарства"])

    def test_apply_mark_topic_discussed(self):
        mem = ConversationMemory()
        mem.apply(MemoryPatch(mark_topic_discussed="сон"))
        mem.apply(MemoryPatch(mark_topic_discussed="сон"))
        self.assertEqual(mem.topics_discussed, ["сон"])

    def test_apply_wellness_band_field(self):
        mem = ConversationMemory()
        mem.apply(MemoryPatch(set_field={"wellness_band": "good"}))
        self.assertEqual(mem.wellness_band, "good")

    def test_apply_increment_empty_turns(self):
        mem = ConversationMemory()
        mem.apply(MemoryPatch(increment_empty_turns=1))
        mem.apply(MemoryPatch(increment_empty_turns=2))
        self.assertEqual(mem.empty_turn_count, 3)
        mem.apply(MemoryPatch(reset_empty_turns=True))
        self.assertEqual(mem.empty_turn_count, 0)

    def test_apply_set_field_and_flags(self):
        mem = ConversationMemory()
        mem.apply(MemoryPatch(set_field={
            "last_question": "Как спали?",
            "flags": {"help_pending": True, "agenda_question_open": True},
        }))
        self.assertEqual(mem.last_question, "Как спали?")
        self.assertTrue(mem.flags.help_pending)
        self.assertTrue(mem.agenda_question_open)

    def test_family_answer_patch(self):
        mem = ConversationMemory(family_questions=[
            FamilyQuestion(id="q1", text="Как таблетки?"),
        ])
        mem.apply(MemoryPatch(family_answer=("q1", "приняла утром")))
        self.assertEqual(mem.family_questions[0].status, "answered")
        self.assertEqual(mem.family_questions[0].answer, "приняла утром")

    def test_record_turn_increments(self):
        mem = ConversationMemory()
        mem.record_turn(user_text="хорошо", agent_reply="Рада слышать", question="Как дела?")
        self.assertEqual(mem.turn_no, 1)
        self.assertEqual(mem.last_answer, "хорошо")
        self.assertEqual(mem.last_reply, "Рада слышать")

    def test_skill_context_lines(self):
        mem = ConversationMemory(
            topics_discussed=["сон"],
            last_question="Как спали?",
            facts=["приняла лекарства"],
        )
        lines = mem.to_skill_context_lines()
        joined = " ".join(lines)
        self.assertIn("сон", joined)
        self.assertIn("лекарства", joined)

    def test_clone_independent(self):
        mem = ConversationMemory(facts=["a"])
        copy = mem.clone()
        copy.facts.append("b")
        self.assertEqual(mem.facts, ["a"])


class AgendaManagerTests(unittest.TestCase):
    def setUp(self):
        self.agenda = AgendaManager.from_canonical()
        self.analyzer = TurnAnalyzer(safety_engine=SafetyEngine())

    def test_canonical_topic_order_new_spec(self):
        self.assertEqual(
            self.agenda.all_topic_keys(),
            CANONICAL_AGENDA_TOPICS,
        )
        self.assertEqual(self.agenda.current_topic_key(), TOPIC_WELLNESS)

    def test_greeting_text_varied_and_asks_wellness(self):
        g = self.agenda.greeting_text()
        self.assertIn("чувств", g.lower())
        self.assertIn(g, GREETING_POOL)

    def test_good_path_after_wellness(self):
        self.agenda.mark_question_asked()
        u = self.analyzer.analyze("всё хорошо, бодро", confidence=0.9)
        patches = self.agenda.mark_discussed(u)
        self.assertEqual(self.agenda.wellness_band, WellnessBand.GOOD)
        self.assertTrue(self.agenda.on_good_path)
        self.assertEqual(self.agenda.current_topic_key(), TOPIC_GOOD_PROBE)
        self.assertTrue(any(
            p.set_field.get("wellness_band") == "good"
            for p in patches if p.set_field
        ))

    def test_bad_path_after_wellness(self):
        self.agenda.mark_question_asked()
        u = self.analyzer.analyze("плохо, голова болит", confidence=0.9)
        self.agenda.mark_discussed(u)
        self.assertEqual(self.agenda.wellness_band, WellnessBand.BAD)
        self.assertTrue(self.agenda.on_bad_path)
        self.assertEqual(self.agenda.current_topic_key(), TOPIC_BAD_SYMPTOM)

    def test_critical_path_skips_to_record(self):
        self.agenda.mark_question_asked()
        u = self.analyzer.analyze("я упал", confidence=0.9)
        self.agenda.mark_discussed(u)
        self.assertEqual(self.agenda.wellness_band, WellnessBand.CRITICAL)
        self.assertEqual(self.agenda.current_topic_key(), TOPIC_RECORD_NOTIFY)
        self.assertTrue(self.agenda.should_fast_close())

    def test_good_probe_advances_three_times(self):
        self.agenda.mark_question_asked()
        u = self.analyzer.analyze("всё отлично", confidence=0.9)
        self.agenda.mark_discussed(u)
        for answer in ("настроение хорошее", "спала нормально", "пойду в магазин"):
            self.agenda.mark_question_asked()
            u = self.analyzer.analyze(answer, confidence=0.9)
            self.agenda.mark_discussed(u)
        self.assertEqual(self.agenda.current_topic_key(), TOPIC_RECORD_NOTIFY)

    def test_record_notify_then_closing(self):
        self.agenda._seek_topic(TOPIC_RECORD_NOTIFY)
        self.agenda.mark_question_asked()
        u = self.analyzer.analyze("да", confidence=0.9)
        self.agenda.mark_discussed(u)
        self.assertTrue(self.agenda.record_notified)
        self.assertEqual(self.agenda.current_topic_key(), TOPIC_CLOSING)

    def test_closing_text_by_band_good(self):
        self.agenda.wellness_band = WellnessBand.GOOD
        closing = self.agenda.closing_text(hour=10)
        self.assertTrue(
            "дня" in closing.lower() or "утра" in closing.lower()
        )

    def test_closing_text_by_band_bad(self):
        self.agenda.wellness_band = WellnessBand.BAD
        closing = self.agenda.closing_text()
        low = closing.lower()
        self.assertIn("выздоравл", low)
        self.assertIn("запис", low)

    def test_record_notify_no_promise(self):
        text = self.agenda.record_notify_text()
        low = text.lower()
        self.assertIn("запис", low)
        self.assertIn("приложен", low)
        self.assertNotIn("вызову", low)
        self.assertNotIn("позвоню", low)

    def test_family_questions_before_closing(self):
        self.agenda.inject_family_questions([
            {"id": "fq1", "text": "Вы гуляли?", "author": "Маша"},
        ])
        keys = self.agenda.all_topic_keys()
        self.assertIn(FAMILY_TOPIC_LABEL, keys)
        self.assertLess(keys.index(FAMILY_TOPIC_LABEL), keys.index(TOPIC_CLOSING))

    def test_family_mark_discussed_records_answer(self):
        self.agenda.inject_family_questions([
            {"id": "fq1", "text": "Как таблетки?", "author": "Сын"},
        ])
        closing_idx = self.agenda.all_topic_keys().index(TOPIC_CLOSING)
        self.agenda.cursor = closing_idx - 1
        self.agenda.mark_question_asked()
        u = self.analyzer.analyze("приняла утром", confidence=0.9)
        patches = self.agenda.mark_discussed(u)
        self.assertTrue(
            any(p.family_answer == ("fq1", "приняла утром") for p in patches))

    def test_sync_to_memory_includes_wellness(self):
        self.agenda.wellness_band = WellnessBand.GOOD
        self.agenda.on_good_path = True
        patch = self.agenda.sync_to_memory()
        mem = ConversationMemory()
        mem.apply(patch)
        self.assertEqual(mem.wellness_band, "good")

    def test_extract_fact_candidates_includes_band(self):
        self.agenda.wellness_band = WellnessBand.GOOD
        u = self.analyzer.analyze("хорошо", confidence=0.9)
        facts = self.agenda.extract_fact_candidates(u)
        self.assertTrue(any("good" in f for f in facts))

    def test_narrative_defers_agenda(self):
        self.agenda.cursor = 0
        self.agenda.mark_question_asked()
        text = (
            "Вчера внучка приезжала, мы пили чай и смотрели старые альбомы "
            "до позднего вечера"
        )
        u = self.analyzer.analyze(
            text,
            confidence=0.9,
            current_topic=TOPIC_WELLNESS,
            agenda_question_open=True,
        )
        self.assertTrue(self.agenda.should_defer_for_narrative(u))
        patches = self.agenda.mark_discussed(u)
        self.assertTrue(self.agenda.paused)


class IntegrationSmokeTests(unittest.TestCase):
    """End-to-end phase-1 slice: good path through record and closing."""

    def test_good_path_full_flow(self):
        agenda = AgendaManager.from_canonical()
        analyzer = TurnAnalyzer(safety_engine=SafetyEngine())
        memory = ConversationMemory()

        # Turn 0 greeting is outside agenda cursor
        greeting = agenda.greeting_text()
        self.assertIn("чувств", greeting.lower())

        # Wellness → good path
        agenda.mark_question_asked()
        u = analyzer.analyze("всё хорошо", confidence=0.9)
        memory.apply_many(agenda.mark_discussed(u))
        self.assertEqual(agenda.current_topic_key(), TOPIC_GOOD_PROBE)

        # 3 good probes
        for text in ("настроение хорошее", "спала нормально", "пойду гулять"):
            agenda.mark_question_asked()
            u = analyzer.analyze(text, confidence=0.9)
            memory.apply_many(agenda.mark_discussed(u))

        self.assertEqual(agenda.current_topic_key(), TOPIC_RECORD_NOTIFY)

        # Record notify
        agenda.mark_question_asked()
        u = analyzer.analyze("да", confidence=0.9)
        memory.apply_many(agenda.mark_discussed(u))
        self.assertEqual(agenda.current_topic_key(), TOPIC_CLOSING)
        self.assertTrue(agenda.record_notified)

        closing = agenda.closing_text(hour=14)
        self.assertIn("дня", closing.lower())

    def test_bad_path_records_symptoms(self):
        agenda = AgendaManager.from_canonical()
        analyzer = TurnAnalyzer(safety_engine=SafetyEngine())

        agenda.mark_question_asked()
        u = analyzer.analyze("плохо, голова болит", confidence=0.9)
        agenda.mark_discussed(u)
        self.assertEqual(agenda.current_topic_key(), TOPIC_BAD_SYMPTOM)

        agenda.mark_question_asked()
        u = analyzer.analyze("терпимо, но тяжело", confidence=0.9)
        agenda.mark_discussed(u)

        notify = agenda.record_notify_text()
        self.assertIn("приложен", notify.lower())


if __name__ == "__main__":
    unittest.main()
