"""Semantic agenda — product flow with wellness bands and adaptive paths."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Mapping, Sequence

from conversation_system.agenda.topics import (
    BAD_WORDS,
    CANONICAL_AGENDA_TOPICS,
    FAMILY_TOPIC_LABEL,
    GOOD_PROBE_SUBTOPICS,
    OK_WORDS,
    TOPIC_BAD_SYMPTOM,
    TOPIC_CLOSING,
    TOPIC_GOOD_PROBE,
    TOPIC_RECORD_NOTIFY,
    TOPIC_WELLNESS,
    TOPIC_KEYS,
)
from conversation_system.domain.understanding import (
    FamilyQuestion,
    MemoryPatch,
    SpeechAct,
    TurnUnderstanding,
)
from conversation_system.domain.wellness import (
    WellnessBand,
    bad_path_probe_count,
    classify_wellness,
    closing_requires_fast_exit,
    good_path_probe_count,
)
from conversation_system.reply.pools import (
    BAD_SYMPTOM_PROBE_POOL,
    GOOD_PROBE_POOL,
    GREETING_POOL,
    MEDIUM_SYMPTOM_PROBE_POOL,
    RECORD_NOTIFY_POOL,
    WELLNESS_REASK_POOL,
    goodbye_pool_for_band,
    pick_from_pool,
)
from conversation_system.turn._classifiers import is_refusal
from conversation_system.turn._cleaners import short_real_answer, wellness_short_answer
from conversation_system.turn.analyzer import matches_topic, mentions_symptom

# Single-word answers to scripted BAD_SYMPTOM_PROBE_POOL questions (intensity,
# timing, yes/no) — must close the probe without dead-end ack on BAD_PATH.
_REPAIR_RESTATEMENT_RE = re.compile(
    r"я\s+же\s+(?:сказал|говорил|сказала|говорила)|"
    r"уже\s+(?:сказал|говорил|сказала|говорила)|"
    r"повторяю\s+(?:же\s+)?(?:что|вам)?",
    re.IGNORECASE,
)

_SEVERITY_LEXICON_RE = re.compile(
    r"сильн|терпим|норм|слаб|не\s*сильн|немного|чуть|"
    r"невыносим|ужасн|терплю|посильн",
    re.IGNORECASE,
)

_SYMPTOM_PROBE_SHORT_WORDS = frozenset((
    "сильно", "слабо", "терпимо", "терпимая", "сильная", "сильнее", "слабее",
    "очень", "немного", "чуть", "невыносимо", "непереносимо", "терплю",
    "утром", "вечером", "вчера", "ночью", "сегодня", "давно", "недавно",
    "постоянно", "волнами", "иногда", "регулярно", "периодически",
    "хуже", "лучше", "также", "похоже", "неизменно", "без", "изменений",
    "принимал", "принимала", "приняла", "принял", "выпила", "выпил",
    "есть", "нету",
))


@dataclass
class InterruptionFrame:
    """Saved agenda position when a side question interrupts the flow."""

    return_phase: str = ""
    return_slot_index: int = -1
    return_slot: str = ""
    return_question_id: str = ""


@dataclass
class AgendaTopic:
    """One walkable agenda entry."""

    key: str
    spoken_prompt: str = ""
    is_family: bool = False
    family_id: str = ""


@dataclass
class AgendaManager:
    """Check-in agenda: wellness listen → adaptive probe → record → closing."""

    topics: List[AgendaTopic] = field(default_factory=list)
    cursor: int = 0
    question_open: bool = False
    done: bool = False
    paused: bool = False
    deferred_topic: str = ""
    wellness_band: WellnessBand = WellnessBand.UNKNOWN
    good_probe_index: int = 0
    bad_symptom_probe_index: int = 0
    greeting_index: int = 0
    _greeting_text: str = ""
    record_notified: bool = False
    on_bad_path: bool = False
    on_good_path: bool = False
    interruption: InterruptionFrame = field(default_factory=InterruptionFrame)
    covered_good_slots: List[str] = field(default_factory=list)
    _last_covered_slot: str = field(default="", repr=False)

    @classmethod
    def from_canonical(cls) -> "AgendaManager":
        entries = [
            AgendaTopic(key=t, spoken_prompt="")
            for t in CANONICAL_AGENDA_TOPICS
        ]
        return cls(topics=entries)

    @classmethod
    def load_from_scenarios(cls, scenarios_text: str = "") -> "AgendaManager":
        """Build agenda; legacy vera_scenarios no longer drives topic order."""
        return cls.from_canonical()

    def inject_family_questions(
        self,
        items: Sequence[Mapping[str, str]] | Sequence[FamilyQuestion],
        *,
        limit: int = 5,
    ) -> None:
        """Append family-app questions before closing topic."""
        closing_idx = self._closing_topic_index()
        insert_at = closing_idx if closing_idx >= 0 else len(self.topics)
        new_topics: list[AgendaTopic] = []
        for raw in list(items)[:limit]:
            if isinstance(raw, FamilyQuestion):
                fq = raw
            else:
                text = str(raw.get("text") or "").strip()
                if not text:
                    continue
                author = str(raw.get("author") or "").strip() or "Родные"
                fq = FamilyQuestion(
                    id=str(raw.get("id") or ""),
                    text=text,
                    author=author,
                )
            spoken = f"Вопрос от родных ({fq.author}): {fq.text}"
            new_topics.append(AgendaTopic(
                key=FAMILY_TOPIC_LABEL,
                spoken_prompt=spoken,
                is_family=True,
                family_id=fq.id,
            ))
        for i, topic in enumerate(new_topics):
            self.topics.insert(insert_at + i, topic)

    def _closing_topic_index(self) -> int:
        for i, t in enumerate(self.topics):
            if t.key == TOPIC_CLOSING:
                return i
        return -1

    def current_good_slot(self, ledger=None) -> str:
        """Active good-path sub-topic (mood / sleep / plans).

        When *ledger* is provided, skip slots already ANSWERED in QuestionLedger
        (source of truth) instead of relying on good_probe_index alone.
        """
        if not self.on_good_path:
            return ""
        if ledger is not None and hasattr(ledger, "can_ask_slot"):
            for slot in GOOD_PROBE_SUBTOPICS:
                if ledger.can_ask_slot(slot):
                    return slot
            return ""
        idx = min(self.good_probe_index, len(GOOD_PROBE_SUBTOPICS) - 1)
        return GOOD_PROBE_SUBTOPICS[idx]

    def covered_slots(self) -> tuple[str, ...]:
        return tuple(self.covered_good_slots)

    def forbidden_slots(self, ledger=None) -> tuple[str, ...]:
        current = self.current_good_slot()
        covered = set(self.covered_good_slots)
        if ledger is not None and hasattr(ledger, "forbidden_slots"):
            covered.update(ledger.forbidden_slots())
        return tuple(
            s for s in GOOD_PROBE_SUBTOPICS
            if s in covered and s != current
        )

    def slot_must_do(self, slot: str = "") -> str:
        target = (slot or self.current_good_slot()).strip()
        labels = {
            "настроение": "настроении",
            "сон": "сне",
            "планы": "планах на день",
        }
        phrase = labels.get(target, target)
        return f"Спроси ТОЛЬКО о {phrase} — одним естественным вопросом."

    def mark_good_slot_covered(self, slot: str) -> None:
        s = (slot or "").strip()
        if s and s not in self.covered_good_slots:
            self.covered_good_slots.append(s)
            self._last_covered_slot = s

    def consume_last_covered_slot(self) -> str:
        s = (self._last_covered_slot or "").strip()
        self._last_covered_slot = ""
        return s

    def assign_greeting(self, text: str) -> None:
        """Pin per-call greeting chosen at session open (variety engine)."""
        t = (text or "").strip()
        if t:
            self._greeting_text = t

    def greeting_text(self) -> str:
        """Mandatory first turn: varied greeting + how they feel."""
        if self._greeting_text:
            return self._greeting_text
        return pick_from_pool(GREETING_POOL, index=self.greeting_index)

    def current_topic(self) -> AgendaTopic | None:
        if self.done or self.cursor >= len(self.topics):
            return None
        return self.topics[self.cursor]

    def current_topic_key(self) -> str:
        topic = self.current_topic()
        return topic.key if topic else ""

    def next_topic_key(self) -> str:
        nxt = self.cursor + 1
        if nxt >= len(self.topics):
            return ""
        return self.topics[nxt].key

    def set_wellness_from_text(self, text: str) -> WellnessBand:
        """Classify and store wellness band after initial listen."""
        self.wellness_band = classify_wellness(text)
        if self.wellness_band == WellnessBand.GOOD:
            self.on_good_path = True
            self.on_bad_path = False
        elif self.wellness_band in (
            WellnessBand.BAD,
            WellnessBand.CRITICAL,
            WellnessBand.MEDIUM,
        ):
            self.on_bad_path = True
            self.on_good_path = False
        return self.wellness_band

    def apply_path_after_wellness(
        self,
        understanding: TurnUnderstanding | None = None,
    ) -> MemoryPatch:
        """After wellness listen: branch cursor to good or bad probe topic."""
        if self.wellness_band == WellnessBand.CRITICAL:
            # Skip probes — jump to record_notify
            self._seek_topic(TOPIC_RECORD_NOTIFY)
            return MemoryPatch(
                set_field={
                    "flags": {"on_bad_path": True},
                },
            )
        if self.wellness_band == WellnessBand.GOOD:
            self.on_good_path = True
            self._seek_topic(TOPIC_GOOD_PROBE)
            self.good_probe_index = 0
        else:
            self.on_bad_path = True
            self._seek_topic(TOPIC_BAD_SYMPTOM)
            self.bad_symptom_probe_index = self._initial_bad_probe_index(
                understanding,
            )
        return MemoryPatch(
            set_field={
                "flags": {
                    "on_good_path": self.on_good_path,
                    "on_bad_path": self.on_bad_path,
                },
            },
        )

    def _initial_bad_probe_index(
        self,
        understanding: TurnUnderstanding | None,
    ) -> int:
        """Skip generic «что беспокоит» when symptoms already named."""
        if understanding is None:
            return 0
        text = (understanding.clean_text or "").strip()
        if understanding.symptom_focus or mentions_symptom(text):
            return 1
        return 0

    def _has_severity_signal(self, text: str) -> bool:
        if not (text or "").strip():
            return False
        return bool(_SEVERITY_LEXICON_RE.search(text.lower()))

    def _is_probe_repair_phrase(self, understanding: TurnUnderstanding) -> bool:
        if understanding.speech_act in (
            SpeechAct.REPAIR,
            SpeechAct.META_CONFUSION,
        ):
            return True
        text = (understanding.clean_text or "").strip()
        if not text:
            return False
        return bool(_REPAIR_RESTATEMENT_RE.search(text.lower()))

    def _seek_topic(self, key: str) -> bool:
        for i, t in enumerate(self.topics):
            if t.key == key:
                self.cursor = i
                self.question_open = False
                return True
        return False

    def mark_question_asked(self) -> str:
        topic = self.current_topic()
        if topic is not None:
            self.question_open = True
            return topic.key
        return ""

    def advance(self) -> bool:
        """Move cursor forward; return True if agenda just finished."""
        if self.done:
            return True
        topic = self.current_topic()
        if topic is None:
            self.done = True
            return True
        self.cursor += 1
        self.question_open = False
        self.deferred_topic = ""
        if self.cursor >= len(self.topics):
            self.done = True
            return True
        return self.done

    def advance_good_probe(self) -> bool:
        """Advance within good-path probes (2–3 questions)."""
        self.good_probe_index += 1
        if self.good_probe_index >= good_path_probe_count():
            self._seek_topic(TOPIC_RECORD_NOTIFY)
            return False
        return True

    def advance_bad_symptom_probe(self) -> bool:
        """Advance bad-path symptom depth; after depth budget → record."""
        self.bad_symptom_probe_index += 1
        if self.bad_symptom_probe_index >= bad_path_probe_count():
            self._seek_topic(TOPIC_RECORD_NOTIFY)
            return False
        return True

    def defer_current(
        self,
        *,
        phase: str = "",
        return_question_id: str = "",
    ) -> MemoryPatch:
        topic = self.current_topic_key()
        self.paused = True
        self.question_open = False
        self.deferred_topic = topic
        self.interruption = InterruptionFrame(
            return_phase=(phase or "").strip(),
            return_slot_index=self.good_probe_index,
            return_slot=self.current_good_slot(),
            return_question_id=(return_question_id or "").strip(),
        )
        return MemoryPatch(
            set_field={
                "deferred_topic": topic,
                "flags": {"agenda_paused": True, "agenda_question_open": False},
            },
        )

    def resume(self) -> MemoryPatch:
        self.paused = False
        if self.deferred_topic:
            self.question_open = True
        return MemoryPatch(
            set_field={"flags": {"agenda_paused": False}},
        )

    def resume_after_interrupt(self) -> MemoryPatch:
        """Restore probe index after side-question — do not restart good path."""
        if self.interruption.return_slot_index >= 0:
            self.good_probe_index = self.interruption.return_slot_index
        self.paused = False
        if self.deferred_topic:
            self.question_open = True
        return MemoryPatch(
            set_field={"flags": {"agenda_paused": False}},
        )

    def clear_interruption(self) -> None:
        self.interruption = InterruptionFrame()

    def closing_text(self, *, hour: int | None = None) -> str:
        """State-dependent goodbye — scripted, no LLM."""
        pool = goodbye_pool_for_band(self.wellness_band, hour=hour)
        return pick_from_pool(pool, index=self.cursor)

    def record_notify_text(self) -> str:
        """Scripted notify relatives — product rule: no promise to call/send."""
        return pick_from_pool(RECORD_NOTIFY_POOL, index=self.good_probe_index)

    def spoken_prompt_for_current(self) -> str:
        """Scripted prompt for current agenda phase — fast path."""
        topic = self.current_topic()
        if topic is None:
            return ""
        if topic.spoken_prompt:
            return topic.spoken_prompt
        key = topic.key
        if key == TOPIC_WELLNESS:
            if self.on_bad_path:
                pool = BAD_SYMPTOM_PROBE_POOL
                if self.wellness_band == WellnessBand.MEDIUM:
                    pool = MEDIUM_SYMPTOM_PROBE_POOL
                return pick_from_pool(
                    pool,
                    index=self.bad_symptom_probe_index,
                )
            if self.question_open or self.on_good_path:
                return pick_from_pool(
                    WELLNESS_REASK_POOL,
                    index=self.greeting_index,
                )
            return pick_from_pool(GREETING_POOL, index=self.greeting_index)
        if key == TOPIC_GOOD_PROBE and self.on_good_path:
            sub = self.current_good_slot()
            idx = min(self.good_probe_index, len(GOOD_PROBE_POOL) - 1)
            prompt = pick_from_pool(GOOD_PROBE_POOL, index=idx)
            if sub and not matches_topic(prompt, sub):
                for offset in range(len(GOOD_PROBE_POOL)):
                    candidate = GOOD_PROBE_POOL[
                        (idx + offset) % len(GOOD_PROBE_POOL)
                    ]
                    if matches_topic(candidate, sub):
                        prompt = candidate
                        break
            return prompt
        if key == TOPIC_BAD_SYMPTOM and self.on_bad_path:
            pool = BAD_SYMPTOM_PROBE_POOL
            if self.wellness_band == WellnessBand.MEDIUM:
                pool = MEDIUM_SYMPTOM_PROBE_POOL
            return pick_from_pool(
                pool,
                index=self.bad_symptom_probe_index,
            )
        if key == TOPIC_RECORD_NOTIFY:
            return self.record_notify_text()
        if key == TOPIC_CLOSING:
            return self.closing_text()
        return ""

    def should_fast_close(self) -> bool:
        return closing_requires_fast_exit(self.wellness_band)

    def semantic_close(
        self,
        understanding: TurnUnderstanding,
        *,
        clearing_symptom: bool = False,
    ) -> bool:
        """True when caller content closes the open agenda topic."""
        text = understanding.clean_text
        topic = self.current_topic_key()
        if not topic or not text:
            return False
        current = self.current_topic()
        if current and current.is_family:
            return understanding.word_count >= 1 and understanding.speech_act not in (
                SpeechAct.EMPTY,
                SpeechAct.REPAIR,
                SpeechAct.META_CONFUSION,
            )
        if understanding.speech_act == SpeechAct.REFUSAL:
            if topic == TOPIC_RECORD_NOTIFY:
                return True
            return False
        if topic == TOPIC_WELLNESS:
            band = classify_wellness(text)
            if band in (
                WellnessBand.GOOD,
                WellnessBand.BAD,
                WellnessBand.CRITICAL,
                WellnessBand.MEDIUM,
            ):
                return True
            if wellness_short_answer(text):
                return True
            if not self.question_open:
                return False
            return self._answers_wellness(text)
        if topic == TOPIC_GOOD_PROBE:
            return self._good_probe_answered(understanding)
        if topic == TOPIC_BAD_SYMPTOM:
            return self._bad_symptom_probe_answered(understanding)
        if topic == TOPIC_RECORD_NOTIFY:
            return True
        if topic == TOPIC_CLOSING:
            return understanding.speech_act in (
                SpeechAct.CLOSING,
                SpeechAct.CLOSING_DIRECT,
                SpeechAct.AFFIRMATION,
            )
        if self._matches_topic(text, topic):
            return True
        if topic in ("самочувствие", "настроение") and self._answers_wellness(text):
            return True
        if understanding.symptom_resolved and clearing_symptom:
            return True
        return False

    def _good_probe_answered(self, understanding: TurnUnderstanding) -> bool:
        sub = self.current_good_slot()
        if not sub:
            return False
        text = understanding.clean_text
        if not text:
            return False
        if matches_topic(text, sub):
            return True
        keys = TOPIC_KEYS.get(sub, ())
        low = text.lower()
        if understanding.word_count >= 2 and any(k in low for k in keys):
            return True
        if wellness_short_answer(text) and any(k in low for k in keys):
            return True
        if sub == "настроение":
            from conversation_system.agenda.topics import BAD_WORDS, OK_WORDS

            if any(w in low for w in BAD_WORDS):
                return False
            if "чувству" in low and any(
                w in low for w in ("хорош", "нормал", "отличн", "бодр", "норм")
            ):
                return True
            if understanding.word_count >= 3 and any(w in low for w in OK_WORDS):
                return True
        if self.question_open and wellness_short_answer(text):
            return True
        if self.question_open and understanding.word_count >= 2:
            for covered in self.covered_good_slots:
                if covered != sub and matches_topic(text, covered):
                    return True
        return False

    def _bad_symptom_probe_answered(self, understanding: TurnUnderstanding) -> bool:
        """Short severity/timing answers close symptom depth probes."""
        text = understanding.clean_text
        if not text:
            return False
        if self._is_probe_repair_phrase(understanding):
            return False

        low = text.lower()
        probe_idx = self.bad_symptom_probe_index

        if probe_idx == 0:
            if mentions_symptom(text):
                return True
            if short_real_answer(text) and matches_topic(text, TOPIC_BAD_SYMPTOM):
                return True
            words = re.findall(r"[а-яёa-z]+", low)
            if words and all(w in _SYMPTOM_PROBE_SHORT_WORDS for w in words):
                return True
            return False

        if probe_idx >= 1:
            if self._has_severity_signal(text):
                return True
            from conversation_system.domain.wellness import is_symptom_intensifier
            if is_symptom_intensifier(text):
                return True
            words = re.findall(r"[а-яёa-z]+", low)
            if words and all(w in _SYMPTOM_PROBE_SHORT_WORDS for w in words):
                return True
            if probe_idx >= 2 and understanding.word_count >= 2:
                return True
            return False

        return False

    def mark_discussed(
        self,
        understanding: TurnUnderstanding,
        *,
        clearing_symptom: bool = False,
        force_topic: str = "",
    ) -> list[MemoryPatch]:
        """Semantic mark_discussed — returns patches, advances when closed."""
        patches: list[MemoryPatch] = []
        topic = force_topic or self.current_topic_key()
        if not topic:
            return patches

        if not self.semantic_close(
                understanding, clearing_symptom=clearing_symptom):
            if understanding.is_narrative and topic != FAMILY_TOPIC_LABEL:
                patches.append(self.defer_current())
            return patches

        patches.append(MemoryPatch(
            mark_topic_discussed=topic,
            append_note=f"обсуждено: {topic}",
        ))

        if topic == TOPIC_WELLNESS and understanding.clean_text:
            band = self.set_wellness_from_text(understanding.clean_text)
            patches.append(MemoryPatch(
                set_field={"wellness_band": band.value},
            ))
            patches.append(self.apply_path_after_wellness(understanding))

        current = self.current_topic()
        if current and current.is_family and understanding.clean_text:
            patches.append(MemoryPatch(
                family_answer=(current.family_id, understanding.clean_text),
            ))

        if topic == TOPIC_GOOD_PROBE:
            slot = self.current_good_slot()
            if slot:
                self.mark_good_slot_covered(slot)
            self.advance_good_probe()
        elif topic == TOPIC_BAD_SYMPTOM:
            self.advance_bad_symptom_probe()
        elif topic == TOPIC_RECORD_NOTIFY:
            self.record_notified = True
            self._seek_topic(TOPIC_CLOSING)
        elif topic == TOPIC_WELLNESS:
            pass
        else:
            finished = self.advance()
            if finished:
                patches.append(MemoryPatch(
                    set_field={"flags": {"agenda_done": True}},
                ))

        patches.append(MemoryPatch(
            set_field={
                "agenda_cursor": self.cursor,
                "agenda_question_open": self.question_open,
                "flags": {"agenda_done": self.done},
            },
        ))
        return patches

    def should_defer_for_narrative(self, understanding: TurnUnderstanding) -> bool:
        if not self.question_open:
            return False
        if understanding.speech_act != SpeechAct.NARRATIVE \
                and not understanding.is_narrative:
            return False
        topic = self.current_topic_key()
        if topic == FAMILY_TOPIC_LABEL:
            return False
        if self.semantic_close(understanding):
            return False
        return True

    def sync_to_memory(self) -> MemoryPatch:
        return MemoryPatch(set_field={
            "agenda_cursor": self.cursor,
            "agenda_question_open": self.question_open,
            "deferred_topic": self.deferred_topic,
            "wellness_band": self.wellness_band.value,
            "flags": {
                "agenda_done": self.done,
                "agenda_paused": self.paused,
                "record_notified": self.record_notified,
                "on_good_path": self.on_good_path,
                "on_bad_path": self.on_bad_path,
            },
        })

    def sync_from_memory(
        self,
        *,
        cursor: int,
        question_open: bool,
        done: bool,
        paused: bool,
        deferred_topic: str,
        wellness_band: str = "unknown",
        record_notified: bool = False,
        on_good_path: bool = False,
        on_bad_path: bool = False,
        good_probe_index: int = 0,
        bad_symptom_probe_index: int = 0,
        covered_good_slots: Sequence[str] | None = None,
        interruption_phase: str = "",
        interruption_slot_index: int = -1,
        interruption_slot: str = "",
        interruption_question_id: str = "",
    ) -> None:
        self.cursor = cursor
        self.question_open = question_open
        self.done = done
        self.paused = paused
        self.deferred_topic = deferred_topic
        try:
            self.wellness_band = WellnessBand(wellness_band)
        except ValueError:
            self.wellness_band = WellnessBand.UNKNOWN
        self.record_notified = record_notified
        self.on_good_path = on_good_path
        self.on_bad_path = on_bad_path
        self.good_probe_index = good_probe_index
        self.bad_symptom_probe_index = bad_symptom_probe_index
        if covered_good_slots is not None:
            self.covered_good_slots = list(covered_good_slots)
        self.interruption = InterruptionFrame(
            return_phase=interruption_phase,
            return_slot_index=interruption_slot_index,
            return_slot=interruption_slot,
            return_question_id=interruption_question_id,
        )

    def _matches_topic(self, text: str, topic: str) -> bool:
        return matches_topic(text, topic)

    def _answers_wellness(self, text: str) -> bool:
        if not (text or "").strip():
            return False
        if wellness_short_answer(text):
            return True
        low = text.lower()
        if any(w in low for w in OK_WORDS) or any(w in low for w in BAD_WORDS):
            return True
        return matches_topic(text, TOPIC_WELLNESS)

    def all_topic_keys(self) -> tuple[str, ...]:
        return tuple(t.key for t in self.topics)

    def is_family_topic(self) -> bool:
        topic = self.current_topic()
        return bool(topic and topic.is_family)

    def extract_fact_candidates(self, understanding: TurnUnderstanding) -> list[str]:
        """Lightweight fact extraction for memory (no LLM)."""
        text = understanding.clean_text
        if not text:
            return []
        facts: list[str] = []
        low = text.lower()
        if mentions_symptom(text) and not understanding.symptom_resolved:
            focus = understanding.symptom_focus or "недомогание"
            facts.append(f"жалоба: {focus}")
        if any(w in low for w in ("таблет", "лекар", "принял", "приняла")):
            facts.append("приняла лекарства")
        if matches_topic(text, "сон"):
            facts.append("обсуждали сон")
        if matches_topic(text, "планы"):
            facts.append("есть планы на день")
        if any(w in low for w in ("настроени", "груст", "радост", "весел")):
            facts.append("настроение")
        if self.wellness_band != WellnessBand.UNKNOWN:
            facts.append(f"самочувствие: {self.wellness_band.value}")
        if understanding.speech_act in (SpeechAct.REFUSAL, SpeechAct.CLOSING):
            facts.append("отказ или прощание")
        return facts
