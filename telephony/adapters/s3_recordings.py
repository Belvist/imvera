"""Recordings storage (s3_recordings): WAV persistence for replies/turns.

Two layers:
- Local filesystem (always): ``{outdir}/{call_id}/{kind}-{turn}.wav`` — the
  offline/legacy path and the replay source on a single host.
- MinIO/S3 (optional, Phase 2): when MOSS_S3_* is configured, WAVs are also
  uploaded as objects; Postgres stores the object key + checksum and the
  local copy is a cache.

The interface keeps the historical save_wav/save_user_wav signatures.
"""

import datetime
import hashlib
import io
import os
import shutil
import threading
import time

_MINIO = None
_BUCKET = None
# REALTIME FIX: negative cache. A configured-but-down MinIO used to be
# re-probed on every save_wav/save_user_wav (per turn!) with full network
# timeouts inside the voice path. After a failure we stay quiet for a while.
_MINIO_FAIL_UNTIL = 0.0
_MINIO_RETRY_SECONDS = float(os.environ.get("MOSS_S3_RETRY_SECONDS", "60"))
_MINIO_LK = threading.Lock()


def _ensure_minio():
    """Lazy MinIO client. Returns (client, bucket) or (None, None).

    Failures are negatively cached for MOSS_S3_RETRY_SECONDS (default 60);
    initialisation is serialised so two concurrent first uploads cannot
    race two clients/bucket probes."""
    global _MINIO, _BUCKET, _MINIO_FAIL_UNTIL
    if _MINIO is not None:
        return _MINIO, _BUCKET
    if time.time() < _MINIO_FAIL_UNTIL:
        return None, None
    with _MINIO_LK:
        if _MINIO is not None:
            return _MINIO, _BUCKET
        if time.time() < _MINIO_FAIL_UNTIL:
            return None, None
        endpoint = os.environ.get("MOSS_S3_ENDPOINT", "")
        ak = os.environ.get("MOSS_S3_ACCESS_KEY", "")
        sk = os.environ.get("MOSS_S3_SECRET_KEY", "")
        bucket = os.environ.get("MOSS_S3_BUCKET", "mossvoice-recordings")
        if not endpoint or not ak or not sk:
            return None, None
        try:
            from minio import Minio
            from urllib.parse import urlparse
            parsed = urlparse(endpoint)
            secure = parsed.scheme == "https"
            host = parsed.hostname or ""
            port = parsed.port or (443 if secure else 9000)
            client = Minio(f"{host}:{port}", access_key=ak,
                           secret_key=sk, secure=secure)
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
            _MINIO = client
            _BUCKET = bucket
            print("[s3] MinIO recording upload enabled", flush=True)
        except Exception as e:  # noqa: BLE001
            _MINIO_FAIL_UNTIL = time.time() + _MINIO_RETRY_SECONDS
            print(f"[s3] MinIO unavailable ({e}); disk-only recordings "
                  f"(retry in {int(_MINIO_RETRY_SECONDS)}s)", flush=True)
            return None, None
    return _MINIO, _BUCKET


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def minio_enabled():
    """True when MinIO is configured AND reachable (best-effort probe)."""
    client, bucket = _ensure_minio()
    return client is not None


def put_object(key, data):
    """Upload bytes to MinIO (best-effort). Returns the object key on
    success, None when MinIO is not configured or the upload fails."""
    client, bucket = _ensure_minio()
    if client is None:
        return None
    try:
        client.put_object(bucket, key, io.BytesIO(data), len(data))
        return key
    except Exception as e:  # noqa: BLE001
        print(f"[s3] upload {key} failed: {e}", flush=True)
        return None


def save_wav(outdir, wav_bytes, call_id=None, turn_id=None):
    """Persist a reply WAV. Returns the local path; when MinIO is configured
    the object is uploaded too (caller stores the key in Postgres)."""
    os.makedirs(outdir, exist_ok=True)
    if call_id:
        outdir = os.path.join(outdir, call_id)
        os.makedirs(outdir, exist_ok=True)
    stub = f"reply-{turn_id:04d}.wav" if turn_id is not None \
        else f"reply-{datetime.datetime.now().strftime('%H%M%S')}.wav"
    p = os.path.join(outdir, stub)
    with open(p, "wb") as f:
        f.write(wav_bytes)
    if call_id:
        put_object(f"calls/{call_id}/{stub}", wav_bytes)
    return p


def save_user_wav(outdir, wav_path, call_id=None, turn_id=None):
    """Copy the caller's audio to the call archive so it can be replayed later.

    Recordings are isolated per call: ``{outdir}/{call_id}/user-{turn}.wav``.
    A turn id is a per-call counter, so two simultaneous calls never collide.
    When MinIO is configured the copy is uploaded as an object too.
    """
    if not wav_path or not os.path.exists(wav_path):
        return None
    if call_id:
        outdir = os.path.join(outdir, call_id)
    os.makedirs(outdir, exist_ok=True)
    stub = f"user-{turn_id:04d}.wav" if turn_id is not None \
        else f"user-{datetime.datetime.now().strftime('%H%M%S')}.wav"
    p = os.path.join(outdir, stub)
    try:
        shutil.copyfile(wav_path, p)
        if call_id:
            with open(p, "rb") as f:
                put_object(f"calls/{call_id}/{stub}", f.read())
        return p
    except OSError:
        return None


def object_checksum(data):
    """SHA-256 of audio bytes (stored in Postgres alongside the key)."""
    return _sha256(data)