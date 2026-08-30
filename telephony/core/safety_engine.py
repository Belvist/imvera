"""SafetyEngine — deterministic, tokenized safety verdicts (Stage 0A / Phase 1).

The Agent no longer makes safety decisions from raw substring matching
(S11-S25: "мне плохо" matching "не плох", "мне нужна помощь" matching
"не нужн", "мне очень хорошо" matching "не очень", ...). The Agent emits an
Observation {question, raw_text, confidence, source} into the SafetyEngine and
consumes the returned VerdictEvent. The engine is a pure, deterministic,
stateful machine:

    NONE -> POSSIBLE_RED -> (control question asked by the dialogue layer)
                        -> CONFIRMED_RED | UNCERTAIN_RED | OK

Invariants guaranteed by the machine (see test_invariants.py):
  * CONFIRMED_RED / UNCERTAIN_RED are latched: never downgraded to ok/GREEN.
  * A negated distress word ("не плохо", "температуры нет") never yields RED.
  * A third-person subject ("бабушка упала") never yields caller RED.
  * An inanimate object fall ("упала банка") never yields RED.
  * Low STT confidence can neither create GREEN nor confirm RED.
  * Empty / robotic transcripts are no_speech, never ok.
  * freeze() (dialogue done) blocks all later turns from mutating verdicts.

No I/O, no models: it programs against plain text/strings, so the same
machine runs in tests, in the worker and in the orchestrator.
"""

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIDENCE_THRESHOLD = 0.4

# Negation window: a negator within +/-N tokens of a signal word negates it.
NEG_WINDOW = 3

NEGATORS = frozenset((
    "не", "нет", "нету", "ни", "ничего", "без", "никогда", "нельзя",
    "нечем", "негде", "некуда", "никак",
))

# "не могу/не можешь/не может X" is an inability, NOT a negation of X.
_ABILITY = frozenset(("могу", "можешь", "может", "можем", "могут", "можно"))

AFFIRMATIVE = frozenset((
    "да", "ага", "угу", "конечно", "давай", "сильно", "хуже",
))

DENIAL = frozenset((
    "нет", "неа", "ничего", "не", "нету", "не надо", "не нужно",
    "не нужна", "не требуется", "не стоит", "прошло", "прошла",
    "отпустило", "уже лучше", "лучше",
))

# Exact tokens that alone mean an emergency (subject-aware via window).
EMERGENCY_TOKENS = frozenset((
    "скорая", "скорую", "скорой", "скорые", "неотложка", "неотложку",
    "неотложной", "инфаркт", "инсульт", "срочно", "срочная",
    "врач", "врача", "врачу", "врачи", "доктор", "доктора", "доктору",
    "докторы",
))

# Emergency tokens that only escalate for a SELF-directed ACUTE context:
# "врач/доктор/срочно" appear constantly in everyday speech ("записалась к
# врачу", "бабушке срочно нужен врач", "сходил к доктору"). A routine
# mention must NOT confirm a red alert. See block 5 in _analyze.
_CONTEXTUAL_EMERGENCY_TOKENS = frozenset((
    "срочно", "срочная", "врач", "врача", "врачу", "врачи", "доктор",
    "доктора", "доктору", "докторы",
))

# Root prefixes for health-distress signals (possible_red).
MED_ROOTS = (
    "плох", "неважн", "худ", "уста", "слабост", "слаб", "нездоров",
    "подавлен", "груст", "тревож", "тяжел", "тошн", "температур", "озноб",
    "голов", "круж", "давл", "сердц", "тахикард", "груд", "бол", "жжет",
    "колет",
)

# Root prefixes for severe signals (confirmed_red candidate).
HIGH_ROOTS = (
    "упа", "пада", "умир", "умер", "поконч", "суицид", "задохн",
    "обвар", "ожог", "обожг",
)

# Words meaning "dropped something" — not a fall, ignore.
_DROP_TOKENS = frozenset(("уронил", "уронила", "уронили", "уронилa"))

# Falls caused by an inanimate object (never a caller RED).
OBJECT_FALL_ROOTS = (
    "банк", "телефон", "стул", "тарелк", "ваз", "чашк", "кружк", "стакан",
    "ложк", "вилк", "нож", "табурет", "пульт", "очк", "книг", "ручк",
    "полотенц", "пакет", "коробк", "бутылк", "цветок", "горшок", "шапк",
    "сумк", "магнит", "рамк", "фото", "ключ",
    # nature: "листья падают", "снег идёт/падает", "дождь", "яблоки" —
    # weather/season statements, never a person falling
    "лист", "снег", "дожд", "яблок", "град", "ветк", "капл", "звезд",
)

# Health metrics that may "fall" but ARE a health concern ("давление упало").
HEALTH_METRIC_FALL_ROOTS = ("давл", "сахар", "пульс", "тонус")

# How far (tokens) a metric subject may sit from the fall verb it explains
# ("настроение в принципе хорошее, но сегодня днём упало" — 8 tokens).
FALL_SUBJECT_WINDOW = 8

# Indefinite subjects that make a subject-less fall ambiguous ("что-то
# упало", "ничего не упало") — not a person, not a confirmed fall.
_THING_FALL_SUBJECTS = frozenset(("что-то", "что", "ничего", "всё", "все"))

# Root prefixes of positive/ok signals.
POSITIVE_ROOTS = (
    "хорош", "нормал", "отлич", "прекрасн", "замечатель", "неплох",
    "порядк", "бодр", "здоров", "приемл", "жал",
)

# Third-person subjects: signals near these never become caller RED.
THIRD_ROOTS = (
    "бабушк", "дедушк", "мам", "пап", "родител", "сын", "дочер", "сестр",
    "брат", "сосед", "муж", "жен", "внук", "внучк", "свекров", "тещ",
    "мачех", "подруг", "друг", "их",
)
THIRD_TOKENS = frozenset(("он", "она", "они"))

SELF_TOKENS = frozenset(("я", "мне", "меня", "мной", "мною", "у меня",
                         "мой", "моя", "моё", "мое", "мои", "себя", "собой"))

HELP_ROOTS = (
    "помо", "помог", "помож", "продук", "магазин", "купи", "больниц",
    "близк", "родн", "принес", "сходи", "позвон", "переда", "вод", "нужн",
    "требу",
)

MEDS_ROOTS = ("таблет", "лекар", "принимал", "принимала", "выпил", "выпила",
              "выпила", "пью")

# Words that express a NEED even in a past-tense statement: "продукты
# кончились, надо сходить", "мне нужна помощь".
_NEED_WORDS = frozenset(("нужно", "надо", "нужна", "нужен", "нужны",
                         "требуется", "необходимо"))

# Informal imperative forms that make a phrase a REQUEST even next to a
# past-tense verb ("купил продукты, сходи за хлебом").
_IMPERATIVE = frozenset(("купи", "сходи", "позвони", "передай", "принеси",
                         "помоги", "скажи", "предупреди", "позови", "вызови"))

# Ideation phrases (subject/negation aware; see _analyze).
IDEATION_PHRASES = (
    "хочу умереть", "хотел умереть", "хотела умереть", "хочет умереть",
    "хочется умереть", "покончить с собой", "свести счёты с жизнью",
    "свести счёты", "не хочу жить", "не хочу больше жить", "умираю",
    "я умираю", "не хочу умереть", "не хочу умирать", "не умираю",
)
_NEGATED_IDEATION = ("не хочу умереть", "не хочу умирать", "не умираю")

BREATHING_PHRASES = (
    "не могу дышать", "не могу вдохнуть", "трудно дышать", "дышать не могу",
    "задыхаюсь", "задохнусь", "нечем дышать",
)

STANDUP_PHRASES = (
    "не могу встать", "не встать", "не могу подняться",
)

ACUTE_PAIN_PHRASES = (
    "всё болит", "сильно болит", "болит сильно", "очень больно",
    "сильная боль", "невыносимая боль", "боль невыносимая", "очень болит",
)

COMPLAINT_PHRASES = ("не очень хорошо", "не очень", "не хорошо",
                     "неважно себя чувствую")

# A control-question answer that STARTS with a denial token ("Нет, не сейчас
# хорошо") denies the concern — the complaint phrase later in the sentence
# refers to the EARLIER context ("до этого болела"). Real call 2026-08-21:
# "Нет, не сейчас хорошо, а почему ты так подумал?" was misread as a
# confirmation and escalated to alert.
_LEADING_DENIALS = ("нет", "неа", "нету")


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

@dataclass
class Observation:
    """What the dialogue layer hands to the SafetyEngine each turn."""
    question: str | None = None        # the question the agent last asked
    raw_text: str | None = None        # cleaned caller transcript
    confidence: float | None = None    # STT confidence 0..1 (None = unknown)
    source: str = "stt"


@dataclass
class VerdictEvent:
    """SafetyEngine output the dialogue machine consumes."""
    kind: str = "unknown"              # no_speech|ok|possible_red|uncertain_red|
                                       # confirmed_red|help_request|third_person|
                                       # unknown|frozen
    confidence: float | None = None
    source: str = ""
    observed: str = ""
    low_confidence: bool = False
    latched: bool = False
    notes: tuple = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tokens(text):
    return re.findall(r"[а-яёa-z]+", (text or "").lower())


def _negated_indexes(tokens):
    """Indexes of tokens negated by a negator within +/- NEG_WINDOW.

    "не могу дышать" is an inability, NOT a negation of "дышать": a negator
    immediately followed by an ability verb does not negate what follows.
    """
    neg = set()
    for i, tok in enumerate(tokens):
        if tok not in NEGATORS:
            continue
        if i + 1 < len(tokens) and tokens[i + 1] in _ABILITY:
            continue
        for j in range(max(0, i - NEG_WINDOW), min(len(tokens), i + NEG_WINDOW + 1)):
            if j != i:
                neg.add(j)
    return neg


def _idx(tokens, word):
    for i, t in enumerate(tokens):
        if t == word:
            return i
    return -1


def _negated_left(tokens, j, window=NEG_WINDOW):
    """True when a negator sits BEFORE token j (leading denial).

    Falls are asymmetric (2026-08-29): only a negator IN FRONT of the fall
    verb cancels it ("я не упал" = no fall), while a negator AFTER it is an
    intensifier, not a denial ("я упал, но не сильно" = the fall HAPPENED,
    "не" just softens how badly). The symmetric ±NEG_WINDOW window used to
    swallow real falls once "не" landed within 3 tokens after the verb.
    """
    for i in range(max(0, j - window), j):
        if tokens[i] in NEGATORS:
            if i + 1 < len(tokens) and tokens[i + 1] in _ABILITY:
                continue
            return True
    return False


# Positive words are only negated by a negator DIRECTLY before them (up to 2
# tokens): «не хорошо», «не совсем хорошо» are complaints; «я отлично
# чувствую, ничего не болела, жива здорова» — the «не» belongs to
# "болела", the trailing "жива здорова" is a SEPARATE positive clause.
POSITIVE_NEG_WINDOW = 2


def _has_phrase(tokens, phrase):
    """True if the phrase's word sequence appears contiguously in tokens.

    The whole engine runs on TOKEN SEQUENCES, never substrings: "не очень"
    must NOT match inside "мне очень хорошо" (S15), "не плох" must NOT match
    inside "мне плохо" (S11).
    """
    words = phrase.split()
    n = len(words)
    for i in range(len(tokens) - n + 1):
        if all(tokens[i + k] == words[k] for k in range(n)):
            return True
    return False


def _has_third(tokens):
    return any(t in THIRD_TOKENS or any(t.startswith(r) for r in THIRD_ROOTS)
               for t in tokens)


def _subject_of(tokens, j, fall=True):
    """Classify the subject near token j: "object" | "third" | "self" | "none".

    Object wins for fall verbs ("упала банка"). Otherwise the NEAREST subject
    marker decides ("мне сказали, что бабушка упала" — the fall belongs to
    бабушка, not the caller).
    """
    lo = max(0, j - NEG_WINDOW)
    hi = min(len(tokens), j + NEG_WINDOW + 1)
    best, best_d = None, 10 ** 9
    for k in range(lo, hi):
        if k == j:
            continue
        tok = tokens[k]
        if fall and any(tok.startswith(r) for r in OBJECT_FALL_ROOTS):
            return "object"
        cls = None
        if tok in THIRD_TOKENS or any(tok.startswith(r) for r in THIRD_ROOTS):
            cls = "third"
        elif tok in SELF_TOKENS:
            cls = "self"
        if cls is not None and abs(k - j) < best_d:
            best_d = abs(k - j)
            best = cls
    return best or "none"


# ---------------------------------------------------------------------------
# The machine
# ---------------------------------------------------------------------------

class SafetyEngine:
    """Stateful per-call safety machine (one instance per Agent)."""

    def __init__(self):
        self._state = "NONE"          # NONE|POSSIBLE_RED|UNCERTAIN_RED|
                                      # CONFIRMED_RED|OK
        self._awaiting = False        # control question pending
        self._frozen = False
        self._last = None

    # -- public API ------------------------------------------------------- #
    def observe(self, obs):
        """Feed one Observation; return a VerdictEvent (never raises)."""
        if self._frozen:
            return self._event("frozen", obs)
        p = self._analyze(obs)
        kind = p["kind"]

        # Low STT confidence (U9): can neither create GREEN nor confirm RED.
        if p["low_conf"]:
            if kind == "ok":
                kind = "unknown"              # cannot confirm a clean bill
            elif kind == "confirmed_red":
                kind = "possible_red"         # cannot confirm an emergency

        # Latch: confirmed RED never downgrades to ok/GREEN. UNCERTAIN_RED
        # (an unconfirmed concern) is NOT latched — a later positive
        # ("уже отпустило", "настроение хорошее") clears it back to OK so
        # the conversation can resume the agenda. Without this, a single
        # "да" on an open question wedged the call in safety_active forever
        # (live post-mortem 2026-08-29: 47/100 synthetic calls never
        # finished — every following turn answered from safety_active).
        if self._state == "CONFIRMED_RED":
            return self._event("confirmed_red", obs, p, latched=True)

        if kind == "no_speech":
            return self._event("no_speech", obs, p)

        # While a control question is pending, only the ANSWER matters.
        if self._awaiting:
            if p["low_conf"]:
                # U9: low STT confidence can neither confirm RED nor clear to
                # GREEN — even an explicit "да"/"нет" is untrusted when the
                # transcript itself may be a hallucination. Escalate as an
                # unconfirmed concern instead (latched, never GREEN).
                self._state = "UNCERTAIN_RED"
                self._awaiting = False
                return self._event("uncertain_red", obs, p)
            if p["affirmative"]:
                # CONFIRM-QUESTION GATE (2026-08-29): a bare "да"/"ага" only
                # confirms when the pending question is a YES/NO one ("вам
                # плохо?", "нужна помощь?"). If Vera asked an OPEN question
                # ("что вас беспокоит?", "что именно сейчас?") then "да" is
                # a backchannel ("да, слушаю") — NOT a confirmation of
                # danger. Escalate to UNCERTAIN (re-ask) instead of a
                # confirmed_red that alarms the family for a routine
                # complaint (live post-mortem: 7/100 synthetic calls false-
                # alarmed on «да»).
                q = (getattr(obs, "question", None) or "").lower()
                if q and not re.search(r"(плохо|неважно|нужна помощь|"
                                       r"помощь|худо|плохое самочувствие|"
                                       r"больно|болит)", q):
                    self._state = "UNCERTAIN_RED"
                    self._awaiting = False
                    return self._event("uncertain_red", obs, p)
                self._state = "CONFIRMED_RED"
                self._awaiting = False
                return self._event("confirmed_red", obs, p)
            if p["denial"] or kind == "ok":
                self._state = "OK"
                self._awaiting = False
                return self._event("ok", obs, p)
            if kind == "help_request":
                self._awaiting = False
                return self._event("help_request", obs, p)
            if kind == "third_person":
                self._state = "UNCERTAIN_RED"
                self._awaiting = False
                return self._event("uncertain_red", obs, p)
            # anything else: can neither confirm nor clear the concern
            self._state = "UNCERTAIN_RED"
            self._awaiting = False
            return self._event("uncertain_red", obs, p)

        if kind == "confirmed_red":
            self._state = "CONFIRMED_RED"
            return self._event("confirmed_red", obs, p)
        if kind == "possible_red":
            self._state = "POSSIBLE_RED"
            self._awaiting = True
            return self._event("possible_red", obs, p)
        if kind == "help_request":
            return self._event("help_request", obs, p)
        if kind == "third_person":
            return self._event("third_person", obs, p)
        if kind == "ok":
            self._state = "OK"
            return self._event("ok", obs, p)
        return self._event("unknown", obs, p)

    def freeze(self):
        """Terminal (dialogue done): no later turn may change the verdict."""
        self._frozen = True

    @property
    def frozen(self):
        return self._frozen

    @property
    def state(self):
        return self._state

    @property
    def awaiting_confirmation(self):
        return self._awaiting

    @property
    def last_event(self):
        return self._last

    # -- helpers ---------------------------------------------------------- #
    def _event(self, kind, obs, p=None, latched=False):
        ev = VerdictEvent(
            kind=kind,
            confidence=obs.confidence if obs is not None else None,
            source=(obs.source if obs is not None else "") or "",
            observed=(obs.raw_text if obs is not None else None) or "",
            low_confidence=bool(p and p["low_conf"]),
            latched=latched,
            notes=tuple(p["notes"]) if p else (),
        )
        self._last = ev
        return ev

    def _analyze(self, obs):
        """Single-utterance classification (pure). Returns a dict with
        kind, affirmative, denial, low_conf and notes."""
        text = (obs.raw_text or "").strip()
        # Qwen3-ASR не даёт реального сигнала уверенности -> confidence
        # чаще всего None. Неизвестная уверенность = трактуем как
        # низкую (U9): без этого защита не срабатывает вообще.
        low_conf = (obs.confidence is None
                    or obs.confidence < CONFIDENCE_THRESHOLD)
        if not text:
            return {"kind": "no_speech", "affirmative": False,
                    "denial": False, "low_conf": low_conf, "notes": ()}
        tokens = _tokens(text)
        norm = " ".join(tokens)
        negated = _negated_indexes(tokens)
        notes = []

        # ---- 1. ideation (subject/negation aware) ------------------------
        for phrase in IDEATION_PHRASES:
            if not _has_phrase(tokens, phrase):
                continue
            if any(_has_phrase(tokens, np) for np in _NEGATED_IDEATION):
                break  # "не хочу умереть" / "не умираю" -> cleared
            last = phrase.split()[-1]
            j = _idx(tokens, last)
            subj = _subject_of(tokens, j, fall=False) if j >= 0 else "none"
            if subj == "third":
                notes.append("у родных кризис")
                return {"kind": "third_person", "affirmative": False,
                        "denial": False, "low_conf": low_conf,
                        "notes": tuple(notes)}
            if _has_phrase(tokens, "не хочу жить") or (
                    "не" in tokens and "жить" in tokens
                    and "умереть" not in tokens and "умирать" not in tokens):
                # loneliness vs self-harm ambiguity ("не хочу жить",
                # "не хочу жить одна", "не хочу больше жить"): needs a
                # control question, never an automatic RED.
                notes.append("неоднозначный контекст (одиночество/идеация)")
                return {"kind": "possible_red", "affirmative": False,
                        "denial": False, "low_conf": low_conf,
                        "notes": tuple(notes)}
            notes.append("идеация")
            return {"kind": "confirmed_red", "affirmative": True,
                    "denial": False, "low_conf": low_conf,
                    "notes": tuple(notes)}

        # ---- 2. breathing / stand-up / acute pain phrases ----------------
        for group in (BREATHING_PHRASES, STANDUP_PHRASES, ACUTE_PAIN_PHRASES):
            for phrase in group:
                if not _has_phrase(tokens, phrase):
                    continue
                last = phrase.split()[-1]
                j = _idx(tokens, last)
                subj = _subject_of(tokens, j) if j >= 0 else "none"
                if subj == "third":
                    notes.append("у близких острая проблема")
                    return {"kind": "third_person", "affirmative": False,
                            "denial": False, "low_conf": low_conf,
                            "notes": tuple(notes)}
                notes.append("острая симптоматика")
                return {"kind": "confirmed_red", "affirmative": True,
                        "denial": False, "low_conf": low_conf,
                        "notes": tuple(notes)}

        # ---- 3. complaint phrases ("не очень хорошо" IS a complaint) -----
        for phrase in COMPLAINT_PHRASES:
            if not _has_phrase(tokens, phrase):
                continue
            if tokens and tokens[0] in _LEADING_DENIALS:
                # "Нет, не сейчас хорошо" answers the control question with
                # NO — clear instead of confirm.
                notes.append("отрицание в начале ответа на контрольный вопрос")
                return {"kind": "denial", "affirmative": False,
                        "denial": True, "low_conf": low_conf,
                        "notes": tuple(notes)}
            if _has_third(tokens) and not any(t in SELF_TOKENS for t in tokens):
                notes.append("жалоба близкого")
                return {"kind": "third_person", "affirmative": False,
                        "denial": False, "low_conf": low_conf,
                        "notes": tuple(notes)}
            notes.append("неважное самочувствие")
            return {"kind": "possible_red", "affirmative": True,
                    "denial": False, "low_conf": low_conf,
                    "notes": tuple(notes)}

        # ---- 4. health-metric fall ("давление упало") --------------------
        for j, t in enumerate(tokens):
            if t.startswith(("упа", "пада")) and j not in negated and \
                    any(any(t2.startswith(m) for m in HEALTH_METRIC_FALL_ROOTS)
                        for t2 in tokens[max(0, j - NEG_WINDOW):
                                         j + NEG_WINDOW + 1]):
                notes.append("показатель здоровья упал")
                return {"kind": "possible_red", "affirmative": True,
                        "denial": False, "low_conf": low_conf,
                        "notes": tuple(notes)}

        # ---- 5. emergency exact tokens ------------------------------------
        for j, tok in enumerate(tokens):
            if tok not in EMERGENCY_TOKENS or j in negated:
                continue
            if tok in ("инфаркт", "инсульт") and \
                    _subject_of(tokens, j) == "third":
                notes.append("у близкого острая проблема")
                return {"kind": "third_person", "affirmative": False,
                        "denial": False, "low_conf": low_conf,
                        "notes": tuple(notes)}
            # SUBJECT FILTER (2026-08-29): «врача/врачу/доктора/доктору/
            # срочно/срочная» are NOT emergencies on their own — a routine
            # "записалась к врачу", "сходил к доктору" or "бабушке срочно
            # нужен врач" is a normal life event, not a confirmed emergency.
            # Only a SELF-directed acute context ("мне нужен врач прямо
            # сейчас", "вызовите мне врача") escalates to confirmed_red.
            if tok in _CONTEXTUAL_EMERGENCY_TOKENS:
                subj = _subject_of(tokens, j)
                if subj == "third":
                    notes.append("у близкого проблема")
                    return {"kind": "third_person", "affirmative": False,
                            "denial": False, "low_conf": low_conf,
                            "notes": tuple(notes)}
                # Self or unattributed is NOT enough: "сходил к врачу" has
                # no acute marker. Require an acute companion word nearby.
                if not any(
                        t.startswith(("сроч", "скор", "неотлож", "выз", "нуж",
                                      "помог", "сейч", "немедл", "прям",
                                      "вызови", "звони", "нужен", "нужно",
                                      "нужна"))
                        for t in tokens[max(0, j - NEG_WINDOW):
                                        j + NEG_WINDOW + 1]):
                    continue
            notes.append("экстренная ситуация")
            return {"kind": "confirmed_red", "affirmative": True,
                    "denial": False, "low_conf": low_conf,
                    "notes": tuple(notes)}

        # ---- 6. token scan: high / med / help / meds / positive ----------
        high_self = high_third = False
        med_self = med_third = False
        help_request = False
        meds_taken = False
        pos_found = False
        object_fall_seen = False
        dropped_seen = False

        for j, tok in enumerate(tokens):
            is_neg = j in negated
            if tok in _DROP_TOKENS:
                dropped_seen = True
                continue
            if any(tok.startswith(r) for r in ("вста", "подн")):
                # Rising/getting up is a NORMAL daily action ("встала с утра",
                # "поднялась на этаж"). Only the INVERSE is distress:
                # "не встаю", "не могу встать", "не поднялась". Without this
                # guard a routine "встала" fired a false emergency, while a
                # real "не встаю" was silently skipped as negated.
                cannot = is_neg or (
                    any(n in tokens for n in ("не", "ни"))
                    and any(t.startswith(("смог", "смож", "мог", "мож"))
                            for t in tokens))
                if cannot:
                    high_self = True
                continue
            if any(tok.startswith(r)
                   for r in ("кровь", "крови", "кровотеч", "кровоизл")):
                # Blood words — NOT the "кров" prefix: "кровать" (bed) is an
                # everyday word and must never trigger an emergency.
                if not is_neg:
                    if _subject_of(tokens, j) == "third":
                        high_third = True
                    else:
                        high_self = True
                continue
            if any(tok.startswith(r) for r in POSITIVE_ROOTS):
                # POSITIVE ASYMMETRY (2026-08-29): «я отлично чувствую,
                # ничего НЕ болела» — the "не" negates "болела", NOT the
                # "отлично" two words before it. The symmetric ±window used
                # to flip a clean bill of health into "не хорошо" (possible_
                # red) and Vera answered "вам сейчас плохо?" to a caller
                # who said they feel great. A positive is only negated by a
                # negator DIRECTLY before it (narrow window) — «не хорошо»
                # is a complaint, but «отлично ... не болела, жива здорова»
                # keeps the trailing positive clause separate.
                if _negated_left(tokens, j, window=POSITIVE_NEG_WINDOW):
                    # "не хорошо" is a complaint; "не жалуюсь" is fine.
                    # LEADING-DENIAL override: "Нет, не сейчас хорошо" answers
                    # the control question with NO — the complaint refers to
                    # the earlier context, not the current state.
                    if not tok.startswith(("жал", "неплох")) \
                            and tokens[0] not in _LEADING_DENIALS:
                        notes.append("неважное самочувствие (не хорошо)")
                        return {"kind": "possible_red", "affirmative": True,
                                "denial": False, "low_conf": low_conf,
                                "notes": tuple(notes)}
                else:
                    pos_found = True
            if any(tok.startswith(r) for r in ("упа", "пада")):
                # FALL ASYMMETRY (2026-08-29): only a negator BEFORE the
                # fall verb cancels it ("я не упал"); a negator AFTER is an
                # intensifier ("я упал, но не сильно" = the fall happened).
                # The symmetric ±window used to swallow real falls once "не"
                # landed within 3 tokens after the verb.
                if _negated_left(tokens, j):
                    continue
                subj = _subject_of(tokens, j)
                if subj == "object":
                    object_fall_seen = True
                    continue
                if subj == "third":
                    high_third = True
                    continue
                if subj == "self":
                    high_self = True
                    continue
                # NO SUBJECT: distinguish a METRIC/THING "falling" from a
                # PERSON falling. «настроение упало», «давление упало»,
                # «что-то упало» — a metric or an inanimate thing "falling"
                # is NOT a person falling (real call f7f7605d7d03: Vera
                # alarmed the family for a bad mood). But bare «упала»/
                # «упал» IS a person (the «я» is dropped in speech — the
                # safety corpus requires confirmed_red for them).
                # A metric subject can be FAR from the verb («настроение в
                # принципе хорошее, но сегодня днём упало» — 8 tokens).
                nearby = tokens[max(0, j - FALL_SUBJECT_WINDOW):
                                j + FALL_SUBJECT_WINDOW + 1]
                is_metric = any(
                    tok2.startswith(r)
                    for r in HEALTH_METRIC_FALL_ROOTS + ("настроени",)
                    for tok2 in nearby)
                is_thing = any(t2 in _THING_FALL_SUBJECTS for t2 in nearby)
                if is_metric:
                    notes.append("показатель здоровья/настроение упало")
                    return {"kind": "possible_red", "affirmative": True,
                            "denial": False, "low_conf": low_conf,
                            "notes": tuple(notes)}
                if is_thing:
                    # «что-то/ничего/всё упало» — ambiguous, ask
                    med_self = True
                    continue
                # otherwise a subject-less fall verb IS a person falling
                high_self = True
            if is_neg:
                continue
            if any(tok.startswith(r) for r in HIGH_ROOTS):
                if _subject_of(tokens, j) == "third":
                    high_third = True
                else:
                    high_self = True
            if any(tok.startswith(r) for r in MED_ROOTS):
                if _subject_of(tokens, j) == "third":
                    med_third = True
                else:
                    med_self = True
            if any(tok.startswith(r) for r in HELP_ROOTS):
                # Past-tense forms ("купила", "сходила", "позвонила") are
                # STATEMENTS about the past, not requests; only imperatives
                # ("купите", "сходи", "позвоните", "передайте") and
                # needs ("нужна помощь", "требуется") are real help signals.
                if tok.endswith(("ла", "ли", "ло", "л")) or tok in (
                        "помог", "принес", "принёс"):
                    continue
                help_request = True
            if any(tok.startswith(r) for r in MEDS_ROOTS):
                meds_taken = True

        if high_self:
            notes.append("острая симптоматика")
            return {"kind": "confirmed_red", "affirmative": True,
                    "denial": False, "low_conf": low_conf,
                    "notes": tuple(notes)}
        if high_third:
            notes.append("у близких проблема")
            return {"kind": "third_person", "affirmative": False,
                    "denial": False, "low_conf": low_conf,
                    "notes": tuple(notes)}
        if med_self:
            notes.append("плохое самочувствие")
            return {"kind": "possible_red", "affirmative": True,
                    "denial": False, "low_conf": low_conf,
                    "notes": tuple(notes)}
        if med_third:
            notes.append("у близких недомогание")
            return {"kind": "third_person", "affirmative": False,
                    "denial": False, "low_conf": low_conf,
                    "notes": tuple(notes)}
        if help_request:
            # Phrase-level guard: a statement about the PAST is not a
            # request. "Купила продукты", "передала родным" — no help.
            # "Купите продукты", "мне нужна помощь" — help. A past-tense
            # verb with no imperative/need word means "it already happened".
            past_verbs = any(t.endswith(("ла", "ли", "ло", "л"))
                             for t in tokens)
            if past_verbs and not any(
                    t.endswith(("ите", "ьте")) or t in _IMPERATIVE
                    or t in _NEED_WORDS for t in tokens):
                notes.append("запрос помощи (прошедшее время)")
                return {"kind": "unknown", "affirmative": False,
                        "denial": False, "low_conf": low_conf,
                        "notes": tuple(notes)}
            notes.append("запрос помощи")
            return {"kind": "help_request", "affirmative": False,
                    "denial": False, "low_conf": low_conf,
                    "notes": tuple(notes)}
        if meds_taken:
            notes.append("принимает лекарства")
            return {"kind": "ok", "affirmative": False, "denial": False,
                    "low_conf": low_conf, "notes": tuple(notes)}
        if pos_found:
            return {"kind": "ok", "affirmative": False, "denial": False,
                    "low_conf": low_conf, "notes": ()}
        if object_fall_seen:
            # an inanimate object fell ("упала банка") — nothing concerning
            return {"kind": "ok", "affirmative": False, "denial": False,
                    "low_conf": low_conf, "notes": ()}
        if dropped_seen:
            # "я уронил телефон" — dropped something, not a fall
            return {"kind": "ok", "affirmative": False, "denial": False,
                    "low_conf": low_conf, "notes": ()}

        # ---- 7. short standalone answers ---------------------------------
        if _has_phrase(tokens, "не знаю") or _has_phrase(tokens, "не помню"):
            # "не знаю" is a NON-answer, not a denial of distress.
            return {"kind": "unknown", "affirmative": False, "denial": False,
                    "low_conf": low_conf, "notes": ()}
        if any(t in AFFIRMATIVE for t in tokens) and not any(
                t in DENIAL for t in tokens):
            return {"kind": "help_request", "affirmative": True,
                    "denial": False, "low_conf": low_conf,
                    "notes": ("подтверждение",)}
        if any(t in DENIAL for t in tokens):
            return {"kind": "ok", "affirmative": False, "denial": True,
                    "low_conf": low_conf, "notes": ()}
        return {"kind": "unknown", "affirmative": False, "denial": False,
                "low_conf": low_conf, "notes": ()}