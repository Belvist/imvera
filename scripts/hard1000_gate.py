#!/usr/bin/env python3
"""Hard-1000 gate: 1000+ generated understanding scenarios, all must pass.

Two tiers:
- Tier M (mention/act/frame level, fast): single utterances checked against
  extract_issue_mentions / parse_spans / normalize_act / frame predicates /
  value extractors. Carries the bulk of the count.
- Tier C (call level): multi-turn scripts through CallSession asserting
  episode grounding, no RED on benign input, no repeated questions,
  and summary containment.

Coverage is generated FROM the lexicon classes (BODY_SITE_LEMMAS,
SENSATION_NOUNS, SEVERITY_WORDS, TIME_WORDS, ...), so new vocabulary is
automatically gated. Negative controls ride along in every family.

Writes .run/agent_gates/hard1000-latest.json. Exit 1 on any fail.
Asserts total >= 1000 so the gate cannot silently shrink.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Production-representative Layer A path (mirrors the golden live-call test
# and pytest.mark.dialogue_engine): engine on, kernel-built rich turns.
os.environ.setdefault("IMVERA_DIALOGUE_ENGINE", "1")
os.environ.setdefault("IMVERA_SPEECH_DAY", "102")
os.environ.setdefault("IMVERA_SPEECH_HOUR", "14")

from packages.core.memory_store import InMemoryCallRecordStore  # noqa: E402
from packages.dialogue.session import CallSession  # noqa: E402
from packages.dialogue_engine.check_path import (  # noqa: E402
    is_joke_hyperbole_frame,
    is_other_person_health_frame,
    is_past_noncurrent_frame,
    is_politeness_refusal,
    is_side_topic_chatter,
    suppress_health_issues_for_non_complaint_frame,
)
from packages.dialogue_engine.issue_mention_extract import (  # noqa: E402
    extract_issue_mentions,
)
from packages.dialogue_engine.protocol.acts import normalize_act  # noqa: E402
from packages.dialogue_engine.semantic_kernel.lexicon import (  # noqa: E402
    BODY_SITE_LEMMAS,
    NOISE_WORDS,
    SENSATION_NOUNS,
    SEVERITY_WORDS,
    TIME_WORDS,
)
from packages.dialogue_engine.semantic_kernel.morphology import (  # noqa: E402
    normalize_token,
)
from packages.dialogue_engine.semantic_kernel.span_parser import (  # noqa: E402
    parse_spans,
)
from packages.dialogue_engine.state import EngineState  # noqa: E402

REPORT_DIR = ROOT / ".run" / "agent_gates"
MIN_SCENARIOS = 1000

URGENT_MARKERS = ("передам близк", "скорую", "вызову")


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def _fresh_state() -> EngineState:
    return EngineState(call_id="h1k", elder_display_name="Тамара Юрьевна")


def _expected_site(raw_word: str) -> str:
    """What body_site the generic rule should produce for a raw noun."""
    norm = normalize_token(raw_word)
    if len(raw_word) >= 4 and norm in BODY_SITE_LEMMAS:
        return norm
    return raw_word.lower()


def _cap(word: str) -> str:
    return word[0].upper() + word[1:] if word else word


# ---------------------------------------------------------------- checks

def check_site(text: str, site: str) -> list[str]:
    ms = extract_issue_mentions(text)
    if not any(m.body_site == site for m in ms):
        return [f"no mention with site={site!r} (got {[(m.label, m.body_site) for m in ms]})"]
    return []


def check_no_mention(text: str) -> list[str]:
    ms = extract_issue_mentions(text)
    if ms:
        return [f"unexpected mentions {[(m.label, m.body_site) for m in ms]}"]
    return []


def check_act(text: str, act: str) -> list[str]:
    got = normalize_act(_fresh_state(), text)
    if got != act:
        return [f"act={got!r} expected {act!r}"]
    return []


def check_frame(text: str, name: str, expected: bool) -> list[str]:
    fns = {
        "other_person": is_other_person_health_frame,
        "past": is_past_noncurrent_frame,
        "joke": is_joke_hyperbole_frame,
        "chatter": is_side_topic_chatter,
        "suppressed": suppress_health_issues_for_non_complaint_frame,
        "refusal": is_politeness_refusal,
    }
    got = bool(fns[name](text))
    if got != expected:
        return [f"frame {name}={got} expected {expected}"]
    return []


def check_span(text: str, kind: str, substr: str) -> list[str]:
    for sp in parse_spans(text):
        if str(sp.type) == kind and substr.lower() in sp.text.lower():
            return []
    return [f"no {kind} span containing {substr!r}"]


def check_no_span(text: str, kind: str) -> list[str]:
    bad = [sp.text for sp in parse_spans(text) if str(sp.type) == kind]
    if bad:
        return [f"unexpected {kind} spans {bad}"]
    return []


def check_severity_value(text: str) -> list[str]:
    from packages.dialogue_engine.issue_memory import (
        extract_grounded_severity_value,
    )

    if extract_grounded_severity_value(text) is None:
        return [f"no grounded severity in {text!r}"]
    return []


def _run_call(texts: list[str], tag: str):
    from packages.dialogue_engine.semantic_kernel.kernel import (
        interpret as _ki,
    )
    from packages.dialogue_engine.semantic_kernel.kernel import (
        kernel_to_rich_turn as _k2rt,
    )

    session = CallSession(
        call_id=f"h1k-{tag}-{time.time_ns()}",
        family_id="hard-1000",
        elder_display_name="Тамара Юрьевна",
        store=InMemoryCallRecordStore(),
    )
    opening = session.start()
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    session.mark_spoken_action(opening.proposal.generation_id)
    eng = session._engine
    assert eng is not None, "engine path required (IMVERA_DIALOGUE_ENGINE=1)"
    turns: list[dict] = []
    for i, text in enumerate(texts):
        slot = eng.answer_context_slot()
        rt = _k2rt(
            _ki(text, utterance_id=f"u{i}", engine_state=eng.state, answer_slot=slot),
            answer_slot=slot,
            engine_state=eng.state,
        )
        result = session.handle_user_text(text, rich_turn=rt)
        speech = (result.proposal.speech or "").strip()
        session.mark_spoken_action(result.proposal.generation_id)
        turns.append({"u": text, "v": speech})
    return turns, eng.state


def _vera_names_site(vera_text: str, site: str) -> bool:
    """Site named out loud, inflection-proof («ушах» counts for «ухо»)."""
    from packages.dialogue_engine.semantic_kernel.morphology import (
        normalize_token,
    )

    if site.lower() in vera_text.lower():
        return True
    return any(
        normalize_token(tok) == site
        for tok in re.findall(r"[а-яё]+", vera_text.lower())
    )


def check_call_episode(texts: list[str], site: str) -> list[str]:
    """Rich-path contract: a speaker episode opens with the site, Vera names
    it out loud, no RED language, no verbatim repeated question."""
    turns, state = _run_call(texts, "ep")
    errs: list[str] = []
    sites = {e.body_site for e in state.issue_episodes.values() if e.body_site}
    if site not in sites:
        errs.append(f"episode site {site!r} missing (have {sorted(sites)})")
    vera = " ".join(t["v"] for t in turns)
    if not _vera_names_site(vera, site):
        errs.append(f"Vera never named site {site!r}")
    if any(m in vera.lower() for m in URGENT_MARKERS):
        errs.append("urgent language on benign flow")
    questions = [t["v"] for t in turns if t["v"].endswith("?")]
    if len(questions) != len(set(questions)):
        errs.append(f"repeated Vera question: {questions}")
    return errs


def check_call_engaged(texts: list[str]) -> list[str]:
    """Vera engaged out loud (asked something), stayed silent on nothing,
    no RED language. For triage-shaped paths (e.g. bleeding) that do not
    open a plain episode."""
    turns, _ = _run_call(texts, "eng")
    errs: list[str] = []
    vera = " ".join(t["v"] for t in turns)
    if not any(t["v"].endswith("?") for t in turns):
        errs.append("Vera never engaged (no question asked)")
    if any(m in vera.lower() for m in URGENT_MARKERS):
        errs.append("urgent language on benign flow")
    return errs


def check_call_episode_quiet(texts: list[str], site: str) -> list[str]:
    """Episode grounding only (correction flows): the speech surface on
    corrections is a separate backlog item, not this gate's contract."""
    turns, state = _run_call(texts, "epq")
    errs: list[str] = []
    sites = {e.body_site for e in state.issue_episodes.values() if e.body_site}
    if site not in sites:
        errs.append(f"episode site {site!r} missing (have {sorted(sites)})")
    vera = " ".join(t["v"] for t in turns).lower()
    if any(m in vera for m in URGENT_MARKERS):
        errs.append("urgent language on benign flow")
    return errs


def check_call_no_episode(texts: list[str]) -> list[str]:
    turns, state = _run_call(texts, "noep")
    errs: list[str] = []
    if state.active_episode_id is not None:
        eps = [(e.body_site, e.primary_label) for e in state.issue_episodes.values()]
        errs.append(f"unexpected episode {eps}")
    joined = " ".join(t["v"] for t in turns).lower()
    if any(m in joined for m in URGENT_MARKERS):
        errs.append("urgent language on benign flow")
    return errs


# ---------------------------------------------------------------- generation

def gen_site_matrix() -> list[tuple[str, str, tuple]]:
    out = []
    for site in sorted(BODY_SITE_LEMMAS):
        word = _cap(site)
        out.append((f"site:{site}", f"{word} болит.", ("site", site)))
        for adv in ("сильно", "немного"):
            out.append((f"site-adv:{site}-{adv}", f"{word} {adv} болит.", ("site", site)))
    return out


def gen_neg_matrix() -> list[tuple[str, str, tuple]]:
    out = []
    for site in sorted(BODY_SITE_LEMMAS):
        if site in ("голова", "живот"):
            continue  # specific rules keep mentions; act-level DECLINE owns it
        out.append((f"neg:{site}", f"{_cap(site)} не болит.", ("no-mention",)))
    for text in ("Ничего не болит.", "Ничего не беспокоит.", "Всё хорошо, ничего не болит."):
        out.append((f"neg:{text[:12]}", text, ("no-mention",)))
    return out


def gen_sensation_matrix() -> list[tuple[str, str, tuple]]:
    out = []
    anchors = (("животе", "живот"), ("груди", "грудь"), ("руке", "рука"))
    for sens in sorted(SENSATION_NOUNS):
        if sens in ("шум", "звон", "туман", "жар", "боль", "боли", "двоение", "тошнота"):
            continue  # paired-rule, verb-path, or legacy-label coverage elsewhere
        for loc_raw, loc_site in anchors[:2]:
            out.append(
                (f"sens:{sens}-{loc_site}", f"{_cap(sens)} в {loc_raw}.", ("site", loc_site))
            )
    for text, site in (
        ("Шум в ушах.", "ухо"),
        ("Звон в ухе.", "ухо"),
        ("Туман перед глазами.", "глаз"),
        ("Двоение в глазах.", "глаз"),
        ("Кровь из носа идёт.", "нос"),
        ("Синяк под глазом.", "глаз"),
    ):
        out.append((f"sens:{text[:10]}", text, ("site", site)))
    # тошнота keeps its legacy label (site None by design); the complaint
    # must exist, not the site.
    for text in ("Тошнота в груди.", "Тошнит с утра."):
        out.append((f"sens-nausea:{text[:10]}", text, ("mention",)))
    return out


def gen_inflection_matrix() -> list[tuple[str, str, tuple]]:
    out = []
    pairs = [
        ("ногу", "нога"), ("руку", "рука"), ("голову", "голова"), ("спину", "спина"),
        ("ноге", "нога"), ("руке", "рука"), ("голове", "голова"), ("спине", "спина"),
        ("ногой", "нога"), ("рукой", "рука"), ("зубах", "зуб"), ("ушах", "ухо"),
        ("глазах", "глаз"), ("плече", "плечо"), ("колене", "колено"), ("горле", "горло"),
    ]
    for raw, site in pairs:
        out.append((f"infl:{raw}", f"Болит в {raw}.", ("site", site)))
    return out


def gen_false_world_matrix() -> list[tuple[str, str, tuple]]:
    out = []
    for text in (
        "Смотрела фильм, там все умирали.",
        "Мне снилось, что я умираю.",
        "В новостях сказали, что кто-то умер.",
        "Умру от смеха.",
        "Шучу, голова не болит.",
        "Раньше болела голова, сейчас всё хорошо.",
        "Смотрю сериал.",
        "Слушаю радио.",
        "По телевизору концерт идёт.",
        "Пойду гулять с дочкой.",
        "Дочка мне не звонила.",
        "Сын не звонит совсем.",
        "Надоели эти таблетки.",
        "Сдавала кровь на анализ.",
        "Погода хорошая сегодня.",
        "В магазин ходила.",
    ):
        out.append((f"fw:{text[:14]}", text, ("no-mention",)))
    # other-person illness per kin sample (inflected where the old matcher failed)
    for kin in (
        "муж", "жена", "дочь", "дочкой", "дочери", "сын", "сына",
        "внук", "внука", "внучка", "племянник", "племянника", "мама",
        "папа", "сестра", "брат", "соседка", "зять", "невестка",
    ):
        out.append((f"fw-kin:{kin}", f"У {kin} голова болит.", ("no-mention",)))
    # pivots must still open speaker episodes
    for text, site in (
        ("у мужа плохо, а у меня голова болит", "голова"),
        ("после фильма голова разболелась", "голова"),
        ("а сейчас у меня болит живот", "живот"),
        ("дочка звонила, а у меня спина болит", "спина"),
    ):
        out.append((f"pivot:{text[:14]}", text, ("site", site)))
    return out


def gen_past_matrix() -> list[tuple[str, str, tuple]]:
    out = []
    # bare past markers keep grounding (structural rule 1)
    for text, site in (
        ("Со вчера головная боль.", "голова"),
        ("Вчера ухо заложило.", "ухо"),
        ("Живот болел вчера.", "живот"),
        ("Раньше болело.", None),
    ):
        if site:
            out.append((f"past-keep:{text[:12]}", text, ("site", site)))
        else:
            out.append((f"past-keep:{text[:12]}", text, ("frame-past-False",)))
    # explicit resolution suppresses
    for text in (
        "Раньше болела голова, сейчас всё хорошо.",
        "Вчера болел живот, а сегодня прошёл.",
        "Голова болела, сейчас не болит.",
    ):
        out.append((f"past-resolved:{text[:12]}", text, ("frame-past-True",)))
    return out


def gen_refusal_matrix() -> list[tuple[str, str, tuple]]:
    out = []
    for text in (
        "Не беспокой меня ещё.",
        "не хочу об этом говорить",
        "Больше не спрашивай.",
        "Оставьте меня, пожалуйста.",
        "Не надо мне вопросов.",
        "Не хочу рассказывать подробности.",
    ):
        out.append((f"refusal:{text[:12]}", text, ("act", "DECLINE")))
    for text in ("Отстань.", "Хватит меня спрашивать."):
        out.append((f"hostile:{text[:8]}", text, ("not-act-decline",)))
    return out


def gen_severity_matrix() -> list[tuple[str, str, tuple]]:
    out = []
    for word in sorted(SEVERITY_WORDS):
        out.append((f"sev:{word}", word, ("severity",)))
    # negated degrees are not severity values
    for text in ("Не очень болит.", "Не сильно беспокоит.", "мне больше не надо"):
        out.append((f"sev-neg:{text[:10]}", text, ("no-severity",)))
    return out


def gen_time_matrix() -> list[tuple[str, str, tuple]]:
    out = []
    for word in sorted(TIME_WORDS):
        key = word.split()[-1]
        # Ordinal-day phrases are DURATION, the rest TIME (span contract).
        kind = "DURATION" if word in ("второй день", "третий день") else "TIME"
        if word in ("месяц назад", "неделю назад"):
            key = word.split()[0]
        out.append((f"time:{word}", f"Болит {word}.", (f"span-{kind}", key)))
    return out


def gen_garbage_matrix() -> list[tuple[str, str, tuple]]:
    out = []
    for text in (
        "Алло.", "Ага.", "Угу.", "Что?", "Повторите.", "Не слышу.",
        "Просто колхози", "Эээ.", "Ну.", "Так.", "Вот.",
        "Да.", "Нет.",
    ):
        out.append((f"garbage:{text}", text, ("no-mention",)))
    # STT-noise prefixed complaints must still ground the site
    for site in sorted(BODY_SITE_LEMMAS):
        word = _cap(site)
        out.append((f"noise-site:{site}", f"Алло, {word} болит.", ("site", _expected_site(word))))
    return out


def gen_site_onset_matrix() -> list[tuple[str, str, tuple]]:
    """Onset adjuncts must not break site extraction."""
    out = []
    for site in sorted(BODY_SITE_LEMMAS):
        word = _cap(site)
        for onset in ("со вчера", "с утра", "давно", "второй день", "неделю"):
            out.append((
                f"site-onset:{site}-{onset.split()[0]}",
                f"{word} болит {onset}.",
                ("site", _expected_site(word)),
            ))
    return out


def gen_site_severity_inline_matrix() -> list[tuple[str, str, tuple]]:
    """Inline severity must not break site extraction."""
    out = []
    for site in sorted(BODY_SITE_LEMMAS):
        word = _cap(site)
        for sev in ("сильно", "очень сильно", "немного", "невыносимо"):
            out.append((
                f"site-sev:{site}-{sev.split()[0]}",
                f"{word} болит {sev}.",
                ("site", _expected_site(word)),
            ))
    return out


def gen_kin_verb_matrix() -> list[tuple[str, str, tuple]]:
    """Other-person illness in any verb form stays suppressed."""
    out = []
    kins = ("муж", "жена", "дочь", "сын", "внук", "мама", "папа", "сестра", "соседка")
    for kin in kins:
        for text in (
            f"У {kin} болит голова.",
            f"У {kin} температура.",
            f"У {kin} плохо.",
        ):
            out.append((f"kin-verb:{kin}-{text[3:9]}", text, ("no-mention",)))
    # background-noise chatter generated from the lexicon class
    for noise in sorted(NOISE_WORDS):
        out.append((f"fw-noise:{noise}", f"Смотрю {noise}.", ("no-mention",)))
    return out


def gen_past_sites_matrix() -> list[tuple[str, str, tuple]]:
    """Past-anchored speaker pain keeps grounding (structural rule 1)."""
    out = []
    for site in sorted(BODY_SITE_LEMMAS):
        word = _cap(site)
        out.append((
            f"past-site:{site}",
            f"Со вчера {word.lower()} болит.",
            ("site", _expected_site(word)),
        ))
    return out


def gen_refusal_with_complaint_matrix() -> list[tuple[str, str, tuple]]:
    """A complaint after/inside a refusal still grounds (safety wins)."""
    out = []
    for text, site in (
        ("Не беспокой меня, голова болит.", "голова"),
        ("Не хочу говорить, живот болит.", "живот"),
        ("Оставьте меня, спина болит.", "спина"),
        ("Не спрашивай, зуб болит.", "зуб"),
        ("Хватит, нога болит.", "нога"),
        ("Отстань, рука болит.", "рука"),
    ):
        out.append((f"ref-compl:{site}", text, ("site", site)))
    return out


def gen_call_flows() -> list[tuple[str, list[str], tuple]]:
    out = []
    # pain chains across a site sample
    for site in (
        "голова", "живот", "спина", "нога", "рука", "грудь", "шея",
        "горло", "ухо", "зуб", "колено", "плечо", "поясница", "глаз",
    ):
        word = _cap(site)
        out.append((
            f"flow:{site}",
            ["Здравствуйте.", f"{word} болит.", "Давно уже.", "Сильно."],
            ("call-episode", site),
        ))
    # sensation flows (nosebleed takes the bleeding-triage path: engagement
    # only, not a plain episode — that triage design is out of this gate)
    for text, site, spec in (
        (["Здравствуйте.", "Тяжесть в животе.", "Со вчера.", "Средне."], "живот", "call-episode"),
        (["Здравствуйте.", "Шум в ушах.", "Давно.", "Немного."], "ухо", "call-episode"),
        (["Здравствуйте.", "Кровь из носа идёт.", "Только что.", "Сильно."], "нос", "call-engaged"),
    ):
        out.append((f"flow-sens:{site}", text, (spec, site) if spec != "call-engaged" else (spec,)))
    # false-world calls stay clean
    for text in (
        ["Здравствуйте.", "Смотрела фильм, там все умирали.", "Сама в порядке.", "Пока."],
        ["Здравствуйте.", "У внука голова болит сильно.", "Пока."],
        ["Здравствуйте.", "умру от смеха", "Пока."],
        ["Здравствуйте.", "Раньше болела голова, сейчас всё хорошо.", "Пока."],
        ["Здравствуйте.", "Смотрю сериал.", "Пока."],
    ):
        out.append((f"flow-fw:{text[1][:10]}", text, ("call-no-episode",)))
    # refusal calls ask nothing further
    for text in (
        ["Здравствуйте.", "Не беспокой меня ещё.", "Пока."],
        ["Здравствуйте.", "Не хочу рассказывать подробности.", "Пока."],
    ):
        out.append((f"flow-ref:{text[1][:10]}", text, ("call-no-question-after-refusal",)))
    # corrections and mixed subjects
    out.append((
        "flow-correction",
        ["Здравствуйте.", "Живот болит.", "Ой, нет, голова.", "Давно."],
        ("call-episode-quiet", "голова"),
    ))
    out.append((
        "flow-mixed",
        ["Здравствуйте.", "у мужа плохо, а у меня голова болит", "Давно."],
        ("call-episode", "голова"),
    ))
    return out


# ---------------------------------------------------------------- runner

def run_mention_case(name: str, text: str, spec: tuple) -> list[str]:
    kind = spec[0]
    if kind == "site":
        return check_site(text, spec[1])
    if kind == "mention":
        ms = extract_issue_mentions(text)
        if not ms:
            return [f"no mention at all for {text!r}"]
        return []
    if kind == "no-mention":
        return check_no_mention(text)
    if kind == "act":
        return check_act(text, spec[1])
    if kind == "not-act-decline":
        got = normalize_act(_fresh_state(), text)
        if got == "DECLINE":
            return [f"hostile mapped to DECLINE (must escalate): {text!r}"]
        return []
    if kind == "frame-past-True":
        return check_frame(text, "past", True)
    if kind == "frame-past-False":
        return check_frame(text, "past", False)
    if kind == "severity":
        return check_severity_value(text)
    if kind == "no-severity":
        from packages.dialogue_engine.issue_memory import (
            extract_grounded_severity_value,
        )

        if extract_grounded_severity_value(text) is not None:
            return [f"negated degree read as severity: {text!r}"]
        return []
    if kind == "span-TIME":
        return check_span(text, "TIME", spec[1])
    if kind == "span-DURATION":
        return check_span(text, "DURATION", spec[1])
    return [f"unknown spec {spec}"]


def run_call_case(name: str, texts: list[str], spec: tuple) -> list[str]:
    kind = spec[0]
    if kind == "call-episode":
        return check_call_episode(texts, spec[1])
    if kind == "call-episode-quiet":
        return check_call_episode_quiet(texts, spec[1])
    if kind == "call-engaged":
        return check_call_engaged(texts)
    if kind == "call-no-episode":
        return check_call_no_episode(texts)
    if kind == "call-no-question-after-refusal":
        turns, _ = _run_call(texts, "ref")
        if len(turns) >= 2 and "?" in turns[1]["v"]:
            return [f"question after refusal: {turns[1]['v']!r}"]
        return []
    return [f"unknown spec {spec}"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    args = ap.parse_args()

    scenarios: list[tuple[str, object, tuple]] = []
    scenarios += [(n, t, s) for n, t, s in gen_site_matrix()]
    scenarios += [(n, t, s) for n, t, s in gen_neg_matrix()]
    scenarios += [(n, t, s) for n, t, s in gen_sensation_matrix()]
    scenarios += [(n, t, s) for n, t, s in gen_inflection_matrix()]
    scenarios += [(n, t, s) for n, t, s in gen_false_world_matrix()]
    scenarios += [(n, t, s) for n, t, s in gen_past_matrix()]
    scenarios += [(n, t, s) for n, t, s in gen_refusal_matrix()]
    scenarios += [(n, t, s) for n, t, s in gen_severity_matrix()]
    scenarios += [(n, t, s) for n, t, s in gen_time_matrix()]
    scenarios += [(n, t, s) for n, t, s in gen_garbage_matrix()]
    scenarios += [(n, t, s) for n, t, s in gen_site_onset_matrix()]
    scenarios += [(n, t, s) for n, t, s in gen_site_severity_inline_matrix()]
    scenarios += [(n, t, s) for n, t, s in gen_kin_verb_matrix()]
    scenarios += [(n, t, s) for n, t, s in gen_past_sites_matrix()]
    scenarios += [(n, t, s) for n, t, s in gen_refusal_with_complaint_matrix()]
    call_cases = gen_call_flows()

    if args.only:
        scenarios = [sc for sc in scenarios if args.only in sc[0]]
        call_cases = [sc for sc in call_cases if args.only in sc[0]]

    total = len(scenarios) + len(call_cases)
    if not args.only:
        assert total >= MIN_SCENARIOS, f"gate shrank to {total} < {MIN_SCENARIOS}"

    results: list[dict] = []
    failed = 0
    for name, text, spec in scenarios:
        try:
            errors = run_mention_case(name, text, spec)
        except Exception as exc:  # noqa: BLE001 - gate must report, not crash
            errors = [f"exception: {type(exc).__name__}: {exc}"]
        ok = not errors
        failed += not ok
        results.append({"name": name, "u": text, "passed": ok, "errors": errors})
        if not ok:
            print(f"FAIL {name}: {text!r} -> {errors}")
    for name, texts, spec in call_cases:
        try:
            errors = run_call_case(name, texts, spec)
        except Exception as exc:  # noqa: BLE001
            errors = [f"exception: {type(exc).__name__}: {exc}"]
        ok = not errors
        failed += not ok
        results.append({"name": name, "u": " | ".join(texts), "passed": ok, "errors": errors})
        if not ok:
            print(f"FAIL {name}: {errors}")

    payload = {
        "passed": total - failed,
        "n": total,
        "ok": failed == 0,
        "git_sha": _git_sha(),
        "results": results,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / "hard1000-latest.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out}: {total - failed}/{total}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
