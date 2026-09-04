"""Phrase quality bench — Qwen3-4B only, 3 sampling presets, 50 actions."""
from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from golden_path.analyzer import Analysis, AnalysisKind
from golden_path.content_plan import build_content_plan
from golden_path.fixtures.phrase_quality_cases import (
    PHRASE_QUALITY_CASES,
    PhraseQualityCase,
    apply_bench_user_analysis,
)
from golden_path.generation_profile import (
    BENCH_PROFILE_ORDER,
    PROFILES,
    VERA_DIALOGUE_GENERATION_PROFILE,
    load_generation_profile,
)
from golden_path.llm import GoldenPathLLM
from golden_path.planner import Plan
from golden_path.prompts import contains_thinking_leak
from golden_path.renderer_policy import plan_uses_llm_renderer
from golden_path.spoken_quality import check_spoken_quality
from golden_path.validator import validate_reply

_BANNED = ("давайте дальше", "давайте перейдём", "я вызову", "я позвоню")
_BROKEN_RU = re.compile(r"\b\w+ющ\w+\b")  # crude broken pattern guard


@dataclass
class CaseResult:
    case_id: str
    category: str
    profile: str
    prompt: str
    raw_output: str
    validator_ok: bool
    violations: list[str]
    final_output: str
    latency_ms: float
    auto_pass: bool
    auto_notes: list[str] = field(default_factory=list)


def _plan_from_case(case: PhraseQualityCase) -> Plan:
    return Plan(
        action=case.action,
        slot=case.slot,
        answer_type=case.answer_type,
        reason="bench_fixture",
    )


def _analysis_stub(case: PhraseQualityCase) -> Analysis:
    return Analysis(kind=AnalysisKind.NORMAL_RESPONSE)


def _auto_check(
    case: PhraseQualityCase,
    text: str,
    validated_ok: bool,
    used_fallback: bool,
    violations: list[str],
) -> tuple[bool, list[str]]:
    notes: list[str] = []
    low = (text or "").lower()
    if not text.strip():
        notes.append("empty_output")
    if violations and not used_fallback:
        notes.append("validator_fail")
    if text.count("?") > 1:
        notes.append("multi_question")
    for phrase in _BANNED:
        if phrase in low:
            notes.append(f"banned:{phrase}")
    if contains_thinking_leak(text):
        notes.append("thinking_leak")
    for code in check_spoken_quality(text):
        notes.append(f"spoken:{code}")
    if case.action.value == "ANSWER_USER" and case.answer_type not in (
        None,
    ) and case.answer_type and case.answer_type.value in ("IDENTITY", "PRIVACY"):
        pass
    elif case.action.value == "ANSWER_USER" and "?" in text:
        notes.append("question_on_answer_user")
    if case.slot and case.state_overrides.get("slot_statuses"):
        statuses = case.state_overrides["slot_statuses"]
        for slot_name, status in statuses.items():
            if status == "ANSWERED" and slot_name in low and "?" in text:
                notes.append(f"reask_answered:{slot_name}")
    return len(notes) == 0, notes


def run_profile(
    llm: GoldenPathLLM,
    profile_name: str,
    *,
    trace_dir: Path,
) -> list[CaseResult]:
    profile = load_generation_profile(profile_name)
    llm.profile = profile
    results: list[CaseResult] = []

    for case in PHRASE_QUALITY_CASES:
        state = case.build_state()
        plan = _plan_from_case(case)
        analysis = _analysis_stub(case)
        content_plan = build_content_plan(plan, state, analysis, case.user_message)
        action = plan.action.value
        if plan.action.value == "ASK_SLOT":
            action = "ASK_SLOT"

        if not plan_uses_llm_renderer(plan):
            from golden_path.fallbacks import typed_fallback

            apply_bench_user_analysis(case, state)
            text = typed_fallback(
                plan.action,
                state,
                slot=case.slot,
                answer_type=case.answer_type,
            )
            latency_ms = 0.0
            raw = ""
            prompt = f"ACTION: {plan.action_name()} [deterministic]"
            validated_ok = True
            used_fallback = True
            violations: list[str] = []
            final = text
        else:
            started = time.perf_counter()
            raw, bundle = llm.generate(
                action=action,
                user_message=case.user_message,
                state=state,
                slot=case.slot,
                answer_type=case.answer_type,
                content_plan=content_plan,
            )
            latency_ms = (time.perf_counter() - started) * 1000.0
            prompt = bundle.exact_prompt
            validated = validate_reply(
                raw,
                plan.action,
                state,
                slot=case.slot,
                answer_type=case.answer_type,
                apply_fallback=True,
            )
            validated_ok = validated.ok
            used_fallback = validated.used_fallback
            violations = list(validated.violations)
            final = validated.text

        auto_ok, auto_notes = _auto_check(
            case, final, validated_ok, used_fallback, violations
        )
        results.append(
            CaseResult(
                case_id=case.case_id,
                category=case.category,
                profile=profile_name,
                prompt=prompt,
                raw_output=raw or "",
                validator_ok=validated_ok,
                violations=violations,
                final_output=final,
                latency_ms=latency_ms,
                auto_pass=auto_ok,
                auto_notes=auto_notes,
            )
        )
    return results


def summarize(results: list[CaseResult]) -> dict[str, Any]:
    total = len(results)
    auto_pass = sum(1 for r in results if r.auto_pass)
    validator_ok = sum(1 for r in results if r.validator_ok)
    latencies = [r.latency_ms for r in results]
    latencies.sort()
    p50 = latencies[len(latencies) // 2] if latencies else 0.0
    return {
        "total": total,
        "auto_pass": auto_pass,
        "auto_pass_rate": round(auto_pass / total, 4) if total else 0.0,
        "validator_ok": validator_ok,
        "validator_ok_rate": round(validator_ok / total, 4) if total else 0.0,
        "latency_p50_ms": round(p50, 1),
        "failures": [
            {"case_id": r.case_id, "notes": r.auto_notes, "output": r.final_output[:120]}
            for r in results
            if not r.auto_pass
        ],
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Qwen3-4B phrase quality bench")
    parser.add_argument("--profile", choices=list(PROFILES.keys()), default=None)
    parser.add_argument("--all-presets", action="store_true")
    parser.add_argument("--trace-dir", default="golden_path/traces")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    llm = GoldenPathLLM()
    health = llm.check_health()
    if not health.ready:
        print("LLM not ready — start scripts/run_llm_host.sh", file=sys.stderr)
        return 2

    thinking = llm.verify_thinking_disabled()
    trace_dir = Path(args.trace_dir)
    trace_dir.mkdir(parents=True, exist_ok=True)

    profiles = BENCH_PROFILE_ORDER if args.all_presets else [args.profile or VERA_DIALOGUE_GENERATION_PROFILE]
    report: dict[str, Any] = {
        "model": health.model_id,
        "thinking": thinking,
        "profiles": {},
    }

    best_name = profiles[0]
    best_rate = -1.0

    for pname in profiles:
        results = run_profile(llm, pname, trace_dir=trace_dir)
        summary = summarize(results)
        report["profiles"][pname] = summary
        out = trace_dir / f"phrase-quality-{pname}.json"
        out.write_text(
            json.dumps(
                {
                    "summary": summary,
                    "results": [r.__dict__ for r in results],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"{pname}: auto_pass {summary['auto_pass']}/{summary['total']} "
              f"({summary['auto_pass_rate']*100:.1f}%) p50={summary['latency_p50_ms']}ms")
        if summary["auto_pass_rate"] > best_rate:
            best_rate = summary["auto_pass_rate"]
            best_name = pname

    report["best_generation_profile"] = best_name
    report["status"] = (
        "FINAL_SPOKEN_ACCEPTABLE"
        if best_rate >= 0.98
        else "BLOCKED_FINAL_LANGUAGE_QUALITY"
        if best_rate < 0.90
        else "FINAL_SPOKEN_NEEDS_REVIEW"
    )

    summary_path = trace_dir / "phrase-quality-summary.json"
    summary_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nBest profile: {best_name}")
    print(f"Status: {report['status']}")
    print(f"Thinking disabled: {thinking.get('thinking_disabled')}")
    print(f"Summary: {summary_path}")

    if args.strict and report["status"] != "FINAL_SPOKEN_ACCEPTABLE":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
