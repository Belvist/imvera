"""PJSUA2 SIP client — headless AudioMediaPlayer / AudioMediaRecorder (Phase B)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.blackbox_caller.config import BlackboxConfig
from tools.blackbox_caller.sip_client import SipSessionInfo
from tools.pjsua2_blackbox_caller.config import load_pjsua2_config


class Pjsua2ImportError(RuntimeError):
    pass


def _require_pjsua2() -> Any:
    try:
        import pjsua2 as pj  # type: ignore[import-untyped]
    except ImportError as exc:
        raise Pjsua2ImportError(
            "PJSUA2 transport gate requires pjsua2 Python bindings built against pjproject. "
            "See docs/gates/pjsua2-transport-gate.md"
        ) from exc
    return pj


class Pjsua2SipClient:
    """External live gate backend — replaces legacy_lab pyVoIP on Mac/host boundary."""

    def __init__(self, config: BlackboxConfig) -> None:
        self.config = config
        self._pj_cfg = load_pjsua2_config()
        self._pj = _require_pjsua2()
        self._endpoint = None
        self._account = None
        self._call = None
        self._recorder_path: Path | None = None
        self._downlink_bytes = b""
        self.negotiated_codec = ""
        self.negotiated_clock_rate = 0
        self.offered_codecs = list(self._pj_cfg.offered_codecs)
        self.sip_call_id: str | None = None

    def connect(self) -> SipSessionInfo:
        raise NotImplementedError(
            "PJSUA2 caller skeleton — implement REGISTER/INVITE/AudioMedia in Phase B cutover"
        )

    def close(self) -> bytes:
        return self._downlink_bytes

    @property
    def call(self) -> Any:
        if self._call is None:
            raise RuntimeError("PJSUA2 call not connected")
        return self._call

    @property
    def recorder(self) -> Any:
        raise NotImplementedError("use caller_downlink.wav from AudioMediaRecorder")

    @property
    def detector(self) -> Any:
        raise NotImplementedError("use server trace + downlink WAV for bot detection")

    def wait_bot_finish(self, timeout_s: float) -> bool:
        raise NotImplementedError

    def wait_bot_start(self, timeout_s: float) -> bool:
        raise NotImplementedError
