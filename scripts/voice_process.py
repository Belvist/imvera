"""Start/stop voice stack processes without duplicates."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / ".run"


def _pid_path(name: str) -> Path:
    return RUN / f"{name}.pid"


def _log_path(name: str) -> Path:
    return RUN / f"{name}.log"


def is_running(name: str) -> bool:
    path = _pid_path(name)
    if not path.exists():
        return False
    try:
        pid = int(path.read_text().strip())
    except ValueError:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        path.unlink(missing_ok=True)
        return False


def stop(name: str) -> None:
    path = _pid_path(name)
    if not path.exists():
        return
    try:
        pid = int(path.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        for _ in range(20):
            try:
                os.kill(pid, 0)
                time.sleep(0.2)
            except OSError:
                break
        else:
            os.kill(pid, signal.SIGKILL)
    except (ValueError, OSError):
        pass
    path.unlink(missing_ok=True)


def start(
    name: str,
    cmd: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> subprocess.Popen:
    stop(name)
    RUN.mkdir(exist_ok=True)
    log = _log_path(name).open("w")
    proc = subprocess.Popen(
        cmd,
        cwd=cwd or ROOT,
        env=env or os.environ.copy(),
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    _pid_path(name).write_text(str(proc.pid))
    return proc


def run_checked(cmd: list[str], *, check: bool = True) -> int:
    print("+", " ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT, check=False)
    if check and result.returncode != 0:
        sys.exit(result.returncode)
    return result.returncode
