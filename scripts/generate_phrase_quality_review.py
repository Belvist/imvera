#!/usr/bin/env python3
"""Generate human-readable phrase quality review for owner."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from golden_path.analyzer import Analysis, AnalysisKind
from golden_path.content_plan import build_content_plan
from golden_path.fixtures.phrase_quality_cases import (
    PHRASE_QUALITY_CASES,
    apply_bench_user_analysis,
)
from golden_path.generation_profile import VERA_DIALOGUE_GENERATION_PROFILE, load_generation_profile
from golden_path.llm import GoldenPathLLM
from golden_path.planner import Plan
from golden_path.prompts import contains_thinking_leak
from golden_path.renderer_policy import plan_uses_llm_renderer
from golden_path.spoken_quality import check_spoken_quality
from golden_path.validator import validate_reply


def _violation_category(violations: list[str]) -> str:
    if not violations:
        return "raw_pass"
    for v in violations:
        if v == "too_many_questions":
            return "extra_question"
        if v.startswith("forbidden_slot"):
            return "forbidden_slot"
        if v.startswith("reask_") or v.startswith("ask_blocked"):
            return "forbidden_slot"
        if v == "empty_llm_output":
            return "empty_output"
        if v.startswith("banned:"):
            return "command_tone"
        if v == "promise":
            return "action_mismatch"
        if "question_on" in v:
            return "extra_question"
    return "other"


def run_cases(profile_name: str) -> list[dict[str, object]]:
    llm = GoldenPathLLM()
    llm.profile = load_generation_profile(profile_name)
    rows: list[dict[str, object]] = []

    for case in PHRASE_QUALITY_CASES:
        state = case.build_state()
        plan = Plan(
            action=case.action,
            slot=case.slot,
            answer_type=case.answer_type,
            reason="review",
        )
        analysis = Analysis(kind=AnalysisKind.NORMAL_RESPONSE)
        content_plan = build_content_plan(plan, state, analysis, case.user_message)
        action = "ASK_SLOT" if case.action.value == "ASK_SLOT" else case.action.value

        deterministic = False
        regen = False
        raw = ""
        violations: list[str] = []
        spoken_v: list[str] = []

        if not plan_uses_llm_renderer(plan):
            from golden_path.fallbacks import typed_fallback

            apply_bench_user_analysis(case, state)
            final = typed_fallback(
                plan.action, state, slot=case.slot, answer_type=case.answer_type
            )
            deterministic = True
            validator_ok = True
            used_fallback = True
            spoken_v = check_spoken_quality(final)
        else:
            raw, _bundle = llm.generate(
                action=action,
                user_message=case.user_message,
                state=state,
                slot=case.slot,
                answer_type=case.answer_type,
                content_plan=content_plan,
            )
            v1 = validate_reply(
                raw, plan.action, state, slot=case.slot,
                answer_type=case.answer_type, apply_fallback=False,
            )
            if v1.ok:
                final = v1.text
                validator_ok = True
                used_fallback = False
                violations = []
            else:
                regen = True
                correction = "Исправь ответ. Одна короткая фраза. Максимум один вопрос."
                raw2, _ = llm.generate(
                    action=action,
                    user_message=case.user_message,
                    state=state,
                    slot=case.slot,
                    answer_type=case.answer_type,
                    content_plan=content_plan,
                    correction_hint=correction,
                )
                v2 = validate_reply(
                    raw2, plan.action, state, slot=case.slot,
                    answer_type=case.answer_type, apply_fallback=True,
                )
                raw = raw2
                final = v2.text
                validator_ok = v2.ok
                used_fallback = v2.used_fallback
                violations = list(v2.violations)

                violations = list(v2.violations)
            spoken_v = check_spoken_quality(final)

        structural_ok = validator_ok or used_fallback
        language_ok = not spoken_v
        full_pass = structural_ok and language_ok
        auto_fail = not full_pass or contains_thinking_leak(final)

        rows.append(
            {
                "case_id": case.case_id,
                "category": case.category,
                "action": plan.action_name(),
                "user": case.user_message,
                "raw": raw,
                "final": final,
                "validator_ok": validator_ok,
                "violations": violations,
                "spoken_violations": spoken_v,
                "structural_ok": structural_ok,
                "language_ok": language_ok,
                "full_pass": full_pass,
                "regen": regen,
                "fallback": used_fallback,
                "deterministic": deterministic,
                "auto_fail": auto_fail,
                "violation_category": _violation_category(violations),
            }
        )
    return rows


def render_markdown(rows: list[dict[str, object]], profile: str) -> str:
    total = len(rows)
    raw_pass = sum(1 for r in rows if not r["violations"] and not r["fallback"])
    regen_count = sum(1 for r in rows if r["regen"])
    fallback_count = sum(1 for r in rows if r["fallback"])
    deterministic_fallback = sum(
        1 for r in rows if r["fallback"] and r.get("deterministic")
    )
    validator_fallback = sum(
        1 for r in rows if r["fallback"] and not r.get("deterministic")
    )
    full_pass = sum(1 for r in rows if r["full_pass"])
    structural_ok = sum(1 for r in rows if r["structural_ok"])
    language_ok = sum(1 for r in rows if r["language_ok"])
    auto_fail = sum(1 for r in rows if r["auto_fail"])

    hist = Counter(
        str(r["violation_category"])
        for r in rows
        if r["violations"] and not r.get("deterministic")
    )
    spoken_hist = Counter(
        v for r in rows for v in r.get("spoken_violations", [])
    )

    lines = [
        "# Phrase Quality Review — Owner Read",
        "",
        f"Profile: `{profile}`",
        "",
        "## Summary",
        "",
        f"- total=**{total}**",
        f"- full_pass=**{full_pass}** (STRUCTURAL + LANGUAGE on FINAL)",
        f"- structural_ok=**{structural_ok}**",
        f"- language_ok=**{language_ok}**",
        f"- raw_pass=**{raw_pass}**",
        f"- regen_count=**{regen_count}**",
        f"- fallback_count=**{fallback_count}**",
        f"- deterministic_fallback=**{deterministic_fallback}** (control actions — by design)",
        f"- validator_fallback=**{validator_fallback}** (LLM rejected → typed fallback)",
        f"- auto_fail=**{auto_fail}**",
        "",
        "### Validator-triggered fallback histogram",
        "",
    ]
    if hist:
        for reason, count in hist.most_common():
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- (none)")
    lines.extend(["", "### Spoken-quality violations on FINAL", ""])
    if spoken_hist:
        for reason, count in spoken_hist.most_common():
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- (none)")
    lines.extend(["", "---", ""])

    for r in rows:
        fb_flag = " **← FALLBACK**" if r["fallback"] else ""
        lines.extend(
            [
                f"## {r['case_id']}{fb_flag}",
                "",
                f"**CASE:** {r['category']}",
                f"**ACTION:** {r['action']}",
                f"**USER:** {r['user']}",
                f"**RAW QWEN OUTPUT:** {r['raw'] or '(deterministic / empty)'}",
                f"**FINAL OUTPUT:** {r['final']}",
                f"**GATE:** structural={r['structural_ok']} language={r['language_ok']} full_pass={r['full_pass']}",
                f"**VALIDATOR:** ok={r['validator_ok']} violations={r['violations']}",
                f"**SPOKEN:** {r.get('spoken_violations') or 'ok'}",
                f"**REGENERATED:** {'yes' if r['regen'] else 'no'}",
                f"**FALLBACK:** {'yes' if r['fallback'] else 'no'}",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    profile = VERA_DIALOGUE_GENERATION_PROFILE
    llm = GoldenPathLLM()
    if not llm.check_health().ready:
        print("LLM not ready", file=sys.stderr)
        return 2

    rows = run_cases(profile)
    md = render_markdown(rows, profile)
    out = _REPO / "docs" / "PHRASE_QUALITY_REVIEW.md"
    out.write_text(md, encoding="utf-8")
    json_out = _REPO / "golden_path" / "traces" / "phrase-quality-review.json"
    json_out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out}")
    print(f"Wrote {json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
