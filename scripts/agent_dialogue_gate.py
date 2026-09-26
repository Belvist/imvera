#!/usr/bin/env python3
"""Agent-runnable dialogue gate — CallSession path, no Zoiper.

Runs the owner wellness/decline checklist through the same CallSession →
DialogueEngine path used in live calls (text in, speech out). Writes a
report under .run/agent_gates/ so Grok Bot / OpenCode can prove behaviour
without a human handset.

Layers:
  A (this script): engine-faithful text — always runnable if bridge code
     imports work. Does NOT exercise SIP/RTP/STT.
  B (existing): `make live-call-1` / `make live-debug-1` — real SIP/RTP
     when FreeSWITCH + pyVoIP lab is up.

Usage:
  python3 scripts/agent_dialogue_gate.py
  python3 scripts/agent_dialogue_gate.py --strict-first-probe
  make agent-dialogue-gate

Exit 0 = PASS, 1 = FAIL.
"""

from __future__ import annotations

import argparse
import os
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession

PAIN_MARKERS = ("голов", "сердц", "живот", "что болит")
URGENT_MARKERS = ("передам близк", "срочн", "вызову", "скорую")
REPORT_DIR = ROOT / ".run" / "agent_gates"


@dataclass
class TurnResult:
    user: str
    speech: str
    intent: str | None = None
    action: str | None = None


@dataclass
class GateReport:
    gate: str = "agent_dialogue_gate"
    layer: str = "A_callsession_engine"
    passed: bool = False
    git_sha: str = ""
    call_id: str = ""
    forbidden_actions: list[str] = field(default_factory=list)
    turns: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    note: str = (
        "Layer A proves DialogueEngine+CallSession behaviour. "
        "SIP/RTP/STT still need make live-call-1 / live-debug-1 (layer B)."
    )


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def _speech_of(result) -> str:
    return (result.proposal.speech or "").strip()


def _intent_of(result) -> str | None:
    prop = result.proposal
    for attr in ("intent", "action", "obligation"):
        val = getattr(prop, attr, None)
        if val:
            return str(val)
    return None


def run_checklist(*, strict_first_probe: bool) -> GateReport:
    call_id = f"agent-gate-{time.time_ns()}"
    report = GateReport(git_sha=_git_sha(), call_id=call_id)
    session = CallSession(
        call_id=call_id,
        family_id="agent-gate",
        elder_display_name="Тамара Юрьевна",
        store=InMemoryCallRecordStore(),
    )
    opening = session.start()
    session.state.mandatory_checks.update(
        identity=True, consent=True, can_talk=True
    )
    session.state.greeted = True
    session.mark_spoken_action(opening.proposal.generation_id)

    script = [
        "Привет. Чувствую себя, ну, более-менее сегодня.",
        "И ничего вроде не беспокоит.",
        "Ничего не болит, всё хорошо.",
        "Поел нормально.",
    ]

    turns: list[TurnResult] = []
    for text in script:
        result = session.handle_user_text(text)
        speech = _speech_of(result)
        session.mark_spoken_action(result.proposal.generation_id)
        turns.append(
            TurnResult(
                user=text,
                speech=speech,
                intent=_intent_of(result),
                action=str(getattr(result.proposal, "action", "") or ""),
            )
        )

    engine = session._engine
    assert engine is not None
    forbidden = list(engine.state.forbidden_actions or [])
    report.forbidden_actions = forbidden
    report.turns = [asdict(t) for t in turns]

    # --- hard fails (owner checklist) ---
    if "pain_site_probe" not in forbidden:
        report.errors.append(
            "DECLINE path did not set forbidden pain_site_probe "
            "(CDK step 2 act effects missing on this turn)"
        )
    if "concern_probe" not in forbidden:
        report.errors.append(
            "DECLINE path did not set forbidden concern_probe"
        )

    # After decline lines (index 1+), speech must not pain-site grill
    for t in turns[1:]:
        low = t.speech.lower()
        if any(m in low for m in PAIN_MARKERS):
            report.errors.append(
                f"pain-site language after decline: user={t.user!r} "
                f"vera={t.speech!r}"
            )
        if any(m in low for m in URGENT_MARKERS):
            report.errors.append(
                f"urgent/family escalation language on decline path: "
                f"vera={t.speech!r}"
            )

    # First reply after so-so: preferred not to open concern grill
    if turns:
        first = turns[0].speech.lower()
        if any(m in first for m in PAIN_MARKERS) or "беспокоит сильнее" in first:
            msg = (
                "after «более-менее» Vera opened concern/pain probe: "
                f"{turns[0].speech!r}"
            )
            if strict_first_probe:
                report.errors.append(msg)
            else:
                report.warnings.append(msg)

    report.passed = not report.errors
    return report



def run_dream_narrative_scenario() -> GateReport:
    """fs-80cf029f class: dream body mention must not open pain onset."""
    call_id = f"agent-gate-dream-{time.time_ns()}"
    report = GateReport(
        gate="agent_dialogue_gate_dream_narrative",
        git_sha=_git_sha(),
        call_id=call_id,
    )
    os.environ.setdefault("IMVERA_COVERAGE_LADDER", "1")
    from packages.dialogue_engine.scenario_runner import ScenarioRunner
    from packages.dialogue_engine.events import CallStarted, User
    from packages.dialogue_engine.effects import SpeakEffect
    from packages.dialogue_engine.semantic_kernel.kernel import interpret, kernel_to_rich_turn

    dream = (
        "Великолепно спала. О, Сталина видела! Сталина во сне видела. "
        "Приходил ко мне руку тянул."
    )
    r = ScenarioRunner(call_id=call_id, elder_display_name="Тамара Юрьевна")
    turns: list[TurnResult] = []
    r.run([CallStarted()])
    for u in (
        "Нормально, всё хорошо.",
        "Ничего не беспокоит.",
        "Поела нормально.",
        "Лекарств нет.",
    ):
        res = r.run([u])
        speech = " ".join(
            e.text for e in res.speak_effects if isinstance(e, SpeakEffect)
        )
        turns.append(TurnResult(user=u, speech=speech))
    kr = interpret(dream, utterance_id="u-dream", answer_slot="sleep", engine_state=r.state)
    rich = kernel_to_rich_turn(kr)
    res = r.run([User(text=dream, rich_turn=rich)])
    speech = " ".join(e.text for e in res.speak_effects if isinstance(e, SpeakEffect))
    turns.append(TurnResult(user=dream, speech=speech))
    report.turns = [asdict(t) for t in turns]
    report.forbidden_actions = list(r.state.forbidden_actions or [])
    low = speech.lower()
    if any(m in low for m in ("боль", "когда появилась", "рука тянул — зафиксировала")):
        report.errors.append(f"dream narrative opened pain probe: {speech!r}")
    if r.state.active_episode_id:
        report.errors.append(f"dream narrative created episode {r.state.active_episode_id}")
    if (r.state.wellness_concern or "").strip():
        report.errors.append(
            f"dream narrative wrote wellness_concern={r.state.wellness_concern!r}"
        )
    report.passed = not report.errors
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict-first-probe",
        action="store_true",
        help="FAIL if «более-менее» already opens concern (owner-hard mode)",
    )
    args = parser.parse_args()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = run_checklist(strict_first_probe=args.strict_first_probe)
    dream_report = run_dream_narrative_scenario()
    out = REPORT_DIR / f"{report.call_id}.json"
    out.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")
    dream_out = REPORT_DIR / f"{dream_report.call_id}.json"
    dream_out.write_text(
        json.dumps(asdict(dream_report), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    latest = REPORT_DIR / "latest.json"
    latest.write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
    (REPORT_DIR / "dream_narrative_latest.json").write_text(
        dream_out.read_text(encoding="utf-8"), encoding="utf-8"
    )

    status = "PASS" if report.passed else "FAIL"
    print(f"agent_dialogue_gate {status} sha={report.git_sha} call_id={report.call_id}")
    print(f"report={out}")
    print(f"forbidden={report.forbidden_actions}")
    for t in report.turns:
        print(f"  U: {t['user']}")
        print(f"  V: {t['speech'][:200]}")
    for w in report.warnings:
        print(f"WARN: {w}")
    for e in report.errors:
        print(f"ERROR: {e}")
    dstatus = "PASS" if dream_report.passed else "FAIL"
    print(f"dream_narrative_gate {dstatus} call_id={dream_report.call_id}")
    print(f"dream_report={dream_out}")
    for t in dream_report.turns:
        print(f"  U: {t['user'][:120]}")
        print(f"  V: {t['speech'][:200]}")
    for e in dream_report.errors:
        print(f"ERROR: {e}")
    print(report.note)
    return 0 if (report.passed and dream_report.passed) else 1


if __name__ == "__main__":
    raise SystemExit(main())
