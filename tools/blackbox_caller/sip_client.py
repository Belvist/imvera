"""External SIP client — pyVoIP backend (PJSUA2 documented as production upgrade path)."""

from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass
from typing import Any, Protocol

from tools.blackbox_caller.audio import DownlinkRecorder
from tools.blackbox_caller.config import BlackboxConfig
from tools.blackbox_caller.speech_detector import DownlinkSpeechDetector, SpeechDetectorConfig


class SipCall(Protocol):
    def write_audio(self, data: bytes) -> None: ...
    def read_audio(self, length: int, *, blocking: bool = True) -> bytes: ...
    def hangup(self) -> None: ...
    @property
    def state(self) -> Any: ...


@dataclass
class SipSessionInfo:
    sip_call_id: str | None
    connected: bool
    answered: bool


def _require_pyvoip() -> None:
    try:
        import audioop_lts  # noqa: F401
    except ImportError:
        try:
            import audioop  # noqa: F401
        except ImportError:
            raise RuntimeError(
                "BLACKBOX_GATE=FAIL: install sip-lab deps: pip install -e '.[sip-lab]'"
            ) from None
    try:
        import pyVoIP  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "BLACKBOX_GATE=FAIL: pyVoIP required (pip install -e '.[sip-lab]'). "
            "PJSUA2 is preferred for production PSTN gate but not bundled here."
        ) from None


def _resolve_client_ip(sip_host: str, sip_port: int) -> str:
    import os

    env = os.environ.get("IMVERA_LIVE_CLIENT_IP") or os.environ.get("FS_NODE_IP")
    if env:
        return env
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect((sip_host, sip_port))
        return probe.getsockname()[0]
    finally:
        probe.close()


def _preflight_port(port: int) -> None:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.bind(("0.0.0.0", port))
    except OSError as exc:
        raise RuntimeError(f"BLACKBOX_GATE=FAIL: local SIP port {port} in use") from exc
    finally:
        probe.close()


class PyVoIPSipClient:
    """Real SIP/RTP caller via pyVoIP — external to IMVERA packages."""

    def __init__(self, config: BlackboxConfig) -> None:
        self.config = config
        self._phone = None
        self._call = None
        self._recorder = DownlinkRecorder()
        self._detector = DownlinkSpeechDetector(
            SpeechDetectorConfig(
                sample_rate=config.sample_rate,
                frame_ms=config.frame_ms,
                silence_frames_for_end=max(1, config.bot_silence_ms // config.frame_ms),
            )
        )
        self._pump_stop = threading.Event()
        self._pump_thread: threading.Thread | None = None
        self.sip_call_id: str | None = None

    def connect(self) -> SipSessionInfo:
        _require_pyvoip()
        from pyVoIP.VoIP import CallState, VoIPPhone

        _preflight_port(self.config.local_sip_port)
        client_ip = _resolve_client_ip(self.config.sip_host, self.config.sip_port)
        if client_ip.startswith("127."):
            raise RuntimeError(
                "BLACKBOX_GATE=FAIL: use LAN host IP for RTP (not 127.0.0.1). "
                "Set IMVERA_LIVE_SIP_HOST / IMVERA_LIVE_CLIENT_IP."
            )
        self._phone = VoIPPhone(
            self.config.sip_host,
            self.config.sip_port,
            self.config.sip_user,
            self.config.sip_password,
            myIP=client_ip,
            sipPort=self.config.local_sip_port,
            rtpPortLow=self.config.rtp_port_low,
            rtpPortHigh=self.config.rtp_port_high,
        )
        self._phone.start()
        time.sleep(1.5)
        self._call = self._phone.call(self.config.extension)
        self.sip_call_id = getattr(self._call, "call_id", None)
        for _ in range(80):
            if self._call.state == CallState.ANSWERED:
                self._start_pump()
                return SipSessionInfo(
                    sip_call_id=self.sip_call_id,
                    connected=True,
                    answered=True,
                )
            time.sleep(0.25)
        return SipSessionInfo(
            sip_call_id=self.sip_call_id,
            connected=False,
            answered=False,
        )

    def _start_pump(self) -> None:
        frame_bytes = self.config.frame_bytes

        def _loop() -> None:
            silence = bytes([128]) * frame_bytes
            while not self._pump_stop.is_set():
                try:
                    chunk = self._call.read_audio(frame_bytes, blocking=True)
                except Exception:
                    time.sleep(0.01)
                    continue
                if chunk:
                    self._recorder.extend(chunk)
                    self._detector.feed(chunk)
                else:
                    self._detector.feed(silence)
                time.sleep(0.001)

        self._pump_thread = threading.Thread(target=_loop, daemon=True)
        self._pump_thread.start()
        for _ in range(15):
            try:
                self._call.write_audio(silence)
            except Exception:
                break
            time.sleep(0.02)

    def wait_bot_finish(self, timeout_s: float) -> bool:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if self._detector.bot_speaking:
                # wait until feed marks finished
                pass
            elif len(self._recorder.bytes()) > self.config.frame_bytes * 10:
                # had audio and now silent
                if not self._detector.bot_speaking:
                    return True
            time.sleep(0.05)
        return False

    def wait_bot_start(self, timeout_s: float) -> bool:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if self._detector.bot_speaking:
                return True
            time.sleep(0.05)
        return False

    @property
    def call(self) -> SipCall:
        if self._call is None:
            raise RuntimeError("SIP call not connected")
        return self._call

    @property
    def recorder(self) -> DownlinkRecorder:
        return self._recorder

    @property
    def detector(self) -> DownlinkSpeechDetector:
        return self._detector

    def close(self) -> bytes:
        self._pump_stop.set()
        if self._pump_thread:
            self._pump_thread.join(timeout=2.0)
        try:
            if self._call is not None:
                self._call.hangup()
        except Exception:
            pass
        try:
            if self._phone is not None:
                self._phone.stop()
        except Exception:
            pass
        return self._recorder.bytes()
