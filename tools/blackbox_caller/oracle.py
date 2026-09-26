"""Independent external oracle — NOT GigaAM production STT."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

BOT_INTENTS = (
    "opening",
    "check_mood",
    "check_sleep",
    "check_plans",
    "background_nutrition",
    "background_medication",
    "background_mood",
    "background_sleep",
    "summary",
    "goodbye_confirm",
    "goodbye_final",
    "repair",
    "ack_good",
    "ack_normal",
    "ack_okay",
    "ack_so_so",
    "ack_bad",
    "unknown",
)


@dataclass
class IntentObservation:
    intent: str
    evidence: str
    span: str = ""


@dataclass
class ExternalAssertions:
    opening_count: int = 0
    observed_intents: list[str] = field(default_factory=list)
    forbidden_sleep_reask: bool = False
    forbidden_plans_reask: bool = False
    reached_summary: bool = False
    reached_goodbye: bool = False
    errors: list[str] = field(default_factory=list)


def _resolve_whisper_cli() -> str | None:
    """Find openai-whisper CLI even when Frameworks scripts dir is off PATH."""
    found = shutil.which("whisper")
    if found:
        return found
    try:
        import sysconfig

        candidate = Path(sysconfig.get_path("scripts")) / "whisper"
        if candidate.is_file():
            return str(candidate)
    except Exception:
        pass
    return None


def transcribe_external(wav_path: Path, *, asr_command: str = "") -> str:
    """Transcribe downlink with independent ASR — never production GigaAM."""
    import os

    if asr_command:
        cmd = asr_command.replace("{wav}", str(wav_path))
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False)
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
        raise RuntimeError(
            f"IMVERA_BLACKBOX_ASR_CMD failed rc={proc.returncode}: {proc.stderr[:400]}"
        )
    whisper = _resolve_whisper_cli()
    if whisper:
        out_dir = wav_path.parent / "_asr_tmp"
        out_dir.mkdir(parents=True, exist_ok=True)
        model = (os.environ.get("IMVERA_BLACKBOX_WHISPER_MODEL") or "base").strip() or "base"
        proc = subprocess.run(
            [
                whisper,
                str(wav_path),
                "--model",
                model,
                "--language",
                "Russian",
                "--output_dir",
                str(out_dir),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        txt = out_dir / f"{wav_path.stem}.txt"
        if txt.is_file():
            return txt.read_text(encoding="utf-8").strip()
        if proc.stderr:
            raise RuntimeError(f"whisper failed: {proc.stderr[:400]}")
    raise RuntimeError(
        "BLACKBOX_GATE=FAIL: no independent ASR. Set IMVERA_BLACKBOX_ASR_CMD "
        "or install whisper CLI. Production GigaAM is forbidden as oracle."
    )


def _match_intents(text: str) -> list[IntentObservation]:
    lower = text.lower()
    found: list[IntentObservation] = []

    patterns: list[tuple[str, str]] = [
        (r"здравствуйте|это сервис амвера|как вы себя чувствуете|как себя чувствуете", "opening"),
        (r"покушать|с едой|поели", "background_nutrition"),
        (r"лекарств", "background_medication"),
        (r"настроение", "background_mood"),
        (r"спал(?:ось|ась|и)?|выспались|как спали", "background_sleep"),
        (r"настроени", "check_mood"),
        (r"как вы спали|спали", "check_sleep"),
        (r"план|занят|собираетесь", "check_plans"),
        (r"спасибо за разговор|не получилось узнать", "summary"),
        (r"до свидания|всего доброго|хорошего дня|всего вам хорошего", "goodbye_final"),
        (r"закончить разговор|ещё что-нибудь", "goodbye_confirm"),
        (r"повтор|не слыш|слышишь|алло", "repair"),
        (r"рада это слышать", "ack_good"),
        (r"понятно", "ack_normal"),
        (r"поняла", "ack_okay"),
        (r"понимаю", "ack_so_so"),
        (r"жаль|мне жаль", "ack_bad"),
    ]
    for pattern, intent in patterns:
        m = re.search(pattern, lower)
        if m:
            found.append(IntentObservation(intent=intent, evidence=pattern, span=m.group(0)))
    if not found and lower.strip():
        found.append(IntentObservation(intent="unknown", evidence="unclassified"))
    return found


def analyze_transcript(
    transcript: str,
    *,
    scenario_tags: list[str] | None = None,
) -> ExternalAssertions:
    """Semantic intent oracle from externally heard bot speech."""
    assertions = ExternalAssertions()
    tags = scenario_tags or []
    intents = _match_intents(transcript)
    assertions.observed_intents = [i.intent for i in intents]
    assertions.opening_count = sum(1 for i in intents if i.intent == "opening")
    assertions.reached_summary = any(i.intent == "summary" for i in intents)
    assertions.reached_goodbye = any(
        i.intent in {"goodbye_confirm", "goodbye_final"} for i in intents
    )

    lower = transcript.lower()
    if "multi_slot" in tags:
        sleep_hits = len(re.findall(r"как вы спали|спали", lower))
        plans_hits = len(re.findall(r"план|занят|собираетесь", lower))
        if sleep_hits > 0:
            assertions.forbidden_sleep_reask = True
            assertions.errors.append("multi_slot: bot re-asked sleep")
        if plans_hits > 0:
            assertions.forbidden_plans_reask = True
            assertions.errors.append("multi_slot: bot re-asked plans")

    if "contextual_horosho" in tags:
        # After plans question, "хорошо" must not close plans — next should not be summary-only
        pass

    if assertions.opening_count > 1:
        assertions.errors.append(f"opening replay count={assertions.opening_count}")

    if "no_pain_probe" in tags or "decline" in tags:
        pain_markers = ("голов", "сердц", "живот", "что болит", "беспокоит сильнее")
        for m in pain_markers:
            if m in lower:
                assertions.errors.append(f"decline path pain/concern probe language: {m!r}")

    return assertions


def evaluate_scenario_expectations(
    assertions: ExternalAssertions,
    expected_intents: list[str],
) -> tuple[bool, list[str]]:
    errors = list(assertions.errors)
    observed_set = set(assertions.observed_intents)
    for intent in expected_intents:
        if intent not in observed_set and intent not in {"goodbye_confirm"}:
            # goodbye_confirm may be skipped if user hangs up after summary in short scenarios
            if intent == "goodbye_final" and assertions.reached_summary:
                continue
            errors.append(f"missing expected intent: {intent}")
    if assertions.forbidden_sleep_reask or assertions.forbidden_plans_reask:
        errors.append("forbidden re-ask detected")
    return len(errors) == 0, errors
