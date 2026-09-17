from __future__ import annotations

import sys
from unittest.mock import Mock, call

import pytest

from packages.dialogue_engine import tinyllm
from tools.voice_lab import ambiguity_bench as bench


@pytest.fixture(autouse=True)
def _ensure_slot_answer_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "tools.voice_lab.train_slot_answer_clf.train",
        Mock(side_effect=AssertionError("Real training is forbidden in benchmark tests")),
    )
    monkeypatch.setattr(
        tinyllm, "classify",
        Mock(side_effect=AssertionError("Real classification is forbidden in benchmark tests")),
    )
    monkeypatch.setattr(
        bench, "_deterministic_route",
        Mock(side_effect=AssertionError("Real classification is forbidden in benchmark tests")),
    )
    monkeypatch.setenv("IMVERA_TINYLLM_MODEL", "route_clf")
    monkeypatch.setattr(sys, "argv", ["ambiguity_bench.py"])


@pytest.mark.parametrize("route, expected_status", [("answer", 0), ("repair", 1)])
def test_default_main_gates_deterministic_misses(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    route: str, expected_status: int,
) -> None:
    monkeypatch.setattr(bench, "CASES", [("test", "wellness", "answer")])
    classify = Mock(return_value=route)
    monkeypatch.setattr(bench, "_deterministic_route", classify)

    assert bench.main() == expected_status

    classify.assert_called_once_with("test", "wellness")
    output = capsys.readouterr().out
    assert f"acc={1 - expected_status:.2f}" in output
    assert "abstain=0" in output
    assert ("miss:" in output) == bool(expected_status)


@pytest.mark.parametrize("models", ["deterministic,tiny", "tiny,deterministic"])
@pytest.mark.parametrize("errors, abstain", [([], 0), (["wrong route"], 0), ([], 1)])
def test_main_gates_every_candidate_and_reports_all_results(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    models: str, errors: list[str], abstain: int,
) -> None:
    deterministic = Mock(return_value=bench.BenchResult("deterministic", 1.0, 1, 2, 0, []))
    tiny = Mock(return_value=bench.BenchResult("tiny:route_clf", 1.0, 3, 4, abstain, errors))
    monkeypatch.setattr(bench, "run_deterministic", deterministic)
    monkeypatch.setattr(bench, "run_tiny", tiny)
    monkeypatch.setattr(sys, "argv", ["ambiguity_bench.py", "--models", models, "--repeat", "2"])

    assert bench.main() == int(bool(errors or abstain))

    deterministic.assert_called_once_with()
    tiny.assert_called_once_with("route_clf", 2)
    output = capsys.readouterr().out
    assert "== deterministic:" in output
    assert "== tiny:route_clf:" in output
    assert f"abstain={abstain}" in output
    if errors:
        assert "miss: wrong route" in output


@pytest.mark.parametrize("model", ["route_clf", "mock-model"])
@pytest.mark.parametrize(
    "routes, accuracy, abstain, errors",
    [
        (["answer", "unclear", "answer"], 1.0, 0, 0),
        ([None, None, None], 0.0, 6, 0),
        (["answer", None, "repair"], 1 / 3, 2, 2),
    ],
)
def test_tiny_accuracy_counts_all_attempts_except_warmup(
    monkeypatch: pytest.MonkeyPatch, model: str, routes: list[str | None],
    accuracy: float, abstain: int, errors: int,
) -> None:
    cases = [("first", "wellness", "answer"), ("second", None, "garbage"),
             ("third", "mood", "answer")]
    monkeypatch.setattr(bench, "CASES", cases)
    warmup = [None] if model != "route_clf" else []
    classify = Mock(side_effect=warmup + routes * 2)
    monkeypatch.setattr(tinyllm, "classify", classify)

    result = bench.run_tiny(model, 2)

    assert result.accuracy == pytest.approx(accuracy)
    assert result.abstain == abstain
    assert len(result.errors) == errors
    assert result.name == f"tiny:{model}"
    expected_calls = [call(text, pending_question=pending) for text, pending, _ in cases] * 2
    if warmup:
        expected_calls.insert(0, call("Проверка связи.", pending_question="wellness"))
    assert classify.call_args_list == expected_calls


@pytest.mark.parametrize("repeat", [0, -1])
def test_tiny_rejects_nonpositive_repeat_before_classification(
    repeat: int,
) -> None:
    with pytest.raises(ValueError, match="repeat must be positive"):
        bench.run_tiny("mock-model", repeat)
    tinyllm.classify.assert_not_called()


@pytest.mark.parametrize("repeat", ["0", "-2"])
@pytest.mark.parametrize("models", ["deterministic", "tiny"])
def test_main_rejects_nonpositive_repeat_before_running(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    repeat: str, models: str,
) -> None:
    deterministic = Mock()
    tiny = Mock()
    monkeypatch.setattr(bench, "run_deterministic", deterministic)
    monkeypatch.setattr(bench, "run_tiny", tiny)
    monkeypatch.setattr(
        sys, "argv", ["ambiguity_bench.py", "--models", models, "--repeat", repeat],
    )

    with pytest.raises(SystemExit) as exc:
        bench.main()

    assert exc.value.code == 2
    assert "--repeat must be positive" in capsys.readouterr().err
    deterministic.assert_not_called()
    tiny.assert_not_called()
