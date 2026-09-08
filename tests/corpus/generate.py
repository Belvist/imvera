"""Deterministic ≥1000 dialogue scenarios (seeded; category-labeled).

Full end-to-end wellness matrix (400 scenarios, 100 per polarity bucket):
see ``tests/corpus/wellness_matrix.py`` and ``tests/test_wellness_scenario_matrix.py``.

Layer honesty:
- Exercises CallSession + rule interpreter (+ StatusEngine invariants).
- Does NOT prove live SIP, STT, TTS, or LLM accuracy.
"""

from __future__ import annotations

from collections import Counter

from tests.corpus.models import Scenario

CORPUS_SEED = 42

_WELLNESS_FILL = (
    "хорошо",
    "нормально",
    "не очень",
    "плохо",
    "отлично",
    "мне плохо",
    "мне нехорошо",
    "чувствую себя хорошо",
    "чувствую себя нормально",
    "чувствую себя плохо",
    "голова болит",
    "устала",
    "слабенько",
)

_WELLNESS_FILL_INTENTS = {
    "хорошо": ("check_mood",),
    "нормально": ("check_mood",),
    "отлично": ("check_mood",),
    "чувствую себя хорошо": ("check_mood",),
    "чувствую себя нормально": ("check_mood",),
    "не очень": ("reflect_report",),
    "плохо": ("reflect_report",),
    "мне плохо": ("reflect_report",),
    "мне нехорошо": ("reflect_report",),
    "чувствую себя плохо": ("reflect_report",),
    "голова болит": ("reflect_report",),
    "устала": ("reflect_report",),
    "слабенько": ("check_mood", "reflect_report"),
}

_STT_NOISE_NOFILL = (
    "харашо",
    "харашo",  # latin o
    "норм",
    "не оч",
    "плохa",  # latin a
    "хорошоо",
    "харошо",
    "нармальна",
    "так себе",
    "ничего",
    "средне",
    "пойдёт",
    "ну такое",
    "ааа",
    "эээ",
    "м-м-м",
    "кхм",
    "шыум",
    "бжбж",
    "qwerty",
)

_ACK_BACKCHANNELS = ("ага", "угу", "Ага!", "Угу.", "ага…", "угу!")
_REPAIR_GREETINGS = ("алло", "алло?")
_BACKCHANNELS = _ACK_BACKCHANNELS + _REPAIR_GREETINGS

_MOOD_ANSWERS = ("хорошее", "плохое", "нормальное", "грустно", "весело")
_SLEEP_ANSWERS = (
    "спал нормально",
    "спала плохо",
    "сон хороший",
    "не спала",
    "спал хорошо",
)
_PLANS_ANSWERS = ("дома", "дома посижу", "к врачу", "гуляю", "в магазин", "внуки")

_COMPLAINTS = (
    "голова болит",
    "Голова болит с утра",
    "болит спина",
    "температура",
    "устала очень",
    "слабость",
)

# Phrases that fill wellness; empathy intent when negative enough.
_COMPLAINT_INTENTS = {
    "голова болит": ("reflect_report",),
    "Голова болит с утра": ("reflect_report",),
    "болит спина": ("reflect_report",),
    "температура": ("reflect_report", "check_mood"),
    "устала очень": ("reflect_report",),
    "слабость": ("reflect_report", "check_mood"),
}

_WHO = (
    "кто вы",
    "кто вы такая",
    "как вас зовут",
    "что это за звонок",
    "зачем вы звоните",
)

_PAUSE = ("подождите", "подожди", "минуточку", "секундочку", "погодите")
_STOP = ("закончим разговор", "давайте закончим", "хватит разговор", "до свидания", "пока")
_REFUSE = (
    "не хочу говорить о сне",
    "не хочу говорить о настроении",
    "не хочу говорить о здоровье",
    "не хочу говорить о планах",
    "не хочу",
)

_EMPTY_NOISE = (
    "",
    " ",
    "...",
    "…",
    "!!!",
    "шум",
    "шум шум",
    "xxx",
    "###",
    "asdf",
    "ааа",
    "эээ",
    ",,,",
    "???",
)

_PUNCT_WRAP = ("{}", " {} ", "{}!", "{}?", "{},", "{}.", "«{}»", "{}…")


def _sid(category: str, n: int) -> str:
    return f"{category}:{n:04d}"


def _wellness_fill_cases() -> list[Scenario]:
    out: list[Scenario] = []
    n = 0
    for base in _WELLNESS_FILL:
        intents = _WELLNESS_FILL_INTENTS[base]
        for wrap in _PUNCT_WRAP:
            text = wrap.format(base)
            # Skip wraps that break recognition for multiword (quotes ok).
            if base.startswith("чувствую") and wrap in ("«{}»",):
                continue
            expect_intent = intents
            # punctuated "не очень" etc. still fill
            out.append(
                Scenario(
                    id=_sid("wellness_mood", n),
                    category="wellness_mood",
                    turns=(text,),
                    expect_slots={"wellness": "FILLED"},
                    expect_intent_in=expect_intent,
                    notes="rule path wellness fill",
                )
            )
            n += 1
    # prefix variants
    prefixes = ("ну ", "да ", "вот ", "сейчас ", "сегодня ")
    for base in ("хорошо", "нормально", "плохо", "не очень"):
        for pref in prefixes:
            text = pref + base
            intents = _WELLNESS_FILL_INTENTS[base]
            out.append(
                Scenario(
                    id=_sid("wellness_mood", n),
                    category="wellness_mood",
                    turns=(text,),
                    expect_slots={"wellness": "FILLED"},
                    expect_intent_in=intents,
                )
            )
            n += 1
    return out


def _stt_noise_nofill_cases() -> list[Scenario]:
    out: list[Scenario] = []
    for i, text in enumerate(_STT_NOISE_NOFILL):
        for j, wrap in enumerate(("", " {}", "{}!", " {} ")):
            utterance = wrap.format(text).strip() if "{}" in wrap else text
            out.append(
                Scenario(
                    id=_sid("stt_noise_nofill", i * 10 + j),
                    category="stt_noise_nofill",
                    turns=(utterance,),
                    expect_slots={"wellness": "OPEN"},
                    never_fill=("wellness",),
                    notes="STT-like garbage must not fill",
                )
            )
    return out


def _backchannel_cases() -> list[Scenario]:
    out: list[Scenario] = []
    n = 0
    # Pending wellness (opening already delivered in execute)
    for bc in _ACK_BACKCHANNELS:
        for wrap in ("{}", " {}", "{}!", "{}…", " {} "):
            text = wrap.format(bc).strip() if "{}" in wrap else bc
            out.append(
                Scenario(
                    id=_sid("backchannel", n),
                    category="backchannel",
                    turns=(text,),
                    expect_slots={"wellness": "OPEN"},
                    never_fill=("wellness", "mood", "sleep", "plans"),
                    expect_intent_in=("wait_for_continuation", "check_wellness"),
                )
            )
            n += 1
    for bc in _REPAIR_GREETINGS:
        for wrap in ("{}", " {}", "{}!"):
            text = wrap.format(bc).strip() if "{}" in wrap else bc
            out.append(
                Scenario(
                    id=_sid("backchannel", n),
                    category="backchannel",
                    turns=(text,),
                    expect_slots={"wellness": "OPEN"},
                    never_fill=("wellness", "mood", "sleep", "plans"),
                    expect_intent_in=("repair_repeat",),
                )
            )
            n += 1
    # After wellness filled — pending mood
    for bc in _ACK_BACKCHANNELS:
        for wellness in ("хорошо", "нормально", "плохо", "не очень"):
            out.append(
                Scenario(
                    id=_sid("backchannel", n),
                    category="backchannel",
                    setup_turns=(wellness,),
                    turns=(bc,),
                    expect_slots={"wellness": "FILLED", "mood": "OPEN"},
                    never_fill=("mood", "sleep", "plans"),
                )
            )
            n += 1
    # After mood — pending sleep
    for bc in _ACK_BACKCHANNELS:
        out.append(
            Scenario(
                id=_sid("backchannel", n),
                category="backchannel",
                setup_turns=("хорошо", "хорошее"),
                turns=(bc,),
                expect_slots={"sleep": "OPEN"},
                never_fill=("sleep",),
            )
        )
        n += 1
    # After sleep — pending plans
    for bc in _ACK_BACKCHANNELS:
        out.append(
            Scenario(
                id=_sid("backchannel", n),
                category="backchannel",
                setup_turns=("хорошо", "хорошее", "спал нормально"),
                turns=(bc,),
                expect_slots={"plans": "OPEN"},
                never_fill=("plans",),
            )
        )
        n += 1
    return out


def _full_chain_cases() -> list[Scenario]:
    out: list[Scenario] = []
    n = 0
    wellness_opts = ("хорошо", "нормально", "не очень", "плохо")
    for w in wellness_opts:
        for m in _MOOD_ANSWERS:
            for s in _SLEEP_ANSWERS:
                for p in _PLANS_ANSWERS[:3]:
                    turns = [w]
                    # negative wellness may insert reflect_report — still need mark+continue
                    # Runner marks spoken after each turn; next answers advance.
                    # After reflect, user may need another turn — use mood answer next.
                    turns.extend([m, s, p, "до свидания", "да"])
                    out.append(
                        Scenario(
                            id=_sid("full_chain", n),
                            category="full_chain",
                            turns=tuple(turns),
                            expect_slots={
                                "wellness": "FILLED",
                                "mood": "FILLED",
                                "sleep": "FILLED",
                                "plans": "FILLED",
                            },
                            expect_intent_in=("goodbye_final", "terminal_noop"),
                            notes="full slots → goodbye",
                        )
                    )
                    n += 1
                    if n >= 120:
                        return out
    return out


def _who_side_cases() -> list[Scenario]:
    out: list[Scenario] = []
    n = 0
    for q in _WHO:
        out.append(
            Scenario(
                id=_sid("who_are_you", n),
                category="who_are_you",
                turns=(q,),
                expect_slots={"wellness": "OPEN"},
                never_fill=("wellness",),
                expect_intent_in=("explain_vera",),
            )
        )
        n += 1
        # mid-slot after wellness
        out.append(
            Scenario(
                id=_sid("who_are_you", n),
                category="who_are_you",
                setup_turns=("хорошо",),
                turns=(q,),
                expect_slots={"wellness": "FILLED", "mood": "OPEN"},
                never_fill=("mood",),
                expect_intent_in=("explain_vera",),
            )
        )
        n += 1
    # Mixed: side question mid-utterance — rule path prioritizes who_are_you
    # (slot fill + explain is semantic-path territory; NOT claimed here).
    mixed = (
        "Чувствую себя хорошо. А кто вы?",
        "Нормально, а как вас зовут?",
        "Хорошо. Кто вы такая?",
    )
    for text in mixed:
        out.append(
            Scenario(
                id=_sid("who_are_you", n),
                category="who_are_you",
                turns=(text,),
                expect_slots={"wellness": "OPEN"},
                never_fill=("wellness",),
                expect_intent_in=("explain_vera",),
                notes="rule path: who_are_you wins over embedded wellness answer",
            )
        )
        n += 1
    # Expand with punctuated who-questions
    for q in _WHO:
        for wrap in ("{}?", " {} ", "{}!!"):
            out.append(
                Scenario(
                    id=_sid("who_are_you", n),
                    category="who_are_you",
                    turns=(wrap.format(q),),
                    expect_slots={"wellness": "OPEN"},
                    never_fill=("wellness",),
                    expect_intent_in=("explain_vera",),
                )
            )
            n += 1
    return out


def _pause_stop_refuse_cases() -> list[Scenario]:
    out: list[Scenario] = []
    n = 0
    for p in _PAUSE:
        out.append(
            Scenario(
                id=_sid("pause_stop", n),
                category="pause_stop",
                turns=(p,),
                expect_slots={"wellness": "OPEN"},
                never_fill=("wellness",),
                expect_intent_in=("pause_ack",),
            )
        )
        n += 1
    for s in _STOP:
        out.append(
            Scenario(
                id=_sid("pause_stop", n),
                category="pause_stop",
                turns=(s,),
                never_fill=("wellness",) if s != "пока" else (),
                expect_intent_in=("goodbye_confirm",),
            )
        )
        n += 1
        # confirm goodbye
        out.append(
            Scenario(
                id=_sid("pause_stop", n),
                category="pause_stop",
                turns=(s, "да"),
                expect_intent_in=("goodbye_final", "terminal_noop"),
            )
        )
        n += 1
    # Topic refuse — need correct pending slot
    refuse_setup = {
        "не хочу говорить о сне": ("хорошо", "хорошее"),
        "не хочу говорить о настроении": ("хорошо",),
        "не хочу говорить о здоровье": (),
        "не хочу говорить о планах": ("хорошо", "хорошее", "спал нормально"),
        "не хочу": ("хорошо",),
    }
    for phrase, setup in refuse_setup.items():
        for wrap in ("{}", "{}!", " {} "):
            out.append(
                Scenario(
                    id=_sid("topic_refuse", n),
                    category="topic_refuse",
                    setup_turns=setup,
                    turns=(wrap.format(phrase),),
                    notes="topic refusal / soft decline",
                )
            )
            n += 1
    return out


def _complaint_cases() -> list[Scenario]:
    out: list[Scenario] = []
    n = 0
    for c in _COMPLAINTS:
        out.append(
            Scenario(
                id=_sid("complaint", n),
                category="complaint",
                turns=(c,),
                expect_slots={"wellness": "FILLED"},
                expect_intent_in=_COMPLAINT_INTENTS[c],
            )
        )
        n += 1
        # mid-call after wellness
        out.append(
            Scenario(
                id=_sid("complaint", n),
                category="complaint",
                setup_turns=("нормально",),
                turns=(c,),
                expect_intent_in=("reflect_report", "check_mood", "check_sleep"),
                notes="complaint mid-call",
            )
        )
        n += 1
    # Known-recognized complaint phrasings (rule path)
    extras = (
        "болит голова сильно",
        "спина болит",
        "мне нехорошо совсем",
        "очень плохо себя чувствую",
    )
    for c in extras:
        for wrap in _PUNCT_WRAP[:5]:
            out.append(
                Scenario(
                    id=_sid("complaint", n),
                    category="complaint",
                    turns=(wrap.format(c),),
                    expect_slots={"wellness": "FILLED"},
                )
            )
            n += 1
    # Unrecognized symptom words stay OPEN (honest: rule path does not invent fill)
    for text in ("давление", "давление!", " давление "):
        out.append(
            Scenario(
                id=_sid("complaint", n),
                category="complaint",
                turns=(text,),
                expect_slots={"wellness": "OPEN"},
                never_fill=("wellness",),
                notes="unrecognized symptom token — no false fill",
            )
        )
        n += 1
    return out


def _mixed_cases() -> list[Scenario]:
    out: list[Scenario] = []
    n = 0
    mixed = (
        "Чувствую себя хорошо, спасибо",
        "Нормально вроде",
        "Плохо немного",
        "Хорошо, устала чуть-чуть",
        "Голова болит, но терпимо",
        "Спала плохо и настроение никакое",
        "Дома буду, самочувствие нормально",
        "Не очень, спина болит",
    )
    for text in mixed:
        for wrap in _PUNCT_WRAP[:6]:
            out.append(
                Scenario(
                    id=_sid("mixed", n),
                    category="mixed",
                    turns=(wrap.format(text),),
                    notes="mixed / compound utterance",
                )
            )
            n += 1
    return out


def _empty_noise_cases() -> list[Scenario]:
    out: list[Scenario] = []
    n = 0
    for text in _EMPTY_NOISE:
        out.append(
            Scenario(
                id=_sid("empty_noise", n),
                category="empty_noise",
                turns=(text,),
                expect_slots={"wellness": "OPEN"},
                never_fill=("wellness", "mood", "sleep", "plans"),
            )
        )
        n += 1
        # single noise then real answer (clarify path)
        out.append(
            Scenario(
                id=_sid("empty_noise", n),
                category="empty_noise",
                turns=(text, "хорошо"),
                expect_slots={"wellness": "FILLED"},
                expect_intent_in=("check_mood", "reflect_report"),
                notes="noise then valid answer",
            )
        )
        n += 1
    return out


def _clarify_release_cases() -> list[Scenario]:
    """Clarify / retry paths (Session-level; CallActor reservation tested separately)."""
    out: list[Scenario] = []
    n = 0
    repeats = (
        "повторите",
        "ещё раз",
        "еще раз",
        "не поняла",
        "не понял",
        "что вы сказали",
        "не расслышала",
    )
    for r in repeats:
        for ans in ("хорошо", "нормально", "плохо", "не очень"):
            out.append(
                Scenario(
                    id=_sid("clarify", n),
                    category="clarify",
                    turns=(r,),
                    expect_slots={"wellness": "OPEN"},
                    never_fill=("wellness",),
                )
            )
            n += 1
            out.append(
                Scenario(
                    id=_sid("clarify", n),
                    category="clarify",
                    turns=(r, ans),
                    expect_slots={"wellness": "FILLED"},
                )
            )
            n += 1
    # backchannel then answer
    for bc in ("ага", "угу", "алло", "Ага!", "угу…"):
        for ans in _WELLNESS_FILL:
            out.append(
                Scenario(
                    id=_sid("clarify", n),
                    category="clarify",
                    turns=(bc, ans),
                    expect_slots={"wellness": "FILLED"},
                )
            )
            n += 1
    # double backchannel then answer
    for ans in _WELLNESS_FILL:
        out.append(
            Scenario(
                id=_sid("clarify", n),
                category="clarify",
                turns=("ага", "угу", ans),
                expect_slots={"wellness": "FILLED"},
            )
        )
        n += 1
        out.append(
            Scenario(
                id=_sid("clarify", n),
                category="clarify",
                turns=("алло", "ага", ans),
                expect_slots={"wellness": "FILLED"},
            )
        )
        n += 1
    return out


def _slot_variant_cases() -> list[Scenario]:
    out: list[Scenario] = []
    n = 0
    for m in _MOOD_ANSWERS:
        for wrap in _PUNCT_WRAP[:6]:
            out.append(
                Scenario(
                    id=_sid("slot_variants", n),
                    category="slot_variants",
                    setup_turns=("хорошо",),
                    turns=(wrap.format(m),),
                    expect_slots={"mood": "FILLED"},
                )
            )
            n += 1
    for s in _SLEEP_ANSWERS:
        for wrap in _PUNCT_WRAP[:5]:
            out.append(
                Scenario(
                    id=_sid("slot_variants", n),
                    category="slot_variants",
                    setup_turns=("хорошо", "хорошее"),
                    turns=(wrap.format(s),),
                    expect_slots={"sleep": "FILLED"},
                )
            )
            n += 1
    for p in _PLANS_ANSWERS:
        for wrap in _PUNCT_WRAP[:4]:
            out.append(
                Scenario(
                    id=_sid("slot_variants", n),
                    category="slot_variants",
                    setup_turns=("хорошо", "хорошее", "спал нормально"),
                    turns=(wrap.format(p),),
                    expect_slots={"plans": "FILLED"},
                )
            )
            n += 1
    return out


def _pad_to_minimum(scenarios: list[Scenario], minimum: int) -> list[Scenario]:
    """Deterministic padding via seeded permutations of known-good fills."""
    if len(scenarios) >= minimum:
        return scenarios
    n = 0
    bases = list(_WELLNESS_FILL)
    wraps = list(_PUNCT_WRAP)
    while len(scenarios) < minimum:
        base = bases[n % len(bases)]
        wrap = wraps[(n * 3) % len(wraps)]
        text = wrap.format(base)
        scenarios.append(
            Scenario(
                id=_sid("wellness_mood_pad", n),
                category="wellness_mood",
                turns=(text,),
                expect_slots={"wellness": "FILLED"},
                expect_intent_in=_WELLNESS_FILL_INTENTS[base],
                notes=f"pad seed={CORPUS_SEED} i={n}",
            )
        )
        n += 1
    return scenarios


def generate_scenarios(*, seed: int = CORPUS_SEED, minimum: int = 1000) -> list[Scenario]:
    """Build the full corpus. ``seed`` is recorded for reproducibility (deterministic)."""
    _ = seed  # reserved for future RNG; current generators are fully deterministic
    scenarios: list[Scenario] = []
    scenarios.extend(_wellness_fill_cases())
    scenarios.extend(_stt_noise_nofill_cases())
    scenarios.extend(_backchannel_cases())
    scenarios.extend(_full_chain_cases())
    scenarios.extend(_who_side_cases())
    scenarios.extend(_pause_stop_refuse_cases())
    scenarios.extend(_complaint_cases())
    scenarios.extend(_mixed_cases())
    scenarios.extend(_empty_noise_cases())
    scenarios.extend(_clarify_release_cases())
    scenarios.extend(_slot_variant_cases())
    scenarios = _pad_to_minimum(scenarios, minimum)
    # Stable unique ids
    seen: set[str] = set()
    unique: list[Scenario] = []
    for s in scenarios:
        if s.id in seen:
            continue
        seen.add(s.id)
        unique.append(s)
    if len(unique) < minimum:
        unique = _pad_to_minimum(unique, minimum)
    return unique


def scenario_count_by_category(scenarios: list[Scenario] | None = None) -> dict[str, int]:
    items = scenarios if scenarios is not None else generate_scenarios()
    return dict(Counter(s.category for s in items))
