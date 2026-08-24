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

from core.safety_engine import Observation, SafetyEngine  # noqa: E402

# CROSS-CALL VARIETY (2026-08-23): the Agent instance is recreated per call,
# so a per-instance "last question" memory repeated the same phrases every
# call. This process-level ring remembers recently SPOKEN canned phrases for
# the lifetime of the telephony container and steers _pick_not_repeated away
# from them. maxlen 20 ~= one full call's worth of canned lines.
_RECENT_SPOKEN = collections.deque(maxlen=20)
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
    "окей": "да", "ок": "да", "давай": "да",
    "нет": "нет", "неа": "нет", "не нужно": "помощь не нужна",
    "не надо": "помощь не нужна", "нет спасибо": "помощь не нужна",
    "хорошо": "всё хорошо", "всё хорошо": "всё хорошо", "все хорошо": "всё хорошо",
    "нормально": "всё нормально", "норм": "всё нормально",
    "все нормально": "всё нормально", "всё нормально": "всё нормально",
    "неплохо": "всё нормально", "терпимо": "всё терпимо", "так себе": "так себе",
    "плохо": "всё плохо", "не важно": "неважно",
    "неважно": "неважно", "ничего": "ничего не нужно",
    "помощь": "нужна помощь", "помощь нужна": "нужна помощь",
    "помощь требуется": "нужна помощь", "нужна помощь": "нужна помощь",
    # polite/greeting phrases that were being eaten by the junk filter:
    # they are REAL turns (goodbye must reach the goodbye flow!)
    "до свидания": "до свидания", "пока": "до свидания",
    "пока пока": "до свидания", "всего доброго": "до свидания",
    "спасибо": "спасибо", "большое спасибо": "спасибо",
    "здравствуйте": "здравствуйте", "привет": "привет",
    "алло": "алло", "да да": "да", "ну да": "да",
}

_SHORT_ANSWER_WORDS = frozenset((
    "всё", "все", "да", "ага", "угу", "ок", "окей", "давай", "неплохо",
    "хорошо", "нормально", "норм", "терпимо", "неважно", "плохо",
    "помощь", "требуется", "нужна", "нужно", "надо", "не", "нуждаюсь",
    "нет", "нет спасибо", "не нужно", "не надо", "ничего", "спасибо",
    "есть", "конечно", "неа", "до", "свидания", "пока", "всего",
    "доброго", "большое", "здравствуйте", "привет", "алло", "ну",
))


def short_real_answer(raw):
    """Return the canonical form of a short real answer, or None.

    Only applies to very short (<=3 words) utterances where EVERY word is a
    known answer word — filters hallucinated fragments out while keeping
    "нет спасибо" intact.
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
    if not all(w in _SHORT_ANSWER_WORDS for w in words):
        return None
    return _SHORT_ANSWER_MAP.get(t)


def clean_transcript(text):
    if not text:
        return None
    t = text.strip()
    # drop very short/fragmentary results
    if len(t) < 2:
        return None
    # drop whisper filler/hallucination phrases
    if _JUNK_RE.match(t):
        # CONVERSATION FIX: keep genuine short answers — the junk regex
        # intentionally overlaps them ("всё", "хорошо", "да", "нет"), yet a
        # VAD/endpoint-gated utterance that transcribes to exactly one of
        # them is a real reply, not hallucination.
        short = short_real_answer(t)
        if short:
            return short
        return None
    # drop repeating-word hallucinations ("Next Next Next...")
    if _is_repetition(t):
        return None
    # keep multi-word spoken turns
    return t


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
            "приемле", "норм")
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
VERA_LLM_ID = os.environ.get("MOSS_LLM_MODEL", "mlx-community/Qwen3-1.7B-8bit")
VERA_LLM_URL = os.environ.get("MOSS_LLM_URL", "http://127.0.0.1:9500")

VERA_SYSTEM_PROMPT = (
    "Ты — Вера, молодая девушка, тёплая и заботливая помощница службы Имвэра (письменно IMVERA).\n"
    "Общайся как живой человек: слушай собеседника, откликайся именно на его "
    "слова, помни всё, что он уже сказал в этом разговоре, сопереживай.\n"
    "ЖИВАЯ БЕСЕДА, а не вежливые кивки: пустые «Понимаю» и «Вот как» без "
    "содержания — ПЛОХОЙ ответ. Откликайся на детали (что именно человек "
    "рассказал, кого упомянул, что планировал). Почти в КАЖДОМ ответе "
    "задавай один естественный вопрос по теме: уточни подробности, спроси "
    "про самочувствие, планы, настроение. Вопрос — проявление интереса; без "
    "него разговор умирает.\n"
    "Формат: две-три короткие фразы, 10–30 слов, только русский. РОВНО ОДИН "
    "вопросительный знак в ответе — не больше. Только на русском.\n"
    "ВЕЖЛИВОСТЬ: всегда обращайтесь на «вы», НИКОГДА на «ты». Правильно: "
    "«Как вы себя чувствуете?», «Что вы сегодня делали?». Неправильно: «как "
    "ты», «тебе», «твой». Вы обращаетесь к пожилому человеку уважительно.\n"
    "НЕ выдумывай того, чего не было: не оценивай внешность и голос («вы "
    "хорошо выглядите»), не придумывай события. Откликайся ТОЛЬКО на то, "
    "что человек реально сказал.\n"
    "ТЕМЫ ВОПРОСОВ — только забота о человеке: самочувствие сейчас, что-то "
    "болит или отпустило, давление, таблетки (приняла ли, помогли ли), сон, "
    "аппетит, настроение, планы на день, как близкие. Если человек упомянул "
    "симптом или лекарство («голова болела», «таблетку выпила») — ОБЯЗАТЕЛЬНО "
    "уточните именно про это: «Как голова сейчас? Таблетка помогла?»\n"
    "ЗАПРЕЩЁННЫЕ вопросы: где человек находится, адрес, точное время и место "
    "встреч, личные данные, деньги. Такие вопросы пугают и звучат как "
    "слежка. Если человек спрашивает, зачем вы это спрашиваете, — извинитесь "
    "коротко («Простите, переспросила лишнее») и вернитесь к самочувствию.\n"
    "НЕ задавай один и тот же вопрос дважды за разговор: похожий вопрос уже "
    "виден в истории — спроси о чём-то другом из сказанного.\n"
    "Приветствие прозвучало ОДИН раз в начале звонка. Если человек сказал "
    "«привет» уже после начала — НЕ здоровьтесь заново и НЕ переспрашивайте "
    "то, что уже спрашивали (вопросы перед глазами в истории). Отвечайте на "
    "сказанное и двигайте разговор вперёд.\n"
    "КАТЕГОРИЧЕСКИ: не спрашивайте «как вы себя чувствуете?» дважды за "
    "разговор и сразу после того, как человек уже ответил на этот вопрос. "
    "Спрашивайте о ЧЁМ-ТО ДРУГОМ из сказанного: детали, планы, семья, дела.\n"
    "Если цель текущего ответа — уточнить — задай ровно один прямой вопрос "
    "по теме и ничего больше.\n"
    "При жалобах на здоровье или опасности говори о своих действиях: "
    "«я рядом», «я записываю» — и не давай советов встать, пойти, пить или "
    "лечь.\n"
    "НИКОГДА не обещай действий от своего имени: не говори «я вызову», "
    "«я позвоню», «я отправлю», «я предупрежу», «я передам». Ты только "
    "записываешь: записи видят близкие в приложении Имвэра и действуют сами. "
    "Можно говорить «я записала», «близкие это увидят»; можно спросить, "
    "нужна ли скорая или помощь, но не обещать их вызвать.\n"
    "Без медицинских советов и диагнозов: при жалобах на здоровье предложи "
    "записать для близких.\n"
    "Если собеседник прощается — тепло попрощайся и закончи разговор.\n"
    "Пиши только сам ответ — его прочитают вслух. Без кавычек, без подписей."
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


def _clean_llm(text):
    """Делает вывод модели безопасным для озвучки."""
    t = " ".join((text or "").split())
    t = re.sub(r"^(Вера|Assistant|Ответ)\s*:\s*", "", t, flags=re.IGNORECASE)
    parts = re.split(r"(?<=[.!?…])\s+", t)
    t = " ".join(parts[:2]).strip()
    if len(t) > 380:
        cut = t[:380].rfind(" ")
        t = t[:cut].rstrip() + "."
    return t


_CLOSING_RE = re.compile(
    r"(до свидания|до свиданья|досвидания|всего доброго|всего хорошего|"
    r"до встречи|прощайте|спасибо за звонок|на сегодня всё|заканчиваем|"
    r"не буду мешать|пойду отдыхать|позвоню позже|будьте здоровы|"
    r"пока пока|пока-пока)",
    re.IGNORECASE,
)


def _is_closing(text):
    """True when the caller is explicitly winding down the conversation.

    Deliberately conservative: bare "пока" is NOT a close (it often means
    "пока нет" / "not yet" in answer to a question); only unambiguous
    goodbyes count, so a real request is never cut short.
    """
    if not text:
        return False
    return bool(_CLOSING_RE.search(text))


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
    AGENDA = (
        ("самочувствие", (
            "Как вы себя чувствуете сейчас?",
            "Как самочувствие сегодня?",
            "Как ваше самочувствие?",
            "Ну что, как себя чувствуем сегодня?",
            "Как поживаете, как здоровье?",
        )),
        ("настроение", (
            "Как настроение?",
            "Что настроение сегодня — бодрое?",
            "Какое сегодня настроение?",
            "Хорошее ли сегодня настроение?",
            "Настроение как — не грустите?",
        )),
        ("сон", (
            "Как спалось ночью?",
            "Хорошо ли вы спали?",
            "Как ночной сон — спокойный?",
            "Ночью хорошо спалось?",
            "Как выспались сегодня?",
        )),
        ("планы", (
            "Какие планы на сегодня?",
            "Чем сегодня займётесь?",
            "Что сегодня задумали делать?",
            "Как проведёте сегодняшний день?",
            "Есть ли какие планы на день?",
        )),
        ("передать родным", (
            "Что-нибудь передать близким?",
            "Хотите что-то записать для родных?",
            "Передать ли что-то вашим близким?",
            "Что передать вашим родным от вас?",
            "Есть что-то, что я должна передать семье?",
        )),
    )

    def __init__(self, config=None, llm=None):
        self.memory = []
        self.llm_history = []          # (role, text) for the LLM dialogue
        self.mode = "companion"
        self.step = 0          # derived from mode (kept for session docs)
        self.status = "unknown"  # verdict: unknown -> ok/attention/alert
        self.notes = []
        self.done = False
        self.last_intent = ""
        self.config = config or {}
        self.llm = llm
        # Stage 0A: safety decisions live in their own deterministic machine.
        self.safety = SafetyEngine()
        self._last_question = None       # what we asked before this turn
        self._last_confidence = None     # STT confidence (None = unknown)
        self._clearing = False           # control question pending: OK clears
        self._help_pending = False       # a help question is on the table
        # Family-app questions for THIS call (see set_family_questions).
        self.family_questions = []
        self._init_agenda()

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
        """Instant fallback question for the CURRENT topic."""
        all_ = self._agenda_all()
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
        self.mode = "companion"
        self.step = 0
        self.status = "unknown"
        self.notes = []
        self.done = False
        self.config = {}
        self.safety = SafetyEngine()
        self._last_question = None
        self._last_confidence = None
        self._clearing = False
        self._help_pending = False
        self.family_questions = []
        self._init_agenda()

    def start_check_in(self):
        """Service-initiated call: open with the routine greeting question.

        Returns the greeting to speak. In the default companion mode no
        greeting question is forced — the conversation just happens."""
        self.mode = "check_in"
        self._update_step()
        self._last_question = MVERA_GREETING
        # ECHO GUARD (2026-08-23): the recording is a MONO MIX, so the tail of
        # this greeting ("Здравствуйте!") lands in turn-1 audio and tiny used
        # to transcribe it as the CALLER's words. Seeding _last_reply lets
        # orchestrator._looks_like_echo catch that echo on the first turn.
        self._last_reply = MVERA_GREETING
        # the greeting IS agenda topic 0 («самочувствие») on the table
        self._agenda_asked = True
        return MVERA_GREETING

    def observe_confidence(self, confidence):
        """STT confidence 0..1 for the NEXT turn (None when unavailable).
        Low confidence can neither create GREEN nor confirm RED (U9)."""
        self._last_confidence = confidence

    def _set_mode(self, mode):
        self.mode = mode
        self._update_step()

    def _note(self, text):
        """Append a verdict note once (no duplicates in long conversations)."""
        if text not in self.notes:
            self.notes.append(text)

    def _update_step(self):
        self.step = self._MODE_STEP.get(self.mode, 0)

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

    def plan_reply(self, caller_text):
        """Run the MVERA mode machine; return a reply plan without talking
        to any model. Plan keys:
            text      user utterance
            intent    LLM objective (None -> the fallback is the FINAL reply)
            fallback  canned phrase (also the garbage/timeout fallback)
        State mutations (memory, mode, status, notes, llm_history user turn)
        happen HERE — safe under the per-call lock."""
        # TERMINAL GUARD (S24): after done, late/duplicate turns cannot
        # mutate the verdict, the history or the engine state.
        if self.done:
            return {"text": caller_text, "intent": None,
                    "fallback": self._goodbye(), "terminal": True}
        if caller_text:
            self.memory.append(caller_text)
            self.llm_history.append(("user", caller_text))
        self._help_pending = False

        ev = self.safety.observe(Observation(
            question=self._last_question,
            raw_text=caller_text,
            confidence=self._last_confidence,
            source="stt",
        ))

        if ev.kind == "frozen":
            return {"text": caller_text, "intent": None,
                    "fallback": self._goodbye()}
        if ev.kind == "confirmed_red":
            # SAFETY: danger always outranks an ordinary goodbye.
            self.status = "alert"
            self.notes.append("обнаружена опасность")
            self._set_mode("safety_active")
            self._finish()
            # NO false hope: Vera never promises to call anyone — she only
            # records; the app shows it to the family, they act.
            return {"text": caller_text, "terminal": True,
                    "intent": "успокоить, попросить оставаться на месте, "
                              "сказать что записала, спросить нужна ли "
                              "скорая; ничего не обещать вызвать",
                    "fallback": random.choice([
                        "Останьтесь на месте. Я всё записала, близкие "
                        "увидят. Вам нужна скорая?",
                        "Не вставайте. Я отметила, родные узнают. "
                        "Дождитесь помощи.",
                    ])}
        if _is_closing(caller_text):
            # MISHEAR GUARD: whisper-tiny confuses «Да, всё хорошо» ↔ «До
            # свидания». If a goodbye arrives as an answer to our own
            # question (check-in/clarify) and it is short — confirm once
            # instead of hanging up on a person who may have just said
            # "всё хорошо". A real goodbye confirms; a mishearing corrects.
            words = len((caller_text or "").split())
            if self.mode in ("check_in", "clarify") and words <= 3 \
                    and not getattr(self, "_closing_confirmed", False):
                self._closing_confirm_pending = True
                q = ("Вы сейчас прощаетесь? Скажите «да» — и я пожелаю вам "
                     "добра, или расскажите, как вы себя чувствуете.")
                self._last_question = q
                return {"text": caller_text, "intent": None,
                        "fallback": q}
            self._set_mode("closing")
            self._finish()
            return {"text": caller_text, "terminal": True,
                    "intent": "тепло попрощаться: короткое пожелание "
                              "(«Берегите себя», «Всего доброго»)",
                    "fallback": self._goodbye()}
        if getattr(self, "_closing_confirm_pending", False) and caller_text:
            # the turn right after the goodbye-confirmation request
            self._closing_confirm_pending = False
            t = (caller_text or "").lower()
            if _is_closing(t) or re.search(r"\b(да|ага|угу|конечно)\b", t):
                self._set_mode("closing")
                self._finish()
                return {"text": caller_text, "terminal": True,
                        "intent": "тепло попрощаться",
                        "fallback": self._goodbye()}
            # not a goodbye after all — continue the conversation normally
        return self._plan_mode(caller_text, ev)

    def _plan_mode(self, caller_text, ev):
        """Event -> mode/intent/fallback for a non-terminal turn."""
        # HELP CONFIRMATION WINDOW: _help_pending was armed when we asked a
        # help question last turn ("Нужна ли вам помощь?"). Consume it HERE,
        # once per turn — clearing it earlier in plan_reply ran BEFORE this
        # check, so a bare "да" could never be recognised as a confirmation.
        help_was_pending = getattr(self, "_help_pending", False)
        self._help_pending = False
        # CONVERSATIONAL REPAIR: when the caller asks us to repeat, the only
        # right answer is to say our previous reply again — not a new topic.
        if caller_text and re.search(
                r"(повторите|повтори|что ты сказала|что вы сказали|"
                r"не расслышал|не понял|что как)", caller_text.lower()):
            last = getattr(self, "_last_reply", None)
            if last:
                return {"text": caller_text, "intent": None,
                        "fallback": f"Повторяю: {last}"}
        if ev.kind == "no_speech":
            # SILENCE/NOISE FLOW: never feed noise to the LLM, never repeat
            # the same prompt. 1st empty turn -> gentle repeat request;
            # from the 2nd on -> check on the person (they may feel unwell,
            # have fallen asleep, or the phone may be far away).
            self._empty_turns = getattr(self, "_empty_turns", 0) + 1
            self._set_mode("clarify")
            if self._empty_turns == 1:
                fb = "Повторите, пожалуйста, я вас не расслышала."
            elif self._empty_turns == 2:
                # deterministic escalation: the person may feel unwell
                fb = "Вы меня слышите? Вам плохо?"
            else:
                fb = random.choice([
                    "Всё ли у вас в порядке? Отзовитесь, пожалуйста.",
                    "Если вам плохо — скажите, я записываю для близких.",
                    "Я на линии, слышу тишину. Вам нужна помощь?",
                    "Скажите хоть слово, я очень слушаю вас сейчас.",
                ])
            return {"text": caller_text, "intent": None, "fallback": fb}
        self._empty_turns = 0
        if ev.kind == "possible_red":
            # POSSIBLE_RED -> gentle control question; stay observant.
            self._note("плохое самочувствие")
            self.status = "attention"
            self._set_mode("safety_confirm")
            self._clearing = True
            q = self._pick_not_repeated([
                "Мне показалось, что вы неважно себя чувствуете. "
                "Вам сейчас плохо?",
                "Вы говорите, что вам нехорошо. Записать это для близких?",
            ])
            self._last_question = q
            return {"text": caller_text,
                    "intent": "мягко уточнить самочувствие, не пугая человека; "
                              "не обещать вызвать помощь",
                    "fallback": q}
        if ev.kind == "uncertain_red":
            self._note("самочувствие не подтверждено")
            self.status = "attention"
            self._set_mode("safety_active")
            q = self._pick_not_repeated([
                "Не буду настаивать. Если станет хуже — скажите, я запишу.",
                "Хорошо. Если станет хуже — сразу скажите.",
            ])
            self._last_question = q
            return {"text": caller_text,
                    "intent": "успокоить и продолжить разговор, не настаивая; "
                              "не обещать вызывать помощь",
                    "fallback": q}
        if ev.kind == "help_request":
            # A bare "да"/"конечно" in free conversation is NOT a help
            # request — it only means help when we asked a help question
            # this turn ("Нужна ли вам помощь?") or the phrase is explicit
            # ("мне нужна помощь", "помогите").
            explicit = "запрос помощи" in (ev.notes or ())
            if not explicit and not help_was_pending:
                return {"text": caller_text,
                        "intent": "откликнуться на детали сказанного и задать один естественный уточняющий вопрос по теме",
                        "fallback": random.choice([
                            "Понимаю.",
                            "Вот как.",
                            "Наверное, так и бывает.",
                        ])}
            self._note("требуется помощь")
            self.status = "attention"
            self._set_mode("check_in")
            self._help_pending = True
            q = self._ask_help()
            self._last_question = q
            return {"text": caller_text,
                    "intent": "сказать, что записала просьбу о помощи — "
                              "близкие её увидят, спросить, что именно "
                              "нужно; не обещать ничего сделать самой",
                    "fallback": q}
        if ev.kind == "third_person":
            self._note("беспокойство о близких")
            self.status = "attention"
            self._set_mode("check_in")
            self._help_pending = True
            q = self._pick_not_repeated([
                "Расскажите подробнее, что случилось?",
                "Я записала ваше беспокойство. Что именно случилось?",
            ])
            self._last_question = q
            return {"text": caller_text,
                    "intent": "узнать больше о беспокойстве собеседника; "
                              "записи видят близкие, ничего не обещать "
                              "передавать самому",
                    "fallback": q}
        if ev.kind == "ok":
            # CONVERSATION FIX: a positive answer does NOT auto-advance to a
            # help question. Vera simply stays in the conversation. Status:
            # an OK right after a safety control question CLEARS the concern;
            # otherwise OK never downgrades attention/alert (help request,
            # third-person worry, uncertain red) and only promotes unknown.
            if self._clearing:
                self.status = "ok"
                self._clearing = False
                # the caller just denied the concern and asked why we thought
                # so — acknowledge the false alarm warmly (real call:
                # "а почему ты так подумал?")
                fb = self._pick_not_repeated([
                    "Простите, я перестраховалась — вы сказали, что голова "
                    "болела. Как она сейчас?",
                    "Поняла вас, извините за тревогу. Как самочувствие "
                    "сейчас?",
                ])
                self._last_question = fb
                return {"text": caller_text, "intent": None, "fallback": fb}
            elif self.status == "unknown":
                self.status = "ok"
            # SPEED FAST PATH: a short confirmation ("да", "всё хорошо") is
            # answered from a rotating script INSTANTLY — no LLM round-trip
            # (~2 s saved on the most common turn type). The follow-up now
            # comes from the CALL AGENDA (task-oriented flow): the answered
            # topic closes, Vera moves to the next one.
            canon = short_real_answer(caller_text)
            if canon and len(caller_text.split()) <= 3:
                if self._agenda_asked and self._agenda_advance(caller_text):
                    fb = self._wrap_up_question()
                    return {"text": caller_text, "intent": None,
                            "fallback": fb}
                # VARIETY: warm acknowledgments pool (was 2 phrases repeated
                # every call — the top complaint 2026-08-23).
                q = self._ask_task() or self._pick_not_repeated([
                    "Хорошо. Я рядом — если что-то понадобится, скажите.",
                    "Отлично. Тогда всего доброго, я на связи.",
                    "Рада слышать. Я тут, если что.",
                    "Хорошо-хорошо. Пусть день будет спокойным.",
                    "Замечательно. Звоните, как почувствуете что-то.",
                    "Очень хорошо. Я всегда на связи с вами.",
                ])
                return {"text": caller_text, "intent": None, "fallback": q}
            # longer positive answer: close the topic, hand the NEXT topic
            # to the LLM as its reply goal (task stays in free wording).
            finished = self._agenda_asked and self._agenda_advance(caller_text)
            if finished:
                fb = self._wrap_up_question()
                return {"text": caller_text,
                        "intent": "тёпло подвести итог: всё записала для "
                                  "близких; спросить, не хочет ли человек "
                                  "что-то ещё добавить",
                        "fallback": fb}
            q = (self._ask_task()
                 or self._pick_not_repeated([
                     "Очень рада это слышать.",
                     "Как же хорошо, спасибо.",
                     "Вот и замечательно.",
                     "У меня прямо легче стало.",
                     "Рада за вас, правда.",
                 ]))
            nxt = self._agenda_topic()
            if self._current_is_family():
                # Family-app question: the EXACT text must reach the elder,
                # so the reply goal carries it verbatim.
                goal = ("тёпло откликнуться на сказанное, затем передать "
                        "вопрос от близких дословно: "
                        f"«{self._agenda_question()}» — только этот один "
                        "вопрос")
            elif nxt:
                goal = (f"порадоваться, откликнуться на детали сказанного и "
                        f"одним естественным вопросом перейти к теме «{nxt}»")
            else:
                goal = "порадоваться и откликнуться на детали сказанного"
            return {"text": caller_text, "intent": goal, "fallback": q}
        # unknown: NOT masked to attention — it stays its own status and can
        # never become GREEN. Vera just responds to what was said — and the
        # CALL AGENDA keeps the task in sight: her reply goal names the
        # current topic, so even free LLM phrasing stays on-task.
        topic = self._agenda_topic()
        if topic is not None and not self._agenda_asked:
            q = self._ask_task()
            if self._current_is_family():
                intent = ("откликнуться на сказанное и передать вопрос от "
                          f"близких дословно: «{self._agenda_question()}»")
            else:
                intent = ("откликнуться на детали сказанного и одним "
                          f"естественным вопросом спросить про «{topic}»")
            return {"text": caller_text, "intent": intent, "fallback": q}
        if topic is not None:
            return {"text": caller_text,
                    "intent": "откликнуться на детали сказанного и задать "
                              "один уточняющий вопрос по теме "
                              f"«{topic}» (это цель звонка)",
                    "fallback": random.choice([
                        "Понимаю.",
                        "Вот как.",
                        "Наверное, так и бывает.",
                    ])}
        return {"text": caller_text,
                "intent": "откликнуться на детали сказанного и задать один естественный уточняющий вопрос по теме",
                "fallback": random.choice([
                    "Понимаю.",
                    "Вот как.",
                    "Наверное, так и бывает.",
                ])}

    def _build_history(self):
        # NOTE (latency experiment 2026-08-21): moving the per-turn intent
        # out of the system prompt (trailing system msg / appended to the
        # user turn) was tried to enable llama.cpp KV-cache reuse — BOTH
        # variants degraded Qwen3 (latency up to 3.3-6s, «ты» вместо «вы»,
        # выдуманные детали). The intent lives in the system prompt; the
        # measured end-to-end cost is acceptable (~2.5s to first sound).
        system = VERA_SYSTEM_PROMPT
        if VERA_SCENARIOS:
            system = f"{system}\n\n{VERA_SCENARIOS}"
        history = [{"role": "system", "content": system}]
        # LATENCY TRACE (route step 6) showed the LLM is NOT the bottleneck
        # (30-85 ms per reply); TTS dominates only under concurrent-call
        # contention on the single slot. The window is kept at 10 turns: it
        # spans the wellness thread without sacrificing earlier context.
        for role, txt in self.llm_history[-10:]:
            history.append({"role": "user" if role == "user" else "assistant",
                            "content": txt})
        # CONVERSATION FIX A: the current user turn is ALREADY in
        # llm_history (added by plan_reply) — never append it a second time.
        # CONVERSATION FIX B: the reply objective is part of the SYSTEM
        # context, never smuggled in as a fake user message.
        if self.last_intent:
            # PROMPT-CACHE: the intent rides on the CURRENT USER message (new
            # every turn anyway), so the system+history prefix stays stable
            # and llama.cpp reuses its KV cache. The intent-in-system variant
            # invalidated the cache every turn (+1-2 s prompt processing).
            last = history[-1]
            note = f"(Цель ответа: {self.last_intent}"
            last_reply = getattr(self, "_last_reply", None)
            if last_reply:
                note += (f"; твой предыдущий ответ был «{last_reply}» — "
                         "не повторяй его вопрос, спроси о другом")
            note += ")"
            if last["role"] == "user":
                last["content"] = last["content"] + "\n" + note
            else:
                history.append({"role": "user", "content": note})
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
            return
        try:
            for delta in streamer(history):
                if delta:
                    yield delta
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] reply stream error: {e}", flush=True)

    def commit_reply(self, reply_text):
        """Record the final assistant reply in the dialogue history (call
        AFTER generation finished; never before it starts)."""
        if reply_text:
            self.llm_history.append(("assistant", reply_text))
            self._last_reply = reply_text

    def _pick_not_repeated(self, variants):
        """Pick a phrase that differs from the last asked question AND from
        anything spoken in RECENT calls (process-level ring). Falls back to
        the full pool when everything was recently used — variety degrades
        gracefully instead of breaking."""
        pool = [v for v in variants if v != getattr(self, "_last_question",
                                                    None)]
        with _RECENT_LOCK:
            fresh = [v for v in (pool or variants)
                     if v not in _RECENT_SPOKEN]
            pick = random.choice(fresh or pool or variants)
            _RECENT_SPOKEN.append(pick)
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
        return random.choice(self.GOODBYES)

    GOODBYES = (
        "Спасибо! Всё записала. До свидания!",
        "Хорошо, записала. Всего доброго!",
        "Спасибо за разговор! Всё записала для близких. До свидания!",
        "Рада была побеседовать. Берегите себя, всего доброго!",
        "Всё отметила, родные это увидят. Будьте здоровы!",
        "Хорошего вам дня и крепкого здоровья. До свидания!",
    )

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