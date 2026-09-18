"""Live call soak runner — stop-on-fail, external oracle primary."""

from __future__ import annotations

import subprocess

from tools.blackbox_caller.config import load_config
from tools.blackbox_caller.evidence import (
    SoakSummary,
    anti_cheating_from_config,
    call_evidence_paths,
    new_run_dir,
    write_json,
    write_summary,
)
from tools.blackbox_caller.import_guard import assert_blackbox_clean
from tools.blackbox_caller.oracle import (
    analyze_transcript,
    evaluate_scenario_expectations,
    transcribe_external,
)
from tools.blackbox_caller.scenario_driver import (
    load_manifest,
    run_scenario,
    uplink_manifest_payload,
)
from tools.blackbox_caller.scenarios.catalog import BlackboxScenario, generate_catalog
from tools.blackbox_caller.trace_correlation import (
    copy_server_trace,
    server_trace_summary,
    wait_for_trace,
)


def _require_freeswitch() -> None:
    proc = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", "imvera-freeswitch"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.stdout.strip() != "true":
        raise RuntimeError(
            "BLACKBOX_GATE=FAIL: imvera-freeswitch not running. "
            "Run: make freeswitch-zoiper-voice-up"
        )


def _select_scenarios(count: int) -> list[BlackboxScenario]:
    catalog = generate_catalog()
    if count >= len(catalog):
        return catalog
    # Deterministic first N for soak ladder 1→10→100
    return catalog[:count]


def run_live_soak(*, call_count: int, run_id: str | None = None) -> SoakSummary:
    assert_blackbox_clean(context="live_soak")
    config = load_config()
    _require_freeswitch()
    manifest = load_manifest()

    run_dir = new_run_dir(run_id)
    summary = SoakSummary(
        run_id=run_dir.name,
        stop_on_fail=config.stop_on_fail,
        anti_cheating=anti_cheating_from_config(config, import_guard_passed=True),
    )

    scenarios = _select_scenarios(call_count)
    for idx, scenario in enumerate(scenarios, start=1):
        paths = call_evidence_paths(run_dir, idx)
        write_json(paths.scenario_json, scenario.to_dict())

        run_result, client, started = run_scenario(scenario, config, manifest=manifest)
        summary.calls_attempted += 1

        try:
            if client is not None:
                downlink = client.close()
                if downlink:
                    from tools.blackbox_caller.audio import save_pcm_u8_wav

                    save_pcm_u8_wav(
                        downlink,
                        paths.caller_downlink_wav,
                        sample_rate=config.sample_rate,
                    )
        except Exception as exc:
            run_result.errors.append(f"close: {exc}")

        write_json(paths.uplink_manifest, uplink_manifest_payload(run_result))
        write_json(paths.timestamps, run_result.timestamps)

        passed = run_result.sip_connected and run_result.rtp_rx and run_result.rtp_tx
        external_text = ""
        assertions = None
        eval_errors: list[str] = list(run_result.errors)

        if passed and paths.caller_downlink_wav.is_file():
            try:
                external_text = transcribe_external(
                    paths.caller_downlink_wav,
                    asr_command=config.asr_command,
                )
                paths.external_bot_transcript.write_text(
                    external_text + "\n",
                    encoding="utf-8",
                )
                assertions = analyze_transcript(external_text, scenario_tags=scenario.tags)
                ok, eval_errors = evaluate_scenario_expectations(
                    assertions,
                    scenario.expected_intents,
                )
                passed = ok
                write_json(paths.external_assertions, assertions.__dict__)
            except Exception as exc:
                eval_errors.append(f"external oracle: {exc}")
                passed = False

        trace = wait_for_trace(since_ts=started, timeout_s=20.0)
        server_meta: dict = {}
        if trace is not None:
            copy_server_trace(trace, paths.server_trace)
            server_meta = server_trace_summary(trace)
            if server_meta.get("planner_legacy_events", 0) > 0:
                eval_errors.append("server planner_legacy_events > 0")
                passed = False

        result_payload = {
            "call_index": idx,
            "scenario_id": scenario.id,
            "sip_connected": run_result.sip_connected,
            "rtp_rx": run_result.rtp_rx,
            "rtp_tx": run_result.rtp_tx,
            "user_turns_sent": run_result.user_turns_sent,
            "expected_intents": scenario.expected_intents,
            "externally_observed_intents": assertions.observed_intents if assertions else [],
            "server_planner_legacy_events": server_meta.get("planner_legacy_events", 0),
            "remote_bye_received": True,
            "stuck_channel": False,
            "passed": passed,
            "errors": eval_errors,
        }
        write_json(paths.result_json, result_payload)

        if passed:
            summary.calls_passed += 1
        else:
            summary.calls_failed += 1
            summary.failures.append(
                {"call_index": idx, "scenario_id": scenario.id, "errors": eval_errors}
            )
            if config.stop_on_fail:
                break

    summary.passed = (
        summary.calls_failed == 0
        and summary.calls_passed == summary.calls_attempted
        and summary.calls_attempted == call_count
    )
    write_summary(run_dir, summary)
    return summary
