"""Isolated Linux lifecycle/HTTP proof; PCM fixture is not neural speech."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import httpx

FIXTURE = """
import json, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *args): pass
    def do_GET(self):
        value = ({'data': [{'id': 'controlled-pcm-fixture'}]}
                 if self.path == '/v1/models' else {'voices': ['vera_kseniya']})
        body = json.dumps(value).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.send_response(200)
        self.send_header('Content-Type', 'audio/pcm')
        self.send_header('Transfer-Encoding', 'chunked')
        self.end_headers()
        try:
            count = 50 if data['input'] == 'Проверка отмены.' else 3
            for index in range(count):
                pcm = b'\\0\\0' * 8
                self.wfile.write(('%x\\r\\n' % len(pcm)).encode() + pcm + b'\\r\\n')
                self.wfile.flush()
                time.sleep(.03)
            self.wfile.write(b'0\\r\\n\\r\\n')
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError): pass
ThreadingHTTPServer(('0.0.0.0', 8899), Handler).serve_forever()
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    env = dict(os.environ)
    for key in (
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_TLS",
        "DOCKER_TLS_VERIFY",
        "DOCKER_CERT_PATH",
    ):
        env.pop(key, None)
    prefix = ["docker", "--host=unix:///var/run/docker.sock"]

    def docker(*command: str) -> str:
        return subprocess.check_output(prefix + list(command), env=env, text=True).strip()

    def wait(check, timeout=30):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                result = check()
                if result:
                    return result
            except (httpx.HTTPError, OSError, KeyError, subprocess.CalledProcessError):
                pass
            time.sleep(0.1)
        raise TimeoutError("container proof gate did not settle")

    image = f"imvera/tts-http:{args.sha}"
    token = "imvera-review-" + uuid.uuid4().hex[:8]
    network = token + "-net"
    names = []
    record = {
        "source_sha": args.sha,
        "boundary": "actual Docker, controlled PCM resident fixture",
        "neural_tts_or_sip_acceptance": False,
    }
    details = json.loads(docker("image", "inspect", image))[0]
    assert details["Config"]["User"] == "10001:10001"
    assert details["Config"]["Labels"]["org.opencontainers.image.revision"] == args.sha
    record["image_id"] = details["Id"]
    hardened = [
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "--memory",
        "1g",
        "--cpus",
        "1",
        "--pids-limit",
        "128",
        "--init",
        "--stop-timeout",
        "30",
    ]
    docker("network", "create", network)
    try:
        with tempfile.TemporaryDirectory(prefix=token) as temporary:
            root = Path(temporary)
            root.chmod(0o755)
            fixture = root / "fixture.py"
            fixture.write_text(FIXTURE)
            fixture.chmod(0o644)
            resident = token + "-resident"
            names.append(resident)
            docker(
                "run",
                "-d",
                "--name",
                resident,
                "--network",
                network,
                "--network-alias",
                "resident",
                *hardened,
                "-v",
                f"{fixture}:/fixture.py:ro",
                image,
                "python",
                "/fixture.py",
            )
            wait(
                lambda: docker(
                    "exec",
                    resident,
                    "python",
                    "-c",
                    "import urllib.request; "
                    "urllib.request.urlopen('http://127.0.0.1:8899/v1/models', timeout=1); "
                    "print('ready')",
                )
            )
            worker = token + "-tts"
            names.append(worker)
            docker(
                "run",
                "-d",
                "--name",
                worker,
                "--restart",
                "unless-stopped",
                "--network",
                network,
                *hardened,
                "-p",
                "127.0.0.1::9102",
                "-e",
                "IMVERA_QWEN_TTS_URL=http://resident:8899",
                image,
            )
            binding = wait(
                lambda: (
                    ports
                    if (
                        ports := json.loads(
                            docker("inspect", "--format", "{{json .NetworkSettings.Ports}}", worker)
                        )
                    ).get("9102/tcp")
                    else None
                )
            )
            url = "http://127.0.0.1:" + binding["9102/tcp"][0]["HostPort"]
            with httpx.Client(timeout=10) as client:

                def ready():
                    response = client.get(url + "/health/ready")
                    return response.json() if response.status_code == 200 else None

                health = wait(ready)
                assert health["runtime"]["git_sha"] == args.sha
                assert health["runtime"]["runtime_mode"] == "production"
                assert health["runtime"]["profile_id"] == "linux-cpu-qwen-http"
                assert health["model_revision"] == "qwen_gguf:controlled-pcm-fixture"
                record["ready"] = health
                payload = {
                    "call_id": "container-proof",
                    "request_id": "r1",
                    "generation_id": "g1",
                    "phrase_id": "p1",
                    "text": "Проверка потока.",
                    "timeout_ms": 2000,
                }
                started = time.monotonic()
                with client.stream("POST", url + "/v1/synthesize", json=payload) as response:
                    assert response.status_code == 200
                    frames = []
                    for line in response.iter_lines():
                        frame = json.loads(line)
                        if not frames:
                            record["controlled_first_frame_ms"] = (
                                time.monotonic() - started
                            ) * 1000
                        frames.append(frame)
                assert any(frame.get("pcm_b64") for frame in frames)
                assert frames[-1] == {"done": True}
                record["successful_frames"] = len(frames)
                payload.update(request_id="r2", generation_id="g2", text="Проверка отмены.")
                with client.stream("POST", url + "/v1/synthesize", json=payload) as response:
                    lines = response.iter_lines()
                    assert json.loads(next(lines))["pcm_b64"]
                    cancelled = client.post(url + "/v1/cancel", json={"generation_id": "g2"})
                    assert cancelled.status_code == 200
                    rest = [json.loads(line) for line in lines]
                assert rest[-1] == {"done": True, "cancelled": True}
                settled = wait(
                    lambda: (
                        value
                        if (value := ready())
                        and value["queue_depth"] == 0
                        and value["cancellation"]["active"] == 0
                        else None
                    )
                )
                record["after_cancel"] = settled
            config = json.loads(docker("inspect", worker))[0]["HostConfig"]
            assert config["ReadonlyRootfs"] and config["Memory"] == 1024**3
            assert config["PidsLimit"] == 128 and config["Init"]
            record["hardened"] = True
            started = time.monotonic()
            docker("stop", worker)
            record["normal_stop_s"] = time.monotonic() - started
            assert record["normal_stop_s"] < 30
            failed = token + "-failed"
            names.append(failed)
            docker(
                "run",
                "-d",
                "--name",
                failed,
                "--restart",
                "unless-stopped",
                *hardened,
                "-e",
                "IMVERA_QWEN_TTS_URL=http://127.0.0.1:9",
                image,
            )
            restarted = wait(
                lambda: (
                    count
                    if (count := int(docker("inspect", "--format", "{{.RestartCount}}", failed)))
                    >= 1
                    else None
                ),
                timeout=20,
            )
            logs = docker("logs", failed)
            assert "startup_failed selected_engine=qwen_gguf" in logs
            assert "silero" not in logs.lower()
            record["cold_failure_supervisor_restarts"] = restarted
            record["no_lab_fallback"] = True
            docker("stop", failed)
    finally:
        for name in reversed(names):
            subprocess.run(prefix + ["rm", "-f", name], env=env, capture_output=True)
        subprocess.run(prefix + ["network", "rm", network], env=env, capture_output=True)
    args.output.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
