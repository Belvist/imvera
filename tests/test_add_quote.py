from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from tools.voice_lab import add_quote


@pytest.fixture(autouse=True)
def _ensure_slot_answer_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "tools.voice_lab.train_slot_answer_clf.train",
        Mock(side_effect=AssertionError("Real model training is forbidden in CLI tests")),
    )


@pytest.fixture
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Mock]:
    trainer = tmp_path / "trainer.py"
    marker = "    # --- LIVE_QUOTES: append every anchor-miss with its true label ---"
    trainer.write_text(f"SEED_ROWS = [\n{marker}\n]\n", encoding="utf-8")
    monkeypatch.setattr(add_quote, "ROOT", tmp_path)
    monkeypatch.setattr(add_quote, "TRAINER", trainer)
    monkeypatch.setattr(
        sys, "argv",
        ["add_quote.py", "--slot", "onset", "--label", "answer", "--text", " С УТРА "],
    )
    run = Mock(return_value=subprocess.CompletedProcess([], 0, "output\n", "diagnostic\n"))
    monkeypatch.setattr(subprocess, "run", run)
    return trainer, run


@pytest.mark.parametrize("inherited_coverage", ["0", "1"])
def test_runs_all_stages_with_explicit_gate_flags(
    cli: tuple[Path, Mock], monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], inherited_coverage: str,
) -> None:
    trainer, run = cli
    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", inherited_coverage)
    monkeypatch.setenv("ADD_QUOTE_TEST_ENV", "preserved")
    original_env = os.environ.copy()

    assert add_quote.main() == 0

    commands = [call.args[0] for call in run.call_args_list]
    assert commands == [
        [sys.executable, str(trainer)],
        [sys.executable, str(trainer.parent / "tools/voice_lab/ambiguity_bench.py")],
        [sys.executable, str(trainer.parent / "scripts/dialogue_behavior_fuzz.py"),
         "--n", "1000", "--seed", "7"],
        [sys.executable, str(trainer.parent / "scripts/dialogue_behavior_fuzz.py"),
         "--n", "1000", "--seed", "7"],
    ]
    for call, coverage in zip(run.call_args_list, [inherited_coverage, "1", "0", "1"]):
        assert call.kwargs == {
            "cwd": trainer.parent,
            "env": {**original_env, "IMVERA_COVERAGE_LADDER": coverage},
            "capture_output": True,
            "text": True,
        }
    assert os.environ == original_env
    output = capsys.readouterr()
    assert output.out.count("output\n") == 4
    assert output.err == "diagnostic\n" * 4


@pytest.mark.parametrize("failed_stage", range(4))
@pytest.mark.parametrize("returncode", [2, 17])
def test_failure_propagates_and_stops_later_stages(
    cli: tuple[Path, Mock], capsys: pytest.CaptureFixture[str],
    failed_stage: int, returncode: int,
) -> None:
    _, run = cli
    stdout = "first line\n" + "details\n" * 100 + "last stdout line\n"
    stderr = "first error\n" + "diagnostic\n" * 100 + "last stderr line\n"
    run.side_effect = [
        subprocess.CompletedProcess([], 0, "", "") for _ in range(failed_stage)
    ] + [subprocess.CompletedProcess([], returncode, stdout, stderr)]

    assert add_quote.main() == returncode
    assert run.call_count == failed_stage + 1
    output = capsys.readouterr()
    assert stdout in output.out
    assert stderr in output.err
    name = ["trainer", "bench (coverage=1)", "fuzz (coverage=0)", "fuzz (coverage=1)"]
    assert output.err.endswith(f"{name[failed_stage]} failed (exit {returncode})\n")
    assert "success" not in output.out.lower()


@pytest.mark.parametrize("text", ["", " ", "\t\r\n", "\u2003"])
def test_blank_input_rejected_before_file_access(
    cli: tuple[Path, Mock], monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], text: str,
) -> None:
    trainer, run = cli
    before = trainer.read_bytes()
    monkeypatch.setattr(sys, "argv", [*sys.argv[:-1], text])
    with monkeypatch.context() as guard:
        guard.setattr(Path, "read_text", Mock(side_effect=AssertionError("Unexpected read")))
        guard.setattr(Path, "write_text", Mock(side_effect=AssertionError("Unexpected write")))
        with pytest.raises(SystemExit) as exc:
            add_quote.main()
    assert exc.value.code == 2
    assert trainer.read_bytes() == before
    run.assert_not_called()
    output = capsys.readouterr()
    assert "--text must not be blank" in output.err
    assert not output.out


@pytest.mark.parametrize("text", [
    " С УТРА ",
    "Он сказал: \"БОЛИТ\"; 'ещё' \\ сегодня\nи вчера\r\n",
    '\"); __import__("builtins").print("injected"); ("',
    'x", "answer"),\n]\nraise RuntimeError("injected")\nrows = [("onset", "x',
])
def test_quote_is_only_a_literal_tuple(
    cli: tuple[Path, Mock], monkeypatch: pytest.MonkeyPatch, text: str,
) -> None:
    trainer, _ = cli
    before = trainer.read_text(encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [*sys.argv[:-1], text])

    assert add_quote.main() == 0

    source = trainer.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert len(tree.body) == 1
    assignment = tree.body[0]
    assert isinstance(assignment, ast.Assign)
    assert ast.literal_eval(assignment.value) == [("onset", text.strip().lower(), "answer")]
    row = f"    {('onset', text.strip().lower(), 'answer')!r},\n"
    assert source.replace(row, "", 1) == before


def test_session_fixture_fails_when_sklearn_is_missing(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "conftest.py").write_text(
        (root / "tests" / "conftest.py").read_text(encoding="utf-8"), encoding="utf-8",
    )
    (tests / "test_probe.py").write_text(
        "def test_probe():\n    raise AssertionError('test body must not run')\n",
        encoding="utf-8",
    )
    sklearn = tmp_path / "sklearn"
    sklearn.mkdir()
    (sklearn / "__init__.py").write_text(
        "raise ModuleNotFoundError(\"No module named 'sklearn'\", name='sklearn')\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"],
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join([str(tmp_path), str(root)]),
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTEST_ADDOPTS": "",
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "ERROR at setup of test_probe" in result.stdout
    assert "No module named 'sklearn'" in result.stdout
    assert "1 error" in result.stdout
    assert "test body must not run" not in result.stdout
    assert not (tmp_path / "models" / "slot_answer_clf.pkl").exists()
