"""Stress gate — load DialogueEngine / CallActor / CallSession paths with full JSONL logging.

Layers (ADR-014 oriented):
  engine       — 500-scenario corpus via CorpusRunner (parallel workers)
  call_actor   — same corpus through CallSession + CallActor + mock TTS (async concurrency)
  session      — tests/corpus 1k scenarios via CallSession (parallel workers)

Output: .run/stress_gate/<run_id>/
  summary.json
  scenarios.jsonl      — one record per scenario per layer
  failures.jsonl       — failed scenarios only
  gaps.json            — failure taxonomy + recommended next fixes
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

StressLayer = Literal["engine", "call_actor", "session", "all"]

RUN_ROOT = ROOT / ".run" / "stress_gate"

_GAP_HINTS: dict[str, str] = {
    "goodbye_final": "DialogueEngine reducer/playout completion — verify chain",
    "opening_count": "Double opening — stale delivery V2 or duplicate CallStarted",
    "partial_unresolved_close": "Timer/wait or clarify path — check timer handling",
    "slot fill order": "Reducer slot progression — wellness→mood→sleep→plans invariant broken",
    "wellness ack": "Response plan ack prefix mismatch for wellness category",
    "planner_legacy": "IMVERA_DIALOGUE_ENGINE=1 not active — dual brain risk",
    "tts": "CallActor TTS delivery / reservation release on failure",
    "timeout": "CallActor deliver hung — check playback pump + generation_id cancel",
    "corpus": "CallSession path diverges from DialogueEngine — sync semantic bridge",
}


@dataclass
class StressConfig:
    count: int = 100
    workers: int = 8
    call_actor_concurrency: int = 4
    layers: StressLayer = "all"
    stop_on_fail: bool = False
    run_id: str = ""
    out_dir: Path | None = None
    verbose_failures: bool = True

    def resolved_run_id(self) -> str:
        return self.run_id or datetime.now(UTC).strftime("%Y%m%d-%H%M%S")

    def resolved_out_dir(self) -> Path:
        if self.out_dir is not None:
            return self.out_dir
        return RUN_ROOT / self.resolved_run_id()


@dataclass
class ScenarioRecord:
    layer: str
    scenario_id: str
    category: str
    passed: bool
    elapsed_ms: float
    errors: list[str] = field(default_factory=list)
    invariants: dict[str, int] = field(default_factory=dict)
    speak_intents: list[str] = field(default_factory=list)
    reached_goodbye_final: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "scenario_id": self.scenario_id,
            "category": self.category,
            "passed": self.passed,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "errors": self.errors,
            "invariants": self.invariants,
            "speak_intents": self.speak_intents,
            "reached_goodbye_final": self.reached_goodbye_final,
            "extra": self.extra,
        }


@dataclass
class LayerSummary:
    layer: str
    total: int
    passed: int
    failed: int
    elapsed_s: float
    scenarios_per_s: float
    failure_buckets: dict[str, int] = field(default_factory=dict)

    @property
    def gate_passed(self) -> bool:
        return self.failed == 0 and self.total > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "gate": "PASS" if self.gate_passed else "FAIL",
            "elapsed_s": round(self.elapsed_s, 3),
            "scenarios_per_s": round(self.scenarios_per_s, 2),
            "failure_buckets": self.failure_buckets,
        }


@dataclass
class StressSummary:
    run_id: str
    git_sha: str
    config: dict[str, Any]
    layers: list[LayerSummary] = field(default_factory=list)
    overall_passed: bool = False
    gaps: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "git_sha": self.git_sha,
            "config": self.config,
            "overall": "PASS" if self.overall_passed else "FAIL",
            "layers": [layer.to_dict() for layer in self.layers],
            "gaps": self.gaps,
        }


def git_sha_short() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, OSError):
        return os.environ.get("IMVERA_GIT_SHA", "unknown")


def _ensure_engine_env() -> None:
    os.environ["IMVERA_DIALOGUE_ENGINE"] = "1"
    os.environ["IMVERA_VOICE_DIRECT_WELLNESS_OPENING"] = "1"


def _bucket_errors(errors: list[str]) -> str:
    joined = " ".join(errors).lower()
    for key in _GAP_HINTS:
        if key in joined:
            return key
    if errors:
        return errors[0][:80]
    return "unknown"


def _build_gaps(records: list[ScenarioRecord]) -> list[dict[str, Any]]:
    buckets: dict[str, list[str]] = {}
    for rec in records:
        if rec.passed:
            continue
        bucket = _bucket_errors(rec.errors)
        buckets.setdefault(bucket, []).append(rec.scenario_id)

    gaps: list[dict[str, Any]] = []
    for bucket, ids in sorted(buckets.items(), key=lambda x: -len(x[1])):
        hint = _GAP_HINTS.get(bucket, "Inspect failures.jsonl for scenario_id traces")
        gaps.append(
            {
                "bucket": bucket,
                "count": len(ids),
                "sample_ids": ids[:5],
                "recommendation": hint,
            }
        )
    return gaps


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _run_engine_scenario(scenario) -> ScenarioRecord:
    from packages.dialogue_engine.corpus.runner import CorpusRunner

    t0 = time.perf_counter()
    try:
        result = CorpusRunner(scenario).run()
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        inv = result.invariants
        return ScenarioRecord(
            layer="engine",
            scenario_id=scenario.id,
            category=scenario.wellness_category,
            passed=result.passed,
            elapsed_ms=elapsed_ms,
            errors=result.errors,
            invariants={
                "opening_replays": inv.opening_replays,
                "duplicate_playout_mutations": inv.duplicate_playout_mutations,
                "failed_to_goodbye_final": inv.failed_to_goodbye_final,
                "premature_unresolved_close": inv.premature_unresolved_close,
            },
            speak_intents=result.speak_intents,
            reached_goodbye_final=result.reached_goodbye_final,
        )
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return ScenarioRecord(
            layer="engine",
            scenario_id=scenario.id,
            category=scenario.wellness_category,
            passed=False,
            elapsed_ms=elapsed_ms,
            errors=[f"exception: {exc}"],
            extra={"traceback": traceback.format_exc()},
        )


def run_engine_stress(
    config: StressConfig, scenarios: list
) -> tuple[LayerSummary, list[ScenarioRecord]]:
    t0 = time.monotonic()
    records: list[ScenarioRecord] = []
    workers = max(1, min(config.workers, len(scenarios)))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_run_engine_scenario, sc): sc for sc in scenarios}
        for fut in as_completed(futures):
            rec = fut.result()
            records.append(rec)
            if config.stop_on_fail and not rec.passed:
                for pending in futures:
                    if not pending.done():
                        pending.cancel()

    elapsed = time.monotonic() - t0
    passed = sum(1 for r in records if r.passed)
    buckets: dict[str, int] = {}
    for rec in records:
        if not rec.passed:
            b = _bucket_errors(rec.errors)
            buckets[b] = buckets.get(b, 0) + 1

    summary = LayerSummary(
        layer="engine",
        total=len(records),
        passed=passed,
        failed=len(records) - passed,
        elapsed_s=elapsed,
        scenarios_per_s=len(records) / elapsed if elapsed > 0 else 0.0,
        failure_buckets=buckets,
    )
    return summary, records


def _interpret_user_text_for_corpus(session, text: str, answer_slot: str | None):
    from packages.dialogue.interpretation import interpret_user_turn, to_turn_interpretation
    from packages.dialogue.state import DialogueState
    from packages.dialogue_engine.fast_interpreter import fast_interpret_semantic
    from packages.dialogue_engine.semantic import semantic_from_legacy, semantic_to_interpretation

    fast_sem, confident = fast_interpret_semantic(text, answer_slot=answer_slot)
    if confident:
        semantic = fast_sem
        interp = semantic_to_interpretation(semantic)
    else:
        shadow = DialogueState(
            call_id=session.state.call_id,
            elder_display_name=session.state.elder_display_name,
            family_id=session.state.family_id,
            fsm_state=session.state.fsm_state,
            pending_slot=answer_slot,
            pending_question_delivered=answer_slot is not None,
            delivered_answer_slot=answer_slot,
        )
        legacy_interp = interpret_user_turn(shadow, text)
        semantic = semantic_from_legacy(legacy_interp, text=text, answer_slot=answer_slot)
        interp = semantic_to_interpretation(semantic)

    contract = to_turn_interpretation(
        session.state,
        session.turn_id + 1,
        text,
        interp,
        state_version=session.state.state_version,
    )
    return interp, contract


async def _deliver_engine_turn(actor, session, result) -> list[str]:
    """Deliver SessionTurnResult through CallActor; return delivery errors."""
    errors: list[str] = []
    queue: list = [result]
    while queue:
        current = queue.pop(0)
        try:
            await asyncio.wait_for(actor._deliver_session_turn(current), timeout=8.0)
        except Exception as exc:
            errors.append(f"deliver: {exc}")
            break
        gen = current.proposal.generation_id if current.proposal else ""
        if gen and current.proposal.speech:
            session.mark_spoken_action(gen)
        follow = session.pop_engine_playout_followup()
        if follow is not None:
            queue.append(follow)
    return errors


async def _run_call_actor_scenario_async(scenario) -> ScenarioRecord:
    from packages.core.memory_store import InMemoryCallRecordStore
    from packages.dialogue.session import CallSession
    from packages.dialogue_engine.corpus.schema import (
        DeferLastSpeak,
        DeliverPlayout,
        DeliverPlayoutDuplicate,
        FireTimerExpired,
        StaleLastSpeak,
        UserStep,
    )
    from packages.dialogue_engine.effects import SpeakEffect
    from packages.voice_runtime.call_actor import CallActor, CallActorConfig, MediaCallbacks
    from packages.voice_runtime.playback import PlaybackQueue

    _ensure_engine_env()
    t0 = time.perf_counter()
    errors: list[str] = []
    speak_intents: list[str] = []

    async def noop(*_a, **_k):
        return None

    async def mock_synthesize(text, **kwargs):
        yield SimpleNamespace(pcm_s16le=b"\x00\x01" * 160, sample_rate=16000)

    session = CallSession(
        call_id=f"stress-{scenario.id}",
        family_id="stress-family",
        store=InMemoryCallRecordStore(),
    )
    if session._engine is None:
        return ScenarioRecord(
            layer="call_actor",
            scenario_id=scenario.id,
            category=scenario.wellness_category,
            passed=False,
            elapsed_ms=(time.perf_counter() - t0) * 1000.0,
            errors=["DialogueEngine not active on session"],
        )

    actor = CallActor(
        call_id=session.state.call_id,
        family_id="stress-family",
        session=session,
        stt=SimpleNamespace(),
        tts=SimpleNamespace(synthesize=mock_synthesize, cancel=noop),
        llm=SimpleNamespace(cancel_request=noop),
        media=MediaCallbacks(noop, noop, noop, noop),
        config=CallActorConfig(telephony_stream=False, post_speech_pause_ms=0),
    )
    actor._playback = PlaybackQueue(call_id=actor.call_id, sample_rate=16000)
    actor._playback_task = asyncio.create_task(actor._playback_pump())

    pending_speaks: list[SpeakEffect] = []
    last_delivered: SpeakEffect | None = None
    deferred: SpeakEffect | None = None

    try:
        start = session.start()
        if start.speak_effect is not None:
            speak_intents.append(start.speak_effect.intent)
        errors.extend(await _deliver_engine_turn(actor, session, start))
        if start.speak_effect is not None:
            pending_speaks.append(start.speak_effect)

        for step in scenario.steps:
            if isinstance(step, UserStep):
                answer_slot = session._engine.answer_context_slot()
                interp, contract = _interpret_user_text_for_corpus(session, step.text, answer_slot)
                result = session.handle_user_text(step.text, interp=interp, contract=contract)
                if result.speak_effect is not None:
                    speak_intents.append(result.speak_effect.intent)
                    pending_speaks.append(result.speak_effect)
                errors.extend(await _deliver_engine_turn(actor, session, result))
                if result.timer_effect is not None:
                    await actor._schedule_engine_timer(result.timer_effect)
            elif isinstance(step, DeliverPlayout):
                if step.include_summary:
                    while pending_speaks:
                        effect = pending_speaks.pop(0)
                        if effect.marks_question:
                            pending_speaks.insert(0, effect)
                            break
                        last_delivered = effect
                        session.mark_spoken_action(effect.generation_id)
                else:
                    if pending_speaks:
                        effect = pending_speaks.pop(0)
                        last_delivered = effect
                        session.mark_spoken_action(effect.generation_id)
            elif isinstance(step, DeliverPlayoutDuplicate):
                if last_delivered is not None:
                    session.mark_spoken_action(last_delivered.generation_id)
            elif isinstance(step, FireTimerExpired):
                timer_id = (
                    step.timer_id or f"wait-{session._engine.state.waiting_on_slot or 'wellness'}"
                )
                await actor._cancel_engine_timer()
                expired = session.handle_wait_expired(timer_id)
                if expired.speak_effect is not None:
                    speak_intents.append(expired.speak_effect.intent)
                errors.extend(await _deliver_engine_turn(actor, session, expired))
            elif isinstance(step, DeferLastSpeak):
                if pending_speaks:
                    deferred = pending_speaks.pop()
                    session._engine.on_delivery_deferred(deferred)
            elif isinstance(step, StaleLastSpeak):
                if deferred is not None:
                    session._engine.on_speak_effect_stale(deferred)
                    deferred = None

        reached = session._engine.state.goodbye_confirmed and "goodbye_final" in speak_intents
        if not reached and not scenario.allow_partial_close:
            errors.append("goodbye_final not reached via CallActor path")

    except Exception as exc:
        errors.append(f"exception: {exc}")
        errors.append(traceback.format_exc().splitlines()[-1])

    finally:
        if actor._playback_task is not None:
            actor._playback_task.cancel()
            await asyncio.gather(actor._playback_task, return_exceptions=True)
        await actor._cancel_engine_timer()
        await actor._cancel_wait_timer()

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return ScenarioRecord(
        layer="call_actor",
        scenario_id=scenario.id,
        category=scenario.wellness_category,
        passed=not errors,
        elapsed_ms=elapsed_ms,
        errors=errors,
        speak_intents=speak_intents,
        reached_goodbye_final="goodbye_final" in speak_intents
        and session._engine.state.goodbye_confirmed,
        extra={"engine_revision": session._engine.revision},
    )


def _run_call_actor_scenario(scenario) -> ScenarioRecord:
    return asyncio.run(_run_call_actor_scenario_async(scenario))


def run_call_actor_stress(
    config: StressConfig, scenarios: list
) -> tuple[LayerSummary, list[ScenarioRecord]]:
    t0 = time.monotonic()
    records: list[ScenarioRecord] = []
    concurrency = max(1, min(config.call_actor_concurrency, len(scenarios)))

    async def _run_all() -> None:
        sem = asyncio.Semaphore(concurrency)

        async def _one(sc) -> ScenarioRecord:
            async with sem:
                return await _run_call_actor_scenario_async(sc)

        tasks = [asyncio.create_task(_one(sc)) for sc in scenarios]
        for task in asyncio.as_completed(tasks):
            rec = await task
            records.append(rec)
            if config.stop_on_fail and not rec.passed:
                for t in tasks:
                    if not t.done():
                        t.cancel()

    asyncio.run(_run_all())
    elapsed = time.monotonic() - t0
    passed = sum(1 for r in records if r.passed)
    buckets: dict[str, int] = {}
    for rec in records:
        if not rec.passed:
            b = _bucket_errors(rec.errors)
            buckets[b] = buckets.get(b, 0) + 1

    summary = LayerSummary(
        layer="call_actor",
        total=len(records),
        passed=passed,
        failed=len(records) - passed,
        elapsed_s=elapsed,
        scenarios_per_s=len(records) / elapsed if elapsed > 0 else 0.0,
        failure_buckets=buckets,
    )
    return summary, records


def _run_session_scenario(scenario) -> ScenarioRecord:
    from tests.corpus.execute import run_scenario

    # tests/corpus targets CallSession + Planner (legacy path), not DialogueEngine.
    prev_engine = os.environ.get("IMVERA_DIALOGUE_ENGINE")
    os.environ["IMVERA_DIALOGUE_ENGINE"] = "0"
    t0 = time.perf_counter()
    try:
        result = run_scenario(scenario)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return ScenarioRecord(
            layer="session",
            scenario_id=scenario.id,
            category=scenario.category,
            passed=result.ok,
            elapsed_ms=elapsed_ms,
            errors=result.errors,
            extra={"turns": len(result.turns), "path": "planner_legacy"},
        )
    except Exception as exc:
        return ScenarioRecord(
            layer="session",
            scenario_id=scenario.id,
            category=getattr(scenario, "category", "unknown"),
            passed=False,
            elapsed_ms=(time.perf_counter() - t0) * 1000.0,
            errors=[f"exception: {exc}"],
        )
    finally:
        if prev_engine is None:
            os.environ.pop("IMVERA_DIALOGUE_ENGINE", None)
        else:
            os.environ["IMVERA_DIALOGUE_ENGINE"] = prev_engine


def run_session_stress(
    config: StressConfig, scenarios: list
) -> tuple[LayerSummary, list[ScenarioRecord]]:
    t0 = time.monotonic()
    records: list[ScenarioRecord] = []
    workers = max(1, min(config.workers, len(scenarios)))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_run_session_scenario, sc) for sc in scenarios]
        for fut in as_completed(futures):
            rec = fut.result()
            records.append(rec)
            if config.stop_on_fail and not rec.passed:
                break

    elapsed = time.monotonic() - t0
    passed = sum(1 for r in records if r.passed)
    buckets: dict[str, int] = {}
    for rec in records:
        if not rec.passed:
            b = _bucket_errors(rec.errors)
            buckets[b] = buckets.get(b, 0) + 1

    summary = LayerSummary(
        layer="session",
        total=len(records),
        passed=passed,
        failed=len(records) - passed,
        elapsed_s=elapsed,
        scenarios_per_s=len(records) / elapsed if elapsed > 0 else 0.0,
        failure_buckets=buckets,
    )
    return summary, records


def _select_engine_corpus(count: int) -> list:
    from packages.dialogue_engine.corpus.generator import generate_corpus

    corpus = generate_corpus()
    return corpus[: min(count, len(corpus))]


def _select_session_corpus(count: int) -> list:
    from tests.corpus.generate import generate_scenarios

    return generate_scenarios(minimum=max(count, 100))[:count]


def run_stress_gate(config: StressConfig) -> StressSummary:
    out_dir = config.resolved_out_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    engine_scenarios = _select_engine_corpus(config.count)
    session_scenarios = _select_session_corpus(config.count)

    all_records: list[ScenarioRecord] = []
    layer_summaries: list[LayerSummary] = []

    layers_to_run: list[StressLayer]
    if config.layers == "all":
        layers_to_run = ["engine", "call_actor", "session"]
    else:
        layers_to_run = [config.layers]

    if "engine" in layers_to_run:
        summary, records = run_engine_stress(config, engine_scenarios)
        layer_summaries.append(summary)
        all_records.extend(records)

    if "call_actor" in layers_to_run:
        summary, records = run_call_actor_stress(config, engine_scenarios)
        layer_summaries.append(summary)
        all_records.extend(records)

    if "session" in layers_to_run:
        summary, records = run_session_stress(config, session_scenarios)
        layer_summaries.append(summary)
        all_records.extend(records)

    scenario_rows = [r.to_json() for r in all_records]
    failure_rows = [r.to_json() for r in all_records if not r.passed]
    gaps = _build_gaps(all_records)

    _write_jsonl(out_dir / "scenarios.jsonl", scenario_rows)
    _write_jsonl(out_dir / "failures.jsonl", failure_rows)
    (out_dir / "gaps.json").write_text(
        json.dumps(gaps, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if config.verbose_failures:
        fail_dir = out_dir / "failures"
        fail_dir.mkdir(exist_ok=True)
        for rec in all_records:
            if not rec.passed:
                (fail_dir / f"{rec.layer}_{rec.scenario_id}.json").write_text(
                    json.dumps(rec.to_json(), ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )

    overall = all(layer.gate_passed for layer in layer_summaries)
    stress_summary = StressSummary(
        run_id=config.resolved_run_id(),
        git_sha=git_sha_short(),
        config={
            "count": config.count,
            "workers": config.workers,
            "call_actor_concurrency": config.call_actor_concurrency,
            "layers": config.layers,
            "stop_on_fail": config.stop_on_fail,
        },
        layers=layer_summaries,
        overall_passed=overall,
        gaps=gaps,
    )
    (out_dir / "summary.json").write_text(
        json.dumps(stress_summary.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return stress_summary


def _print_summary(summary: StressSummary, out_dir: Path) -> None:
    print(f"stress-gate run_id={summary.run_id} sha={summary.git_sha}")
    for layer in summary.layers:
        print(
            f"  {layer.layer}: {layer.passed}/{layer.total} PASS "
            f"({layer.elapsed_s:.2f}s, {layer.scenarios_per_s:.1f} scen/s)"
        )
        if layer.failure_buckets:
            print(f"    failures: {layer.failure_buckets}")
    print(f"  overall: {'PASS' if summary.overall_passed else 'FAIL'}")
    print(f"  artifacts: {out_dir}")
    if summary.gaps:
        print("  gaps (top):")
        for gap in summary.gaps[:5]:
            print(f"    [{gap['count']}] {gap['bucket']}: {gap['recommendation']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="IMVERA voice stress gate")
    parser.add_argument(
        "--count",
        type=int,
        default=int(os.environ.get("IMVERA_STRESS_COUNT", "100")),
        help="Scenarios per layer (default 100)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=int(os.environ.get("IMVERA_STRESS_WORKERS", "8")),
        help="Thread pool workers for engine/session layers",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=int(os.environ.get("IMVERA_STRESS_CONCURRENCY", "4")),
        help="Async concurrent CallActor scenarios",
    )
    parser.add_argument(
        "--layer",
        choices=["engine", "call_actor", "session", "all"],
        default=os.environ.get("IMVERA_STRESS_LAYER", "all"),
    )
    parser.add_argument("--stop-on-fail", action="store_true")
    parser.add_argument("--run-id", default=os.environ.get("IMVERA_STRESS_RUN_ID", ""))
    args = parser.parse_args(argv)

    _ensure_engine_env()
    config = StressConfig(
        count=args.count,
        workers=args.workers,
        call_actor_concurrency=args.concurrency,
        layers=args.layer,
        stop_on_fail=args.stop_on_fail,
        run_id=args.run_id,
    )
    summary = run_stress_gate(config)
    out_dir = config.resolved_out_dir()
    _print_summary(summary, out_dir)
    return 0 if summary.overall_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
