"""Metamorphic DecisionRouter tests — no double scheduler mutation."""

from __future__ import annotations

from copy import deepcopy

import pytest

from packages.dialogue_engine.conversation_policy import (
    TurnContext,
    _schedule_next_action_legacy,
    schedule_next_action,
)
from packages.dialogue_engine.decision_router import (
    route_schedule_next_action,
    soft_cohort_selected,
)
from packages.dialogue_engine.state import EngineState
from packages.dialogue_engine.response_plan import ResponsePlan


def _state(call_id: str = "router-meta-1") -> EngineState:
    return EngineState(call_id=call_id, turn_seq=3, first_user_turn_received=True)


def _plan_fingerprint(plan: ResponsePlan) -> tuple:
    return (
        plan.action,
        str(getattr(plan.obligation, "value", plan.obligation)),
        plan.intent,
        plan.slot,
        plan.next_slot,
        plan.control,
        plan.marks_question,
        plan.close_reason,
        tuple(str(n) for n in (plan.question_needs or ())),
        plan.episode_id,
        plan.acknowledge,
        plan.mandatory_question,
    )


def test_legacy_mode_identical_to_direct_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "legacy")
    monkeypatch.delenv("IMVERA_ACTION_POLICY_CUTOVER_ENABLED", raising=False)
    ctx = TurnContext(user_text="нормально")
    a = _state("same-a")
    b = _state("same-a")
    plan_router = schedule_next_action(a, ctx)
    plan_direct = _schedule_next_action_legacy(b, ctx)
    assert _plan_fingerprint(plan_router) == _plan_fingerprint(plan_direct)
    assert a.action_policy_shadow_records == []
    assert getattr(a, "action_policy_router_stats", {}).get("legacy_invocations") == 1


def test_off_alias_identical_to_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "off")
    ctx = TurnContext(user_text="нормально")
    a = _state()
    b = _state()
    assert _plan_fingerprint(schedule_next_action(a, ctx)) == _plan_fingerprint(
        _schedule_next_action_legacy(b, ctx)
    )


def test_shadow_output_identical_to_legacy_and_single_legacy_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "shadow")
    ctx = TurnContext(user_text="нормально")
    shadow_state = _state("shadow-1")
    legacy_state = _state("shadow-1")
    calls = {"n": 0}
    real = _schedule_next_action_legacy

    def counting(state, turn_context):
        calls["n"] += 1
        return real(state, turn_context)

    plan_shadow = route_schedule_next_action(
        shadow_state, ctx, legacy=counting
    )
    plan_legacy = real(legacy_state, ctx)
    assert calls["n"] == 1
    assert _plan_fingerprint(plan_shadow) == _plan_fingerprint(plan_legacy)
    assert shadow_state.action_policy_shadow_records
    assert all(
        r.get("policy_influenced_output") is False
        for r in shadow_state.action_policy_shadow_records
    )


def test_soft_non_selected_cohort_identical_to_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "soft")
    monkeypatch.setenv("IMVERA_ACTION_POLICY_CUTOVER_ENABLED", "1")
    monkeypatch.setenv("IMVERA_ACTION_POLICY_SOFT_PERCENT", "0")
    ctx = TurnContext(user_text="нормально")
    a = _state("cohort-miss")
    b = _state("cohort-miss")
    assert soft_cohort_selected("cohort-miss", percent=0) is False
    assert _plan_fingerprint(schedule_next_action(a, ctx)) == _plan_fingerprint(
        _schedule_next_action_legacy(b, ctx)
    )
    assert a.action_policy_shadow_records == []
    assert getattr(a, "action_policy_router_stats", {}).get("soft_cohort_miss") == 1


def test_soft_policy_failure_falls_back_to_legacy_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "soft")
    monkeypatch.setenv("IMVERA_ACTION_POLICY_CUTOVER_ENABLED", "1")
    monkeypatch.setenv("IMVERA_ACTION_POLICY_SOFT_PERCENT", "100")
    ctx = TurnContext(user_text="нормально")
    state = _state("cohort-hit")
    assert soft_cohort_selected("cohort-hit", percent=100) is True

    import packages.dialogue_engine.decision_router as router

    monkeypatch.setattr(
        router,
        "_choose_policy_plan",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("forced")),
    )
    calls = {"n": 0}
    real = _schedule_next_action_legacy
    expected_state = _state("cohort-hit")
    expected = real(expected_state, ctx)

    def counting(s, tc):
        calls["n"] += 1
        return real(s, tc)

    plan = route_schedule_next_action(state, ctx, legacy=counting)
    assert calls["n"] == 1
    assert _plan_fingerprint(plan) == _plan_fingerprint(expected)
    assert getattr(state, "action_policy_router_stats", {}).get(
        "policy_fallback_legacy"
    ) == 1
    assert state.action_policy_shadow_records
    assert state.action_policy_shadow_records[0]["policy_influenced_output"] is False


def test_policy_mode_without_cutover_is_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "policy")
    monkeypatch.delenv("IMVERA_ACTION_POLICY_CUTOVER_ENABLED", raising=False)
    from packages.dialogue_engine.action_policy_shadow_config import action_policy_mode

    assert action_policy_mode() == "legacy"
    ctx = TurnContext(user_text="нормально")
    a = _state()
    b = _state()
    assert _plan_fingerprint(schedule_next_action(a, ctx)) == _plan_fingerprint(
        _schedule_next_action_legacy(b, ctx)
    )


def test_soft_does_not_invoke_both_schedulers_on_success_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When policy succeeds, legacy must not run (no double mutation)."""
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "soft")
    monkeypatch.setenv("IMVERA_ACTION_POLICY_CUTOVER_ENABLED", "1")
    monkeypatch.setenv("IMVERA_ACTION_POLICY_SOFT_PERCENT", "100")
    ctx = TurnContext(user_text="нормально")
    state = _state("soft-success")

    import packages.dialogue_engine.decision_router as router

    fake_plan = ResponsePlan(
        obligation="acknowledge_important_fact",
        action="speak",
        acknowledge="Понимаю.",
        intent="ack_only",
        marks_question=False,
    )
    fake_rec = {
        "policy_influenced_output": True,
        "shadow_status": "ok",
        "decision_id": "d1",
        "idempotency_key": "k1",
        "critical_violation": False,
        "schema_version": 1,
        "decision_scope": "conversation_scheduler",
        "frozen_policy_sha": "x",
        "policy_version": "action-policy-phase1-v8",
        "shadow_action": "ACK_ONLY",
        "legacy_action": "ACK_ONLY",
        "agree": True,
        "divergence_class": "policy_authoritative",
        "cutover_eligible": True,
        "critical_violation_flags": [],
        "critical_flags": {},
        "pending_before": {"episode_id": None, "need": None},
        "input_kind": "timer_or_internal",
        "decision_origin": "internal_scheduler",
        "turn_id": 3,
        "utterance_id": "",
        "engine_revision_before_legacy": 0,
        "engine_turn_seq": 3,
        "deployment_sha": "test",
        "shadow_total_latency_ms": 0.1,
        "policy_choose_latency_ms": 0.1,
        "shadow_latency_ms": 0.1,
        "mandatory_class": None,
        "snapshot_summary": None,
        "chosen_score": None,
        "chosen_contributions": None,
        "candidate_count": 1,
        "rejection_rule_ids": [],
        "error_stage": "",
        "error_type": "",
        "snapshot_fingerprint_sha256": None,
    }
    monkeypatch.setattr(
        router,
        "_choose_policy_plan",
        lambda *_a, **_k: (deepcopy(fake_plan), dict(fake_rec)),
    )
    calls = {"n": 0}

    def boom_legacy(*_a, **_k):
        calls["n"] += 1
        raise AssertionError("legacy must not run when policy authoritative succeeds")

    plan = route_schedule_next_action(state, ctx, legacy=boom_legacy)
    assert calls["n"] == 0
    assert plan.intent == "ack_only"
    assert getattr(state, "action_policy_router_stats", {}).get(
        "policy_authoritative"
    ) == 1
    assert state.action_policy_shadow_records[0]["policy_influenced_output"] is True
