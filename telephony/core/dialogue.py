"""Dialogue engine: the MVERA state machine and the VERA LLM persona.

Contains the transcript/LLM text cleaners (shared with the STT/LLM adapters)
and the turn-based Agent. No I/O: it programs against duck-typed llm/tts
objects, so the same dialogue layer works with local or cloud providers.
"""

import collections
import os
import random
import re
import threading
from dataclasses import dataclass, field

from core.safety_engine import Observation, SafetyEngine  # noqa: E402

# CROSS-CALL VARIETY (2026-08-23): the Agent instance is recreated per call,
# so a per-instance "last question" memory repeated the same phrases every
# call. This process-level ring remembers recently SPOKEN canned phrases for
# the lifetime of the telephony container and steers _pick_not_repeated away
# from them. maxlen 60 ~= three full calls' worth of canned lines (backup).
_RECENT_SPOKEN = collections.deque(maxlen=60)
_RECENT_LOCK = threading.Lock()


# Whisper often hallucinates on near-silence / very short clips.
# AUDIT FIX: Russian filler/hallucination phrases added — "спасибо", "пока"
# etc. were slipping through and, pre-fix, became phantom user turns.
_JUNK_RE = re.compile(
    r"^(\s*"
    r"(i|the|a|an|and|so|uh|um|huh|what|is it|are you|are you awake|do you)"   # single filler words
    r"[\s.,!?]*"
    r"|"
    r"(thank you|thanks|thanks for watching|thanks for listening|bye|bye-bye|"
    r"goodbye|good bye|hello|hi|next|you know|uh huh|mm hmm|hmm|okay|ok)"
    r"[\s.,!?]*"
    r"|"
    r"(спасибо|пока|пока-пока|всё|все|да|нет|ну|ага|угу|а|о|э|мм|хм|"
    r"привет|здравствуйте|до свидания|хорошо|ладно|понятно|ясно)"
    r"[\s.,!?]*"
    r")$",
    re.IGNORECASE,
)

# If the SAME word repeats >=3 times it's a Whisper noise-hallucination
# ("Next Next Next...", "Bye Bye Bye..."), not real speech.
def _is_repetition(text):
    words = re.findall(r"[а-яёa-z]+", text.lower())
    if len(words) < 3:
        return False
    if len(set(words)) == 1 and len(words) >= 3:
        return True
    return False


# CONVERSATION FIX: real short answers ("да", "нет", "хорошо", "помощь") were
# being discarded by the hallucination junk filter, so the agent answered
# "Повторите, пожалуйста" to perfectly valid one-word replies — the most
# common complaint of a call that "behaves strangely". The audio reaching
# this filter has already been gated by VAD/endpointing (there WAS speech),
# so a canonical short answer is recovered here instead of being dropped.
_SHORT_ANSWER_MAP = {
     "да": "да", "ага": "да", "угу": "да", "конечно": "да", "есть": "да",
     "окей": "да", "ок": "да", "давай": "да", "ус": "да", "ас": "да",
     "естественно": "да", "разумеется": "да", "точно": "да",
     "нет": "нет", "неа": "нет", "не нужно": "помощь не нужна",
     "не надо": "помощь не нужна", "нет спасибо": "помощь не нужна",
     "не хочу": "не хочу", "не стоит": "не стоит",
     "хорошо": "всё хорошо", "всё хорошо": "всё хорошо", "все хорошо": "всё хорошо",
     "нормально": "всё нормально", "норм": "всё нормально",
     "все нормально": "всё нормально", "всё нормально": "всё нормально",
     "неплохо": "всё нормально", "терпимо": "всё терпимо", "так себе": "так себе",
     "плохо": "всё плохо", "не важно": "неважно",
     "неважно": "неважно", "ничего": "ничего не нужно",
     "помощь": "нужна помощь", "помощь нужна": "нужна помощь",
     "помощь требуется": "нужна помощь", "нужна помощь": "нужна помощь",
     "помогите": "нужна помощь", "спасите": "нужна помощь",
     "больно": "мне больно", "болит": "что-то болит",
     "до свидания": "до свидания", "пока": "до свидания",
     "пока пока": "до свидания", "всего доброго": "до свидания",
     "спасибо": "спасибо", "большое спасибо": "спасибо",
     "благодарю": "спасибо", "спс": "спасибо",
     "здравствуйте": "здравствуйте", "привет": "привет",
     "алло": "алло", "да да": "да", "ну да": "да",
     "здорово": "здорово", "отлично": "всё отлично",
     "супер": "всё отлично", "классно": "всё хорошо",
     "улучшилось": "всё хорошо", "снизилось": "всё хорошо",
     "стало легче": "всё хорошо", "перестало": "всё хорошо",
     "свело": "всё хорошо", "пошло": "всё хорошо",
 }

_SHORT_ANSWER_WORDS = frozenset((
     "всё", "все", "да", "ага", "угу", "ок", "окей", "давай", "неплохо",
     "хорошо", "нормально", "норм", "терпимо", "неважно", "плохо",
     "помощь", "требуется", "нужна", "нужно", "надо", "не", "нуждаюсь",
     "нет", "нет спасибо", "не нужно", "не надо", "ничего", "спасибо",
     "есть", "конечно", "неа", "до", "свидания", "пока", "всего",
     "доброго", "большое", "здравствуйте", "привет", "алло", "ну",
     "ус", "ас", "естественно", "разумеется", "точно",
     "не хочу", "не стоит", "больно", "болит", "помогите", "спасите",
     "здорово", "отлично", "супер", "классно", "благодарю", "спс",
     "та", "даа", "дад", "ка", "дау", "дат", "таа", "неет", "нету",
     "ока", "ог", "уга", "гм", "мм", "хорош", "нормал", "помог",
      "приве", "драстующее", "зЗдравствуйте",
     "спасиб", "спасиба", "болшой", "окй", "оке",
     "улучшилось", "снизилось", "перестало", "свело", "пошло",
     "легче", "лучше", "помогло", "ушло", "исчез", "прошла", "ушёл",
     "стало", "куда-то", "наконец-то",
 ))


def short_real_answer(raw):
    """Return the canonical form of a short real answer, or None.

    Only applies to very short (<=3 words) utterances where EVERY word is a
    known answer word (or a known homophone of one). Filters hallucinated
    fragments out while keeping "нет спасибо" and its mishears intact.
    """
    if not raw:
        return None
    t = raw.strip().lower()
    t = re.sub(r"[.,!?…:;]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return None
    words = t.split()
    if len(words) > 3:
        return None
    # Always try a homophone-rewrite pass FIRST: on 8 kHz PSTN audio the
    # canonical word (\"да\") may not even reach us, only the mishear
    # (\"та\" / \"не\"). Rewrite order is: for EACH word apply the
    # homophone table, producing a candidate rewritten phrase; we try that
    # and the original, whichever yields a map hit wins.
    rewritten = [_HOMOPHONE.get(w, w) for w in words]
    canon_t = " ".join(rewritten)
    # Fast path: exact dictionary match on original or rewritten form.
    direct = _SHORT_ANSWER_MAP.get(t) or _SHORT_ANSWER_MAP.get(canon_t)
    if direct:
        return direct
    # Slow path: verify every original/rewritten word is in the known set;
    # this prevents non-words from sneaking through as "short answers".
    allowed = _SHORT_ANSWER_WORDS
    if not all((w in allowed or _HOMOPHONE.get(w) in allowed) for w in words):
        return None
    return _SHORT_ANSWER_MAP.get(canon_t) or _SHORT_ANSWER_MAP.get(t)


# 2026-08-30 UPGRADE: Russian telephone homophone rewrite table. Whisper
# (even large-v3-turbo) on 8 kHz PSTN audio systematically mishears short
# high-frequency Russian words — these cause Vera to hear the wrong intent
# and reply with "Повторите" / go down the wrong branch. Applies ONLY inside
# short_real_answer (short utterances, 1-3 words) where the ambiguity set is
# small enough that a deterministic rewrite is safe.
_HOMOPHONE = {
    "та": "да", "даа": "да", "дад": "да", "дадт": "да",
    "ка": "да", "дау": "да", "дат": "да", "таа": "да",
    "не": "нет", "нету": "нет", "неет": "нет", "неаа": "нет",
    "ока": "ага", "ог": "угу", "агаа": "ага", "уга": "угу",
    "угуу": "угу", "гм": "угу", "мм": "ага",
    "хорош": "хорошо", "хорошо": "хорошо",
    "нормал": "нормально", "нормально": "нормально",
    "помощ": "помощь", "помог": "помощь",
    "приве": "привет", "привет": "привет",
    "драстуйте": "здравствуйте", "драствуйте": "здравствуйте",
    "дравствуйте": "здравствуйте", "зравствуйте": "здравствуйте",
    "спасиб": "спасибо", "спасиба": "спасибо", "болшой": "большое",
    "спокойной": "до свидания", "всегдоброго": "всего доброго",
    "ок": "ок", "окй": "окей", "оке": "окей",
    "пжалста": "пожалуйста",
}


def clean_transcript(text):
    """Clean an STT result: strip junk/hallucinations, recover short real
    answers, return a usable string or None."""
    if not text:
        return None
    t = text.strip()
    # drop very short/fragmentary results
    if len(t) < 2:
        return None
    # drop whisper filler/hallucination phrases
    if _JUNK_RE.match(t):
        short = short_real_answer(t)
        if short:
            return short
        return None
    # drop repeating-word hallucinations ("Next Next Next...")
    if _is_repetition(t):
        return None
    # Homophone post-pass for short real answers: even when an utterance
    # is technically multi-word (\"да да\", \"ок спасибо\"), recover intent
    # before a multi-word branch consumes it.
    words = re.findall(r"[а-яёa-z0-9]+", t.lower())
    if 1 <= len(words) <= 3:
        short = short_real_answer(t)
        if short:
            return short
    # keep multi-word spoken turns
    return t


# ----------------------------------------------------------------------------
# DialogueFSM — the formal dialogue state machine (2026-08-29 rework)
#
# The conversation was previously ONE ~400-line if/elif chain in
# Agent.plan_reply with state scattered across ad-hoc flags (_interrupt,
# _closing_confirm_pending, _help_pending, _agenda_asked, ...). That is what
# cracked: every new rule ("давай пока" should close, "нет спасибо" must be
# honoured) required threading more flags through more branches.
#
# Now the conversation is ONE explicit machine (UML/Harel statechart):
#   * STATE       = the qualitative phase Vera is in;
#   * EVENT       = the classified caller input (verdict-driven);
#   * TRANSITION  = (src, event, guard, action, dst) — the single table below;
#   * EXTENDED STATE = everything else lives on the Agent (agenda index,
#                      confirmations, safety verdict, facts...) and is read by
#                      guards / written by actions.
#
# Engineering rules (enforced by core/fsm.py, see its docstring):
#   guards PURE, RTC dispatch, unhandled event -> explicit safe fallback,
#   "*" sources factor out common behavior (no state explosion).
# ----------------------------------------------------------------------------
from core.fsm import StateMachine  # noqa: E402


class DialogueFSM:
    # ---- states ---------------------------------------------------------
    IDLE = "IDLE"                     # no agenda running (default chat)
    CHECKIN = "CHECKIN"               # service-initiated wellness walk
    SIDE_QUESTION = "SIDE_QUESTION"   # answering the caller's own question
    CLARIFY = "CLARIFY"               # empty/no-speech ladder
    SAFETY_CONFIRM = "SAFETY_CONFIRM"  # possible_red control question
    SAFETY_ACTIVE = "SAFETY_ACTIVE"    # confirmed/uncertain danger
    HELP = "HELP"                     # help request confirmation window
    WORRY = "WORRY"                   # third-person worry
    GOODBYE_CONFIRM = "GOODBYE_CONFIRM"  # one-shot close confirmation
    CLOSING = "CLOSING"               # terminal warm goodbye
    DONE = "DONE"                     # finished

    # public `mode` string each state reports (Agent API compatibility)
    MODE_OF = {
        IDLE: "companion",
        CHECKIN: "check_in",
        SIDE_QUESTION: "companion",
        CLARIFY: "clarify",
        SAFETY_CONFIRM: "safety_confirm",
        SAFETY_ACTIVE: "safety_active",
        HELP: "check_in",
        WORRY: "check_in",
        GOODBYE_CONFIRM: "check_in",
        CLOSING: "closing",
        DONE: "closing",
    }
    # inverse: public mode string -> FSM state (used to restore an interrupt)
    _STATE_OF = {
        "companion": IDLE,
        "check_in": CHECKIN,
        "clarify": CLARIFY,
        "safety_confirm": SAFETY_CONFIRM,
        "safety_active": SAFETY_ACTIVE,
        "closing": CLOSING,
    }
    _MODE_STEP = {"companion": 0, "check_in": 1, "clarify": 2,
                  "safety_confirm": 3, "safety_active": 4, "closing": 5}

    # ---- events (classified caller inputs) ------------------------------
    E_DONE = "done"          # late turn after finish
    E_REPAIR = "repair"      # "повторите, что вы сказали"
    E_DANGER = "danger"      # safety confirmed_red
    E_FROZEN = "frozen"      # safety frozen
    E_GOODBYE = "goodbye"    # explicit closing wording (confirm-eligible)
    E_GOODBYE_DIRECT = "goodbye_direct"  # unambiguous farewell: close now
    E_CONFIRM = "confirm"    # reply while close-confirmation is pending
    E_QUESTION = "question"  # caller asks a question during check-in
    E_HELP = "help"          # help request (explicit or confirming)
    E_WORRY = "worry"        # third-person worry
    E_SYMPTOM = "symptom"    # possible_red
    E_UNCERTAIN = "uncertain"  # uncertain_red
    E_OK = "ok"              # affirmative verdict
    E_HEARD = "heard"        # caller confirms they can hear us (silence ladder)
    E_EMPTY = "empty"        # no usable transcript (silence/lowconf/echo)
    E_GREETING = "greeting"  # caller says hello (first time)
    E_REFUSE = "refuse"      # short polite decline of an offer (P-ACK)
    E_UNKNOWN = "unknown"    # everything else

    def __init__(self):
        self.sm = StateMachine("dialogue", self.IDLE)
        self._build_transitions()
        self._hello_back_done = False   # greeting handler fires once per call
        self._empty_turns = 0
        self._echo_turns = 0
        self._dispatch_depth = 0
        self._refused_offer = False     # P-CLOSE2: honoured decline -> fast close
        # per-dispatch transient (set by dispatch, read by guards)
        self._last_text = None
        self._last_reason = None

    # ---- state access ---------------------------------------------------
    @property
    def state(self):
        return self.sm.state

    def mode(self, agent):
        return self.MODE_OF.get(self.sm.state, "companion")

    def step(self, agent):
        return self._MODE_STEP.get(self.mode(agent), 0)

    def reset(self, agent):
        self.sm.state = self.IDLE
        self._hello_back_done = False
        self._empty_turns = 0
        self._echo_turns = 0
        self._dispatch_depth = 0
        self._refused_offer = False

    # ---- dispatch -------------------------------------------------------
    MAX_DISPATCH_DEPTH = 4   # re-dispatch (resume/repair/confirm) nesting cap

    def dispatch(self, agent, text, reason=None, verdict=None, append=True):
        """Classify the caller input and run the machine (RTC).

        ``verdict``/``append`` are for INTERNAL re-dispatch (resume after an
        interrupt / after a close-confirmation): the safety engine must not
        observe the same text twice, and the history must not record the
        same turn twice."""
        # TERMINAL GUARD: a late/duplicate turn after finish must not mutate
        # the history (matches the pre-rework order — done-check first).
        if append and text and not agent.done:
            agent.memory.append(text)
            agent.llm_history.append(("user", text))
        # DEPTH GUARD (2026-08-29): actions may re-dispatch the SAME turn
        # (repair, side-question resume, close-confirmation continue). A
        # future mis-edit could make that loop forever — cap the nesting so
        # the machine degrades to a warm ack instead of blowing the stack.
        depth = getattr(self, "_dispatch_depth", 0)
        if depth >= self.MAX_DISPATCH_DEPTH:
            return {"text": text,
                    "intent": "откликнуться на сказанное коротко",
                    "fallback": agent._pick_not_repeated(agent.GENERIC_ACKS)}
        self._dispatch_depth = depth + 1
        try:
            ev, verdict = self._classify(agent, text, reason, verdict)
            self._last_text = text
            self._last_reason = reason
            self._last_verdict = verdict
            # The machine is TOTAL: a ("*","*") catch-all in the table turns
            # any unhandled pair into an explicit safe ack (never silent,
            # never an exception on the hot path).
            return self.sm.handle(agent, ev)
        finally:
            self._dispatch_depth -= 1

    # ---- classifier: raw input -> one event -----------------------------
    def _classify(self, agent, text, reason, verdict=None):
        if agent.done:
            return self.E_DONE, verdict
        if text and re.search(
                r"(повторите|повтори|что ты сказала|что вы сказали|"
                r"как вы сказали|ещё раз|еще раз|скажите снова|"
                r"не расслышал|не понял)", text.lower()):
            return self.E_REPAIR, verdict
        # question-over-check-in (read.md #16) is decided BEFORE the safety
        # verdict, matching the pre-rework order. While answering a side
        # question the caller may keep asking — stay in the answer phase.
        if self.sm.state in (self.CHECKIN, self.SIDE_QUESTION) \
                and _is_text_question(text):
            return self.E_QUESTION, verdict
        if verdict is None:
            verdict = agent.safety.observe(Observation(
                question=getattr(agent, "_last_question", None),
                raw_text=text,
                confidence=getattr(agent, "_last_confidence", None),
                source="stt",
            ))
        kind = verdict.kind
        if kind == "frozen":
            return self.E_FROZEN, verdict
        if kind == "confirmed_red":
            return self.E_DANGER, verdict
        # GOODBYE_CONFIRM first: while we are asking «Вы прощаетесь?» ANY
        # reply is a confirmation/denial (a «нет спасибо» there means "I am
        # NOT leaving" — continue), never an offer-refusal that would arm
        # the fast close.
        if self.sm.state == self.GOODBYE_CONFIRM and text:
            if _is_closing_direct(text):
                return self.E_GOODBYE_DIRECT, verdict
            if _is_closing(text):
                return self.E_GOODBYE, verdict
            # in the confirmation window, a bare «пока»/«да»/«ага» IS the
            # confirmation (the caller already said goodbye once)
            if re.fullmatch(r"\s*(пока|да|ага|угу|конечно)[\s.,!?]*",
                            text, re.IGNORECASE):
                return self.E_GOODBYE_DIRECT, verdict
            return self.E_CONFIRM, verdict
        # P-ACK (2026-08-29): a short polite decline ("нет спасибо", "не
        # надо", "ничего") is its OWN event — honoured, never re-interpreted
        # as help/affirmative. Classified BEFORE the safety verdict branches
        # that would route it into a generic/help reply.
        if text and _is_refusal(text):
            return self.E_REFUSE, verdict
        # E_HEARD (2026-08-29): the caller answers the silence ladder /
        # anchor with a presence confirmation («да, я тебя слышу»). Real
        # call ca81bc3ac2c7 showed this was answered with a canned «Рада,
        # что вы говорите» and the conversation stalled. It is a signal to
        # RETURN to the topic, not a generic ack.
        if text and re.search(
                r"(я\s+(тебя|вас)\s+(слышу|слышала)|"
                r"слышу\s+(тебя|вас)\b|слышно\s+(хорошо|нормально)|"
                r"(да|ага|угу)[,\s]*(слышу|слышно)|вы\s+меня\s+слышите)",
                text.lower()):
            return self.E_HEARD, verdict
        # P-CLOSE1: an UNAMBIGUOUS farewell closes now (no re-confirm);
        # a confirm-eligible goodbye goes through the one-shot guard.
        # P-CLOSE2: after a honoured refusal a lone «пока» is a leave, not
        # a «пока нет» — close directly.
        if text and (_is_closing_direct(text) or
                     (self._refused_offer
                      and re.fullmatch(r"\s*пока[\s.,!?]*", text,
                                       re.IGNORECASE))):
            return self.E_GOODBYE_DIRECT, verdict
        if text and _is_closing(text):
            return self.E_GOODBYE, verdict
        # BARE «пока» (2026-08-29): the most common farewell of elderly
        # callers, but not in the confirm-eligible regex (to protect «пока
        # нет»). In normal conversation it is a goodbye — route it through
        # the one-shot confirmation so a second «пока» closes.
        if text and re.fullmatch(r"\s*пока[\s.,!?]*", text, re.IGNORECASE):
            return self.E_GOODBYE, verdict
        if self.sm.state == self.GOODBYE_CONFIRM and text:
            return self.E_CONFIRM, verdict
        # help confirmation window: consume the armed flag once per turn
        help_was_pending = getattr(agent, "_help_pending", False)
        agent._help_pending = False
        if not self._hello_back_done and text and re.search(
                r"(здравствуйте|добрый день|доброе утро|добрый вечер)",
                text.lower()):
            return self.E_GREETING, verdict
        if kind == "possible_red":
            return self.E_SYMPTOM, verdict
        if kind == "uncertain_red":
            return self.E_UNCERTAIN, verdict
        if kind == "help_request":
            if ("запрос помощи" in (verdict.notes or ())) or help_was_pending:
                return self.E_HELP, verdict
            # a bare "да"/"конечно" in free conversation is not help
            return self.E_UNKNOWN, verdict
        if kind == "third_person":
            return self.E_WORRY, verdict
        if kind == "no_speech":
            return self.E_EMPTY, verdict
        if kind == "ok":
            return self.E_OK, verdict
        return self.E_UNKNOWN, verdict

    # ---- guards (PURE predicates over extended state) -------------------
    @staticmethod
    def _g_short(ctx, ev):
        t = ctx._fsm._last_text or ""
        return bool(t) and len(t.split()) <= 3

    @staticmethod
    def _g_short_unconfirmed(ctx, ev):
        """A SHORT goodbye that has not already been confirmed (and the
        caller has not already declined an offer) — confirm it once before
        closing. A refused caller or a re-confirmed goodbye closes directly."""
        if ctx._fsm._refused_offer:
            return False
        if getattr(ctx, "_closing_confirmed", False):
            return False
        t = ctx._fsm._last_text or ""
        return bool(t) and len(t.split()) <= 3

    @staticmethod
    def _g_confirmed(ctx, ev):
        t = (ctx._fsm._last_text or "").lower()
        return _is_closing(t) or bool(re.search(
            r"\b(да|ага|угу|конечно)\b", t))

    @staticmethod
    def _g_resume_phase(ctx, ev):
        inter = getattr(ctx, "_interrupt", None)
        return inter is not None and inter.get("phase") == "resume"

    @staticmethod
    def _g_clearing(ctx, ev):
        return bool(getattr(ctx, "_clearing", False))

    # ---- actions (mutate extended state, return the reply plan) --------
    def _a_unhandled(self, agent, ev):
        """TOTAL-machine catch-all (2026-08-29): reached only when no
        specific (state, event) transition matched — the pairs the
        classifier can NOT produce (e.g. E_CONFIRM outside GOODBYE_CONFIRM,
        E_QUESTION outside CHECKIN/SIDE_QUESTION). Never silent, never an
        exception on the hot path: log the unexpected pair and reply warm."""
        print("[dialogue-fsm] UNHANDLED event=%s state=%s -> warm ack"
              % (ev, self.sm.state), flush=True)
        return {"text": agent._fsm._last_text,
                "intent": "откликнуться на сказанное коротко",
                "fallback": agent._pick_not_repeated(agent.GENERIC_ACKS)}

    def _a_done(self, agent, ev):
        return {"text": agent._fsm._last_text, "intent": None,
                "fallback": agent._goodbye(), "terminal": True}

    def _a_frozen(self, agent, ev):
        return {"text": agent._fsm._last_text, "intent": None,
                "fallback": agent._goodbye(), "terminal": True}

    def _a_danger(self, agent, ev):
        agent.status = "alert"
        agent._note("обнаружена опасность")
        agent._finish()
        return {"text": agent._fsm._last_text, "terminal": True,
                "intent": "успокоить, попросить оставаться на месте, "
                          "сказать что записала, спросить нужна ли "
                          "скорая; ничего не обещать вызвать",
                "fallback": random.choice([
                    "Останьтесь на месте. Я всё записала, близкие "
                    "увидят. Вам нужна скорая?",
                    "Не вставайте. Я отметила, родные узнают. "
                    "Дождитесь помощи.",
                ])}

    def _a_repair(self, agent, ev):
        last = getattr(agent, "_last_reply", None)
        if last:
            return {"text": agent._fsm._last_text, "intent": None,
                    "fallback": f"Повторяю: {last}"}
        # nothing to repeat -> fall through to normal processing
        return self.dispatch(agent, agent._fsm._last_text,
                             agent._fsm._last_reason,
                             verdict=self._last_verdict, append=False)

    def _a_side_start(self, agent, ev):
        # Done → any question after wrap-up is actually closing, not side
        if getattr(agent, "_agenda_done", False):
            agent._finish()
            return {"text": agent._fsm._last_text, "terminal": True,
                    "intent": "тепло попрощаться и сообщить итог",
                    "fallback": agent._goodbye_report()}
        agent._interrupt = {
            "resume_mode": "check_in",
            "agenda_asked": agent._agenda_asked,
            "phase": "answer",
        }
        agent._agenda_asked = False
        return {"text": agent._fsm._last_text,
                "intent": "прямо и тепло ответить на вопрос или реплику "
                          "собеседника своими словами, коротко",
                "fallback": agent._pick_not_repeated(agent.GENERIC_ACKS)}

    def _a_side_answer(self, agent, ev):
        if getattr(agent, "_agenda_done", False):
            agent._finish()
            return {"text": agent._fsm._last_text, "terminal": True,
                    "intent": "тепло попрощаться и сообщить итог",
                    "fallback": agent._goodbye_report()}
        agent._interrupt = dict(agent._interrupt, phase="answer")
        agent._agenda_asked = False
        return {"text": agent._fsm._last_text,
                "intent": "прямо и тепло ответить на вопрос или реплику "
                          "собеседника своими словами, коротко",
                "fallback": agent._pick_not_repeated(agent.GENERIC_ACKS)}

    def _a_side_resume(self, agent, ev):
        inter = agent._interrupt
        agent._interrupt = None
        # resume_mode stores the MODE string ("check_in"); map it back to the
        # FSM state (the stored value is part of the Agent test contract).
        resume_state = self._STATE_OF.get(inter.get("resume_mode"))
        if resume_state:
            self.sm.state = resume_state
        agent._agenda_asked = bool(inter.get("agenda_asked")) if inter \
            else agent._agenda_asked
        # process THIS turn as the topic answer (no re-append, no re-observe)
        return self.dispatch(agent, agent._fsm._last_text,
                             agent._fsm._last_reason,
                             verdict=self._last_verdict, append=False)

    def _a_side_reask(self, agent, ev):
        agent._interrupt = dict(agent._interrupt, phase="resume")
        q = agent._agenda_question() or agent._wrap_up_question()
        agent._last_question = q
        return {"text": agent._fsm._last_text, "intent": None,
                "fallback": ("Пожалуйста. Возвращаясь к нашему "
                             "разговору — " + q)}

    def _a_confirm_ask(self, agent, ev):
        agent._closing_confirm_pending = True
        agent._closing_confirmed = True
        q = ("Вы сейчас прощаетесь? Скажите «да» — и я пожелаю вам "
             "добра, или расскажите, как вы себя чувствуете.")
        agent._last_question = q
        return {"text": agent._fsm._last_text, "intent": None, "fallback": q}

    def _a_confirm_no(self, agent, ev):
        agent._closing_confirm_pending = False
        agent._closing_confirmed = False
        # the caller was NOT leaving — process the reply normally
        self.sm.state = self.CHECKIN
        return self.dispatch(agent, agent._fsm._last_text,
                             agent._fsm._last_reason,
                             verdict=self._last_verdict, append=False)

    def _a_help(self, agent, ev):
        agent._note("требуется помощь")
        agent.status = "attention"
        agent._help_pending = True
        q = agent._ask_help()
        agent._last_question = q
        return {"text": agent._fsm._last_text,
                "intent": "сказать, что записала просьбу о помощи — "
                          "близкие её увидят, спросить, что именно "
                          "нужно; не обещать ничего сделать самой",
                "fallback": q}

    def _a_worry(self, agent, ev):
        agent._note("беспокойство о близких")
        agent.status = "attention"
        agent._help_pending = True
        q = agent._pick_not_repeated(agent.WORRY_FOLLOWUPS)
        agent._last_question = q
        return {"text": agent._fsm._last_text,
                "intent": "узнать больше о беспокойстве собеседника; "
                          "записи видят близкие, ничего не обещать "
                          "передавать самому",
                "fallback": q}

    def _a_symptom(self, agent, ev):
        agent._note("плохое самочувствие")
        agent.status = "attention"
        agent._clearing = True
        # Wellness advance only on positive signals — BAD_WORDS
        # ("плохо" and similar) must still trigger the symptom follow-up.
        # Also require an explicit improvement cue (not just any symptom
        # mention) so "отлично, но болела голова" stays in symptom mode.
        _improves = any(w in agent._fsm._last_text.lower()
                        for w in ("легче", "лучше", "помогло", "ушло",
                                  "исчез", "прошла", "ушёл", "стало",
                                  "улучшилось", "снизилось", "перестало",
                                  "свело", "снова", "пошло", "куда-то",
                                  "лишь бы", "наконец-то"))
        if agent._answers_wellness(agent._fsm._last_text) \
                and not any(w in agent._fsm._last_text.lower()
                            for w in BAD_WORDS) \
                and _improves:
            return self._a_ok(agent, ev)
        q = agent._pick_not_repeated(agent.SYMPTOM_CHECKS)
        agent._last_question = q
        # SYMPTOM GOAL (2026-08-29): the caller named a concrete problem
        # («болела голова», «кружится») — the intent MUST ask about THAT
        # symptom, not drift into a generic «записать для близких».
        t = (agent._fsm._last_text or "").lower()
        symptom = next((w for w in re.findall(
            r"(голов|болит|болела|кружится|кружит|давит|тошнит|"
            r"колет|ноет|тяжесть|шум)", t) if w), None)
        if symptom:
            intent = (f"уточнить про названный симптом "
                      f"(«{symptom}»): как сейчас {symptom}, когда "
                      f"началось; не пугать, не обещать вызвать помощь")
        else:
            intent = ("мягко уточнить самочувствие, не пугая человека; "
                      "не обещать вызвать помощь")
        return {"text": agent._fsm._last_text,
                "intent": intent,
                "fallback": q}

    def _a_uncertain(self, agent, ev):
        agent._note("самочувствие не подтверждено")
        agent.status = "attention"
        text = agent._fsm._last_text or ""
        # After an open symptom question, never «Не буду настаивать…» —
        # re-ask about the body (live 8f650 «Супер, спасибо»).
        if agent._clearing or agent._mentions_symptom(text):
            return self._a_symptom(agent, ev)
        q = agent._pick_not_repeated(agent.STAY_OBSERVANT_ACKS)
        agent._last_question = q
        return {"text": agent._fsm._last_text,
                "intent": "успокоить и продолжить разговор, не настаивая; "
                          "не обещать вызывать помощь",
                "fallback": q}

    def _a_false_alarm(self, agent, ev):
        agent.status = "ok"
        agent._clearing = False
        # Do NOT advance agenda here — keep the paused topic (e.g. mood) so
        # the next positive "да, всё хорошо" can resume it to sleep. Just
        # acknowledge the clearing and re-ask the CURRENT agenda question
        # instead of re-asking the same symptom "Как она сейчас?" which
        # caused the 3× repeat in live call 57a80279cbe8.
        base_ack = agent._pick_not_repeated(agent.FALSE_ALARM_ACKS)
        if "?" in base_ack:
            base_ack = base_ack.split("?")[0].split("Как")[0].strip()
            if not base_ack.endswith("."):
                base_ack += "."
        q = agent._ask_task() or agent._wrap_up_question()
        fb = f"{base_ack} {q}" if q else base_ack
        agent._last_question = fb
        return {"text": agent._fsm._last_text, "intent": None, "fallback": fb}

    def _a_greeting(self, agent, ev):
        agent._fsm._hello_back_done = True
        q = (agent._ask_task()
             or (agent._wrap_up_question()
                 if agent._agenda_topic() is None
                 else "Как вы меня слышите?"))
        return {"text": agent._fsm._last_text, "intent": None,
                "fallback": "{} {}".format(
                    agent._pick_not_repeated(agent.HELLO_BACKS), q)}

    def _a_heard(self, agent, ev):
        """E_HEARD (2026-08-29): the caller confirmed they can hear us on
        the silence ladder/anchor. Warm ack and RETURN to the current topic
        — never a generic canned «рада, что вы говорите», never another
        «хорошо или плохо» demand."""
        ack = agent._pick_not_repeated(agent.HEARD_ACKS)
        q = (agent._ask_task() or agent._wrap_up_question()
             or agent._agenda_question())
        agent._last_question = q
        return {"text": agent._fsm._last_text, "intent": None,
                "fallback": "{} {}".format(ack, q)}

    def _a_refuse(self, agent, ev):
        """P-ACK/P-CLOSE2 (2026-08-29): honour a short polite decline —
        acknowledge WITHOUT pushing another question (this was the top
        complaint of the live post-mortem: «нет спасибо» -> «Да, конечно,
        добавьте что-нибудь?»). Also arms the fast close: a following
        goodbye (or silence) ends the call without re-confirming."""
        agent._fsm._refused_offer = True
        agent._extract_facts(agent._fsm._last_text)
        fb = agent._pick_not_repeated(agent.REFUSAL_ACKS)
        agent._last_question = fb
        return {"text": agent._fsm._last_text, "intent": None, "fallback": fb}

    def _a_empty(self, agent, ev):
        # P-ANCHOR (2026-08-29): silence right after a honoured decline or a
        # pending close-confirmation means the caller has stopped talking —
        # end the call, do NOT demand "хорошо или плохо" from a person who
        # already said goodbye.
        if agent._fsm._refused_offer \
                or getattr(agent, "_closing_confirmed", False):
            agent._finish()
            return {"text": agent._fsm._last_text, "intent": None,
                    "fallback": agent._goodbye_report(), "terminal": True}
        return agent._silence_flow(agent._fsm._last_text,
                                   agent._fsm._last_reason)

    def _a_close(self, agent, ev):
        agent._finish()
        return {"text": agent._fsm._last_text, "terminal": True,
                "intent": "тепло попрощаться и коротко сообщить итог: что "
                          "записала для близких (или что сегодня записей нет, "
                          "но отметила что всё хорошо) — без обещаний, одно "
                          "предложение отчёта + тёплое пожелание",
                "fallback": agent._goodbye_report()}

    def _a_ok(self, agent, ev):
        agent._extract_facts(agent._fsm._last_text)
        text = agent._fsm._last_text or ""
        topic = agent._agenda_topic()
        if agent.status == "unknown":
            agent.status = "ok"
        # NARRATIVE GUARD: a long off-topic story is answered on content,
        # never force-advanced.
        if not agent._current_is_family() \
                and len(text.split()) >= 6 \
                and not agent._matches_topic(text):
            agent._agenda_asked = False
            return {"text": text,
                    "intent": "тепло откликнуться на рассказ человека и "
                              "задать один короткий вопрос по его "
                              "содержанию",
                    "fallback": agent._pick_not_repeated(
                        agent.GENERIC_ACKS)}
        is_short = bool(short_real_answer(text)) and len(text.split()) <= 3
        on_table = agent._agenda_asked and topic is not None
        reached = not on_table and topic is not None \
            and agent._answers_wellness(text) \
            and len(text.split()) <= 2
        if on_table or reached:
            finished = agent._agenda_advance(text)
            if finished:
                fb = agent._wrap_up_question()
                agent._last_question = fb
                return {"text": text,
                        "intent": "тёпло подвести итог: всё записала "
                                  "для близких; спросить, не хочет ли "
                                  "человек что-то ещё добавить",
                        "fallback": fb}
            if is_short and on_table:
                q = agent._ask_task() or agent._wrap_up_question()
                agent._last_question = q
                if agent._current_is_family():
                    fb = q
                else:
                    fb = "{} {}".format(
                        agent._pick_not_repeated(agent.BRIDGES), q)
                return {"text": text, "intent": None, "fallback": fb}
            nxt = agent._agenda_topic()
            q = (agent._ask_task() or agent._wrap_up_question())
            agent._last_question = q
            if agent._current_is_family():
                goal = ("тёпло откликнуться на сказанное, затем передать "
                        "вопрос от близких дословно: "
                        f"«{agent._agenda_question()}» — только этот один "
                        "вопрос")
            elif nxt:
                goal = (f"порадоваться, откликнуться на детали сказанного "
                        f"и одним естественным вопросом перейти к теме "
                        f"«{nxt}»")
            else:
                goal = "порадоваться и откликнуться на детали сказанного"
            return {"text": text, "intent": goal, "fallback": q}
        # Agenda done → next turn must close with report, not generic ack
        if getattr(agent, "_agenda_done", False) or topic is None:
            agent._finish()
            return {"text": text, "terminal": True,
                    "intent": "тепло попрощаться и коротко сообщить итог",
                    "fallback": agent._goodbye_report()}
        fb = "{} {}".format(
            agent._pick_not_repeated(agent.GENERIC_ACKS),
            agent._pick_not_repeated(agent.WRAP_OPENERS))
        agent._last_question = fb
        return {"text": text, "intent": None, "fallback": fb}

    def _a_unknown(self, agent, ev):
        agent._extract_facts(agent._fsm._last_text)
        text = agent._fsm._last_text or ""
        # Open control question + non-answer (thanks/backchannel) → re-ask
        # the body, not a generic ack (live 8f650 «Супер, спасибо»).
        if agent._clearing:
            return self._a_symptom(agent, ev)
        # Symptom anywhere in the turn beats agenda topic (live 9b01:
        # «голова болела» on «передать родным» must ask about the head).
        if agent._mentions_symptom(text):
            return self._a_symptom(agent, ev)
        topic = agent._agenda_topic()
        # Done → close, not generic ack (fixes postmortem no-goodbye)
        if getattr(agent, "_agenda_done", False) or topic is None:
            agent._finish()
            return {"text": text, "terminal": True,
                    "intent": "тепло попрощаться и коротко сообщить итог",
                    "fallback": agent._goodbye_report()}
        words = len(text.split())
        on_table = agent._agenda_asked and topic is not None
        if not on_table and words >= 4:
            agent._agenda_asked = False
            if words >= 6:
                return {"text": text,
                        "intent": "тепло откликнуться на рассказ человека и "
                                  "задать один короткий вопрос по его "
                                  "содержанию",
                        "fallback": agent._pick_not_repeated(
                            agent.GENERIC_ACKS)}
            q = agent._ask_task()
            agent._last_question = q
            if agent._current_is_family():
                g = ("откликнуться на сказанное и передать вопрос от "
                     f"близких дословно: «{agent._agenda_question()}»")
            elif topic is not None:
                g = (f"откликнуться на детали и одним вопросом узнать про "
                     f"«{topic}»")
            else:
                g = ("откликнуться на детали и задать один уточняющий "
                     "вопрос по теме")
            return {"text": text, "intent": g, "fallback": q}
        # On-table answer even if verdict unknown → advance agenda ONLY when
        # it looks like an answer to the current question (matches topic) OR
        # when the topic is "передать родным" (any answer counts as
        # "не хочу передавать" and must advance to wrap-up, otherwise
        # "Ну, две недели" (answer to a follow-up about внук) would stall
        # forever — postmortem 1e13). Long off-topic narrative ("Внучка
        # приезжала...") for "настроение" must NOT force — agenda stays.
        if on_table:
            is_match = agent._matches_topic(text)
            if topic == "самочувствие":
                is_match = is_match or agent._answers_wellness(text)
            # "передать родным" is an offer: any answer advances
            is_offer = topic == "передать родным"
            if is_match or is_offer:
                finished = agent._agenda_advance(text)
                if finished:
                    fb = agent._wrap_up_question()
                    agent._last_question = fb
                    return {"text": text,
                            "intent": "тёпло подвести итог: всё записала "
                                      "для близких; спросить, не хочет ли "
                                      "человек что-то ещё добавить",
                            "fallback": fb}
                nxt = agent._agenda_topic()
                q = agent._ask_task() or agent._wrap_up_question()
                agent._last_question = q
                if agent._current_is_family():
                    goal = ("тёпло откликнуться на сказанное, затем передать "
                            "вопрос от близких дословно: "
                            f"«{agent._agenda_question()}» — только этот один "
                            "вопрос")
                elif nxt:
                    goal = (f"порадоваться, откликнуться на детали сказанного "
                            f"и одним естественным вопросом перейти к теме "
                            f"«{nxt}»")
                else:
                    goal = "порадоваться и откликнуться на детали сказанного"
                return {"text": text, "intent": goal, "fallback": q}
            # off-topic (even short "да, всё хорошо" for mood) → keep topic
            agent._agenda_asked = False
            return {"text": text,
                    "intent": "тепло откликнуться на рассказ человека и "
                              "задать один короткий вопрос по его "
                              "содержанию",
                    "fallback": agent._pick_not_repeated(agent.GENERIC_ACKS)}
        if topic is not None and not agent._agenda_asked:
            q = agent._ask_task()
            agent._last_question = q
            if agent._current_is_family():
                intent = ("откликнуться и передать вопрос от близких "
                          f"дословно: «{agent._agenda_question()}»")
            elif topic is not None:
                intent = ("откликнуться и одним естественным вопросом "
                          f"узнать про «{topic}»")
            else:
                intent = "откликнуться и задать один уточняющий вопрос"
            return {"text": text, "intent": intent, "fallback": q}
        if topic is not None:
            return {"text": text,
                    "intent": "откликнуться на детали сказанного и задать "
                              "один уточняющий вопрос по теме "
                              f"«{topic}» (это цель звонка)",
                    "fallback": agent._pick_not_repeated(agent.GENERIC_ACKS)}
        return {"text": text,
                "intent": "откликнуться на детали сказанного и задать "
                          "один естественный уточняющий вопрос по теме",
                "fallback": agent._pick_not_repeated(agent.GENERIC_ACKS)}

    # ---- the single transition table ------------------------------------
    # (src, event, guard, dst, action). "*" = any state/event. First match
    # wins; guards are pure. Order matters only where guards overlap.
    def _build_transitions(self):
        sm = self.sm
        add = sm.add
        # terminal / cross-cutting (factored via "*" source — no repetition)
        add("*", self.E_DONE, self.DONE, self._a_done,
            name="any/done")
        add("*", self.E_FROZEN, self.DONE, self._a_frozen,
            name="any/frozen")
        add("*", self.E_DANGER, self.SAFETY_ACTIVE, self._a_danger,
            name="any/danger")
        add("*", self.E_REPAIR, None, self._a_repair, name="any/repair")
        # presence confirmation on the silence ladder -> return to the topic
        add("*", self.E_HEARD, self.CHECKIN, self._a_heard, name="any/heard")
        # side-question interrupt (caller asks during the wellness walk)
        add(self.CHECKIN, self.E_QUESTION, self.SIDE_QUESTION,
            self._a_side_start, name="checkin/question")
        add(self.SIDE_QUESTION, self.E_QUESTION, self.SIDE_QUESTION,
            self._a_side_answer, name="side/question")
        # an EMPTY turn mid-interrupt: the silence ladder runs but the
        # interrupt STAYS ACTIVE in "answer" phase (position untouched) —
        # the next real reply resumes it. Must precede the catch-all reask.
        add(self.SIDE_QUESTION, self.E_EMPTY, self.SIDE_QUESTION,
            self._a_empty, name="side/empty")
        add(self.SIDE_QUESTION, "*", self.CHECKIN, self._a_side_resume,
            guard=self._g_resume_phase, name="side/resume")
        add(self.SIDE_QUESTION, "*", self.SIDE_QUESTION, self._a_side_reask,
            name="side/reask")
        # goodbye: one-shot confirmation then real close (P-CLOSE)
        add(self.GOODBYE_CONFIRM, self.E_GOODBYE, self.CLOSING,
            self._a_close, guard=self._g_short, name="confirm/goodbye")
        add(self.GOODBYE_CONFIRM, self.E_CONFIRM, self.CLOSING,
            self._a_close, guard=self._g_confirmed, name="confirm/yes")
        add(self.GOODBYE_CONFIRM, self.E_CONFIRM, self.CHECKIN,
            self._a_confirm_no, name="confirm/no")
        for st in (self.CHECKIN, self.CLARIFY, self.HELP, self.WORRY):
            add(st, self.E_GOODBYE, self.GOODBYE_CONFIRM,
                self._a_confirm_ask,
                guard=self._g_short_unconfirmed,
                name="%s/goodbye-confirm" % st)
        add("*", self.E_GOODBYE, self.CLOSING, self._a_close,
            name="any/goodbye")
        # safety / help / worry
        add("*", self.E_REFUSE, None, self._a_refuse, name="any/refuse")
        add("*", self.E_GOODBYE_DIRECT, self.CLOSING, self._a_close,
            name="any/goodbye-direct")
        add("*", self.E_HELP, self.HELP, self._a_help, name="any/help")
        add("*", self.E_WORRY, self.WORRY, self._a_worry, name="any/worry")
        add("*", self.E_SYMPTOM, self.SAFETY_CONFIRM, self._a_symptom,
            name="any/symptom")
        add("*", self.E_UNCERTAIN, self.SAFETY_ACTIVE, self._a_uncertain,
            name="any/uncertain")
        add(self.SAFETY_CONFIRM, self.E_OK, self.CHECKIN, self._a_false_alarm,
            guard=self._g_clearing, name="safetyconfirm/ok-clears")
        add("*", self.E_EMPTY, self.CLARIFY, self._a_empty, name="any/empty")
        add("*", self.E_GREETING, self.CHECKIN, self._a_greeting,
            name="any/greeting")
        # ordinary turns
        add("*", self.E_OK, None, self._a_ok, name="any/ok")
        add("*", self.E_UNKNOWN, None, self._a_unknown, name="any/unknown")
        # TOTAL MACHINE (2026-08-29): LAST row is the catch-all. It matches
        # only pairs with no specific transition (the classifier cannot
        # produce e.g. E_CONFIRM outside GOODBYE_CONFIRM, E_QUESTION outside
        # CHECKIN/SIDE_QUESTION) and turns them into an explicit warm ack
        # with a log line — never a silent swallow, never an exception on
        # the hot path. MUST stay the last declared row.
        add("*", "*", None, self._a_unhandled, name="any/any (catch-all)")


# ============================================================================
# SKILL.state — compact structured state for the LLM context.
#
# Instead of tailing the full dialogue window (llm_history[-8:] ≈
# 3-6k tokens per call) we pass only a structured snapshot: what
# matters for the NEXT step.  The raw memory/llm_history lists are
# still kept for persistence/auditing; the LLM receives the compact
# form only.  This is the implementation of the SKILL.state
# approach (Google/Purdue) — ~50× token reduction, same accuracy.
# ============================================================================
@dataclass
class SkillState:
    """Compact structured state replacing raw conversation history for the LLM."""
    current_topic: str = ""
    topic_index: int = 0
    topics_covered: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    last_question: str = ""
    last_reply: str = ""
    safety_status: str = "unknown"
    safety_notes: list[str] = field(default_factory=list)
    help_pending: bool = False
    closing_confirmed: bool = False
    agenda_done: bool = False
    conversation_summary: str = ""

    def update(self, agent: "Agent") -> None:
        """Snapshot the Agent's current state into this compact form."""
        self.current_topic = agent._agenda_topic() or ""
        self.topic_index = agent._agenda_idx
        all_topics = agent._agenda_all()
        self.topics_covered = [a[0] for a in all_topics[: agent._agenda_idx]]
        self.facts = list(agent.facts)
        self.last_question = getattr(agent, "_last_question", "") or ""
        self.last_reply = getattr(agent, "_last_reply", "") or ""
        self.safety_status = agent.status
        self.safety_notes = list(agent.notes[-5:])
        self.help_pending = getattr(agent, "_help_pending", False)
        self.closing_confirmed = getattr(agent, "_closing_confirmed", False)
        self.agenda_done = getattr(agent, "_agenda_done", False)
        self.conversation_summary = self._build_summary(agent)

    def _build_summary(self, agent: "Agent") -> str:
        """Natural-language summary of what happened so far (no raw turns)."""
        parts: list[str] = []
        if self.topics_covered:
            parts.append(
                "уже обсуждено: " + ", ".join(self.topics_covered))
        if self.facts:
            parts.append("факты: " + "; ".join(self.facts))
        if self.safety_notes:
            parts.append("заметки: " + "; ".join(self.safety_notes))
        return ". ".join(parts)

    def to_context_lines(self) -> list[str]:
        """Render as context lines injected into the LLM prompt."""
        lines: list[str] = []
        if self.current_topic:
            lines.append("текущая тема — «{}»".format(self.current_topic))
        if self.topics_covered:
            lines.append(
                "уже обсуждено: " + ", ".join(self.topics_covered))
        if self.last_question:
            lines.append("последний вопрос: {}".format(self.last_question))
        if self.last_reply:
            lines.append("ты только что сказала «{}»".format(self.last_reply))
        if self.facts:
            lines.append("факты: " + "; ".join(self.facts))
        if self.conversation_summary:
            lines.append(self.conversation_summary)
        return lines


# ----------------------------------------------------------------------------
# Agent logic — MVERA wellness-check call
# ----------------------------------------------------------------------------
# MVERA: сервис сам звонит пожилому человеку, ведёт короткий разговор,
# спрашивает о самочувствии и необходимости помощи, а после — отдаёт
# родственнику вердикт: всё в порядке / требуется внимание / не ответил /
# обнаружена опасность.

# Brand is IMVERA; the spoken form «Имвэра» is what the TTS says
# (latin IMVERA gets mangled/swallowed by the TTS).
MVERA_GREETING = "Здравствуйте! Это Имвэра. Как вы себя чувствуете?"

OK_WORDS = ("хорош", "нормал", "порядк", "отлично", "прекрас", "замечатель",
            "неплохо", "бодр", "здоров", "всё ок", "в порядке", "не жал",
            "приемле", "норм", "полегча", "полегче", "легче", "лучше",
            "супер", "класс", "шикарно", "весел", "бодряч", "неплох", "окей", "ок")
BAD_WORDS = ("плохо", "не очень", "слабо", "устал", "устала", "худо",
             "нездор", "подавле", "груст", "тревожно", "сильно устал",
             "неважно", "не важ", "хуже", "тяжел", "тревог", "сильно плохо")
DISTRESS_WORDS = ("скора", "упал", "упала", "ушиб", "сильно болит",
                  "не могу встать", "не встаю", "трудно дышать", "не дыш",
                  "температур", "всё болит", "вызовите врача", "врача",
                  "неотложн", "срочно", "проанализ", "скорой", "не дышать")
MED_WORDS = ("принял", "приняла", "принимал", "принимала", "принял лекарство",
             "выпил", "выпила", "пью таблетки", "лекарства", "таблетки",
             "таблетку", "таблетку принял")
HELP_WORDS = ("помощь", "помогите", "помочь", "купить", "продукты", "магазин",
              "нужны лекар", "надо лекар", "врачу", "в больницу", "попросить",
              "помоге", "сходить", "позвонить близким")


# ----------------------------------------------------------------------------
# VERA live replies — the answer-generation model runs as its own service
# (llm_server.py, port 9500). This client talks to it over HTTP; if the
# daemon is down it falls back to loading the model in-process, and if that
# also fails the agent degrades to scripted canned phrases. Either way a
# call never stalls.
# ----------------------------------------------------------------------------
VERA_LLM_ID = os.environ.get("MOSS_LLM_MODEL", "mlx-community/Qwen3-7B-8bit")
VERA_LLM_URL = os.environ.get("MOSS_LLM_URL", "http://127.0.0.1:9500")

VERA_SYSTEM_PROMPT = (
    "Ты — Вера, молодая тёплая русскоязычная ассистентка службы Имвэра (IMVERA). "
    "Звонишь пожилому человеку чтобы поинтересоваться самочувствием и просто "
    "побеседовать. Говоришь по телефону, голосом, без экрана.\n"
    "---\n"
    "ТВОЙ ХАРАКТЕР: живая, естественная, как родная внучка по телефону. Не "
    "робот, не оператор. Не формальна, не читает по бумажке. Сочувствуешь, "
    "поддерживаешь, улыбаешься в голос. Реагируешь на то, что человек "
    "сказал — ПРЕЖДЕ чем задавать новый вопрос.\n"
    "СТРУКТУРА ОТВЕТА (одна-две короткие фразы, общий размер — не длиннее "
    "трёх секунд речи вслух):\n"
    "  1. СНАЧАЛА короткий естественный отклик на сказанное человеком.\n"
    "     • хорошие новости — «Как здорово!», «Рада слышать», «Вот это да!»\n"
    "     • жалобы/боль — «Ой, как неприятно», «Понимаю, сочувствую»,\n"
    "       «Держитесь, я рядом», «Побольше отдыхайте»\n"
    "     • обычное — «Поняла», «Хорошо», «Ага, я вас слушаю», «Интересно»\n"
    "     • спрашивают у тебя — «Спасибо, у меня всё отлично! А как вы?»\n"
    "  2. ПОТОМ ОДИН уточняющий вопрос ПО ТЕМЕ сказанного — чтобы разговор "
    "продолжался, а не спрашивал «как самочувствие» ради галочки. Если "
    "человек сказал про сон — про сон; про внуков — про внуков; про таблетки "
    "— про таблетки. НЕ перескакивай на другую тему.\n"
    "Вопросов в каждом ответе — ТОЧНО ОДИН (не больше, не меньше). "
    "Исключение: если человек явно прощается или жалуется на острую боль — "
    "тогда вопрос можно не задавать.\n"
    "---\n"
    "О СЕБЕ: всегда женский род. «Я рада», «я поняла», «я записала», «я "
    "сочувствую». Обращайся к человеку НА «ВЫ», с уважением, но без "
    "формальности. Никогда на «ты».\n"
    "ЧТО НЕЛЬЗЯ:\n"
    "  • НЕ выдумывай ничего. Не говори «вы сегодня отлично выглядите» — "
    "    ты же по телефону, не видишь человека.\n"
    "  • НЕ пересказывай его же слова своими фразами («Правильно, вы сказали "
    "    что голова болит...») — это выглядит как эхо.\n"
    "  • НЕ задавай один и тот же вопрос дважды за разговор. То, о чём "
    "    уже спрашивала и получила ответ — не спрашивай снова.\n"
    "  • НЕ давай медицинских советов и диагнозов («попейте парацетамол»). "
    "    При жалобах: «Понимаю, записываю. Как давно это беспокоит?»\n"
    "  • НИКОГДА не обещай позвонить/вызвать/отправить. Максимум: «Я записала "
    "    — ваши близкие это увидят». Можно спросить, нужна ли помощь, но не "
    "    обещать организовать её.\n"
    "  • НЕ спрашивай про адрес, деньги, паспортные данные, местонахождение.\n"
    "---\n"
     "РЕАЛЬНОСТЬ: у тебя есть контекст предыдущих реплик этой беседы (включая "
     "то, о чём ты уже спросила) и ИЗВЕСТНЫЕ ФАКТЫ о человеке в скобках "
     "(ИМЯ, возраст, чем обычно занимается, что беспокоило раньше). "
     "ПОМНИ о них и ссылайся там где уместно — так разговор станет живым.\n"
"КОНТЕКСТ: тема и предыдущий твой вопрос передаются каждый ход — "
"используй их как мягкую подсказку. ТЫ формулируешь ответ "
"СВОБОДНО: не следуй букве букве тому, что написано в скобках "
"выше — твоя цель — быть тёплой, заботливой, задать один вопрос "
"по теме. Если тему можно закрыть — закрой мягко. Если нужно "
"уточнить — уточни. Не повторяй свои же предыдущие вопросы, "
"но если человек дал короткий ответ на контрольный вопрос — "
"подтверди его скриптово (да/хорошо/спасибо).\n"
"Если человек прощается — тепло попрощайся в ответ и закончи. "
"Формат: пиши ТОЛЬКО саму фразу-ответ, без кавычек, без заголовков, "
"без перевода строк. Голос сразу начнёт её читать."
 )

# Conversation scenarios (editable without a rebuild): a plain-text file
# appended to the system prompt. Missing file -> no scenario block.
SCENARIOS_FILE = os.environ.get(
    "MOSS_SCENARIOS_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "vera_scenarios.txt"),
)


def _load_scenarios(path=None):
    """Read the scenario file; '#' lines and blanks are skipped."""
    try:
        with open(path or SCENARIOS_FILE, encoding="utf-8") as f:
            lines = [ln.rstrip() for ln in f]
        text = "\n".join(ln for ln in lines
                         if ln.strip() and not ln.lstrip().startswith("#"))
        return text.strip()
    except OSError:
        return ""


VERA_SCENARIOS = _load_scenarios()


_HALLUCINATION_RE = re.compile(
    r"выглядите|выглядишь|голос (хорош|звучит)|какой у вас голос", re.I)


def reply_looks_hallucinated(reply: str, transcript: str) -> bool:
    """Cheap deterministic guard: the reply asserts things the caller never
    said (appearance/voice comments are the classic Qwen3 drift)."""
    if not reply:
        return False
    if _HALLUCINATION_RE.search(reply):
        return True
    # echo-check: reply asserts a fact word absent from what the caller said
    m = re.search(r"вы (хорошо )?(выглядите|себя чувствуете сегодня отлично)",
                  reply, re.I)
    return bool(m) and "чувствует" not in (transcript or "").lower()


# GENDER GUARD (2026-08-24): Vera is a WOMAN and must speak about herself
# in the feminine; Qwen3-4B still slips into masculine forms («я рад»,
# «я понял»). Deterministic feminization of self-references: applied only
# to words in the SAME sentence AFTER a standalone «я», so third-person
# masculine («дедушка был рад») stays untouched.
_SELF_FEM = {
    "рад": "рада", "был": "была", "сделал": "сделала", "готов": "готова",
    "услышал": "услышала", "записал": "записала", "понял": "поняла",
    "передал": "передала", "проверил": "проверила", "помог": "помогла",
    "успел": "успела", "смог": "смогла", "заметил": "заметила",
    "запомнил": "запомнила", "прав": "права", "согласен": "согласна",
    "доволен": "довольна", "занят": "занята", "должен": "должна",
}


def _feminize_self(sentence: str) -> str:
    out, seen_ya = [], False
    for w in sentence.split():
        m = re.match(r"^(.*?)([,.!?…:;]*)$", w)
        core, punct = m.group(1), m.group(2)
        lw = core.lower()
        if lw == "я":
            seen_ya = True
            out.append(w)
            continue
        fem = _SELF_FEM.get(lw)
        if seen_ya and fem and fem != lw:
            if core[:1].isupper():
                fem = fem.capitalize()
            w = fem + punct
            # seen_ya stays True: chained verbs feminize too
            # («я рада и записала»)
        out.append(w)
    return " ".join(out)


def _clean_llm(text):
    """Делает вывод модели безопасным для озвучки."""
    t = " ".join((text or "").split())
    t = re.sub(r"^(Вера|Assistant|Ответ)\s*:\s*", "", t, flags=re.IGNORECASE)
    # ONE-QUESTION RULE (2026-08-24): the prompt says "ровно один
    # вопросительный знак", yet live calls still showed double questions
    # («Как вы сегодня? Чем заняты?») — two questions overwhelm an elderly
    # caller. Deterministically keep only the FIRST interrogative sentence.
    sentences = [s for s in re.split(r"(?<=[.!?…])\s+", t) if s.strip()]
    q_seen = False
    kept = []
    for s in sentences:
        if "?" in s:
            if q_seen:
                break  # drop every question after the first
            q_seen = True
        # GENDER GUARD: Vera speaks about herself only in feminine
        s = _feminize_self(s)
        kept.append(s)
    t = " ".join(kept).strip() or " ".join(sentences[:1]).strip()
    if len(t) > 380:
        cut = t[:380].rfind(" ")
        t = t[:cut].rstrip() + "."
    return t


# BROKEN-REPLY GUARD (2026-08-24): deterministic checks for Qwen3 output
# that must never reach the speaker: parroting openers and latin leakage.
# 2026-08-24 live calls added: «Вы слышали? Как настроение?» (echo of the
# caller's «ага услышал»), «Как приятно, что вы о нас подумали» — all
# mirror-parroting of garbled STT input.
_MIRROR_OPENERS_RE = re.compile(
    r"^\s*(вы говорите|вы слышали|вы сказали|вы сомневаетесь|"
    r"вы спрашиваете|как приятно,?\s+что вы|рад[аы]?,?\s+что вы "
    r"(хорошо|нормально))", re.I)
_LATIN_WORD_RE = re.compile(r"[A-Za-z]")


def reply_looks_broken(reply: str) -> bool:
    """True when the segment must be replaced by a scripted line BEFORE it
    is spoken: mirror-parroting of the caller's words or code-switching to
    english ('Как вы спать tonight' — seen live 2026-08-23)."""
    if not reply:
        return False
    if _MIRROR_OPENERS_RE.match(reply):
        return True
    letters = _LATIN_WORD_RE.findall(reply)
    # a couple of stray latin chars can slip; a real english word cannot
    return len(letters) >= 4


# P-CLOSE1 (2026-08-29): «давай/давайте пока», «всё/ну/ладно пока»,
# «буду прощаться» etc. are UNAMBIGUOUS closes — two-word colloquial
# farewells, never «пока нет». They end the call WITHOUT the one-shot
# re-confirmation («Вы прощаетесь?»), which would have delayed the very
# goodbye the caller just said.
_CLOSING_DIRECT_RE = re.compile(
    r"(давай(те)?\s*,?\s*пока|пока\s*,?\s*давай(те)?|"
    r"(всё|ну|ладно|хватит)\s*,?\s*(давай|пока|давай\s*пока)|"
    r"буду прощаться|будем прощаться|пора прощаться|заканчиваю разговор)",
    re.IGNORECASE,
)


def _is_closing_direct(text):
    """True for an unambiguous farewell that should NOT be re-confirmed
    («давай пока», «всё давай», «буду прощаться»...)."""
    return bool(text and _CLOSING_DIRECT_RE.search(text))


_CLOSING_RE = re.compile(
    r"(до свидания|до свиданья|досвидания|всего доброго|всего хорошего|"
    r"до встречи|прощайте|спасибо за звонок|на сегодня всё|заканчиваем|"
    r"не буду мешать|пойду отдыхать|позвоню позже|будьте здоровы|"
    r"берегите себя|пока пока|пока-пока|давай(те)?\s*,?\s*пока|"
    r"пока\s*,?\s*давай|"
    r"(всё|ну|ладно|хватит)\s*,?\s*(давай|пока|давай\s*пока)|"
    r"буду прощаться|будем прощаться|пора прощаться|заканчиваю разговор)",
    re.IGNORECASE,
)


def _is_closing(text):
    """True when the caller is explicitly winding down the conversation.

    Deliberately conservative: bare "пока" is NOT a close (it often means
    "пока нет" / "not yet" in answer to a question); only unambiguous
    goodbyes count, so a real request is never cut short. Since the 2026-08-29
    live-call post-mortem ("давай, пока" never ended the call) the explicit
    colloquial closes are covered too: давай/давайте пока, всё давай,
    ну пока, ладно пока, буду прощаться.
    """
    if not text:
        return False
    return bool(_CLOSING_RE.search(text))


# REFUSAL DETECTION (P-ACK / P-CLOSE2, 2026-08-29): a short polite decline
# of an offer/question ("нет спасибо", "не надо", "ничего не нужно") must
# be honoured as a stop — Vera acknowledges and does NOT push another
# question. It also arms the fast-close: a following goodbye (or silence)
# ends the call WITHOUT the "Вы прощаетесь?" re-confirmation.
# Match on the PREFIX (a decline may trail off: «нет, спасибо, ничего не
# надо»), word limit generous (≤8) — a polite decline can run on.
_REFUSAL_RE = re.compile(
    r"^\s*(нет\s*[,]?\s*спасибо|нет\s*[,]?\s*не\s*(надо|нужно)|"
    r"не\s*(надо|нужно)|спасибо\s*[,]?\s*не\s*(надо|нужно)|"
    r"ничего\s*[,]?\s*не\s*(надо|нужно|хочу|буду)|"
    r"ничего\s*не\s*хочу|ничего\s*не\s*буду|нет\s*ничего|"
    r"всё\s*[,]?\s*ничего|всё\s*есть|всё\s*есть\s*у\s*меня)",
    re.IGNORECASE,
)


def _is_refusal(text):
    """True for a short explicit decline of an offer (never a bare "нет" —
    that may answer a yes/no control question)."""
    if not text or len(text.split()) > 8:
        return False
    return bool(_REFUSAL_RE.match(text.strip()))


# QUESTION OVER CHECK-IN (2026-08-27): a direct caller question outranks the
# routine wellness check. Conservative by design — only a literal '?' or a
# text that STARTS with an interrogative counts, so a long narration never
# accidentally flips the mode. Russian + a few commonenglish borrowings.
_QUESTION_WORDS = (
    "скажи", "расскажи", "что", "как", "почему", "зачем", "где",
    "когда", "кто", "сколько", "говори", "можешь", "может", "слышишь",
    "понимаешь", "поможешь", "what", "how", "why",
)


def _is_text_question(text):
    """Conservative question detector: '?' anywhere, or the text opens with
    an interrogative word followed by a WORD BOUNDARY (read.md #16):
    «что-то болит», «как-то странно» are NOT questions, «что случилось?»
    is. Only a hyphen/dash continuation keeps a prefix from counting."""
    if not text:
        return False
    if "?" in text:
        return True
    low = (text or "").strip().lower()
    if not low:
        return False
    for w in _QUESTION_WORDS:
        end = len(w)
        if low[:end] == w and (end >= len(low) or low[end] not in "-—"):
            return True
    return False


class Agent:
    """Conversational MVERA agent (mode-driven, not step-driven).

    The old script forced a fixed questionnaire (greeting -> wellbeing ->
    help -> goodbye) and ended the call after two answers. That made the
    product feel like an interview and is gone from the main path.

    A conversation is now a set of MODES — the character of THIS turn, not a
    strict progression:

        companion        ordinary chat (default, user-initiated)
        check_in         routine check-up questions (service-initiated call)
        clarify          didn't hear / nothing usable -> ask to repeat
        safety_confirm   possible danger -> gentle control question
        safety_active    confirmed/uncertain danger -> act + notify
        closing          caller is saying goodbye -> warm close

    Safety verdicts still come from the deterministic SafetyEngine; the Agent
    only maps event kinds to status (ok / attention / alert) and decides the
    reply intent. The call ends ONLY on: confirmed danger, an explicit
    goodbye, or an external hangup (end_call). There is no auto-finish after
    N answers, and no forced question after every reply.

    The WORDING of each reply is generated by the LLM (VERA persona) from the
    full conversation history; canned phrases remain as safe fallbacks when
    the LLM is unavailable.
    """

    MODES = ("companion", "check_in", "clarify", "safety_confirm",
             "safety_active", "closing")
    _MODE_STEP = {"companion": 0, "check_in": 1, "clarify": 2,
                  "safety_confirm": 3, "safety_active": 4, "closing": 5}

    # TASK-ORIENTED CALL AGENDA (2026-08-23): the call walks a SOFT checklist
    # of wellness topics instead of random-walking them like a chat bot.
    # Order mirrors vera_scenarios.txt. NOT a questionnaire: wording stays
    # free (the LLM gets the current topic as its reply goal; these canned
    # variants are only instant fallbacks). Safety/clarify interjections
    # PAUSE the agenda — the flow always returns to the current topic.
    # Variety (2026-08-23): every canned question now has FIVE natural
    # variants; topic keywords stay recognizable for tests/families.
    # T003 (2026-08-25): pools widened to EIGHT variants each (+3 per topic)
    # so cross-call rotation (_pick_not_repeated) rarely exhausts fresh
    # wording. Rules kept: one question mark, warm "вы", no promises,
    # no verbatim duplicates, topic keywords preserved.
    AGENDA = (
        ("самочувствие", (
            "Как вы себя чувствуете сейчас?",
            "Как самочувствие сегодня?",
            "Как ваше самочувствие?",
            "Ну что, как себя чувствуем сегодня?",
            "Как поживаете, как здоровье?",
            "Как вы себя чувствуете в последнее время?",
            "Что-нибудь беспокоит вас сейчас?",
            "Как ощущаете себя сегодня?",
        )),
        ("настроение", (
            "Как настроение?",
            "Что настроение сегодня — бодрое?",
            "Какое сегодня настроение?",
            "Хорошее ли сегодня настроение?",
            "Настроение как — не грустите?",
            "Душевное ли сегодня настроение у вас?",
            "Каким оно сегодня, ваше настроение?",
            "Радостное ли сегодня у вас настроение?",
        )),
        ("сон", (
            "Как спалось ночью?",
            "Хорошо ли вы спали?",
            "Как ночной сон — спокойный?",
            "Ночью хорошо спалось?",
            "Как выспались сегодня?",
            "Сон как прошёл этой ночью?",
            "Спалось ли вам спокойно этой ночью?",
            "Не тревожил вас сон?",
        )),
        ("планы", (
            "Какие планы на сегодня?",
            "Чем сегодня займётесь?",
            "Что сегодня задумали делать?",
            "Как проведёте сегодняшний день?",
            "Есть ли какие планы на день?",
            "Какие планы созрели на сегодня?",
            "Что приятного запланировали на сегодня?",
            "Как проведёте свой сегодняшний день?",
        )),
        ("передать родным", (
            "Что-нибудь передать близким?",
            "Хотите что-то записать для родных?",
            "Передать ли что-то вашим близким?",
            "Что передать вашим родным от вас?",
            "Есть что-то, что я должна передать семье?",
            "Есть слова для ваших близких, которые я могу записать?",
            "Хотите что-то сказать родным через меня?",
            "Записать что-нибудь для семьи?",
        )),
    )

    def __init__(self, config=None, llm=None):
        self.memory = []
        self.llm_history = []          # (role, text) for the LLM dialogue
        self.status = "unknown"  # verdict: unknown -> ok/attention/alert
        self.notes = []
        self.done = False
        self.last_intent = ""
        self.config = config or {}
        self.llm = llm
        # Stage 0A: safety decisions live in their own deterministic machine.
        self.safety = SafetyEngine()
        self._last_question = None       # what we asked before this turn
        self._last_confidence = None     # STT confidence (None = unknown → low per U9)
        self._clearing = False           # control question pending: OK clears
        self._help_pending = False       # a help question is on the table
        self._interrupt = None           # read.md #16: pending question-over-check-in
        self._closing_confirm_pending = False   # "Вы прощаетесь?" is pending
        self._closing_confirmed = False  # the close was confirmed once
        self._recent_spoken = collections.deque(maxlen=20)  # per-call variety ring
        self._asked_questions = collections.deque(maxlen=20)  # questions asked this call
        # Family-app questions for THIS call (see set_family_questions).
        self.family_questions = []
        # Facts (cross-turn memory) extracted from caller turns — see
        # _extract_facts/_facts_note.
        self.facts = []
        # The formal dialogue state machine (2026-08-29): all control flow
        # lives in its transition table; the Agent is the extended-state holder.
        self._fsm = DialogueFSM()
        self._init_agenda()
        # SKILL.state: compact structured state for the LLM context
        # (replaces passing the full llm_history window).  See module
        # docstring for the rationale.
        self.skill_state = SkillState()

    # ---- state accessors (delegated to the FSM) --------------------------
    @property
    def mode(self):
        """The public mode string — derived from the FSM state (Agent API
        compatibility: companion / check_in / clarify / safety_confirm /
        safety_active / closing)."""
        return self._fsm.mode(self)

    @property
    def step(self):
        return self._fsm.step(self)

    def _init_agenda(self):
        """Call-agenda state (task-oriented flow): which topic is live, was
        its question put on the table, and the topics covered so far.
        ``_agenda_extra`` holds per-call dynamic entries (family questions)
        appended AFTER the standard AGENDA."""
        self._agenda_idx = 0
        self._agenda_asked = False
        self._agenda_done = False
        self._agenda_extra = ()

    def set_family_questions(self, items):
        """Snapshot of family-app questions for THIS call. Called ONCE at
        new_call (deterministic turn): arrivals mid-call wait for the next
        call. Each question becomes one agenda entry (ONE question mark per
        turn rule) placed after the standard wellness topics."""
        self.family_questions = []
        extra = []
        for q in list(items or [])[:5]:  # mirrors pg.family_pending(limit=5)
            text = str(q.get("text") or "").strip()
            if not text:
                continue
            item = {
                "id": str(q.get("id") or ""),
                "text": text,
                "author": str(q.get("author") or "").strip() or "Родные",
                "status": "pending",
                "answer": None,
            }
            self.family_questions.append(item)
            # Neutral phrasing — no verb agreement with arbitrary labels
            # like "дочь"/"сын"/"Святослав".
            spoken = (f"Вопрос от родных ({item['author']}): {text}")
            extra.append(("вопрос от родных", (spoken,)))
        self._agenda_extra = tuple(extra)

    def _agenda_all(self):
        """Standard topics + this call's dynamic entries."""
        return tuple(self.AGENDA) + tuple(self._agenda_extra)

    def _current_is_family(self):
        return self._agenda_idx >= len(self.AGENDA)

    def _agenda_topic(self):
        """Name of the CURRENT agenda topic, or None when all are covered."""
        all_ = self._agenda_all()
        if getattr(self, "_agenda_done", False) \
                or self._agenda_idx >= len(all_):
            return None
        return all_[self._agenda_idx][0]

    def _agenda_question(self):
        """Instant fallback question for the CURRENT topic.

        Index-guarded (2026-08-29): reaching here with the agenda exhausted
        used to raise IndexError and drop the turn (two reachable paths:
        interrupt-resume after the last topic, and a 4-5 word story after
        all topics with a family question attached). Degrade to the wrap-up
        question instead — never crash the reply planner."""
        all_ = self._agenda_all()
        if self._agenda_done or self._agenda_idx >= len(all_):
            return self._wrap_up_question()
        return self._pick_not_repeated(all_[self._agenda_idx][1])

    def _ask_task(self):
        """Put the current topic's question on the table (marks it asked).
        Returns the canned question, or a generic ack when the agenda is
        already finished."""
        if self._agenda_topic() is not None:
            self._agenda_asked = True
            q = self._agenda_question()
            self._last_question = q
            return q
        return None

    def _agenda_advance(self, answer_text=None):
        """Close the current topic: record 'обсуждено: <тема>' for the family
        verdict and move on. A family-app entry instead snapshots the
        caller's answer onto the question (synced to PG at end_call).
        Returns True when the agenda just FINISHED."""
        topic = self._agenda_topic()
        if topic is None:
            return False
        if self._current_is_family():
            k = self._agenda_idx - len(self.AGENDA)
            if k < len(self.family_questions):
                item = self.family_questions[k]
                item["status"] = "asked"
                item["answer"] = (answer_text or "").strip() or "(без ответа)"
                self._note(f"вопрос родных ({item['author']}) передан, "
                           "ответ записан")
        else:
            self._note(f"обсуждено: {topic}")
        self._agenda_idx += 1
        self._agenda_asked = False
        if self._agenda_topic() is None:
            self._agenda_done = True
            return True
        return False

    def _wrap_up_question(self):
        """All topics covered — invite final words instead of a new topic."""
        q = self._pick_not_repeated([
            "Вы рассказали обо всём — я всё записала для близких. "
            "Добавите что-нибудь?",
            "Я записала всё важное. Хотите что-то ещё передать родным?",
            "Всё запомнила и записала. Что-нибудь ещё добавить для семьи?",
            "Кажется, обо всём поговорили. Осталось что-то, что надо "
            "записать?",
            "Записала всё, что вы рассказали. Ещё что-то передадите "
            "близким?",
        ])
        self._last_question = q
        return q

    def reset(self):
        self.memory = []
        self.llm_history = []
        self.status = "unknown"
        self.notes = []
        self.done = False
        self.config = {}
        self.safety = SafetyEngine()
        self._last_question = None
        self._last_confidence = None
        self._clearing = False
        self._help_pending = False
        self._interrupt = None
        self._closing_confirm_pending = False
        self._closing_confirmed = False
        self.family_questions = []
        self.facts = []
        self._fsm.reset(self)
        self._init_agenda()
        self.skill_state = SkillState()

    def start_check_in(self):
        """Service-initiated call: open with the routine greeting question.

        Returns the greeting to speak. In the default companion mode no
        greeting question is forced — the conversation just happens."""
        self._fsm.sm.state = self._fsm.CHECKIN
        self._last_question = MVERA_GREETING
        # ECHO GUARD (2026-08-23): the recording is a MONO MIX, so the
        # tail of this greeting ("Здравствуйте!") lands in turn-1 audio and tiny used
        # to transcribe it as the CALLER's words. Seeding _last_reply lets
        # orchestrator._looks_like_echo catch that echo on the first turn.
        self._last_reply = MVERA_GREETING
        # the greeting IS agenda topic 0 («самочувствие») on the table
        self._agenda_asked = True
        # SKILL.state: snapshot the initial state so the first
        # user turn gets context about the greeting.
        self.skill_state.update(self)
        return MVERA_GREETING

    def observe_confidence(self, confidence):
        """STT confidence 0..1 for the NEXT turn (None when unavailable).
        Low confidence can neither create GREEN nor confirm RED (U9)."""
        self._last_confidence = confidence

    def _note(self, text):
        """Append a verdict note once (no duplicates in long conversations)."""
        if text not in self.notes:
            self.notes.append(text)

    # ---- reply planning + token streaming (REALTIME FIX, Stage 4+5) -------
    # plan_reply() runs the DETERMINISTIC mode machine only (fast, under the
    # per-call lock): it decides the mode, the verdict notes, the intent for
    # the model and the canned fallback phrase. The actual model generation
    # happens LATER outside the lock via reply_stream(), yielding deltas so
    # the first finished sentence can be sent to TTS while the rest of the
    # reply is still being generated. commit_reply() records the final text
    # in the dialogue history once it is known.
    #
    # Stage 0A: safety verdicts come from the SafetyEngine (core/safety_engine
    # .py), NOT from substring matching in the dialogue layer. The Agent only
    # decides HOW to reply based on the VerdictEvent.

    def plan_reply(self, caller_text, reason=None):
        """Run the formal dialogue state machine (DialogueFSM); return a
        reply plan without talking to any model. Plan keys:
            text      user utterance
            intent    LLM objective (None -> the fallback is the FINAL reply)
            fallback  canned phrase (also the garbage/timeout fallback)
        State mutations (memory, status, notes, llm_history user turn) happen
        HERE — safe under the per-call lock. All CONTROL FLOW lives in the
        DialogueFSM transition table; this method only classifies the input
        and delegates.

        ``reason`` separates WHY a turn has no usable transcript so the
        empty-turn ladder stays productive instead of blind «Повторите»:
            None       no speech / VAD silence / STT failure
            "low_conf" real speech existed but scored below the gate
            "echo"     transcript looked like Vera's own words
            "stt_uncertain" mid-confidence speech — ask caller to confirm
        Only the empty-turn ladder reads it (see _silence_flow)."""
        # ECHO MUTE (2026-08-25): an "echo" reason means the transcript IS
        # Vera's own words coming back from the mixed recording. Blank the
        # text so it never pollutes memory/history and route it through the
        # echo ladder — a productive repeat request instead of regenerating
        # her own phrase.
        if reason == "echo":
            caller_text = ""
        if reason == "stt_uncertain" and (caller_text or "").strip():
            if short_real_answer(caller_text.strip()):
                reason = None
            else:
                short = caller_text.strip()
                if len(short) > 80:
                    short = short[:77] + "..."
                return {
                    "text": caller_text,
                    "intent": None,
                    "fallback": (
                        f"Я правильно услышала: «{short}»? "
                        "Скажите да или повторите, пожалуйста."
                    ),
                }
        # TERMINAL GUARD (S24) is handled inside the FSM (E_DONE -> terminal
        # goodbye): after done, late/duplicate turns cannot mutate the
        # verdict, the history or the engine state.
        plan = self._fsm.dispatch(self, caller_text, reason)
        self.skill_state.update(self)
        return plan


    # ---- silence / no-speech ladder (2026-08-25) --------------------------
    # The 1st empty turn is NO LONGER a blind «Повторите» — it asks a
    # yes/no ANCHOR on the current wellness state, which whisper-tiny
    # recognises almost perfectly {"хорошо" / "плохо"}, so the call moves
    # forward instead of looping. Repeated emptiness escalates through the
    # calm tapered-ladder and collapses to wordless HOLDs (VUI practice).
    ANCHORS = (
        "Плохо слышно. Скажите коротко: хорошо или плохо.",
        "Очень тихо. Ответьте одним словом: хорошо или плохо.",
        "Слышно плохо. Скажите коротко: хорошо или плохо.",
    )

    def _silence_flow(self, caller_text, reason):
        """Empty-turn reply by CAUSE (plan_reply's ``reason``):
          * "echo"      transcript looked like Vera's own words — 1st: repeat
                        request; 2nd+: anchor then quiet holds.
          * None /      real silence OR speech below the confidence gate —
                        "low_conf"    the yes/no anchor on the FIRST empty turn;
                        next steps go up the calm tapered ladder.
        """
        if reason == "echo":
            n = self._fsm._echo_turns + 1
            self._fsm._echo_turns = n
            if n == 1:
                fb = self._pick_not_repeated(self.REPEAT_REQUESTS)
            elif n == 2:
                fb = self._pick_not_repeated(self.ANCHORS)
            else:
                fb = self._pick_not_repeated(self.QUIET_HOLDS)
            return {"text": caller_text, "intent": None, "fallback": fb}
        n = self._fsm._empty_turns + 1
        self._fsm._empty_turns = n
        if n == 1:
            fb = self._pick_not_repeated(self.ANCHORS)
        elif n == 2:
            fb = "Алло, вы меня слышите?"
        elif n == 3:
            fb = "Если вам удобно, скажите «да» — я рядом и вас слушаю."
        elif n == 4:
            fb = "Я подожду. Скажите, когда будете готовы говорить."
        else:
            fb = self._pick_not_repeated(self.QUIET_HOLDS)
        return {"text": caller_text, "intent": None, "fallback": fb}

    # Topic keyword guessing (content-first): a volunteered reply that names
    # the current topic's signal words closes it even when the question had
    # been deferred by a narrative. Conservative roots only — a generic
    # «всё хорошо» matches nothing.
    _TOPIC_KEYS = {
        "самочувствие": ("самочув", "чувству", "здоров", "болит", "болеет",
                         "голов", "давлен", "таблет", "лекар", "полегча",
                         "отпуст", "температур", "тошн", "кружится", "бодр"),
        "настроение": ("настроени", "груст", "весел", "бодр", "радост",
                       "тоск", "тревож", "депресс", "апати", "скучно",
                       "одиноко", "волнуе"),
        "сон": ("сон", "спал", "поспал", "выспал", "уснул", "снился",
                "ночь", "ночью", "дрых", "кемар", "вздрем", "бессон",
                "просыпа", "храп", "кошмар", "выспа"),
        "планы": ("план", "соберусь", "хочу сегодня", "планиру",
                  "собираюсь", "гулять", "прогулка", "магазин", "готовить",
                  "уборка", "внук", "внучк", "внуч", "гости", "дела"),
        "передать родным": ("передать", "передайте", "записать", "запис",
                            "запиш", "родным", "близким", "семье", "детям",
                            "доч", "сын"),
    }

    def _matches_topic(self, text):
        """Return True when ``text`` clearly answers the CURRENT topic."""
        topic = self._agenda_topic()
        if not topic or not text:
            return False
        keys = self._TOPIC_KEYS.get(topic)
        if not keys:
            return False
        low = text.lower()
        return any(k in low for k in keys)

    def _answers_wellness(self, text):
        """Answer to «как себя чувствуете?» — short or explicit good/bad."""
        if not (text or "").strip():
            return False
        if short_real_answer(text):
            return True
        low = text.lower()
        if any(w in low for w in OK_WORDS) or any(w in low for w in BAD_WORDS):
            return True
        return self._matches_topic(text)

    def _mentions_symptom(self, text):
        """True when the caller names a body complaint (any agenda topic)."""
        if not (text or "").strip():
            return False
        low = text.lower()
        return bool(re.search(
            r"голов|болит|болел|болела|болеет|тошн|круж|давлен|"
            r"температур|слабост|недомог|ноет|колет|шумит|"
            r"сердц|дыш|кашл", low))

    # ---- facts (compact cross-in memory, 2026-08-25) -----------------------
    # Extracted from caller turns so the model gets the ESSENCE of the call
    # without a raw 10-turn window. Rendered as a bracketed note on the
    # current user message (keeps the llama.cpp KV-prefix stable). Filled
    # read-only from the safety keyword lists; capped at recent 6.
    def _extract_facts(self, text):
        if not (text or "").strip():
            return
        low = (text or "").lower()
        facts = []
        if re.search(r"таблет|лекар|принял|приняла|выпил|выпила", low):
            facts.append("приняла лекарства")
        if re.search(r"голов|давлен|болит|температур|плохо", low) and \
                not re.search(r"\bне\s+(болит|плохо|болеет)", low):
            facts.append("недомогание")
        if re.search(r"спа(л|ла)|сон|ночью|заснул", low):
            facts.append("сон")
        if re.search(r"внуч|бабушк|дедушк|сын|дочер|сестр|брат|муж|жён|друг", low):
            facts.append("родные")
        if re.search(r"(послезавтра|сегодня|завтра|собир|план|пойд|у пойду)", low) or \
                re.search(r"(буду|хочу)\s+(\w+\s+){0,3}(гулять|готовить|читать|гулят|делать)", low):
            facts.append("планы")
        if re.search(r"хорош|нормал|отлично|прекрас|бодр", low) and \
                re.search(r"настроен|чувств", low):
            facts.append("настроение хорошее")
        for f in facts:
            if f not in self.facts:
                self.facts.append(f)
        self.facts = self.facts[-6:]

    def _facts_note(self):
        if not self.facts:
            return ""
        return "; известно: " + "; ".join(self.facts)

    # VARIETY (2026-08-24): scripted hello-back openers (elder says
    # «Здравствуйте!»). Was ONE fixed line «И вам здравствуйте!» — heard
    # verbatim on every such call. Rotates cross-call via _pick_not_repeated;
    # the agenda question is appended by the caller, so NO question marks here.
    HELLO_BACKS = (
        "И вам здравствуйте!",
        "Здравствуйте! Рада вас слышать.",
        "Здравствуйте-здравствуйте! Как хорошо, что позвонили.",
        "Здравствуйтесь и вы. Я как раз на связи.",
        "Приветствую вас! Слышу вас хорошо.",
        "Здравствуйте! Очень приятно услышать ваш голос.",
    )

    # VARIETY (2026-08-24): the generic acknowledgment pool used to be THREE
    # bare phrases («Понимаю.», «Вот как.», «Наверное, так и бывает.») picked
    # with plain random.choice in three places — exactly the empty nods the
    # system prompt forbids, repeated call after call. Warm, promise-free
    # alternatives now rotate via _pick_not_repeated (cross-call memory).
    GENERIC_ACKS = (
        "Понимаю вас.",
        "Да, конечно, я вас слушаю.",
        "Хорошо, что рассказали — я всё запомнила.",
        "Спасибо, что поделились со мной.",
        "Я рядом и внимательно вас слушаю.",
        "Как хорошо, что вы мне это рассказываете.",
        "Понимаю, такое бывает. Я записала ваши слова.",
        "Верно ли я поняла — я запишу это для близких?",
    )

    # BRIDGES (2026-08-25): short warm bridge spoken BEFORE the next agenda
    # question on the SPEED FAST PATH (a bare «да»/«хорошо» — no LLM). One
    # connective, no question mark, no promises; the question itself travels
    # separately (so a single „?" rule holds).
    BRIDGES = (
        "Замечательно.",
        "Рада это слышать.",
        "Как хорошо!",
        "Приятно слышать.",
        "Вот и славно.",
        "Хорошо, спасибо за ответ.",
    )

    # WRAP_OPENERS (2026-08-25): the tail of the generic-ack reply when the
    # topic is NOT moved (narrative-deferred / nothing on the table). Always
    # an open one-question invitation so a bare «ага» never ends the call.
    WRAP_OPENERS = (
        "Добавите что-нибудь для близких?",
        "Что-нибудь ещё записать?",
        "Может, что-то вспомнилось?",
        "Есть что-то ещё, чем вы хотите поделиться?",
    )

# HEARD_ACKS (2026-08-29, E_HEARD): the caller confirmed they can hear
    # us on the silence ladder/anchor («да, я тебя слышу»). Warm ack, then
    # RETURN to the topic question.
    HEARD_ACKS = (
        "Слышу вас, спасибо.",
        "Отлично, теперь слышно хорошо.",
        "Рада, что мы слышим друг друга.",
        "Спасибо, что отозвались.",
    )

    # REFUSAL_ACKS (2026-08-29, P-ACK/P-CLOSE2): a short polite decline
    # ("нет спасибо", "не надо", "ничего") is honoured — acknowledge WITHOUT
    # pushing another question (the old "Да, конечно, добавьте что-нибудь?"
    # after "нет спасибо" was the top complaint of the live post-mortem).
    REFUSAL_ACKS = (
        "Хорошо, я всё записала для близких. Обращайтесь, если "
        "что-то понадобится.",
        "Поняла вас. Все важное записано. Если что-то понадобится — "
        "я рядом.",
        "Хорошо. Я оставила запись для семьи. Берегите себя.",
        "Записала всё, что вы рассказали. Родные это увидят. "
        "Берегите себя.",
    )

    # VARIETY (2026-08-24): gentle control question when a symptom is heard
    # (possible_red). Was 2 inline lines; safety MEANING unchanged — the
    # machine still sets _clearing so a following «нет, отпустило» clears.
    # SYMPTOM_CHECKS (2026-08-29 rework): the caller named a symptom (голова
    # болит, кружится...) — Vera must ASK about IT, not abstractly "записать
    # для близких" (the old phrasing was a live-call complaint d0220bac0967:
    # «болела голова» -> «Записать это для близких? Записать это для
    # близких?», the caller's concrete problem was never addressed).
    SYMPTOM_CHECKS = (
        "Вы упомянули, что что-то беспокоит. Что именно сейчас?",
        "Как вас сейчас самочувствие — что ощущаете?",
        "Скажите, что вас беспокоит — я всё внимательно записываю.",
        "Что вы сейчас чувствуете? Расскажите подробнее, я рядом.",
    )

    # VARIETY (2026-08-24): soft stand-down after an unconfirmed concern
    # (uncertain_red). Was 2 inline lines; «я запишу» kept promise-free.
    STAY_OBSERVANT_ACKS = (
        "Не буду настаивать. Если станет хуже — скажите, я запишу.",
        "Хорошо. Если станет хуже — сразу скажите.",
        "Хорошо, верю. Но если что-то изменится — я рядом и всё записываю.",
        "Договорились. Только обещайте сообщить мне, если станет хуже.",
    )

    # VARIETY (2026-08-24): the 1st empty turn used to be ONE fixed line
    # («Повторите, пожалуйста…») heard on EVERY call with a silent start.
    # Warm «вы», no promises, at most one question mark. Pool widened 4→6 —
    # with a silent caller this line opens most turns of the whole call.
    REPEAT_REQUESTS = (
        "Повторите, пожалуйста, я вас не расслышала.",
        "Простите, я не разобрала — скажите ещё раз, пожалуйста.",
        "Плохо слышно. Повторите, я вас слушаю.",
        "Извините, переспросите, пожалуйста, я записываю всё внимательно.",
        "Акустика подводит. Скажите ещё раз, я рядом и слушаю.",
        "Не расслышала ваших слов. Повторите, пожалуйста, чуть медленнее.",
    )

    # TAPERED SILENCE LADDER (2026-08-24, VUI practice — Manning "Voice UI
    # Systems" ch.13: escalating prompts + max error count; W3C COGA:
    # fallbacks must not loop): turns 2-4 are calm full prompts, turn 5+
    # collapses to ONE-WORD holds so long silence never becomes chatter or
    # drama («Вам плохо?», «Постучите по трубке» — dropped, they frightened
    # people on live calls).
    QUIET_HOLDS = (
        "Я рядом.",
        "Я здесь, когда вы будете готовы.",
        "Слушаю вас.",
    )

    # VARIETY (2026-08-24): follow-up after a false-alarm apology (real call:
    # «а почему ты так подумал?»); was 2 lines heard back-to-back on any
    # safety clearing. Rotates via _pick_not_repeated, warm «вы».
    FALSE_ALARM_ACKS = (
        "Простите, я перестраховалась — вы сказали, что голова болела. "
        "Как она сейчас?",
        "Поняла вас, извините за тревогу. Как самочувствие сейчас?",
        "Хорошо, что отпустило. Я всё же записала — близкие в курсе. "
        "Как вы себя чувствуете?",
        "Рада, что всё обошлось. Простите за лишнюю тревогу. Как вы "
        "сейчас, бодрости хватает?",
    )

    # VARIETY (2026-08-24): follow-up when the caller worries about a loved
    # one (third-person worry); was 2 interchangeable questions.
    WORRY_FOLLOWUPS = (
        "Расскажите подробнее, что случилось?",
        "Я записала ваше беспокойство. Что именно случилось?",
        "Спокойно, я всё записываю. Расскажите, что произошло?",
        "Понимаю вашу тревогу. Что именно вас беспокоит? Опишите, "
        "пожалуйста.",
    )

    def _build_history(self):
        # NOTE (latency experiment 2026-08-21): moving the per-turn intent
        # out of the system prompt (trailing system msg / appended to the
        # user turn) was tried to enable llama.cpp KV-cache reuse — BOTH
        # variants degraded Qwen3 (latency up to 3.3-6s, «ты» вместо «вы»,
        # выдуманные детали). The intent lives in the system prompt; the
        # measured end-to-end cost is acceptable (~2.5s to first sound).
        #
        # SKILL.state (2026-09-01): instead of tailing the full
        # llm_history[-8:] window (≈ 3-6k tokens per call) we pass
        # only a compact structured snapshot — what matters for the
        # NEXT step.  Raw turns stay in memory/llm_history for
        # persistence and auditing; the LLM receives the compact
        # form only.
        system = VERA_SYSTEM_PROMPT
        if VERA_SCENARIOS:
            system = f"{system}\n\n{VERA_SCENARIOS}"
        history = [{"role": "system", "content": system}]
        # SKILL.state context: structured snapshot instead of raw turns.
        for line in self.skill_state.to_context_lines():
            history.append({"role": "user", "content": line})
        # The CURRENT user turn (just appended in dispatch()) — the
        # skill_state above captures the PREVIOUS assistant reply only.
        # Read it from memory (not llm_history) to avoid re-sending
        # raw history; this is the one user message the model needs now.
        if self.memory:
            history.append({"role": "user", "content": self.memory[-1]})
        return history

    def _finish(self):
        """Terminal turn: freeze the safety machine against later turns."""
        self.done = True
        self.safety.freeze()

    def reply_stream(self, plan):
        """Yield reply-text DELTAS for a plan (LLM path). A plan with
        intent=None yields its fallback as a single chunk. All failures are
        swallowed: the caller collects chunks and falls back to
        plan['fallback'] when nothing usable arrived."""
        if plan.get("intent") is None or self.llm is None \
                or not (plan.get("text") or "").strip():
            yield plan.get("fallback") or ""
            return
        if plan.get("terminal") and self.mode == "safety_active":
            # SAFETY: under a confirmed threat the reply is the exact
            # pre-validated script — never free LLM phrasing.
            yield plan.get("fallback") or ""
            return
        if self.mode in ("safety_confirm", "safety_active"):
            # SAFETY: control/confirmation turns use the exact pre-validated
            # scripted question — the LLM phrasing drifts, stops asking the
            # yes/no control question and breaks the confirm loop (gate #62).
            # EXCEPT the FIRST symptom complaint («голова болит») — there the
            # caller wants a live caring reply, not a canned line
            # (2026-08-30 live-call feedback: "короткие фразы надо выпилить").
            intent = (plan.get("intent") or "").lower()
            if self.mode == "safety_confirm" \
                    and ("уточнить" in intent or "симптом" in intent):
                pass  # let the LLM phrase it (goes through reply_stream)
            else:
                yield plan.get("fallback") or ""
                return
        self.last_intent = plan.get("intent") or ""
        history = self._build_history()
        streamer = getattr(self.llm, "chat_stream", None)
        if streamer is None:
            out = None
            try:
                out = self.llm.chat(history)
            except Exception:  # noqa: BLE001
                out = None
            if out:
                yield out
            else:
                # D6: LLM returned nothing → yield plan fallback
                fb = plan.get("fallback")
                if fb:
                    yield fb
            return
        try:
            for delta in streamer(history):
                if delta:
                    yield delta
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] reply stream error: {e}", flush=True)
            # D6: stream error → yield plan fallback
            fb = plan.get("fallback")
            if fb:
                yield fb

    def commit_reply(self, reply_text):
        """Record the final assistant reply in the dialogue history
        (call AFTER generation finished; never before it starts)."""
        if reply_text:
            self.llm_history.append(("assistant", reply_text))
            self._last_reply = reply_text
            self.skill_state.update(self)

    def _pick_not_repeated(self, variants):
        """Pick a phrase that differs from the last asked question AND from
        anything spoken recently (per-call ring, then process-level ring).
        Falls back to the full pool when everything was recently used —
        variety degrades gracefully instead of breaking."""
        last_q = getattr(self, "_last_question", None)
        pool = [v for v in variants if v != last_q]
        with _RECENT_LOCK:
            fresh = [v for v in (pool or variants)
                     if v not in self._recent_spoken
                     and v not in self._asked_questions
                     and v not in _RECENT_SPOKEN]
            pick = random.choice(fresh or pool or variants)
            if last_q:
                self._asked_questions.appendleft(last_q)
            self._recent_spoken.appendleft(pick)
            _RECENT_SPOKEN.appendleft(pick)
        return pick

    def _ask_help(self):
        return self._pick_not_repeated([
            "Нужна ли вам помощь?",
            "Помощь требуется?",
            "Что записать для близких?",
            "Что именно нужно сделать? Я запишу для родных.",
            "Какая помощь вам нужна? Опишите, пожалуйста.",
        ])

    def _goodbye(self):
        # VARIETY (2026-08-24): the close is spoken on EVERY call — was only
        # two phrasings, the most-heard repetition in the product. No new
        # promises added («записала/увидят» only), warm «вы», no questions.
        # Rotates via _pick_not_repeated: plain random.choice could still
        # deal the SAME goodbye twice in a row across calls (the ring buffer
        # only guards pools picked through it).
        return self._pick_not_repeated(self.GOODBYES)

    GOODBYES = (
        "Спасибо! Всё записала. До свидания!",
        "Хорошо, записала. Всего доброго!",
        "Спасибо за разговор! Всё записала для близких. До свидания!",
        "Рада была побеседовать. Берегите себя, всего доброго!",
        "Всё отметила, родные это увидят. Будьте здоровы!",
        "Хорошего вам дня и крепкого здоровья. До свидания!",
        "Спасибо, что поговорили со мной. Всё передала в записи — "
        "близкие увидят. До свидания!",
        "Была рада вашему голосу. Здоровья вам, всего самого доброго!",
        "Записала каждое слово. Пусть у вас всё будет хорошо. До свидания!",
        "Благодарю за доверие. Родные прочитают ваши новости. "
        "Берегите себя!",
        "Тепла вам и спокойных дней. Всё записано, до свидания!",
        "Спасибо за этот разговор! Я всё сохранила для семьи. "
        "Будьте здоровы, до свидания!",
    )

    # Продуманный диалог от и до (2026-08-30): закрытие ОБЯЗАТЕЛЬНО сообщает
    # что записано, а не просто "до свидания" — иначе звонок ощущается как
    # сброс. Если есть факты/жалобы/ответы родным — называем, если всё
    # спокойно — говорим прямо что записей нет.
    GOODBYE_TAILS = (
        "Берегите себя, всего доброго!",
        "До свидания, здоровья вам!",
        "Всего доброго, до скорой связи!",
        "Берегите себя, пусть день будет спокойным!",
        "До свидания, была рада слышать ваш голос!",
    )

    def _closing_report(self):
        """Короткий отчёт для прощания: что записала vs прямо что нечего."""
        has_family = any(q.get("status") == "asked"
                         for q in getattr(self, "family_questions", []))
        has_health = any(f in ("недомогание",) for f in self.facts) \
            or self.status in ("attention", "alert")
        # notes like "обсуждено: ..." are not a record by themselves
        meaningful_notes = [n for n in self.notes
                            if not n.startswith("обсуждено:")]
        has_record = has_family or has_health or bool(meaningful_notes)
        if has_record:
            # детали — из фактов или первой meaningful note, но коротко
            detail = ""
            if "недомогание" in self.facts:
                detail = "самочувствие"
            elif has_family:
                detail = "ваши слова для родных"
            elif meaningful_notes:
                detail = meaningful_notes[0].lower()
            else:
                detail = "важные моменты"
            # не дублировать "записала" дважды — GOODBYE_TAILS без неё
            tail = self._pick_not_repeated(self.GOODBYE_TAILS)
            return f"Я всё записала — {detail}, близкие это увидят. {tail}"
        # ничего тревожного — говорим прямо
        tail = self._pick_not_repeated(self.GOODBYE_TAILS)
        return f"Сегодня всё спокойно, отдельных записей не делала, но отметила что вы в порядке. {tail}"

    def _goodbye_report(self):
        return self._closing_report()

    def _ask(self, text):
        """One conversational turn (blocking). Backwards-compatible wrapper
        over plan_reply()/reply_stream()/commit_reply() for callers that
        still expect a single final string."""
        plan = self.plan_reply(text)
        chunks = []
        for delta in self.reply_stream(plan):
            chunks.append(delta)
        reply = _clean_llm(("".join(chunks)).strip()) if plan.get("intent") \
            else ("".join(chunks)).strip()
        if plan.get("intent") and (not reply or len(reply) < 4
                                   or len(reply) > 400):
            reply = plan["fallback"]
        self.commit_reply(reply)
        return reply

    def reply(self, caller_text):
        return self._ask(caller_text)

    @property
    def finished(self):
        return self.done

    @property
    def outcome(self):
        """Вердикт для родственника (Stage 0A: three independent statuses).

        UNKNOWN is its own status and is NOT masked to attention anymore —
        whether an unanswered/unknown call escalates is a product decision of
        the reporting layer, not a lie inside the safety verdict. GREEN (ok)
        is only ever produced from a confirmed positive answer.
        """
        return {"status": self.status, "notes": list(self.notes)}