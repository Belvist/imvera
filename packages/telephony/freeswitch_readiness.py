"""FreeSWITCH container readiness — fail fast before accepting calls."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from enum import StrEnum


CONTAINER_NAME = "imvera-freeswitch"
REQUIRED_MODULES: tuple[str, ...] = ("mod_audio_stream", "mod_sofia", "mod_event_socket")


class FreeSwitchNotReadyReason(StrEnum):
    DOCKER_EXEC_FAILED = "DOCKER_EXEC_FAILED"
    FS_CLI_NO_RESPONSE = "FS_CLI_NO_RESPONSE"
    FS_NOT_UP = "FS_NOT_UP"
    MOD_AUDIO_STREAM_MISSING = "MOD_AUDIO_STREAM_MISSING"
    REQUIRED_MODULE_MISSING = "REQUIRED_MODULE_MISSING"


@dataclass(frozen=True)
class FreeSwitchReadiness:
    ready: bool
    reason: FreeSwitchNotReadyReason | None = None
    detail: str = ""
    modules: dict[str, bool] | None = None

    def message(self) -> str:
        if self.ready:
            return "FREESWITCH READY"
        reason = self.reason or FreeSwitchNotReadyReason.FS_CLI_NO_RESPONSE
        return f"FREESWITCH NOT READY reason={reason} {self.detail}".strip()


def parse_module_exists(stdout: str, module: str) -> bool:
    """Parse `fs_cli -x 'module_exists <name>'` output."""
    for line in stdout.splitlines():
        token = line.strip().lower()
        if token in {"true", "false"}:
            return token == "true"
    return module.lower() in stdout.lower() and "true" in stdout.lower()


def parse_status_up(stdout: str) -> bool:
    text = stdout.lower()
    return (
        ("up" in text and "years" in text)
        or "session(s)" in text
        or "freeswitch" in text
    )


def fs_cli_exec(
    command: str,
    *,
    container: str = CONTAINER_NAME,
    timeout_s: float = 10.0,
) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["docker", "exec", container, "fs_cli", "-x", command],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_s,
    )
    return proc.returncode, proc.stdout, proc.stderr


def check_module_loaded(
    module: str,
    *,
    container: str = CONTAINER_NAME,
) -> tuple[bool, str]:
    code, stdout, stderr = fs_cli_exec(f"module_exists {module}", container=container)
    if code != 0 and not stdout.strip():
        return False, stderr.strip() or f"fs_cli exit {code}"
    return parse_module_exists(stdout, module), stdout.strip() or stderr.strip()


def check_freeswitch_ready(
    *,
    container: str = CONTAINER_NAME,
    require_modules: tuple[str, ...] = REQUIRED_MODULES,
) -> FreeSwitchReadiness:
    code, stdout, stderr = fs_cli_exec("status", container=container)
    if code != 0 and not stdout.strip():
        return FreeSwitchReadiness(
            ready=False,
            reason=FreeSwitchNotReadyReason.DOCKER_EXEC_FAILED,
            detail=stderr.strip() or f"docker exec/fs_cli exit {code}",
        )
    if not parse_status_up(stdout):
        return FreeSwitchReadiness(
            ready=False,
            reason=FreeSwitchNotReadyReason.FS_NOT_UP,
            detail=(stdout or stderr).strip()[:240],
        )

    modules: dict[str, bool] = {}
    for name in require_modules:
        loaded, detail = check_module_loaded(name, container=container)
        modules[name] = loaded
        if not loaded:
            reason = (
                FreeSwitchNotReadyReason.MOD_AUDIO_STREAM_MISSING
                if name == "mod_audio_stream"
                else FreeSwitchNotReadyReason.REQUIRED_MODULE_MISSING
            )
            return FreeSwitchReadiness(
                ready=False,
                reason=reason,
                detail=f"{name} missing ({detail})",
                modules=modules,
            )

    return FreeSwitchReadiness(ready=True, modules=modules)


def wait_freeswitch_ready(
    *,
    container: str = CONTAINER_NAME,
    timeout_s: float = 120.0,
    poll_s: float = 2.0,
) -> FreeSwitchReadiness:
    deadline = time.time() + timeout_s
    last = FreeSwitchReadiness(
        ready=False,
        reason=FreeSwitchNotReadyReason.FS_CLI_NO_RESPONSE,
        detail="timeout waiting for FreeSWITCH",
    )
    while time.time() < deadline:
        last = check_freeswitch_ready(container=container)
        if last.ready:
            return last
        time.sleep(poll_s)
    return last
