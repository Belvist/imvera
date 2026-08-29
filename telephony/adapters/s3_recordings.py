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


def minio_configured():
    """True when MinIO is CONFIGURED (env vars present), regardless of whether
    it is currently reachable.

    Used by retention (read.md rev-4 Gate C). A store that is configured but
    down still holds user recordings, so its deletion must be CONFIRMED before
    the metadata (object keys) is purged. A store that was never configured
    has no external objects to protect, so purging metadata is safe.
    """
    return bool(
        os.environ.get("MOSS_S3_ENDPOINT")
        and os.environ.get("MOSS_S3_ACCESS_KEY")
        and os.environ.get("MOSS_S3_SECRET_KEY")
    )


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


def save_wav(outdir, wav_bytes, call_id=None, turn_id=None, upload=True):
    """Persist a reply WAV to LOCAL disk. Returns the local path.

    ``upload=True`` (default) also pushes the object to MinIO when configured
    — kept for non-hot-path callers (greeting warmup, backchannel). The VOICE
    HOT PATH (read.md rev-3 G1) passes ``upload=False``: the local file write
    stays synchronous but the MinIO network upload is deferred to the
    background PersistenceWorker so object storage never delays first audio.
    """
    os.makedirs(outdir, exist_ok=True)
    if call_id:
        outdir = os.path.join(outdir, call_id)
        os.makedirs(outdir, exist_ok=True)
    stub = f"reply-{turn_id:04d}.wav" if turn_id is not None \
        else f"reply-{datetime.datetime.now().strftime('%H%M%S')}.wav"
    p = os.path.join(outdir, stub)
    with open(p, "wb") as f:
        f.write(wav_bytes)
    if upload and call_id:
        put_object(f"calls/{call_id}/{stub}", wav_bytes)
    return p


def upload_local_file(key, path):
    """Push a local WAV file to MinIO as one object. Best-effort; safe to run
    inside the PersistenceWorker (hot-path caller has already written the
    local copy synchronously)."""
    try:
        with open(path, "rb") as f:
            put_object(key, f.read())
        return key
    except OSError:
        return None


def save_user_wav(outdir, wav_path, call_id=None, turn_id=None, upload=True):
    """Copy the caller's audio to the LOCAL call archive (replay source).

    Recordings are isolated per call: ``{outdir}/{call_id}/user-{turn}.wav``.
    Local copy is always synchronous (the uploaded temp must be captured while
    it exists). ``upload=True`` also pushes the object to MinIO synchronously
    — non-hot-path default. The VOICE HOT PATH passes ``upload=False`` and
    hands MinIO off to the background PersistenceWorker (read.md rev-3 G1).
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
        if upload and call_id:
            with open(p, "rb") as f:
                put_object(f"calls/{call_id}/{stub}", f.read())
        return p
    except OSError:
        return None


def object_checksum(data):
    """SHA-256 of audio bytes (stored in Postgres alongside the key)."""
    return _sha256(data)


def delete_objects(keys):
    """Best-effort removal of S3 objects (read.md rev-3 G8 retention).

    Silently tolerates a down/unconfigured object store — retention must
    never wedge the worker on a network hang. Returns the count actually
    removed (0 when MinIO is not configured/reachable).
    """
    client, bucket = _ensure_minio()
    if client is None:
        return 0
    removed = 0
    for key in keys:
        try:
            client.remove_object(bucket, key)
            removed += 1
        except Exception as e:  # noqa: BLE001
            print(f"[s3] delete {key} failed: {e}", flush=True)
    return removed