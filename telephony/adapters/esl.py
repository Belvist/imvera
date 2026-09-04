"""ESL (Event Socket Layer) client for FreeSWITCH call origination.

Connects to FreeSWITCH ESL on host.docker.internal:8021 and can
originate calls to SIP extensions. Used by the web "call my Mac" button.
"""

import socket
import os
import re
import time

ESL_HOST = os.environ.get("MOSS_ESL_HOST", "host.docker.internal")
ESL_PORT = int(os.environ.get("MOSS_ESL_PORT", "8021"))
ESL_PASSWORD = os.environ.get("MOSS_ESL_PASSWORD", "")
ESL_TIMEOUT = int(os.environ.get("MOSS_ESL_TIMEOUT", "10"))

DEFAULT_EXTENSION = os.environ.get("MOSS_CALL_EXTENSION", "brian")


class ESLConnectionError(RuntimeError):
    pass


def _recv_until(sock, marker=b"\n\n", timeout=10):
    buf = b""
    sock.settimeout(timeout)
    while marker not in buf:
        try:
            chunk = sock.recv(4096)
            if not chunk:
                raise ESLConnectionError("ESL connection closed")
            buf += chunk
        except socket.timeout:
            raise ESLConnectionError("ESL recv timed out")
    return buf


def _drain_events(sock, timeout=0.3):
    sock.settimeout(timeout)
    try:
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
    except socket.timeout:
        pass


def _auth(sock):
    if not ESL_PASSWORD:
        raise ESLConnectionError(
            "MOSS_ESL_PASSWORD is required; no insecure default is available")
    data = _recv_until(sock, b"\n\n")
    welcome = data.split(b"\n")[0].decode("utf-8", errors="replace")
    if "auth/request" not in welcome:
        raise ESLConnectionError(f"Unexpected ESL welcome: {welcome}")
    sock.sendall(f"auth {ESL_PASSWORD}\n\n".encode())
    data = _recv_until(sock, b"\n\n")
    text = data.decode("utf-8", errors="replace")
    if "+OK" not in text and "accepted" not in text:
        raise ESLConnectionError(f"ESL auth failed: {text[:100]}")


def _connect():
    """Open and authenticate one ESL socket without leaking failed sockets."""
    if not ESL_PASSWORD:
        raise ESLConnectionError(
            "MOSS_ESL_PASSWORD is required; no insecure default is available")
    sock = socket.create_connection((ESL_HOST, ESL_PORT), timeout=ESL_TIMEOUT)
    try:
        _auth(sock)
        return sock
    except Exception:
        sock.close()
        raise


def _safe_extension(value):
    """Return a command-safe SIP extension or raise a validation error."""
    text = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", text):
        raise ESLConnectionError("invalid SIP extension")
    return text


def _safe_phone(value):
    """Normalize an E.164-like phone number without ESL metacharacters."""
    text = re.sub(r"[\s()\-]", "", str(value or ""))
    if text.startswith("+"):
        digits = text[1:]
    else:
        digits = text
    if not digits.isdigit() or not 7 <= len(digits) <= 15:
        raise ESLConnectionError("invalid phone number")
    return digits


def _safe_channel_id(value):
    text = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", text):
        raise ESLConnectionError("invalid call identifier")
    return text


def _get_channel_uuid_by_dest(sock):
    """Find the most recent outbound channel UUID (Zoiper profile)."""
    sock.sendall(b"api show channels\n\n")
    sock.settimeout(3)
    data = b""
    for _ in range(10):
        try:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
        except socket.timeout:
            break
    text = data.decode("utf-8", errors="replace")
    best = None
    for line in text.split("\n"):
        if "sofia/zoiper/" in line:
            uuid = line.split(",")[0].strip()
            if re.match(r"^[a-f0-9]{8}-", uuid):
                if best is None or uuid > best:
                    best = uuid
    return best


def originate_call(extension=None):
    """Originate a call to a SIP extension via FreeSWITCH ESL.

    Returns dict with 'ok', 'uuid', and 'message' keys.
    """
    try:
        ext = _safe_extension(extension or DEFAULT_EXTENSION)
    except ESLConnectionError as e:
        return {"ok": False, "uuid": None, "message": str(e)}
    try:
        sock = _connect()

        dest = f"user/{ext}"
        cmd = f"bgapi originate {{ignore_early_media=true}}{dest} &park()"
        sock.sendall((cmd + "\n\n").encode())
        resp = _recv_until(sock, b"\n\n")
        _drain_events(sock)
        sock.close()

        text = resp.decode("utf-8", errors="replace")
        m = re.search(r"Job-UUID:\s*([a-f0-9\-]+)", text)
        if m:
            return {"ok": True, "uuid": m.group(1),
                    "message": f"Call originated to {ext}"}
        err = re.search(r"-ERR\s+(.*)", text)
        if err:
            return {"ok": False, "uuid": None,
                    "message": err.group(1).strip()}
        return {"ok": False, "uuid": None,
                "message": f"Unexpected response: {text[:100]}"}

    except socket.timeout:
        return {"ok": False, "uuid": None, "message": "ESL connection timed out"}
    except ESLConnectionError as e:
        return {"ok": False, "uuid": None, "message": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "uuid": None, "message": str(e)}



def originate_to_number(phone_number: str, caller_id: str = "IMVERA") -> dict:
    """Originate a call to an external phone number via FreeSWITCH ESL.

    Uses sofia/gateway/ru_provider/{number} to route through the configured SIP gateway.
    Returns dict with 'ok', 'uuid', and 'message' keys.
    """
    try:
        phone_number = _safe_phone(phone_number)
        sock = _connect()

        dest = f"sofia/gateway/ru_provider/{phone_number}"
        cmd = f'bgapi originate {{ignore_early_media=true,prefix_code=}}{dest} &park()'
        sock.sendall((cmd + "\n\n").encode())
        resp = _recv_until(sock, b"\n\n")
        _drain_events(sock)
        sock.close()

        text = resp.decode("utf-8", errors="replace")
        m = re.search(r"Job-UUID:\s*([a-f0-9\-]+)", text)
        if m:
            return {"ok": True, "uuid": m.group(1),
                    "message": f"Call originated to {phone_number}"}
        err = re.search(r"-ERR\s+(.*)", text)
        if err:
            return {"ok": False, "uuid": None,
                    "message": err.group(1).strip()}
        return {"ok": False, "uuid": None,
                "message": f"Unexpected response: {text[:100]}"}

    except socket.timeout:
        return {"ok": False, "uuid": None, "message": "ESL connection timed out"}
    except ESLConnectionError as e:
        return {"ok": False, "uuid": None, "message": str(e)}
    except Exception as e:
        return {"ok": False, "uuid": None, "message": str(e)}


def originate_status(result):
    """Normalize originate_* dict to (ok, detail). Failures use ``message``."""
    if not isinstance(result, dict):
        return False, "esl failed"
    if result.get("ok"):
        return True, str(result.get("uuid") or result.get("message") or "ok")
    detail = result.get("message") or result.get("error") or "esl failed"
    text = " ".join(str(detail).split())
    return False, text or "esl failed"


def kill_call(uuid_or_ext):
    """Kill a FreeSWITCH call channel.

    Tries uuid_kill first, then falls back to searching channels
    by destination number. Accepts either a channel UUID or an
    extension number (e.g. '1000').
    """
    try:
        uuid_or_ext = _safe_channel_id(uuid_or_ext)
        # First try direct uuid_kill
        sock = _connect()
        cmd = f"api uuid_kill {uuid_or_ext}"
        sock.sendall((cmd + "\n\n").encode())
        data = _recv_until(sock, b"\n\n")
        text = data.decode("utf-8", errors="replace")
        _drain_events(sock)
        sock.close()

        if "+OK" in text:
            return {"ok": True, "message": f"Killed call {uuid_or_ext}"}

        # Fallback: search for Zoiper channel by destination
        sock = _connect()
        channel_uuid = _get_channel_uuid_by_dest(sock)
        sock.close()

        if channel_uuid:
            sock = _connect()
            cmd = f"api uuid_kill {channel_uuid}"
            sock.sendall((cmd + "\n\n").encode())
            data = _recv_until(sock, b"\n\n")
            text = data.decode("utf-8", errors="replace")
            _drain_events(sock)
            sock.close()
            if "+OK" in text:
                return {"ok": True, "message": f"Killed call {uuid_or_ext} via channel {channel_uuid}"}
            return {"ok": False, "message": f"Channel found but kill failed: {text[:100]}"}

        return {"ok": False, "message": f"No channel found for {uuid_or_ext}"}

    except socket.timeout:
        return {"ok": False, "message": "ESL connection timed out"}
    except ESLConnectionError as e:
        return {"ok": False, "message": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": str(e)}