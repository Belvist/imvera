"""Self-call harness: I call Vera myself (raw TCP SIP + RTP).

Usage: python3 tools/voice_lab/self_call.py
Establishes a call to 7000, plays scripted user WAVs, records Vera's
downlink, hangs up. Output: .run/selfcall/<ts>/ with uplink/downlink WAVs
+ turns.jsonl for analysis. No Zoiper, no pyVoIP, no human needed.
"""

from __future__ import annotations

import audioop
import datetime
import json
import random
import socket
import struct
import sys
import threading
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

FS_HOST = "192.168.1.194"
FS_PORT = 5060
CALLEE = "7000"
LOCAL_IP = "192.168.1.194"
RTP_PORT = 15002
FRAME_MS = 20
SR = 8000

# (wait_for_vera_s, wav_to_play or None)
SCRIPT: list[tuple[float, str | None]] = [
    (6.0, "wellness_good_01.wav"),
    (9.0, "mood_positive_01.wav"),
    (9.0, "sleep_good_01.wav"),
    (9.0, "plans_home_01.wav"),
    (9.0, "goodbye_01.wav"),
]

WAV_DIR = ROOT / "tests" / "assets" / "blackbox_voice" / "wav"


def ulaw_to_pcm(data: bytes) -> bytes:
    return audioop.ulaw2lin(data, 2)


def pcm_to_ulaw(data: bytes) -> bytes:
    return audioop.lin2ulaw(data, 2)


class SipCall:
    def __init__(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(30)
        self.sock.connect((FS_HOST, FS_PORT))
        self.tag = f"self{random.randint(1000, 9999)}"
        self.call_id = f"selfcall-{int(time.time())}@lab"
        self.branch = f"z9hG4bK{random.randint(10000, 99999)}"
        self.cseq = 1
        self.to_tag: str | None = None
        self.remote_rtp: tuple[str, int] | None = None

    def _send(self, method: str, extra: str = "", body: str = "") -> None:
        msg = (
            f"{method} sip:{CALLEE}@{FS_HOST} SIP/2.0\r\n"
            f"Via: SIP/2.0/TCP {LOCAL_IP}:5099;branch={self.branch}\r\n"
            f"From: <sip:selfcaller@{FS_HOST}>;tag={self.tag}\r\n"
            f"To: <sip:{CALLEE}@{FS_HOST}>{self.to_tag or ''}\r\n"
            f"Call-ID: {self.call_id}\r\n"
            f"CSeq: {self.cseq} {method}\r\n"
            f"Contact: <sip:selfcaller@{LOCAL_IP}:5099;transport=tcp>\r\n"
            f"Content-Length: {len(body)}\r\n{extra}\r\n{body}"
        )
        self.sock.sendall(msg.encode())

    def _recv_response(self, timeout: float = 25.0) -> str:
        self.sock.settimeout(timeout)
        buf = b""
        start = time.time()
        while time.time() - start < timeout:
            try:
                chunk = self.sock.recv(8192)
            except TimeoutError:
                break
            if not chunk:
                break
            buf += chunk
            txt = buf.decode(errors="replace")
            if "SIP/2.0 200" in txt or "SIP/2.0 4" in txt or "SIP/2.0 5" in txt:
                return txt
        return buf.decode(errors="replace")

    def invite(self) -> bool:
        sdp = (
            "v=0\r\no=- 1 1 IN IP4 192.168.1.194\r\ns=-\r\n"
            "c=IN IP4 192.168.1.194\r\nt=0 0\r\n"
            f"m=audio {RTP_PORT} RTP/AVP 0 101\r\n"
            "a=rtpmap:0 PCMU/8000\r\na=rtpmap:101 telephone-event/8000\r\n"
        )
        self._send(
            "INVITE",
            extra="Content-Type: application/sdp\r\n",
            body=sdp,
        )
        resp = self._recv_response()
        if "SIP/2.0 200" not in resp:
            print("INVITE FAILED:", resp[:200])
            return False
        for line in resp.split("\r\n"):
            if line.startswith("To:") and "tag=" in line:
                self.to_tag = ";tag=" + line.split("tag=")[1].split(";")[0].strip()
            if line.startswith("m=audio"):
                parts = line.split()
                self.remote_rtp = (FS_HOST, int(parts[1]))
        # ACK
        self.cseq += 1
        ack = (
            f"ACK sip:{CALLEE}@{FS_HOST} SIP/2.0\r\n"
            f"Via: SIP/2.0/TCP {LOCAL_IP}:5099;branch={self.branch}ack\r\n"
            f"From: <sip:selfcaller@{FS_HOST}>;tag={self.tag}\r\n"
            f"To: <sip:{CALLEE}@{FS_HOST}>{self.to_tag or ''}\r\n"
            f"Call-ID: {self.call_id}\r\n"
            f"CSeq: 1 ACK\r\nContent-Length: 0\r\n\r\n"
        )
        self.sock.sendall(ack.encode())
        return True

    def bye(self) -> None:
        try:
            self.cseq += 1
            self._send("BYE")
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


def load_u8_wav(path: Path) -> bytes:
    with wave.open(str(path), "rb") as w:
        raw = w.readframes(w.getnframes())
        width = w.getsampwidth()
        rate = w.getframerate()
        if width == 2:
            raw = audioop.lin2ulaw(raw, 2)
        if rate != 8000:
            raw, _ = audioop.ratecv(raw, 1, 1, rate, 8000, None)
        return raw


def main() -> None:
    ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d-%H%M%S")
    outdir = ROOT / ".run" / "selfcall" / ts
    outdir.mkdir(parents=True, exist_ok=True)
    call = SipCall()
    print("INVITE 7000 ...", flush=True)
    if not call.invite():
        print("CALL FAILED")
        raise SystemExit(1)
    print("answered, remote RTP:", call.remote_rtp, flush=True)

    rtp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rtp.bind(("0.0.0.0", RTP_PORT))
    rtp.settimeout(0.5)
    downlink: bytearray = bytearray()
    stop = threading.Event()

    def receiver() -> None:
        while not stop.is_set():
            try:
                data, _ = rtp.recvfrom(4096)
            except TimeoutError:
                continue
            except Exception:
                break
            if len(data) > 12:
                downlink.extend(data[12:])

    recv_thread = threading.Thread(target=receiver, daemon=True)
    recv_thread.start()

    seq = random.randint(1000, 9000)
    ssrc = random.randint(1, 2**31 - 1)
    timestamp = random.randint(1, 2**31 - 1)

    def send_ulaw(payload: bytes) -> None:
        nonlocal seq, timestamp
        for i in range(0, len(payload), 160):
            chunk = payload[i : i + 160]
            if len(chunk) < 160:
                chunk = chunk + b"\xff" * (160 - len(chunk))
            header = struct.pack(">BBHII", 0x80, 0, seq & 0xFFFF, timestamp, ssrc)
            rtp.sendto(header + chunk, call.remote_rtp)
            seq = (seq + 1) % 65536
            timestamp += 160
            time.sleep(0.02)

    def send_silence(seconds: float) -> None:
        send_ulaw(b"\xff" * 160 * int(seconds * 50))

    turns: list[dict] = []
    t0 = time.time()
    try:
        for wait_s, wav_name in SCRIPT:
            # Continuous RTP (silence) during waits: idle UDP mappings die
            # on Docker Desktop Mac otherwise.
            waited = 0.0
            while waited < wait_s:
                send_silence(0.5)
                waited += 0.5
            if wav_name is None:
                continue
            wav = load_u8_wav(WAV_DIR / wav_name)
            start_len = len(downlink)
            send_ulaw(wav)
            send_silence(0.5)
            turns.append(
                {
                    "played": wav_name,
                    "at_s": round(time.time() - t0, 1),
                    "downlink_bytes_before": start_len,
                }
            )
            print(f"played {wav_name} at {time.time() - t0:.0f}s", flush=True)
        time.sleep(8.0)
    finally:
        stop.set()
        call.bye()
    recv_thread.join(timeout=3.0)

    with wave.open(str(outdir / "downlink.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(8000)
        w.writeframes(bytes(downlink))
    (outdir / "turns.json").write_text(
        json.dumps(
            {
                "turns": turns,
                "downlink_bytes": len(downlink),
                "duration_s": round(time.time() - t0, 1),
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"done: {len(downlink)} downlink bytes -> {outdir}")


if __name__ == "__main__":
    main()
