"""SIP clients for blackbox gate — PJSUA2 live + pyVoIP lab/docker."""

from __future__ import annotations

import os
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


_NOTIFY_PATCHED = False


def _patch_pyvoip_skip_notify() -> None:
    """Subclass UDP sockets so pyVoIP ignores FreeSWITCH SIP NOTIFY."""
    global _NOTIFY_PATCHED
    if _NOTIFY_PATCHED:
        return
    original = socket.socket

    class _PatchedSocket(original):  # type: ignore[misc,valid-type]
        def recv(self, bufsize: int, flags: int = 0) -> bytes:
            if self.type != socket.SOCK_DGRAM:
                return super().recv(bufsize, flags)
            while True:
                data = super().recv(bufsize, flags)
                if not data:
                    return data
                heading = data.split(b"\r\n", 1)[0]
                if heading.startswith(b"NOTIFY "):
                    continue
                return data

    socket.socket = _PatchedSocket  # type: ignore[misc,assignment]
    _NOTIFY_PATCHED = True


_INVITE_PATCHED = False


def _patch_pyvoip_invite() -> None:
    """FreeSWITCH may answer INVITE with 200 OK before 100/180 — stock pyVoIP blocks forever."""
    global _INVITE_PATCHED
    if _INVITE_PATCHED:
        return
    import pyVoIP.SIP as sip_mod
    from pyVoIP.SIP import SIPMessage, SIPMessageType, SIPStatus

    def invite(
        self,
        number: str,
        ms: dict[int, dict[str, Any]],
        sendtype: Any,
    ) -> tuple[SIPMessage, str, int]:
        branch = "z9hG4bK" + self.gen_call_id()[0:25]
        call_id = self.gen_call_id()
        sess_id = self.sessID.next()
        invite_body = self.gen_invite(number, str(sess_id), ms, sendtype, branch, call_id)
        # Stock pyVoIP REGISTER adds ;rport but INVITE does not. On Docker Desktop
        # (esp. with host VPN) FS sees UDP src as a public/NAT IP; without rport it
        # replies to Via host (LAN) which never reaches the caller socket. ;rport
        # forces replies to the mapped source — same path REGISTER already uses.
        via_prefix = f"Via: SIP/2.0/UDP {self.myIP}:{self.myPort};"
        via_line = invite_body.split("\r\n", 3)[1]
        if via_prefix + "branch=" in invite_body and ";rport" not in via_line:
            invite_body = invite_body.replace(
                via_prefix + "branch=",
                via_prefix + "rport;branch=",
                1,
            )
        early_provisional = {
            SIPStatus(100),
            SIPStatus(180),
            SIPStatus(183),
        }
        with self.recvLock:
            self.out.sendto(invite_body.encode("utf8"), (self.server, self.port))
            deadline = time.time() + 30.0
            response: SIPMessage | None = None
            while time.time() < deadline:
                self.s.settimeout(max(0.1, deadline - time.time()))
                try:
                    raw = self.s.recv(8192)
                except TimeoutError:
                    break
                if not raw:
                    continue
                message = SIPMessage(raw)
                if message.type != SIPMessageType.RESPONSE:
                    self.parse_message(message)
                    continue
                if message.headers.get("Call-ID") != call_id:
                    self.parse_message(message)
                    continue
                response = message
                if response.status in early_provisional or response.status == SIPStatus(200):
                    break
                if response.status == SIPStatus(401):
                    auth_hdr = getattr(response, "authentication", None) or {}
                    if auth_hdr.get("realm"):
                        break
                self.parse_message(response)
            if response is None:
                raise TimeoutError(
                    f"SIP INVITE timed out waiting for response to {number}@{self.server}"
                )
            if response.status in early_provisional:
                return SIPMessage(invite_body.encode("utf8")), call_id, sess_id
            if response.status == SIPStatus(200):
                ack = self.gen_ack(response)
                self.out.sendto(ack.encode("utf8"), (self.server, self.port))
                self._pending_invite_ok = response
                return SIPMessage(invite_body.encode("utf8")), call_id, sess_id
            if response.status != SIPStatus(401):
                raise RuntimeError(
                    f"SIP INVITE unexpected response {response.status}: {response.summary()}"
                )

            ack = self.gen_ack(response)
            self.out.sendto(ack.encode("utf8"), (self.server, self.port))
            authhash = self.gen_authorization(response)
            nonce = response.authentication["nonce"]
            realm = response.authentication["realm"]
            auth = (
                f'Authorization: Digest username="{self.username}",realm='
                + f'"{realm}",nonce="{nonce}",uri="sip:{self.server};'
                + f'transport=UDP",response="{str(authhash, "utf8")}",'
                + "algorithm=MD5\r\n"
            )
            invite_auth = self.gen_invite(number, str(sess_id), ms, sendtype, branch, call_id)
            via_line = invite_auth.split("\r\n", 3)[1]
            if via_prefix + "branch=" in invite_auth and ";rport" not in via_line:
                invite_auth = invite_auth.replace(
                    via_prefix + "branch=",
                    via_prefix + "rport;branch=",
                    1,
                )
            invite_auth = invite_auth.replace("\r\nContent-Length", f"\r\n{auth}Content-Length")
            self.out.sendto(invite_auth.encode("utf8"), (self.server, self.port))
            return SIPMessage(invite_auth.encode("utf8")), call_id, sess_id

    sip_mod.SIPClient.invite = invite  # type: ignore[method-assign]
    _INVITE_PATCHED = True


_CALL_PATCHED = False


def _patch_pyvoip_call_answer() -> None:
    """Apply deferred 200 OK to VoIPCall when FreeSWITCH answers before 100/180."""
    global _CALL_PATCHED
    if _CALL_PATCHED:
        return
    from pyVoIP.VoIP import VoIPPhone

    original = VoIPPhone.call

    def call(self, number: str):  # type: ignore[no-untyped-def]
        voip_call = original(self, number)
        pending = getattr(self.sip, "_pending_invite_ok", None)
        if pending is not None:
            voip_call.answered(pending)
            del self.sip._pending_invite_ok
        return voip_call

    VoIPPhone.call = call  # type: ignore[method-assign]
    _CALL_PATCHED = True


def _require_pyvoip(*, docker_internal: bool = False) -> None:
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
        from pyVoIP.VoIP import VoIPPhone  # noqa: F401 — finish loading pyVoIP.SIP
    except ImportError:
        raise RuntimeError(
            "BLACKBOX_GATE=FAIL: pyVoIP required (pip install -e '.[sip-lab]'). "
            "PJSUA2 is preferred for production PSTN gate but not bundled here."
        ) from None
    _patch_pyvoip_skip_notify()
    if not docker_internal:
        _patch_pyvoip_invite()
        _patch_pyvoip_call_answer()


def _is_lan_ipv4(addr: str) -> bool:
    if not addr or addr.startswith("127."):
        return False
    parts = addr.split(".")
    if len(parts) != 4:
        return False
    try:
        octets = [int(p) for p in parts]
    except ValueError:
        return False
    if octets[0] == 10:
        return True
    if octets[0] == 192 and octets[1] == 168:
        return True
    if octets[0] == 172 and 16 <= octets[1] <= 31:
        return True
    return False


def _lan_ip_via_probe(sip_host: str, sip_port: int) -> str:
    target = sip_host if not sip_host.startswith("127.") else "8.8.8.8"
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect((target, 53 if target == "8.8.8.8" else sip_port))
        local = probe.getsockname()[0]
        if _is_lan_ipv4(local):
            return local
    finally:
        probe.close()
    return _lan_ip_via_ifconfig()


def _lan_ip_via_ifconfig() -> str:
    import subprocess

    for iface in ("en0", "en1", "wlan0"):
        proc = subprocess.run(
            ["ipconfig", "getifaddr", iface],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    raise RuntimeError(
        "BLACKBOX_GATE=FAIL: cannot resolve LAN client IP for RTP. "
        "Set IMVERA_LIVE_CLIENT_IP to this machine's LAN address."
    )


def _resolve_client_ip(sip_host: str, sip_port: int) -> str:
    import os

    env = os.environ.get("IMVERA_LIVE_CLIENT_IP") or os.environ.get("FS_NODE_IP")
    if env:
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.bind((env, 0))
            probe.close()
            if _is_lan_ipv4(env):
                return env
        except OSError:
            pass
    return _lan_ip_via_probe(sip_host, sip_port)


def _pick_free_udp_port(start: int, attempts: int = 100) -> int:
    for port in range(start, start + attempts):
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.bind(("0.0.0.0", port))
            return port
        except OSError:
            continue
        finally:
            probe.close()
    raise RuntimeError(f"BLACKBOX_GATE=FAIL: no free local SIP UDP port from {start}")


def _preflight_port(port: int) -> None:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.bind(("0.0.0.0", port))
    except OSError as exc:
        raise RuntimeError(f"BLACKBOX_GATE=FAIL: local SIP port {port} in use") from exc
    finally:
        probe.close()


def _patch_sip_signal_route(sip: Any, signal_host: str, sip_domain: str) -> None:
    """Keep FS auth realm (sip_domain) while sending UDP to reachable signal_host."""
    sip.server = sip_domain
    if signal_host == sip_domain:
        return

    def _wrap_sendto(sock: socket.socket) -> None:
        original = sock.sendto

        def sendto(data: bytes, addr: tuple[str, int]) -> int:
            host, port = addr
            if host == sip_domain:
                host = signal_host
            return original(data, (host, port))

        sock.sendto = sendto  # type: ignore[method-assign]

    _wrap_sendto(sip.s)
    if getattr(sip, "out", None) is not None and sip.out is not sip.s:
        _wrap_sendto(sip.out)


def _start_sip_with_route(phone: Any, signal_host: str, sip_domain: str) -> None:
    """Start pyVoIP SIP stack with signal/domain split before REGISTER."""
    from threading import Timer

    sip = phone.sip
    if sip.NSD:
        raise RuntimeError("Attempted to start already started SIPClient")
    sip.NSD = True
    sip.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sip.s.bind((sip.myIP, sip.myPort))
    sip.out = sip.s
    _patch_sip_signal_route(sip, signal_host, sip_domain)
    sip.register()
    timer = Timer(1, sip.recv_loop)
    timer.name = "SIP Recieve"
    timer.start()


def _resolve_docker_client_ip(sip_host: str, sip_port: int) -> str:
    env = os.environ.get("FS_NODE_IP", "").strip()
    if env and env.lower() != "auto":
        return env
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect((sip_host, sip_port))
        return probe.getsockname()[0]
    finally:
        probe.close()


def create_sip_client(config: BlackboxConfig) -> PyVoIPSipClient:
    """Select SIP backend. External live gate must use PJSUA2 (Phase B)."""
    backend = os.environ.get("IMVERA_BLACKBOX_SIP_BACKEND", "auto").strip().lower()
    if backend in {"pjsua2", "pjsip"}:
        from tools.pjsua2_blackbox_caller.client import Pjsua2SipClient

        return Pjsua2SipClient(config)
    if backend == "pyvoip":
        return PyVoIPSipClient(config)
    if config.transport_mode == "docker_internal":
        return PyVoIPSipClient(config)
    if backend == "auto":
        return PyVoIPSipClient(config)
    raise RuntimeError(f"BLACKBOX_GATE=FAIL: unknown IMVERA_BLACKBOX_SIP_BACKEND={backend}")


class PyVoIPSipClient:
    """legacy_lab_backend — pyVoIP for docker-internal diagnostic smoke only."""

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
        if self.config.transport_mode == "docker_internal":
            return self._connect_docker_internal()
        return self._connect_host_pyvoip()

    def _connect_docker_internal(self) -> SipSessionInfo:
        """Phase A: SIP to freeswitch service name with FS directory realm."""
        _require_pyvoip(docker_internal=True)
        from pyVoIP.VoIP import VoIPPhone
        from pyVoIP.VoIP.status import PhoneStatus

        signal_host = self.config.sip_host
        sip_domain = self.config.sip_domain
        local_port = _pick_free_udp_port(self.config.local_sip_port)
        client_ip = _resolve_docker_client_ip(signal_host, self.config.sip_port)
        self._phone = VoIPPhone(
            signal_host,
            self.config.sip_port,
            self.config.sip_user,
            self.config.sip_password,
            myIP=client_ip,
            sipPort=local_port,
            rtpPortLow=self.config.rtp_port_low,
            rtpPortHigh=self.config.rtp_port_high,
        )
        self._phone.sip.server = sip_domain
        self._phone._status = PhoneStatus.REGISTERING
        try:
            _start_sip_with_route(self._phone, signal_host, sip_domain)
            self._phone.NSD = True
        except Exception:
            self._phone._status = PhoneStatus.FAILED
            self._phone.sip.stop()
            self._phone.NSD = False
            raise
        time.sleep(1.5)
        if self._phone._status.name == "FAILED":
            raise RuntimeError(
                "BLACKBOX_GATE=FAIL: docker SIP REGISTER failed "
                f"(signal={signal_host} domain={sip_domain})"
            )
        self._call = self._phone.call(self.config.extension)
        self.sip_call_id = getattr(self._call, "call_id", None)
        return self._wait_answered()

    def _connect_host_pyvoip(self) -> SipSessionInfo:
        """Host Mac → published Docker SIP (legacy; prefer PJSUA2 for external gate)."""
        _require_pyvoip()
        from pyVoIP.VoIP import VoIPPhone

        local_port = _pick_free_udp_port(self.config.local_sip_port)
        client_ip = _resolve_client_ip(self.config.sip_host, self.config.sip_port)
        if client_ip.startswith("127."):
            raise RuntimeError(
                "BLACKBOX_GATE=FAIL: use LAN host IP for RTP (not 127.0.0.1). "
                "Set IMVERA_LIVE_CLIENT_IP to this machine's LAN address."
            )
        signal_host = self.config.sip_host
        sip_domain = self.config.sip_domain
        self._phone = VoIPPhone(
            signal_host,
            self.config.sip_port,
            self.config.sip_user,
            self.config.sip_password,
            myIP=client_ip,
            sipPort=local_port,
            rtpPortLow=self.config.rtp_port_low,
            rtpPortHigh=self.config.rtp_port_high,
        )
        self._phone.sip.server = sip_domain
        from pyVoIP.VoIP.status import PhoneStatus

        self._phone._status = PhoneStatus.REGISTERING
        try:
            _start_sip_with_route(self._phone, signal_host, sip_domain)
            self._phone.NSD = True
        except Exception:
            self._phone._status = PhoneStatus.FAILED
            self._phone.sip.stop()
            self._phone.NSD = False
            raise
        time.sleep(1.5)
        if self._phone._status.name == "FAILED":
            raise RuntimeError(
                "BLACKBOX_GATE=FAIL: SIP REGISTER failed "
                f"(signal={signal_host} domain={sip_domain} user={self.config.sip_user})"
            )
        try:
            self._phone.sip.s.setblocking(True)
            if getattr(self._phone.sip, "out", None) is not None:
                self._phone.sip.out.setblocking(True)
        except OSError:
            pass
        try:
            self._call = self._phone.call(self.config.extension)
        except TimeoutError:
            # FreeSWITCH may answer while pyVoIP invite recv races; poll calls map.
            for _ in range(20):
                if self._phone.calls:
                    self._call = next(iter(self._phone.calls.values()))
                    break
                time.sleep(0.25)
            else:
                raise
        self.sip_call_id = getattr(self._call, "call_id", None)
        return self._wait_answered()

    def _wait_answered(self) -> SipSessionInfo:
        from pyVoIP.VoIP import CallState

        last_state = None
        for _ in range(80):
            state = self._call.state
            if state != last_state:
                last_state = state
            if state == CallState.ANSWERED:
                self._start_pump()
                return SipSessionInfo(
                    sip_call_id=self.sip_call_id,
                    connected=True,
                    answered=True,
                )
            if state in {CallState.ENDED, getattr(CallState, "CANCELLED", CallState.ENDED)}:
                break
            time.sleep(0.25)
        return SipSessionInfo(
            sip_call_id=self.sip_call_id,
            connected=last_state not in (None, CallState.ENDED),
            answered=False,
        )

    def _start_pump(self) -> None:
        frame_bytes = self.config.frame_bytes
        silence = bytes([128]) * frame_bytes

        def _loop() -> None:
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
