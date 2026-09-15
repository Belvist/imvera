"""Parallel load probe — what does ONE call cost (Mac, no Linux needed).

Hammers STT /v1/transcribe and TTS /v1/synthesize at parallelism 1/2/4/8,
measures per-request latency + 503 rate + worker RSS. Proves (or kills)
the 10-parallel-calls claim with numbers, not opinions.

Usage: python3 tools/voice_lab/parallel_load_probe.py [--levels 1 2 4 8]
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

STT = "http://127.0.0.1:9101/v1/transcribe"
TTS = "http://127.0.0.1:9102/v1/synthesize"
PHRASE = "Здравствуйте. Как вы себя чувствуете?"


def _post(url: str, payload: dict, timeout: float = 60.0) -> tuple[int, bytes, float]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
        return r.status, body, (time.monotonic() - t0) * 1000
    except urllib.error.HTTPError as e:
        return e.code, e.read(), (time.monotonic() - t0) * 1000


def _tts_pcm(text: str) -> bytes:
    status, body, _ = _post(TTS, {
        "call_id": "probe", "generation_id": "g0", "phrase_id": "p0", "text": text,
    })
    assert status == 200, f"tts {status}: {body[:200]}"
    pcm = b""
    for line in body.decode().splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        chunk = row.get("pcm_b64") or row.get("audio_b64") or ""
        if chunk:
            pcm += base64.b64decode(chunk)
    assert len(pcm) > 1000, f"empty tts audio: {body[:200]}"
    return pcm


def _rss(name: str) -> str:
    try:
        out = subprocess.run(["ps", "-ax", "-o", "rss=,command="],
                             capture_output=True, text=True, timeout=10).stdout
        total = sum(int(ln.split()[0]) for ln in out.splitlines() if name in ln) // 1024
        return f"{total}MB"
    except Exception:
        return "?"


def _pct(v: list[float], q: float) -> float:
    s = sorted(v)
    return s[min(len(s) - 1, int(len(s) * q))] if s else float("nan")


def bench_stt(pcm_b64: str, n: int) -> None:
    lat, ok, e503, other = [], 0, 0, 0

    def one(i: int) -> None:
        nonlocal ok, e503, other
        st, body, ms = _post(STT, {"call_id": f"p{i}", "pcm_b64": pcm_b64,
                                   "sample_rate": 16000})
        lat.append(ms)
        if st == 200:
            ok += 1
        elif st == 503:
            e503 += 1
        else:
            other += 1

    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=n) as ex:
        list(ex.map(one, range(max(n * 3, 8))))
    dt = time.monotonic() - t0
    print(f"STT x{n}: ok={ok} 503={e503} other={other} "
          f"p50={_pct(lat, .5):.0f}ms p95={_pct(lat, .95):.0f}ms "
          f"wall={dt:.1f}s rss={_rss('imvera-stt')}")


def bench_tts(n: int) -> None:
    lat, ok, e503, other = [], 0, 0, 0

    def one(i: int) -> None:
        nonlocal ok, e503, other
        st, body, ms = _post(TTS, {"call_id": f"p{i}", "generation_id": f"g{i}",
                                   "phrase_id": "p0", "text": PHRASE})
        lat.append(ms)
        if st == 200:
            ok += 1
        elif st == 503:
            e503 += 1
        else:
            other += 1

    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=n) as ex:
        list(ex.map(one, range(max(n * 3, 8))))
    dt = time.monotonic() - t0
    print(f"TTS x{n}: ok={ok} 503={e503} other={other} "
          f"p50={_pct(lat, .5):.0f}ms p95={_pct(lat, .95):.0f}ms "
          f"wall={dt:.1f}s rss={_rss('imvera-tts')}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", nargs="+", type=int, default=[1, 2, 4, 8])
    args = ap.parse_args()
    print("warming TTS phrase...", flush=True)
    pcm = _tts_pcm(PHRASE)
    pcm_b64 = base64.b64encode(pcm).decode()
    print(f"probe pcm: {len(pcm)} bytes")
    for n in args.levels:
        bench_stt(pcm_b64, n)
    for n in args.levels:
        bench_tts(n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
