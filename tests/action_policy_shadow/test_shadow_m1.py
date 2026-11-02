"""ActionPolicy Shadow M1.1 — production-safe scheduler shadow tests."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from packages.dialogue_engine.action_policy.actions import ActionKind, CandidateAction
from packages.dialogue_engine.action_policy.bridge import legacy_plan_to_action_key
from packages.dialogue_engine.action_policy.policy import PolicyDecision
from packages.dialogue_engine.action_policy_shadow import (
    FROZEN_POLICY_SHA,
    allocate_decision_id,
    classify_divergence,
    run_shadow_pre_legacy,
)
from packages.dialogue_engine.action_policy_shadow_buffer import shadow_health_counters
from packages.dialogue_engine.action_policy_shadow_config import (
    action_policy_mode,
    make_error_record,
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
FROZEN_SHA = "254f0baed11ba7913d276c50ca7bd574778f19a5"


@pytest.fixture(autouse=True)
def _reset_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("IMVERA_ACTION_POLICY_MODE", raising=False)
    import importlib
    import sys

    # Keep evaluator importable even if a prior test popped it from sys.modules.
    if "packages.dialogue_engine.action_policy_shadow" not in sys.modules:
        importlib.import_module("packages.dialogue_engine.action_policy_shadow")
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
    assert action_policy_mode() == "legacy"
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


def test_mode_off_survives_evaluator_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "off")
    import builtins
    import sys

    sys.modules.pop("packages.dialogue_engine.action_policy_shadow", None)
    real_import = builtins.__import__

    def blocked(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "packages.dialogue_engine.action_policy_shadow" or name.startswith(
            "packages.dialogue_engine.action_policy_shadow."
        ):
            raise ImportError("simulated evaluator broken")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", blocked)
    try:
        plan = schedule_next_action(_state(), TurnContext(user_text="привет"))
        assert isinstance(plan, ResponsePlan)
    finally:
        sys.modules.pop("packages.dialogue_engine.action_policy_shadow", None)


def test_mode_shadow_import_error_fail_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "shadow")
    import builtins
    import sys

    sys.modules.pop("packages.dialogue_engine.action_policy_shadow", None)
    real_import = builtins.__import__

    def blocked(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "packages.dialogue_engine.action_policy_shadow":
            raise ImportError("simulated evaluator broken")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", blocked)
    try:
        state = _state()
        plan = schedule_next_action(state, TurnContext(user_text="привет"))
        assert isinstance(plan, ResponsePlan)
        assert state.action_policy_shadow_records
        rec = state.action_policy_shadow_records[0]
        assert rec["shadow_status"] == "error"
        assert rec["critical_violation"] is True
        assert "shadow_choose_error" in rec["critical_violation_flags"]
        assert rec["policy_influenced_output"] is False
    finally:
        # Restore module for later tests (import hook is undone by monkeypatch teardown).
        sys.modules.pop("packages.dialogue_engine.action_policy_shadow", None)


def test_soft_without_cutover_fails_safe_to_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "soft")
    monkeypatch.delenv("IMVERA_ACTION_POLICY_CUTOVER_ENABLED", raising=False)
    assert action_policy_mode() == "legacy"


def test_unknown_mode_fails_safe_to_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "hard")
    assert action_policy_mode() == "legacy"


def test_b_shadow_disagreement_does_not_control_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "shadow")
    import packages.dialogue_engine.action_policy_shadow as shadow_mod

    fake_decision = PolicyDecision(
        chosen=CandidateAction(kind=ActionKind.SUMMARY_CLOSE),
        candidates=(),
        rejected=(),
        policy_version="action-policy-phase1-v8",
    )
    monkeypatch.setattr(shadow_mod, "choose", lambda *_a, **_k: fake_decision)
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
    plan = schedule_next_action(state, TurnContext(turn=turn, user_text=turn.raw_text))
    legacy_key = legacy_plan_to_action_key(plan).label()
    rec = state.action_policy_shadow_records[0]
    assert rec["policy_influenced_output"] is False
    assert rec["shadow_action"] == "SUMMARY_CLOSE"
    assert rec["legacy_action"] == legacy_key
    assert rec["decision_scope"] == "conversation_scheduler"
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
    rec = state.action_policy_shadow_records[0]
    assert rec["shadow_status"] == "error"
    assert rec["critical_violation"] is True
    assert "shadow_choose_error" in rec["critical_violation_flags"]
    assert rec["policy_influenced_output"] is False
    assert rec["schema_version"] == 1
    assert rec["decision_id"]


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
    rec = state.action_policy_shadow_records[0]
    assert rec["error_stage"] == "build_policy_snapshot"
    assert rec["critical_violation"] is True
    assert "shadow_snapshot_error" in rec["critical_violation_flags"]


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
    seen: dict = {}
    real_build = __import__(
        "packages.dialogue_engine.action_policy.snapshot",
        fromlist=["build_policy_snapshot"],
    ).build_policy_snapshot

    def spy_build(st, ctx=None):
        seen["wellness_before"] = st.background_goal_status.get("wellness")
        return real_build(st, ctx)

    monkeypatch.setattr(
        "packages.dialogue_engine.action_policy_shadow.build_policy_snapshot",
        spy_build,
    )
    plan = schedule_next_action(state, TurnContext(user_text="", newly_filled_slots=("wellness",)))
    assert seen["wellness_before"] == "unseen"
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


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _ensure_frozen_sha_available(sha: str | None = FROZEN_SHA) -> None:
    """Fetch an exact historical/active commit omitted by shallow clones, or fail."""
    assert isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha), (
        f"invalid frozen SHA: {sha!r}"
    )
    probe = _git("cat-file", "-e", f"{sha}^{{commit}}")
    if probe.returncode == 0:
        return
    fetched = _git("fetch", "--depth=1", "origin", sha)
    assert fetched.returncode == 0, (
        f"frozen SHA {sha} missing and fetch failed: "
        f"rc={fetched.returncode} stderr={fetched.stderr!r}"
    )
    probe2 = _git("cat-file", "-e", f"{sha}^{{commit}}")
    assert probe2.returncode == 0, (
        f"frozen SHA {sha} still missing after fetch: stderr={probe2.stderr!r}"
    )


def test_h_frozen_policy_unchanged() -> None:
    """Historical proof stays immutable; the active candidate has its own hashes.

    A missing/invalid pin no longer skips protection. Candidate status verifies
    bytes against a checked-in manifest; frozen status additionally verifies Git.
    """
    import hashlib
    import json

    from packages.dialogue_engine import action_policy_shadow_config as cfg

    _ensure_frozen_sha_available()
    if cfg.POLICY_STATUS == "frozen":
        _ensure_frozen_sha_available(cfg.FROZEN_POLICY_SHA)
    historical_path = ROOT / "docs/evaluation/action-policy-phase1-v9-freeze-manifest.json"
    historical = json.loads(historical_path.read_text())
    assert historical["tested_sha"] == cfg.HISTORICAL_BASELINE_SHA == FROZEN_SHA
    all_historical = []
    all_active = []
    active = json.loads((ROOT / cfg.ACTIVE_POLICY_MANIFEST).read_text())
    assert active["policy_version"] == cfg.POLICY_VERSION
    assert active["status"] == cfg.POLICY_STATUS
    assert active["tested_sha"] == cfg.FROZEN_POLICY_SHA
    assert len(active["core_file_sha256"]) == 10
    assert set(active["core_file_sha256"]) == set(historical["core_file_sha256"])
    for name in sorted(historical["core_file_sha256"]):
        rel = f"packages/dialogue_engine/action_policy/{name}"
        proc = subprocess.run(
            ["git", "show", f"{FROZEN_SHA}:{rel}"], cwd=ROOT, capture_output=True, check=False
        )
        assert proc.returncode == 0, f"historical proof missing: {rel}"
        assert hashlib.sha256(proc.stdout).hexdigest() == historical["core_file_sha256"][name]
        all_historical.append(proc.stdout)
        current = (ROOT / rel).read_bytes()
        assert hashlib.sha256(current).hexdigest() == active["core_file_sha256"][name], name
        all_active.append(current)
        if cfg.POLICY_STATUS == "frozen":
            assert cfg.FROZEN_POLICY_SHA and len(cfg.FROZEN_POLICY_SHA) == 40
            proc2 = _git("diff", "--exit-code", cfg.FROZEN_POLICY_SHA, "--", rel)
            assert proc2.returncode == 0 and not proc2.stdout, rel
    assert hashlib.sha256(b"".join(all_historical)).hexdigest() == historical["policy_tree_sha256"]
    assert hashlib.sha256(b"".join(all_active)).hexdigest() == active["policy_tree_sha256"]
    # Companion pickle provenance is measured separately. It is untracked and
    # tests/conftest may build it under a different sklearn/platform; it is not
    # a pure-policy input. This guard protects the ten code/weight core files.
    assert cfg.POLICY_STATUS in {"candidate", "frozen"}
    if cfg.POLICY_STATUS == "candidate":
        assert cfg.FROZEN_POLICY_SHA is None


def test_h_frozen_guard_fails_when_git_object_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: empty stdout + rc=128 must FAIL, not silently pass."""

    def fake_run(*_a, **_k):
        return SimpleNamespace(returncode=128, stdout="", stderr="fatal: bad object")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(AssertionError, match="frozen SHA|frozen guard failed"):
        _ensure_frozen_sha_available()
        proc = _git(
            "diff",
            "--exit-code",
            FROZEN_SHA,
            "HEAD",
            "--",
            "packages/dialogue_engine/action_policy/policy.py",
        )
        assert proc.returncode == 0, (
            f"frozen guard failed for policy.py: rc={proc.returncode}\n"
            f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
        )


@pytest.mark.parametrize("sha", [None, "", "development-not-a-commit", "a" * 39, "g" * 40])
def test_freeze_history_helper_rejects_invalid_pin_before_git(monkeypatch, sha):
    def unexpected_git(*_args):
        raise AssertionError("invalid pin must not reach git")

    monkeypatch.setitem(globals(), "_git", unexpected_git)
    with pytest.raises(AssertionError, match="invalid frozen SHA"):
        _ensure_frozen_sha_available(sha)


@pytest.mark.parametrize("sha", [FROZEN_SHA, "6705f7651b3f0be1194344bf1e777da8a9a195a2"])
def test_freeze_history_helper_missing_pin_fails_closed(monkeypatch, sha):
    calls = []

    def failed_git(*args):
        calls.append(args)
        return SimpleNamespace(returncode=128, stdout="", stderr="missing object or remote")

    monkeypatch.setitem(globals(), "_git", failed_git)
    with pytest.raises(AssertionError, match="missing and fetch failed"):
        _ensure_frozen_sha_available(sha)
    assert calls == [("cat-file", "-e", f"{sha}^{{commit}}"), ("fetch", "--depth=1", "origin", sha)]


def test_freeze_history_helper_requires_object_after_successful_fetch(monkeypatch):
    sha = "6705f7651b3f0be1194344bf1e777da8a9a195a2"
    calls = []

    def incomplete_fetch(*args):
        calls.append(args)
        return SimpleNamespace(
            returncode=0 if args[0] == "fetch" else 128, stdout="", stderr="missing"
        )

    monkeypatch.setitem(globals(), "_git", incomplete_fetch)
    with pytest.raises(AssertionError, match="still missing after fetch"):
        _ensure_frozen_sha_available(sha)
    assert calls == [
        ("cat-file", "-e", f"{sha}^{{commit}}"),
        ("fetch", "--depth=1", "origin", sha),
        ("cat-file", "-e", f"{sha}^{{commit}}"),
    ]


def test_freeze_history_helper_fetches_actual_parent_from_shallow_metadata_clone(
    tmp_path, monkeypatch
):
    """A depth-one metadata HEAD omits its active code pin; exact fetch restores it."""
    origin = tmp_path / "origin"
    origin.mkdir()

    def git_at(path, *args):
        return subprocess.run(["git", *args], cwd=path, capture_output=True, text=True, check=True)

    git_at(origin, "init", "-b", "main")
    git_at(origin, "config", "user.name", "freeze-test")
    git_at(origin, "config", "user.email", "freeze-test@example.invalid")
    (origin / "core.txt").write_text("immutable core\n")
    git_at(origin, "add", "core.txt")
    git_at(origin, "commit", "-m", "candidate core")
    active_sha = git_at(origin, "rev-parse", "HEAD").stdout.strip()
    (origin / "metadata.txt").write_text(active_sha + "\n")
    git_at(origin, "add", "metadata.txt")
    git_at(origin, "commit", "-m", "freeze metadata")
    clone = tmp_path / "shallow"
    git_at(tmp_path, "clone", "--depth=1", origin.as_uri(), str(clone))
    assert git_at(clone, "rev-parse", "--is-shallow-repository").stdout.strip() == "true"
    missing = subprocess.run(["git", "cat-file", "-e", f"{active_sha}^{{commit}}"], cwd=clone)
    assert missing.returncode != 0
    monkeypatch.setitem(globals(), "ROOT", clone)
    _ensure_frozen_sha_available(active_sha)
    git_at(clone, "cat-file", "-e", f"{active_sha}^{{commit}}")
    assert git_at(clone, "show", f"{active_sha}:core.txt").stdout == "immutable core\n"


def test_frozen_core_guard_ensures_active_pin_before_core_diff(monkeypatch, tmp_path):
    import json

    from packages.dialogue_engine import action_policy_shadow_config as cfg

    # Exercise a real frozen commit even while deployment is a candidate.
    # Otherwise the mandatory freeze guard itself prevents the documented
    # candidate → verified-source → freeze-metadata release workflow.
    _ensure_frozen_sha_available()
    object_dir = subprocess.check_output(
        ["git", "rev-parse", "--path-format=absolute", "--git-path", "objects"], cwd=ROOT,
    ).decode().strip()
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".git/objects/info/alternates").write_text(object_dir + "\n")
    historical_rel = "docs/evaluation/action-policy-phase1-v9-freeze-manifest.json"
    historical = json.loads((ROOT / historical_rel).read_text())
    active = json.loads((ROOT / cfg.ACTIVE_POLICY_MANIFEST).read_text())
    for name in historical["core_file_sha256"]:
        rel = f"packages/dialogue_engine/action_policy/{name}"
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / rel).read_bytes())
    subprocess.run(["git", "add", "packages"], cwd=tmp_path, check=True)
    subprocess.run([
        "git", "-c", "user.name=freeze-test", "-c", "user.email=freeze@example.invalid",
        "commit", "-qm", "real frozen guard fixture",
    ], cwd=tmp_path, check=True)
    pin = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path).decode().strip()
    active.update(status="frozen", tested_sha=pin)
    for rel, payload in ((historical_rel, historical), (cfg.ACTIVE_POLICY_MANIFEST, active)):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload))
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    monkeypatch.setattr(cfg, "POLICY_STATUS", "frozen")
    monkeypatch.setattr(cfg, "FROZEN_POLICY_SHA", pin)
    assert cfg.POLICY_STATUS == "frozen"
    ensured = []
    real_ensure = _ensure_frozen_sha_available

    def ensure(sha=FROZEN_SHA):
        ensured.append(sha)
        real_ensure(sha)

    monkeypatch.setitem(globals(), "_ensure_frozen_sha_available", ensure)
    test_h_frozen_policy_unchanged()
    assert ensured == [FROZEN_SHA, cfg.FROZEN_POLICY_SHA]


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
    if rec["shadow_action"] != "ASK_EPISODE:current":
        assert rec["critical_violation"] is True
        assert "critical_pending_discard" in rec["critical_violation_flags"]
        assert rec["divergence_class"] == "critical_pending_difference"
        assert rec["cutover_eligible"] is False
    assert rec["policy_influenced_output"] is False


def test_k_known_v7_pending_repeat_live_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v7 defect reproduction surface — v8 must NOT mirror pending into delivered need."""
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "shadow")
    from packages.contracts.enums import SlotStatus
    from packages.dialogue_engine.action_policy.snapshot import build_policy_snapshot
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
    state.pending_episode_attribute = "current"
    snap = build_policy_snapshot(state)
    # v8: pending obligation is NOT copied into last_delivered / last_question_need.
    assert snap.pending_episode_attribute == "current"
    assert snap.last_delivered_question_need is None
    assert snap.last_question_need is None
    schedule_next_action(state, TurnContext(user_text=""))
    rec = state.action_policy_shadow_records[0]
    assert rec["shadow_action"] == "ASK_EPISODE:current"
    assert rec["policy_influenced_output"] is False


def test_correlation_without_processing_turn_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "shadow")
    state = _state(processing_turn_id=None, revision=9)
    turn = _rich(utterance_id="utt-stable-42", raw_text="норм")
    # Simulate reducer clearing processing_turn_id before schedule.
    state.processing_turn_id = None
    plan = schedule_next_action(state, TurnContext(turn=turn, user_text=turn.raw_text))
    assert isinstance(plan, ResponsePlan)
    rec = state.action_policy_shadow_records[0]
    assert rec["utterance_id"] == "utt-stable-42"
    assert "utt:utt-stable-42" in rec["decision_id"]
    assert rec["idempotency_key"].endswith(rec["decision_id"])
    assert rec["engine_revision_before_legacy"] == 9


def test_persistence_retry_same_idempotency_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "shadow")
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.setenv("IMVERA_VOICE_DIRECT_WELLNESS_OPENING", "1")
    from packages.core.memory_store import InMemoryCallRecordStore
    from packages.dialogue.session import CallSession
    from packages.dialogue_engine.engine import DialogueEngine
    from packages.dialogue_engine.events import CallStarted
    from packages.dialogue_engine.reducer import reduce

    store = InMemoryCallRecordStore()
    session = CallSession(call_id="persist-retry", family_id="f1", store=store)
    session.start()
    # Attach engine explicitly for persistence plumbing (session start may be legacy).
    if session._engine is None:
        session._engine = DialogueEngine(call_id="persist-retry")
    session._engine.state, _ = reduce(session._engine.state, CallStarted())
    eng = session._engine
    eng.state.processing_turn_id = "u-9"
    eng.state.turn_seq = 9
    eng.state.first_user_turn_received = True
    schedule_next_action(eng.state, TurnContext(user_text="привет"))
    assert eng.state.action_policy_shadow_records
    key = eng.state.action_policy_shadow_records[0]["idempotency_key"]

    attempts = {"n": 0}
    real_append = session._append_event

    def flaky(event_type, payload, idempotency_key=None):
        attempts["n"] += 1
        if attempts["n"] == 1 and event_type == "ACTION_POLICY_SHADOW":
            return False
        return real_append(event_type, payload, idempotency_key=idempotency_key)

    monkeypatch.setattr(session, "_append_event", flaky)
    session._persist_action_policy_shadow_records()
    health = shadow_health_counters(eng.state)
    assert health["shadow_records_retry"] >= 1
    assert eng.state.action_policy_shadow_records  # requeued
    assert eng.state.action_policy_shadow_records[0]["idempotency_key"] == key

    session._persist_action_policy_shadow_records()
    health2 = shadow_health_counters(eng.state)
    assert health2["shadow_records_persisted"] >= 1
    assert eng.state.action_policy_shadow_records == []
    events = [
        e for e in store._events.get("persist-retry", []) if e.event_type == "ACTION_POLICY_SHADOW"
    ]
    assert len(events) == 1
    assert events[0].idempotency_key == key


def test_make_error_record_full_schema() -> None:
    rec = make_error_record(
        _state(),
        error_stage="turn_context_view",
        error_type="RuntimeError",
    )
    assert rec["schema_version"] == 1
    assert rec["shadow_status"] == "error"
    assert rec["critical_violation"] is True
    assert "shadow_context_error" in rec["critical_violation_flags"]
    assert rec["decision_scope"] == "conversation_scheduler"
    assert rec["cutover_eligible"] is False
    assert rec["policy_influenced_output"] is False
    for key in (
        "decision_id",
        "idempotency_key",
        "frozen_policy_sha",
        "policy_version",
        "critical_flags",
        "pending_before",
    ):
        assert key in rec


@pytest.mark.parametrize(
    ("shadow", "legacy", "expected"),
    [
        ("ASK_EPISODE:current", "ASK_EPISODE:current", "agree"),
        ("ASK_EPISODE:current", "ACK_ONLY", "shadow_asks_optional"),
        ("ACK_ONLY", "ASK_EPISODE:current", "shadow_skips_optional"),
        ("IMPORTANT_TO_SHARE", "ASK_EPISODE:current", "shadow_transitions_earlier"),
        ("ASK_EPISODE:current", "IMPORTANT_TO_SHARE", "shadow_transitions_later"),
        ("SUMMARY_CLOSE", "ASK_EPISODE:current", "shadow_closes_earlier"),
        ("ASK_EPISODE:current", "SUMMARY_CLOSE", "shadow_closes_later"),
        ("BACKGROUND_GOAL:mood", "ASK_EPISODE:current", "background_goal_difference"),
        ("ASK_EPISODE:severity", "ASK_EPISODE:current", "episode_need_difference"),
        ("LISTEN_META", "ACK_ONLY", "legacy_ack_vs_shadow_action"),
        ("SAFETY", "ASK_EPISODE:current", "critical_safety_difference"),
    ],
)
def test_divergence_classes_reachable(shadow: str, legacy: str, expected: str) -> None:
    agree = shadow == legacy
    got = classify_divergence(
        shadow_label=shadow,
        legacy_label=legacy,
        agree=agree,
        pending_discard=False,
    )
    assert got == expected


def test_divergence_critical_pending_difference() -> None:
    got = classify_divergence(
        shadow_label="ASK_EPISODE:severity",
        legacy_label="ASK_EPISODE:current",
        agree=False,
        pending_discard=True,
    )
    assert got == "critical_pending_difference"


def test_divergence_unclassified_only_for_unknown_pair() -> None:
    got = classify_divergence(
        shadow_label="LISTEN_META",
        legacy_label="ANSWER_USER",
        agree=False,
    )
    assert got == "unclassified"


def test_shadow_total_latency_p99_under_5ms(monkeypatch: pytest.MonkeyPatch) -> None:
    import statistics

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
    totals: list[float] = []
    chooses: list[float] = []
    for i in range(80):
        state.action_policy_shadow_records.clear()
        state.processing_turn_id = f"u-lat-{i}"
        state.turn_seq = 100 + i
        rec = run_shadow_pre_legacy(state, TurnContext(user_text=""))
        totals.append(float(rec["shadow_total_latency_ms"]))
        chooses.append(float(rec["policy_choose_latency_ms"] or 0.0))
    totals.sort()
    chooses.sort()
    p99_t = totals[int(len(totals) * 0.99) - 1]
    p50_t = statistics.median(totals)
    p99_c = chooses[int(len(chooses) * 0.99) - 1]
    assert p99_t < 5.0, f"shadow_total p99={p99_t:.3f}ms p50={p50_t:.3f}"
    assert p99_c < 5.0, f"policy_choose p99={p99_c:.3f}ms"


def test_runtime_truth_exposes_shadow_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "shadow")
    truth = runtime_truth()
    assert truth["action_policy.mode"] == "shadow"
    assert truth["action_policy.policy_version"] == "action-policy-phase1-v11"
    assert truth["action_policy.frozen_policy_sha"] == FROZEN_POLICY_SHA
    assert truth["action_policy.decision_scope"] == "conversation_scheduler"


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


def test_allocate_decision_id_uses_utterance_when_processing_cleared() -> None:
    state = _state(processing_turn_id=None, revision=3)
    turn = _rich(utterance_id="from-turn")
    did, utt, rev = allocate_decision_id(state, TurnContext(turn=turn))
    assert utt == "from-turn"
    assert "utt:from-turn" in did
    assert rev == 3


def test_candidate_guard_does_not_skip_with_an_invalid_freeze_pin(monkeypatch):
    from packages.dialogue_engine import action_policy_shadow_config as cfg

    monkeypatch.setattr(cfg, "FROZEN_POLICY_SHA", "development-not-a-commit")
    with pytest.raises(AssertionError):
        test_h_frozen_policy_unchanged()


def test_candidate_core_guard_runs_without_untracked_model(monkeypatch):
    from pathlib import Path

    real_exists = Path.exists
    monkeypatch.setattr(
        Path,
        "exists",
        lambda path: False if path.name == "slot_answer_clf.pkl" else real_exists(path),
    )
    test_h_frozen_policy_unchanged()


def test_pure_core_guard_does_not_claim_to_validate_untracked_models(monkeypatch):
    from pathlib import Path

    real_read = Path.read_bytes
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda path: b"wrong-model" if path.name == "slot_answer_clf.pkl" else real_read(path),
    )
    test_h_frozen_policy_unchanged()
