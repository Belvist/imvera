"""Task-oriented call agenda (2026-08-23): Vera drives the call through a
soft topic checklist instead of random-walking topics like a chat bot.

Covers: agenda order, per-topic verdict notes, safety interjection pause +
resume, and the wrap-up after the last topic."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.dialogue import (  # noqa: E402
    Agent, _clean_llm, _feminize_self, reply_looks_broken)


class TaskAgendaTests(unittest.TestCase):
    def setUp(self):
        self.agent = Agent(llm=None)
        self.agent.start_check_in()

    def test_agenda_walks_in_order_and_notes_topics(self):
        a = self.agent
        # greeting = topic 0 on the table -> a short OK closes it and asks
        # the NEXT topic («настроение»), instantly, no LLM.
        p = a.plan_reply("да, всё хорошо")
        self.assertIn("настроение", p["fallback"].lower())
        p = a.plan_reply("настроение хорошее, спасибо")
        self.assertTrue("сон" in p["fallback"].lower()
                        or "спал" in p["fallback"].lower())
        p = a.plan_reply("спала хорошо")
        self.assertTrue(any(w in p["fallback"].lower() for w in
                            ("план", "займётес", "делать", "проведёте")))
        p = a.plan_reply("всё хорошо, буду ещё читать")
        fb = p["fallback"].lower()
        self.assertTrue(any(w in fb for w in
                            ("родн", "передать", "записать")))
        p = a.plan_reply("хорошо, запишите для них пару слов")
        self.assertIn("записа", p["fallback"].lower())
        for topic in ("самочувствие", "настроение", "сон", "планы",
                      "передать родным"):
            self.assertIn(f"обсуждено: {topic}", a.notes)

    def test_safety_interjection_pauses_then_resumes(self):
        a = self.agent
        p = a.plan_reply("да, всё хорошо")          # closes самочувствие
        self.assertIn("настроение", p["fallback"].lower())
        # symptom mid-agenda: safety control question PAUSES the agenda
        # (pool wording rotates — match any of its care-check phrasings)
        p = a.plan_reply("голова болит и кружится")
        self.assertTrue(any(w in p["fallback"].lower() for w in
                            ("плохо", "нехорошо", "недомогание",
                             "неважно", "помощь")))
        # denial clears the concern (its own scripted follow-up).
        # Pool wording rotates via _pick_not_repeated — accept ANY member of
        # FALSE_ALARM_ACKS (2026-08-24: pool grew 2→4, matching only the
        # first two phrasings made this test flaky ~50% of runs).
        p = a.plan_reply("нет, не сейчас хорошо, отпустило")
        fb = p["fallback"].lower()
        self.assertTrue(any(w in fb for w in (
            "перестраховалась", "извините за тревогу",
            "лишнюю тревогу", "всё обошлось", "что отпустило")),
            f"not a false-alarm ack: {p['fallback']!r}")
        # next short OK RESUMES the agenda where it paused — now «сон»,
        # NOT a restart from «самочувствие»
        p = a.plan_reply("да, всё хорошо")
        self.assertTrue("сон" in p["fallback"].lower()
                        or "спал" in p["fallback"].lower())

    def test_empty_turns_do_not_advance_agenda(self):
        a = self.agent
        for _ in range(3):
            a.plan_reply("")
        self.assertEqual(a._agenda_idx, 0)
        p = a.plan_reply("да, всё хорошо")
        self.assertIn("настроение", p["fallback"].lower())


class VarietyTests(unittest.TestCase):
    """Cross-call variety (2026-08-23): canned questions must NOT repeat
    between consecutive calls in the same process."""

    @staticmethod
    def _run_call():
        a = Agent(llm=None)
        a.start_check_in()
        asked = []
        asked.append(a.plan_reply("да, всё хорошо")["fallback"])    # mood
        asked.append(a.plan_reply("настроение хорошее")["fallback"])  # sleep
        asked.append(a.plan_reply("спала хорошо")["fallback"])      # plans
        asked.append(a.plan_reply("всё хорошо, буду читать")["fallback"])
        return asked

    def test_two_calls_no_repeated_canned_questions(self):
        first = self._run_call()
        second = self._run_call()
        overlap = set(first) & set(second)
        self.assertFalse(overlap,
                         f"canned lines repeated across calls: {overlap}")

    def test_small_pool_degrades_gracefully(self):
        a = Agent(llm=None)
        pool = ["А?", "Б?"]
        for _ in range(10):
            pick = a._pick_not_repeated(pool)
            self.assertIn(pick, pool)

    def test_goodbye_pool_variety_and_no_promises(self):
        # 2026-08-24: the close used to be 2 phrases heard on EVERY call.
        # Product rules: Vera never promises to call/send anything — she
        # only records; at most ONE question mark per line; unique lines.
        self.assertGreaterEqual(len(Agent.GOODBYES), 5)
        self.assertEqual(len(set(Agent.GOODBYES)), len(Agent.GOODBYES))
        forbidden = ("вызову", "позвоню", "отправлю", "предупрежу",
                     "передам", "сообщу")
        for line in Agent.GOODBYES:
            low = line.lower()
            for word in forbidden:
                self.assertNotIn(word, low, f"promise in goodbye: {line}")
            self.assertLessEqual(line.count("?"), 1)
            self.assertNotIn(" ты ", f" {low} ")

    def test_goodbye_no_repeat_across_calls_and_pool_rules(self):
        # 2026-08-24 (run 2): _goodbye() still used plain random.choice —
        # the SAME close could land twice in a row across calls even after
        # the pool grew to 6. It now rotates via _pick_not_repeated.
        first = Agent(llm=None)._goodbye()
        second = Agent(llm=None)._goodbye()
        self.assertNotEqual(first, second,
                            f"same goodbye twice in a row: {first!r}")
        # 2026-08-24 (run 2): REPEAT_REQUESTS widened 4→6; rules hold
        # (unique, warm «вы», no promises, <=1 question mark).
        pool = Agent.REPEAT_REQUESTS
        self.assertGreaterEqual(len(pool), 5)
        self.assertEqual(len(set(pool)), len(pool))
        forbidden = ("вызову", "позвоню", "отправлю", "предупрежу",
                     "передам", "сообщу")
        for line in pool:
            low = line.lower()
            for word in forbidden:
                self.assertNotIn(word, low, f"promise in line: {line}")

    def test_hello_back_pool_variety_and_rules(self):
        # 2026-08-24 (run 3): the scripted hello-back opener was ONE fixed
        # line («И вам здравствуйте!») heard verbatim on every call that
        # opened with «здравствуйте». Now a 6-line pool rotating cross-call
        # via _pick_not_repeated; product rules hold.
        pool = Agent.HELLO_BACKS
        self.assertGreaterEqual(len(pool), 5)
        self.assertEqual(len(set(pool)), len(pool))
        self.assertNotIn("И вам здравствуйте! Как", pool)  # no double lines
        forbidden = ("вызову", "позвоню", "отправлю", "предупрежу",
                     "передам", "сообщу")
        for line in pool:
            low = line.lower()
            for word in forbidden:
                self.assertNotIn(word, low, f"promise in hello-back: {line}")
            self.assertEqual(line.count("?"), 0,
                             f"question mark in opener: {line}")
            self.assertNotIn(" ты ", f" {low} ")
        # two consecutive calls pick different openers (cross-call ring)
        first = Agent(llm=None)._pick_not_repeated(Agent.HELLO_BACKS)
        second = Agent(llm=None)._pick_not_repeated(Agent.HELLO_BACKS)
        self.assertNotEqual(first, second,
                            f"same hello-back twice in a row: {first!r}")

    def test_generic_acks_pool_variety_and_no_promises(self):
        # 2026-08-24: generic acknowledgments were THREE bare phrases
        # («Понимаю.», «Вот как.») picked by plain random.choice — the exact
        # empty nods the system prompt forbids. Pool must be warm, unique,
        # promise-free and rotate via _pick_not_repeated.
        pool = Agent.GENERIC_ACKS
        self.assertGreaterEqual(len(pool), 5)
        self.assertEqual(len(set(pool)), len(pool))
        forbidden = ("вызову", "позвоню", "отправлю", "предупрежу",
                     "передам", "сообщу")
        for line in pool:
            low = line.lower()
            for word in forbidden:
                self.assertNotIn(word, low, f"promise in ack: {line}")
            self.assertLessEqual(line.count("?"), 1)
            self.assertNotIn(" ты ", f" {low} ")
        # rotation actually varies picks within one call (no bare repeats):
        a = Agent(llm=None)
        picks = {a._pick_not_repeated(pool) for _ in range(4)}
        self.assertGreaterEqual(len(picks), 3)

    def test_small_pools_variety_and_no_promises(self):
        # 2026-08-24: silence escalation / false-alarm apology / third-person
        # worry follow-ups each had 2-4 inline lines; now named class pools
        # (>= 3 unique, promise-free, «вы», <=1 question mark) that rotate
        # via _pick_not_repeated.
        forbidden = ("вызову", "позвоню", "отправлю", "предупрежу",
                     "передам", "сообщу")
        for pool in (Agent.QUIET_HOLDS, Agent.FALSE_ALARM_ACKS,
                     Agent.WORRY_FOLLOWUPS):
            self.assertGreaterEqual(len(pool), 3)
            self.assertEqual(len(set(pool)), len(pool))
            for line in pool:
                low = line.lower()
                for word in forbidden:
                    self.assertNotIn(word, low,
                                     f"promise in line: {line}")
                self.assertNotIn(" ты ", f" {low} ")
                self.assertLessEqual(line.count("?"), 1)
        a = Agent(llm=None)
        picks = {a._pick_not_repeated(Agent.QUIET_HOLDS)
                 for _ in range(5)}
        self.assertGreaterEqual(len(picks), 2)

    def test_tapered_silence_ladder_no_drama(self):
        # 2026-08-24: long silence used to spam dramatic lines («Вам
        # плохо?», «Постучите по трубке», «Вы меня пугаете тишиной»).
        # New ladder: calm prompts 1-4, then one-word holds; drama banned.
        a = Agent(llm=None)
        a.start_check_in()
        seen = []
        for _ in range(8):
            p = a.plan_reply("")
            fb = (p.get("fallback") or "").lower()
            self.assertTrue(fb)
            seen.append(fb)
            a.last_intent = None
        for scary in ("плохо?", "постучите", "пугаете", "пугаю"):
            for fb in seen:
                self.assertNotIn(scary, fb,
                                 f"drama survived ladder: {fb}")
        # late turns collapse to short holds: no question marks after turn 4
        late = seen[4:]
        for fb in late:
            self.assertNotIn("?", fb)


class BrokenReplyGuardTests(unittest.TestCase):
    """2026-08-24: deterministic NLG guards against Qwen3 drift seen live."""

    def test_mirror_openers_rejected(self):
        for bad in ("Вы говорите о сейчас? Какое самочувствие?",
                    "Вы сомневаетесь, как справиться. Как спали?",
                    "Рада, что вы хорошо себя чувствуете сегодня?"):
            self.assertTrue(reply_looks_broken(bad), bad)

    def test_latin_leak_rejected(self):
        self.assertTrue(reply_looks_broken("Как вы спать tonight?"))
        self.assertTrue(reply_looks_broken("Всё good, как настроение?"))
        # normal russian passes
        self.assertFalse(reply_looks_broken(
            "Рада слышать! А настроение какое сегодня?"))

    def test_clean_llm_keeps_single_question(self):
        fixed = _clean_llm("Как вы сегодня? Чем заняты?")
        self.assertEqual(fixed.count("?"), 1)
        # non-question tail after the question is dropped too (reply ends
        # with the question naturally)
        self.assertTrue(fixed.startswith("Как вы сегодня"))

    def test_gender_guard_feminizes_self_only(self):
        # live 2026-08-24: «я рад» / masculine slips from Qwen3
        self.assertEqual(
            _clean_llm("Я рад, что всё хорошо."),
            "Я рада, что всё хорошо.")
        self.assertEqual(
            _clean_llm("Я вас понял. Как настроение?"),
            "Я вас поняла. Как настроение?")
        self.assertEqual(
            _clean_llm("Я был занят, но готов помочь."),
            "Я была занята, но готова помочь.")
        # third-person masculine must survive untouched
        self.assertEqual(
            _feminize_self("Внук был рад помочь."),
            "Внук был рад помочь.")
        # no «я» in sentence -> no change
        self.assertEqual(_feminize_self("Рада слышать!"),
                         "Рада слышать!")

    def test_repair_catches_eshche_raz(self):
        # live: «Скажите еще раз пожалуйста» fell through to the LLM and
        # produced «Хорошо, верю» — now it repeats the last reply
        a = Agent(llm=None)
        a.start_check_in()
        a._last_reply = "Как спалось ночью?"
        p = a.plan_reply("Скажите еще раз пожалуйста")
        self.assertIn("Повторяю", p["fallback"])
        self.assertIn("Как спалось ночью?", p["fallback"])
        p2 = a.plan_reply("Жить еще раз, пожалуйста")
        self.assertIn("Повторяю", p2["fallback"])

    def test_greeting_hello_back_scripted_once(self):
        # live: «Здравствуйте!» got non-sequitur «Какой сегодня день?»;
        # now a warm hello-back + pending agenda question
        a = Agent(llm=None)
        a.start_check_in()
        a._agenda_idx = 1          # mood topic is next
        a._agenda_asked = False
        # T002 (2026-08-25): opener now ROTATES from the HELLO_BACKS pool
        # (variety), so assert the MEANING, not one fixed wording: any pool
        # opener + the pending agenda question («настроение»).
        p = a.plan_reply("Здравствуйте!")
        fb = p["fallback"]
        self.assertTrue(any(fb.startswith(h) for h in Agent.HELLO_BACKS),
                        f"opener not from HELLO_BACKS pool: {fb!r}")
        self.assertIn("настроение", fb.lower())
        # second greeting falls through to natural flow (no crash)
        p2 = a.plan_reply("Здравствуйте ещё раз")
        self.assertTrue(p2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
