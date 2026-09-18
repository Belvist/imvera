#!/usr/bin/env python3
"""One-command launcher for M5 MLX voice + Zoiper SIP lab."""

from __future__ import annotations

import os
import subprocess
import sys
import time

import httpx

from scripts.voice_process import ROOT, is_running, start

LAB_AST = ROOT / "lab" / "asterisk" / "packages"
if str(LAB_AST) not in sys.path:
    sys.path.insert(0, str(LAB_AST))
from asterisk import is_stasis_app_registered, normalize_ari_http_root  # noqa: E402 lab only

from packages.voice_runtime.audio_audit import apply_audio_audit_env
from packages.voice_runtime.lab_half_duplex import apply_lab_half_duplex_env
from packages.voice_runtime.profile import apply_audio_env, audio_settings
from scripts.local_sip_config import load_or_create
from services.tts.lab_fast import apply_lab_fast_env, lab_fast_tts_enabled

VOICE_COMPOSE = ["docker", "compose", "-f", "lab/asterisk/docker-compose.voice.yml"]
WORKERS = ("stt", "tts", "llm")


def _wait_http(url: str, name: str, timeout_s: float = 600.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code == 200:
                print(f"  {name}: ready")
                return True
        except httpx.HTTPError:
            pass
        time.sleep(2.0)
    print(f"BLOCKED: {name} not ready at {url}", file=sys.stderr)
    return False


def _tts_matches_lab_fast() -> bool:
    """When lab fast is on, TTS must be silero_lab — not a warm but slow MLX worker."""
    if not lab_fast_tts_enabled():
        return True
    try:
        r = httpx.get("http://127.0.0.1:9102/health/ready", timeout=2.0)
        if r.status_code != 200:
            return False
        rev = str(r.json().get("model_revision", ""))
        return rev.startswith("silero_lab:silero:") and "macos_say" not in rev
    except httpx.HTTPError:
        return False


def _workers_ready() -> bool:
    for name in WORKERS:
        if not is_running(name):
            return False
        port = {"stt": 9101, "tts": 9102, "llm": 9103}[name]
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/health/ready", timeout=2.0)
            if r.status_code != 200:
                return False
        except httpx.HTTPError:
            return False
    if not _tts_matches_lab_fast():
        print("TTS worker is MLX — lab fast requires silero_lab; will restart workers")
        return False
    return True


def _ensure_workers(env: dict[str, str]) -> int:
    if _workers_ready():
        print("MLX workers already running — skipping models_up")
        return 0
    print("Starting MLX workers via models_up...")
    return subprocess.run(
        [sys.executable, "scripts/models_up.py"],
        cwd=ROOT,
        env=env,
        check=False,
    ).returncode


def _wait_ari_registered(cfg: dict) -> bool:
    http_root = normalize_ari_http_root(
        os.environ.get("IMVERA_ASTERISK_ARI_URL", "http://127.0.0.1:8088")
    )
    auth = (cfg["ari_user"], cfg["ari_password"])
    app = cfg["stasis_app"]
    deadline = time.time() + 120.0
    while time.time() < deadline:
        if is_stasis_app_registered(http_root, auth, app):
            print(f"  ARI app '{app}' registered")
            return True
        time.sleep(2.0)
    print(f"BLOCKED: ARI application '{app}' not registered", file=sys.stderr)
    return False


def _wait_asterisk_cli(timeout_s: float = 60.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            subprocess.check_output(
                ["docker", "exec", "imvera-asterisk", "asterisk", "-rx", "core show version"],
                stderr=subprocess.STDOUT,
                text=True,
            )
            return True
        except subprocess.CalledProcessError:
            time.sleep(1.0)
    print("BLOCKED: Asterisk CLI not ready", file=sys.stderr)
    return False


def _verify_asterisk_modules() -> bool:
    if not _wait_asterisk_cli():
        return False
    try:
        out = subprocess.check_output(
            ["docker", "exec", "imvera-asterisk", "asterisk", "-rx", "module show like websocket"],
            stderr=subprocess.STDOUT,
            text=True,
        )
        if "chan_websocket.so" not in out:
            print("BLOCKED: chan_websocket not loaded in Asterisk container", file=sys.stderr)
            return False
        print("  Asterisk chan_websocket: loaded")
        try:
            from scripts.local_sip_config import load_or_create

            cfg = load_or_create()
            auth = (cfg["ari_user"], cfg["ari_password"])
            http_root = normalize_ari_http_root("http://127.0.0.1:8088")
            import httpx

            for name in ("imvera_capture", "imvera_inject"):
                fmt = audio_settings()[
                    "capture_format" if name == "imvera_capture" else "inject_format"
                ]
                r = httpx.post(
                    f"{http_root}/ari/channels/externalMedia",
                    params={
                        "app": cfg["stasis_app"],
                        "external_host": name,
                        "transport": "websocket",
                        "encapsulation": "none",
                        "format": fmt,
                        "direction": "both",
                        "connection_type": "client",
                        "transport_data": "f(json)",
                    },
                    auth=auth,
                    timeout=5.0,
                )
                if r.status_code not in (200, 201):
                    print(
                        f"BLOCKED: websocket_client connection '{name}' invalid: {r.text}",
                        file=sys.stderr,
                    )
                    return False
                ch_id = r.json().get("id")
                if ch_id:
                    httpx.delete(
                        f"{http_root}/ari/channels/{ch_id}",
                        auth=auth,
                        timeout=5.0,
                    )
            print("  Asterisk websocket client: imvera_capture, imvera_inject")
        except httpx.HTTPError as exc:
            print(f"BLOCKED: cannot verify websocket_client connections: {exc}", file=sys.stderr)
            return False
        return True
    except subprocess.CalledProcessError as exc:
        print(f"BLOCKED: cannot verify Asterisk modules: {exc.output}", file=sys.stderr)
        return False


def main() -> int:
    profile = os.environ.get("IMVERA_VOICE_PROFILE", "m5-gigaam")
    if profile not in {"m5-gigaam", "m5-mlx"}:
        print(
            f"BLOCKED: unsupported profile {profile} (use m5-gigaam or m5-mlx)",
            file=sys.stderr,
        )
        return 1

    cfg = load_or_create()
    print("SIP credentials synced to config/local/asterisk/")

    env = apply_audio_audit_env(
        apply_lab_half_duplex_env(apply_lab_fast_env(apply_audio_env(os.environ.copy())))
    )
    if env.get("IMVERA_TTS_ENGINE") == "silero_lab":
        print("Lab fast TTS: silero_lab (IMVERA_LAB_FAST_TTS=1, ~1-2s warm first_pcm)")
        print(
            "  speaker: kseniya (Silero v5_ru) — NC lab only; "
            "macos say fallback if torch/omegaconf missing"
        )
    if env.get("IMVERA_LAB_HALF_DUPLEX", "1") in {"1", "true", "yes"}:
        pause = env.get("IMVERA_POST_SPEECH_PAUSE_MS", "100")
        preroll = env.get("IMVERA_UPLINK_PREROLL_MS", "2000")
        print(
            f"Lab half-duplex: ON (post-speech pause {pause}ms, preroll {preroll}ms — "
            "Vera finishes → pause → mic; opening_wellness always-listen + echo-ref)"
        )
    elif env.get("IMVERA_ECHO_REF_GATE", "0") in {"1", "true", "yes"}:
        print("Lab always-listen: echo reference gate ON (downlink PCM ring — not ML speaker-ID)")
    else:
        print("Lab listen: always-listen, echo-ref gate OFF (raw uplink)")
    if env.get("IMVERA_AUDIO_AUDIT", "0") in {"1", "true", "yes"}:
        print(
            "Audio audit: ON — trace capture.tick / audio.* / stt.request|result; "
            "dumps .run/captures/<call_id>.pcm + .run/stt_dumps/<call_id>_u-N.wav"
        )

    code = _ensure_workers(env)
    if code != 0:
        return code

    tts_rev = ""
    tts_ok = False
    try:
        tts_health = httpx.get("http://127.0.0.1:9102/health/ready", timeout=3.0)
        tts_ok = tts_health.status_code == 200
        tts_rev = str(tts_health.json().get("model_revision", "")) if tts_ok else ""
    except httpx.HTTPError:
        tts_ok = False
    if not tts_ok or "macos_say" in tts_rev or not tts_rev.startswith("silero_lab:silero:"):
        print(f"BLOCKED: TTS must be silero_lab (Silero), got {tts_rev!r}", file=sys.stderr)
        return 1
    env["IMVERA_TTS_MODEL_REVISION"] = tts_rev
    os.environ["IMVERA_TTS_MODEL_REVISION"] = tts_rev
    print(f"  TTS revision: {tts_rev}")

    cache_dir = ROOT / ".run" / "cache"
    if cache_dir.is_dir():
        for stale in cache_dir.glob("opening_*.json"):
            stale.unlink()
            print(f"  dropped stale opening cache {stale.name}")

    print("Pre-rendering opening phrase cache...")
    prerender = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "prerender_opening.py")],
        cwd=ROOT,
        env=env,
        check=False,
    )
    if prerender.returncode != 0:
        print("WARN: opening prerender failed — first call may wait on TTS", file=sys.stderr)

    env = apply_audio_env(env)
    env.setdefault("IMVERA_STT_URL", "http://127.0.0.1:9101")
    env.setdefault("IMVERA_TTS_URL", "http://127.0.0.1:9102")
    env.setdefault("IMVERA_LLM_URL", "http://127.0.0.1:9103")
    env.setdefault(
        "IMVERA_PG_URL",
        "postgresql://imvera:imvera_dev_change_me@127.0.0.1:5432/imvera",
    )
    env["IMVERA_ASTERISK_ARI_URL"] = normalize_ari_http_root(
        os.environ.get("IMVERA_ASTERISK_ARI_URL", "http://127.0.0.1:8088")
    )
    env["IMVERA_ASTERISK_ARI_USER"] = cfg["ari_user"]
    env["IMVERA_ASTERISK_ARI_PASSWORD"] = cfg["ari_password"]
    env["IMVERA_STASIS_APP"] = cfg["stasis_app"]
    env.setdefault("IMVERA_VOICE_GATEWAY_HTTP", "http://127.0.0.1:9200")
    env.setdefault("IMVERA_ASTERISK_APP_HTTP", "http://127.0.0.1:9201")
    env.setdefault("IMVERA_DEV_FAMILY_ID", "fam-voice")
    env.setdefault("IMVERA_ELDER_DISPLAY_NAME", "Даниил")

    print("Starting voice gateway on :9200...")
    start(
        "voice_gateway",
        [sys.executable, str(ROOT / "services" / "voice_gateway" / "main.py")],
        env=env,
    )
    if not _wait_http("http://127.0.0.1:9200/health/ready", "gateway", 30):
        return 1

    print("Starting Asterisk Stasis app on :9201...")
    start(
        "asterisk_app",
        [sys.executable, str(ROOT / "services" / "asterisk_app" / "main.py")],
        env=env,
    )
    if not _wait_http("http://127.0.0.1:9201/health/live", "asterisk_app", 30):
        return 1

    voice_service_port = int(os.environ.get("IMVERA_VOICE_SERVICE_PORT", "9300"))
    print(f"Starting voice-service on :{voice_service_port}...")
    start(
        "voice_service",
        [sys.executable, str(ROOT / "services" / "voice_service" / "main.py")],
        env=env,
    )
    if not _wait_http(f"http://127.0.0.1:{voice_service_port}/health/live", "voice_service", 30):
        return 1

    print("Starting Asterisk container...")
    subprocess.run([*VOICE_COMPOSE, "up", "-d", "--build"], cwd=ROOT, check=False)
    if not _verify_asterisk_modules():
        return 1
    if not _wait_ari_registered(cfg):
        return 1
    try:
        subprocess.check_call(
            ["docker", "exec", "imvera-asterisk", "asterisk", "-rx", "pjsip reload"],
            cwd=ROOT,
        )
        print("  Asterisk pjsip: reloaded")
    except subprocess.CalledProcessError:
        print("WARN: pjsip reload failed", file=sys.stderr)

    print("\nVoice stack up.")
    audio = audio_settings()
    print(f"  Inject format: {audio['inject_format']} ({audio['output_sample_rate']} Hz)")
    print(
        f"  Capture format: {audio['capture_format']}"
        f" (STT resamples to {audio['internal_sample_rate']} Hz)"
    )
    print(f"  Zoiper: {cfg['username']}@{cfg['sip_server']}:{cfg['port']}")
    print(f"  Password: {cfg['password']}")
    print(f"  Dial: {cfg['vera_extension']}")

    print("\nRunning voice call gate (warm TTS first_pcm budget)...")
    gate_env = env.copy()
    gate_env.setdefault("IMVERA_TTS_WARM_FIRST_PCM_BUDGET_S", "2.0")
    gate = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "voice_call_gate.py")],
        cwd=ROOT,
        env=gate_env,
        check=False,
    )
    if gate.returncode != 0:
        print("BLOCKED: voice-call-gate failed — fix TTS before Zoiper", file=sys.stderr)
        return 1

    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except subprocess.CalledProcessError:
        sha = "unknown"
    print(f"\n  Git SHA: {sha}")
    print("  Live gate: dial 7000 → hang up → python3 scripts/diagnose_call_trace.py <call_id>")
    print("  Pass: playback.completed → listen.enabled → speech.started → stt.final")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
