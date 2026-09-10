"""ActionPolicy Shadow M1 integration tests — production-safe, fail-open."""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.dialogue_engine.action_policy.actions import ActionKind, CandidateAction
from packages.dialogue_engine.action_policy.bridge import legacy_plan_to_action_key
from packages.dialogue_engine.action_policy.policy import PolicyDecision
from packages.dialogue_engine.action_policy_shadow import (
    FROZEN_POLICY_SHA,
    action_policy_mode,
    run_shadow_pre_legacy,
)
from packages.dialogue_engine.conversation_policy import (
    TurnContext,
    _schedule_next_action_legacy,
    schedule_next_action,
)
from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.response_plan import ResponsePlan
from packages.dialogue_engine.runtime import runtime_truth
from packages.dialogue_engine.state import EngineState
from packages.dialogue_engine.turn_understanding import RichUserTurn

ROOT = Path(__file__).resolve().parents[2]
FROZEN_SHA = "61e17934f7be3b10ca5df9b2581cb0a8b853c1fe"


@pytest.fixture(autouse=True)
def _reset_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("IMVERA_ACTION_POLICY_MODE", raising=False)
    yield
    monkeypatch.delenv("IMVERA_ACTION_POLICY_MODE", raising=False)


def _state(**kwargs) -> EngineState:
    base = {
        "call_id": "shadow-test",
        "turn_seq": 3,
        "processing_turn_id": "u-3",
        "first_user_turn_received": True,
    }
    base.update(kwargs)
    return EngineState(**base)


def _rich(**kwargs) -> RichUserTurn:
    base = {
        "utterance_id": "u-3",
        "raw_text": "",
        "dialogue_act": "answer",
        "control": "none",
        "answers_pending_question": False,
        "needs_clarification": False,
    }
    base.update(kwargs)
    return RichUserTurn(**base)


def test_a_mode_off_does_not_call_evaluator(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "off")
    assert action_policy_mode() == "off"
    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("shadow must not run when mode=off")

    monkeypatch.setattr(
        "packages.dialogue_engine.action_policy_shadow.run_shadow_pre_legacy",
        boom,
    )
    state = _state()
    plan = schedule_next_action(state, TurnContext(user_text=""))
    assert called["n"] == 0
    assert isinstance(plan, ResponsePlan)
    assert state.action_policy_shadow_records == []


def test_unknown_mode_fails_safe_to_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "soft")
    assert action_policy_mode() == "off"


def test_b_shadow_disagreement_does_not_control_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "shadow")

    fake_chosen = CandidateAction(kind=ActionKind.SUMMARY_CLOSE)
    fake_decision = PolicyDecision(
        chosen=fake_chosen,
        candidates=(),
        rejected=(),
        policy_version="action-policy-phase1-v7",
    )

    monkeypatch.setattr(
        "packages.dialogue_engine.action_policy_shadow.choose",
        lambda *_a, **_k: fake_decision,
    )
    from packages.contracts.enums import SlotStatus
    from packages.dialogue_engine.state import IssueEpisode

    state = _state()
    state.slots["wellness"] = SlotStatus.FILLED
    state.background_goal_status["wellness"] = "answered"
    state.issue_episodes["ep-1"] = IssueEpisode(
        episode_id="ep-1",
        primary_label="колено",
        kind="symptom",
        known_attributes={},
        status="open",
    )
    state.active_episode_id = "ep-1"
    turn = _rich(raw_text="болит колено")
    plan = schedule_next_action(
        state,
        TurnContext(turn=turn, user_text=turn.raw_text),
    )
    legacy_key = legacy_plan_to_action_key(plan).label()
    assert len(state.action_policy_shadow_records) == 1
    rec = state.action_policy_shadow_records[0]
    assert rec["policy_influenced_output"] is False
    assert rec["shadow_action"] == "SUMMARY_CLOSE"
    assert rec["legacy_action"] == legacy_key
    assert plan is not None
    assert legacy_key != "SUMMARY_CLOSE"


def test_c_fail_open_choose_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "shadow")

    def boom(*_a, **_k):
        raise RuntimeError("choose exploded")

    monkeypatch.setattr(
        "packages.dialogue_engine.action_policy_shadow.choose",
        boom,
    )
    state = _state()
    plan = schedule_next_action(state, TurnContext(user_text="привет"))
    assert isinstance(plan, ResponsePlan)
    assert state.action_policy_shadow_records
    assert state.action_policy_shadow_records[0]["shadow_status"] == "error"
    assert state.action_policy_shadow_records[0]["policy_influenced_output"] is False


def test_d_fail_open_snapshot_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "shadow")

    def boom(*_a, **_k):
        raise RuntimeError("snapshot exploded")

    monkeypatch.setattr(
        "packages.dialogue_engine.action_policy_shadow.build_policy_snapshot",
        boom,
    )
    state = _state()
    plan = schedule_next_action(state, TurnContext(user_text="привет"))
    assert isinstance(plan, ResponsePlan)
    assert state.action_policy_shadow_records[0]["error_stage"] == "build_policy_snapshot"


def test_e_fail_open_telemetry_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "shadow")

    def boom_buffer(*_a, **_k):
        raise RuntimeError("buffer failed")

    monkeypatch.setattr(
        "packages.dialogue_engine.action_policy_shadow.buffer_shadow_record",
        boom_buffer,
    )
    state = _state()
    plan = schedule_next_action(state, TurnContext(user_text="привет"))
    assert isinstance(plan, ResponsePlan)


def test_f_pre_legacy_snapshot_before_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "shadow")
    state = _state()
    state.background_goal_status["wellness"] = "unseen"
    state.required_background_goals = {"wellness"}
    seen = {}

    real_build = __import__(
        "packages.dialogue_engine.action_policy.snapshot", fromlist=["build_policy_snapshot"]
    ).build_policy_snapshot

    def spy_build(st):
        seen["wellness_before"] = st.background_goal_status.get("wellness")
        seen["pending_before"] = st.pending_episode_attribute
        return real_build(st)

    monkeypatch.setattr(
        "packages.dialogue_engine.action_policy_shadow.build_policy_snapshot",
        spy_build,
    )
    plan = schedule_next_action(state, TurnContext(user_text="", newly_filled_slots=("wellness",)))
    assert seen["wellness_before"] == "unseen"
    # Legacy mutates coverage from fills AFTER shadow snapshot.
    assert state.background_goal_status.get("wellness") == "answered"
    assert isinstance(plan, ResponsePlan)
    assert state.action_policy_shadow_records


def test_g_exactly_one_legacy_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "shadow")
    calls = {"n": 0}
    real = _schedule_next_action_legacy

    def counted(state, ctx):
        calls["n"] += 1
        return real(state, ctx)

    monkeypatch.setattr(
        "packages.dialogue_engine.conversation_policy._schedule_next_action_legacy",
        counted,
    )
    schedule_next_action(_state(), TurnContext(user_text="привет"))
    assert calls["n"] == 1


def test_h_frozen_policy_unchanged() -> None:
    import subprocess

    core = [
        "policy.py",
        "scorer.py",
        "features.py",
        "constraints.py",
        "mandatory.py",
        "need_value.py",
        "needs.py",
        "snapshot.py",
        "semantic_signals.py",
        "actions.py",
    ]
    for name in core:
        proc2 = subprocess.run(
            [
                "git",
                "diff",
                f"{FROZEN_SHA}:{ 'packages/dialogue_engine/action_policy/' + name }",
                f"HEAD:{ 'packages/dialogue_engine/action_policy/' + name }",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc2.stdout == "", f"frozen file changed: {name}\n{proc2.stdout}"


def test_i_no_raw_text_in_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "shadow")
    state = _state()
    schedule_next_action(
        state,
        TurnContext(
            turn=_rich(raw_text="секретный текст про давление"),
            user_text="секретный текст про давление",
        ),
    )
    rec = state.action_policy_shadow_records[0]
    blob = str(rec)
    assert "секретный" not in blob
    assert "raw_text" not in rec
    assert "transcript" not in rec
    assert "mandatory_question" not in rec


def test_j_pending_obligation_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "shadow")
    from packages.contracts.enums import SlotStatus
    from packages.dialogue_engine.state import IssueEpisode

    state = _state()
    state.issue_episodes["ep-1"] = IssueEpisode(
        episode_id="ep-1",
        primary_label="колено",
        kind="symptom",
        known_attributes={"onset": "вчера"},
        status="open",
    )
    state.active_episode_id = "ep-1"
    state.pending_episode_attribute = "current"
    state.slots["wellness"] = SlotStatus.FILLED
    state.background_goal_status["wellness"] = "answered"
    schedule_next_action(state, TurnContext(user_text=""))
    rec = state.action_policy_shadow_records[0]
    assert rec["critical_flags"]["pending_obligation"] is True
    # Frozen v7 may ASK a different need; shadow must flag silent pending discard.
    if rec["shadow_action"] != "ASK_EPISODE:current":
        assert rec["critical_violation"] is True
        assert "critical_pending_discard" in rec["critical_violation_flags"]
    assert rec["policy_influenced_output"] is False


def test_k_safety_urgent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "shadow")
    turn = _rich(raw_text="не могу дышать")
    state = _state()
    schedule_next_action(state, TurnContext(turn=turn, user_text=turn.raw_text))
    rec = state.action_policy_shadow_records[0]
    assert rec["critical_flags"]["urgent"] is True
    assert rec["shadow_action"] == "SAFETY"
    assert rec["policy_influenced_output"] is False


def test_l_control_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "shadow")
    turn = _rich(raw_text="пока", control="stop_call")
    state = _state()
    plan = schedule_next_action(state, TurnContext(turn=turn, user_text=turn.raw_text))
    assert legacy_plan_to_action_key(plan).kind.value in {"GOODBYE_FINAL", "CONTROL"}
    assert state.action_policy_shadow_records[0]["policy_influenced_output"] is False


def test_m_repair(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "shadow")
    turn = _rich(raw_text="повторите", dialogue_act="repair")
    state = _state()
    plan = schedule_next_action(state, TurnContext(turn=turn, user_text=turn.raw_text))
    assert legacy_plan_to_action_key(plan).label() == "REPAIR"
    assert state.action_policy_shadow_records[0]["shadow_action"] == "REPAIR"


def test_n_multi_episode_telemetry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "shadow")
    from packages.contracts.enums import SlotStatus
    from packages.dialogue_engine.state import IssueEpisode

    state = _state()
    state.slots["wellness"] = SlotStatus.FILLED
    state.background_goal_status["wellness"] = "answered"
    state.issue_episodes["ep-a"] = IssueEpisode(
        episode_id="ep-a",
        primary_label="голова",
        kind="symptom",
        known_attributes={"onset": "вчера", "current": "active"},
        status="open",
    )
    state.issue_episodes["ep-b"] = IssueEpisode(
        episode_id="ep-b",
        primary_label="плечо",
        kind="symptom",
        known_attributes={},
        status="open",
    )
    state.active_episode_id = "ep-a"
    state.pending_episode_ids = ["ep-b"]
    schedule_next_action(state, TurnContext(user_text=""))
    rec = state.action_policy_shadow_records[0]
    assert rec["snapshot_summary"]["pending_episode_count"] == 1
    assert rec["shadow_action"] is not None


def test_o_its_leave_optional_not_restart(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "shadow")
    from packages.contracts.enums import SlotStatus
    from packages.dialogue_engine.state import IssueEpisode

    state = _state()
    state.slots["wellness"] = SlotStatus.FILLED
    state.background_goal_status["wellness"] = "answered"
    state.important_to_share_asked = True
    state.important_to_share_resolved = True
    state.issue_episodes["ep-1"] = IssueEpisode(
        episode_id="ep-1",
        primary_label="колено",
        kind="symptom",
        known_attributes={
            "onset": "вчера",
            "current": "active",
            "severity": "лёгкая",
        },
        status="open",
    )
    state.active_episode_id = "ep-1"
    schedule_next_action(state, TurnContext(user_text="больше ничего"))
    rec = state.action_policy_shadow_records[0]
    assert rec["shadow_action"] != "ASK_EPISODE:functional_impact"


def test_p_idempotency_key_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "shadow")
    state = _state(processing_turn_id="u-42", turn_seq=42, revision=7)
    schedule_next_action(state, TurnContext(user_text="ok"))
    key = state.action_policy_shadow_records[0]["idempotency_key"]
    assert key == "shadow-test:ACTION_POLICY_SHADOW:u-42:7"


def test_runtime_truth_exposes_shadow_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "shadow")
    truth = runtime_truth()
    assert truth["action_policy.mode"] == "shadow"
    assert truth["action_policy.policy_version"] == "action-policy-phase1-v7"
    assert truth["action_policy.frozen_policy_sha"] == FROZEN_POLICY_SHA


def test_engine_drain_clears_buffer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "shadow")
    eng = DialogueEngine(call_id="drain-test")
    eng.state.processing_turn_id = "u-1"
    eng.state.turn_seq = 1
    schedule_next_action(eng.state, TurnContext(user_text="привет"))
    assert eng.state.action_policy_shadow_records
    drained = eng.drain_action_policy_shadow_records()
    assert drained
    assert eng.state.action_policy_shadow_records == []


def test_call_actor_does_not_import_action_policy() -> None:
    import ast

    path = ROOT / "packages/voice_runtime/call_actor.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    assert not any("action_policy" in m for m in modules)


def test_shadow_latency_p99_under_5ms(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gate: shadow evaluation alone p99 < 5 ms (no I/O)."""
    import statistics
    import time

    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "shadow")
    from packages.contracts.enums import SlotStatus
    from packages.dialogue_engine.state import IssueEpisode

    state = _state()
    state.slots["wellness"] = SlotStatus.FILLED
    state.background_goal_status["wellness"] = "answered"
    state.issue_episodes["ep-1"] = IssueEpisode(
        episode_id="ep-1",
        primary_label="колено",
        kind="symptom",
        known_attributes={"onset": "вчера"},
        status="open",
    )
    state.active_episode_id = "ep-1"
    samples_ms: list[float] = []
    for i in range(80):
        state.action_policy_shadow_records.clear()
        state.processing_turn_id = f"u-lat-{i}"
        state.turn_seq = 100 + i
        t0 = time.perf_counter()
        run_shadow_pre_legacy(state, TurnContext(user_text=""))
        samples_ms.append((time.perf_counter() - t0) * 1000.0)
    samples_ms.sort()
    p99 = samples_ms[int(len(samples_ms) * 0.99) - 1]
    p50 = statistics.median(samples_ms)
    assert p99 < 5.0, f"shadow p99={p99:.3f}ms p50={p50:.3f}ms samples={samples_ms[-5:]}"
