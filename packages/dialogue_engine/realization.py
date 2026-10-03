"""Meaning-driven realization — how Vera says it.

Owner: Renderer. This module never decides *what* happens next, never writes
state, never calls a model, and never invents a fact. It composes the spoken
surface from:

* the move the scheduler already chose (the ``ResponsePlan``), and
* what the person actually just said (``EngineState.last_user_text``, bounded
  verbatim, written once per accepted turn by the reducer).

Why not a bigger phrase bank: a bank can only ever return a line that was
written in advance, so it cannot show that Vera heard *this* person. A
composition takes a grounded content word out of the person's own sentence,
inflects it, and puts it into a stance frame chosen by meaning — which is why
the same code produces «Про внуков поняла.» here and «Про настроение поняла.»
there, without either sentence being stored anywhere.

Hard boundaries (do not weaken):

* no clinical/family fact is created here — only the person's own word is
  reflected back;
* safety/control/consent/urgent/close surfaces keep their exact phrases and
  never pass through this module;
* a reaction is always attached to a real move, never a standalone turn;
* exact repeats are refused through the existing speech ledger.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from packages.dialogue_engine.speech_ledger import is_verbatim_repeat

if TYPE_CHECKING:
    from packages.dialogue_engine.state import EngineState

__all__ = ["HeardTopic", "heard_topic", "reaction_clause", "MAX_REACTION_CHARS"]

MAX_REACTION_CHARS = 60

# Words that carry no topic worth reflecting back, or that already belong to
# the question Vera is about to ask. Deliberately small: a wrong reflection is
# worse than no reflection, so anything doubtful is skipped below.
_TOPIC_STOP = frozenset(
    {
        "сегодня", "вчера", "завтра", "позавчера", "утром", "вечером", "ночью",
        "днем", "сейчас", "потом", "воскресенье", "понедельник", "вторник",
        "среда", "четверг", "пятница", "суббота", "неделя", "месяц", "год",
        "вечер", "утро", "ночь", "день", "обед", "полдень", "час", "минута",
        "начало", "конец", "давно", "раньше", "теперь",
        "время", "раз", "дело", "штука", "вроде", "наверное", "конечно",
        "спасибо", "пожалуйста", "здравствуйте", "до свидания", "алло",
        "привет", "приветик", "здравствуй", "добрый", "доброе", "пока",
        "богу", "слава", "господи", "человек", "люди", "все", "всё",
    }
)

# How an elderly person addresses the voice on the phone. These are vocatives,
# not topics: reflecting «доченька» back produced «Спасибо, что рассказали про
# доченьку» as the answer to «Ничего не тревожит, доченька.» on a live call.
# Diminutives are listed because they are address forms in this register, while
# the plain kinship nouns (дочка, внук, сын) stay reflectable as real topics.
_ADDRESS_TERMS = frozenset(
    {
        "внученька", "внучек", "доченька", "дочурка",
        "сыночек", "сынок", "сынуля", "мамочка", "мамуля", "мама", "папочка",
        "папа", "бабуля", "бабулька", "бабушка", "дедуля", "дедушка",
        "милая", "милок", "милочка", "дорогая", "дорогой", "родная", "родной",
        "солнышко", "голубушка", "голубчик", "деточка", "детка", "крошка",
        "вера", "верочка", "амвера", "имвера", "помощник", "робот", "девушка",
        "женщина", "гражданка", "товарищ",
    }
)

# Spoken particles glued to a word («внуки-то», «давай-ка») are not part of it.
_PARTICLE_RE = re.compile(r"-(?:то|ка|таки|де|с|ста)$")

# Stance frames. A frame takes the reflected noun in the accusative after
# «про». Each carries the pattern that identifies it in a spoken surface, so
# the same sentence shape is not used twice in a call: with several reactions
# the person hears several different acknowledgements, not one repeated.
_TOPIC_FRAMES: tuple[tuple[str, str], ...] = (
    ("Про {acc} поняла.", r"\bпро \S+ поняла\b"),
    ("Поняла про {acc}.", r"\bпоняла про \S+"),
    ("Спасибо, что рассказали про {acc}.", r"\bспасибо что рассказали про \S+"),
    ("Про {acc} услышала.", r"\bпро \S+ услышала\b"),
)

# Topics talked about in the last few turns are not parroted again.
_RECENT_WINDOW = 6

_WORD_RE = re.compile(r"[А-Яа-яЁё][А-Яа-яЁё-]{3,}")


@dataclass(frozen=True)
class HeardTopic:
    """A content word the person used, normalised for safe reflection."""

    noun: str   # nominative normal form
    acc: str    # accusative form used by the frames
    quote: str  # the person's own words, bounded


def _analyse(word: str):
    from packages.dialogue_engine.semantic_kernel.morphology import _load_morph

    morph = _load_morph()
    if morph is None:
        return None
    parsed = morph.parse(word)
    if not parsed:
        return None
    best = parsed[0]
    # An ambiguous parse produces a wrong reflection; abstain instead.
    if best.score < 0.5:
        return None
    if "NOUN" not in best.tag:
        return None
    return best


def heard_topic(text: str) -> HeardTopic | None:
    """The first solid noun the person used, or None when nothing is safe.

    Returns None for backchannels, questions, and anything whose morphology is
    uncertain — a missing reaction is acceptable, a wrong one is not.
    """
    raw = (text or "").strip()
    if len(raw) < 4:
        return None
    from packages.dialogue_engine.deterministic_mission import _is_user_question

    if _is_user_question(raw):
        return None
    for match in _WORD_RE.finditer(raw):
        word = match.group(0).lower().replace("ё", "е")
        word = _PARTICLE_RE.sub("", word)
        if word in _TOPIC_STOP or word in _ADDRESS_TERMS:
            continue
        # Vocative position: «…, дочка.» or «Дочка, …» addresses Vera, while
        # «дочку свою не видела» is a real topic about the person's family.
        _after = raw[match.end():].lstrip()
        _before = raw[: match.start()].rstrip()
        if _after.startswith(",") or (_before.endswith(",") and not _after):
            continue
        parsed = _analyse(word)
        if parsed is None:
            continue
        noun = parsed.normal_form
        if noun in _TOPIC_STOP or noun in _ADDRESS_TERMS or len(noun) < 4:
            continue
        acc = parsed.inflect({"accs"})
        acc_form = acc.word if acc is not None else noun
        return HeardTopic(noun=noun, acc=acc_form, quote=raw[:200])
    return None


def _topic_recently_spoken(state: EngineState, topic: HeardTopic) -> bool:
    """True when this topic was already reflected in the last few turns."""
    stem = topic.noun[:4]
    for surface in state.spoken_surfaces[-_RECENT_WINDOW:]:
        if stem in surface:
            return True
    return False


def _frame_for(state: EngineState, topic: HeardTopic) -> str:
    """The first frame whose shape was not already used in the recent turns.

    Avoiding the exact clause is not enough: «Про внуков поняла.» and «Про
    пирог поняла.» are different sentences with the same shape, and a call that
    repeats one shape four times still sounds like a form.
    """
    import re

    recent = state.spoken_surfaces[-_RECENT_WINDOW:]
    fallback = ""
    for frame, pattern in _TOPIC_FRAMES:
        clause = frame.format(acc=topic.acc)
        if len(clause) > MAX_REACTION_CHARS:
            continue
        if is_verbatim_repeat(state.spoken_surfaces, clause):
            continue
        if not fallback:
            fallback = clause
        if not any(re.search(pattern, surface) for surface in recent):
            return clause
    return fallback


# A question the person answered has a topic even when their sentence has no
# noun («Да, поел.», «Принимаю.»). The wording says only what the answer
# confirmed: polarity picks the stance, and the person's own verb is reused so
# the reply still matches what they said.
#
# Keys are both shapes the engine uses: check-in slots (wellness, mood, sleep,
# plans) and coverage domains (wellbeing, medication, nutrition). A slot that
# is missing here silently loses its reaction — that was a real bug.
_DOMAIN_ACK = {
    "positive": {
        "wellness": "Спасибо, что сказали, как себя чувствуете.",
        "wellbeing": "Спасибо, что сказали, как себя чувствуете.",
        "plans": "Хорошо, что поделились планами.",
        "nutrition": "Хорошо, что поели.",
        "sleep": "Хорошо, что выспались.",
        "medication": "Хорошо, что сказали про лекарства.",
        "mood": "Спасибо, что сказали про настроение.",
    },
    # Polarity unknown: say only that the answer was heard. Claiming «Хорошо,
    # что…» for a value nobody measured is the same class of error as inventing
    # a fact, and it read tone-deaf on live refusals.
    "unknown": {
        "wellness": "Спасибо, что сказали, как себя чувствуете.",
        "wellbeing": "Спасибо, что сказали, как себя чувствуете.",
        "plans": "Спасибо, что рассказали про планы.",
        "nutrition": "Спасибо, что сказали про еду.",
        "sleep": "Спасибо, что сказали, как спалось.",
        "medication": "Хорошо, что сказали про лекарства.",
        "mood": "Спасибо, что сказали про настроение.",
    },
    "negative": {
        "wellness": "Понимаю, спасибо, что сказали, как себя чувствуете.",
        "wellbeing": "Понимаю, спасибо, что сказали, как себя чувствуете.",
        "plans": "Хорошо, что поделились планами.",
        "nutrition": "Поняла, пока не ели.",
        "sleep": "Понимаю, ночь была тяжёлая.",
        "medication": "Понимаю, про лекарства услышала.",
        "mood": "Понимаю, спасибо, что сказали про настроение.",
    },
}

# A topic having been discussed is not evidence of a positive outcome. In
# particular, baseline coverage has a verbatim observation, not a SlotValue
# with adjudicated polarity. Do not manufacture one in the renderer.
_NEUTRAL_DOMAIN_ACK = _DOMAIN_ACK["unknown"]


def _current_record(state: EngineState, slot: str):
    record = state.slot_records.get(slot) or state.coverage_records.get(slot)
    if record is None:
        return None
    if state.last_user_utterance_id:
        if record.source_turn_id != state.last_user_utterance_id:
            return None
    elif not record.source_text or record.source_text not in state.last_user_text:
        return None
    return record


def _slot_topic(state: EngineState, facts) -> HeardTopic | None:
    """The topic of a goal the person just answered, from their own words."""
    for slot in facts or ():
        record = _current_record(state, slot)
        if record is not None and record.source_text:
            topic = heard_topic(record.source_text)
            if topic is not None and not _is_elder_name(state, topic.noun):
                return topic
    return None


def _domain_reaction(state: EngineState, facts) -> str:
    for slot in facts or ():
        record = _current_record(state, slot)
        polarity = record.polarity if record is not None else None
        bank = _DOMAIN_ACK.get(polarity, _NEUTRAL_DOMAIN_ACK)
        clause = bank.get(slot, "")
        if clause and not is_verbatim_repeat(state.spoken_surfaces, clause):
            return clause
    return ""


def _answered_this_turn(state: EngineState, facts) -> list[str]:
    """Slots the person actually answered now, not only the declared ones.

    The scheduler often builds the next question without carrying what was just
    answered, so `plan.acknowledge_facts` can be empty on a turn that filled a
    slot. Grounding is the evidence, not the declaration: a slot whose source
    turn is this utterance was answered by this utterance.
    """
    # A plan can carry older facts for a summary. Only current evidence may
    # acknowledge an answer; old facts cannot colour a new refusal/unknown.
    out = [slot for slot in facts or () if _current_record(state, slot) is not None]
    answered_domain = getattr(state, "last_answered_domain", "") or ""
    if answered_domain and answered_domain not in out:
        out.append(answered_domain)
    turn_id = getattr(state, "last_user_utterance_id", "") or ""
    if not turn_id:
        return out
    for slot, record in {**state.coverage_records, **state.slot_records}.items():
        if slot not in out and record.source_turn_id == turn_id:
            out.append(slot)
    return out


def reaction_clause(state: EngineState, facts=()) -> str:
    """A short grounded reaction to the person's own words, or "".

    Callers append it in front of a real move. Empty is a valid answer: when
    nothing can be grounded, Vera simply says the move without a reaction.
    """
    text = getattr(state, "last_user_text", "") or ""
    if _needs_empathy(text):
        # A heavy statement gets empathy, never a chirpy echo of its topic.
        return ""
    facts = _answered_this_turn(state, facts)
    topic = heard_topic(text)
    if topic is not None and _is_elder_name(state, topic.noun):
        topic = None
    if topic is None:
        topic = _slot_topic(state, facts)
    if topic is not None and not _topic_recently_spoken(state, topic):
        clause = _frame_for(state, topic)
        if clause:
            return clause
    return _domain_reaction(state, facts)


# Acks that occupy the reaction slot without saying anything about this person.
# They may be replaced by a grounded reaction; anything that already refers to
# content is kept.
_GENERIC_ACKS = frozenset(
    {
        "хорошо", "хорошо поняла", "хорошо спасибо", "поняла", "поняла вас",
        "понимаю", "ясно", "ладно", "записала", "спасибо",
        "спасибо что рассказали", "спасибо все записала", "да слышу",
        "да слышу вас", "так", "угу", "хорошо записала",
        # The listener clause says nothing about this person either; the
        # invitation that follows it is the move. A grounded reaction is
        # strictly more informative in front of it.
        "я вас слушаю", "слушаю вас", "я слушаю",
    }
)


def _is_elder_name(state: EngineState, noun: str) -> bool:
    """Vera must not reflect the person's own name back as a topic."""
    name = (getattr(state, "elder_display_name", "") or "").lower().replace("ё", "е")
    if not name:
        return False
    return any(part[:4] == noun[:4] for part in name.split() if len(part) >= 4)


def _needs_empathy(text: str) -> bool:
    """True when the person's own words call for empathy instead of reflection.

    Distress and fatigue are owned by the safety/control layer, which answers
    them with an exact phrase. A topic echo would talk over that.
    """
    from packages.dialogue_engine.conversation_policy import (
        _has_distress_markers,
        _has_fatigue_markers,
    )

    return bool(_has_distress_markers(text) or _has_fatigue_markers(text))


def is_content_free_ack(text: str) -> bool:
    """True for a reaction slot filled with nothing about this person."""
    from packages.dialogue_engine.speech_ledger import is_banned_standalone, normalize

    norm = normalize(text)
    if not norm:
        return True
    return norm in _GENERIC_ACKS or is_banned_standalone(text)
