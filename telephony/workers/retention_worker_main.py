#!/usr/bin/env python3
"""Retention worker (read.md rev-3 G8 + rev-4 Gate C): guaranteed TTL purge.

Ensures real user data matches the retention contract. Runs in the background
business deployment (`retention` compose service), NOT the realtime voice
process — deleting many objects/rows must never steal CPU from live audio.

Guarantees, per expired call (query: ended_at + retention_days < now()):
  1. collect the call's S3 audio object keys from dialogue_turns;
  2. delete the S3 objects and CONFIRM they are gone;  (Gate C)
  3. delete the local WAV dir (the voice local cache);
  4. atomically purge the PG rows (cascades to turns/results/attempts)
     and write a durable audit marker with the call_id only.

rev-4 Gate C: the Postgres metadata holds the object keys, so it must NOT be
purged until the S3 deletion is confirmed — otherwise a down object store
would orphan user recordings forever. When S3 is configured but unavailable,
``purge_one`` keeps the metadata (and therefore the keys) and returns False so
the next run retries (at-least-once deletion). A store that was never
configured has no external objects, so metadata can be purged safely.

An audit event always remains; the transcript/audio never does.

Run:
    python workers/retention_worker_main.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _paths import ensure_runtime_scripts  # noqa: E402

ensure_runtime_scripts()

from adapters.pg import maybe_pg_store            # noqa: E402
from adapters.s3_recordings import (             # noqa: E402
    delete_objects,
    minio_configured,
)


def _local_call_dir(outdir, call_id):
    return os.path.join(outdir, call_id)


def purge_one(pg, call_id, outdir):
    """Fully purge one call, in the rev-4 Gate C order.

    S3 deletion must be CONFIRMED before the Postgres metadata (which holds
    the object keys) is purged. Returns (purged: bool, s3_removed: int,
    local_removed: bool). When S3 is configured but not reachable, returns
    purged=False WITHOUT touching local/PG so a later run can retry.
    """
    keys = pg.audio_keys_for(call_id)
    if minio_configured():
        s3_removed = delete_objects(keys)
        # Gate C: if every object is not confirmed gone, HOLD — keep the
        # metadata (and the object keys) for a later retry. Never purge PG on
        # an unconfirmed export-side delete, or keys would be lost forever.
        if s3_removed < len(keys):
            return False, s3_removed, False
    else:
        # No external object store configured: nothing external to lose.
        s3_removed = 0
    local_removed = False
    d = _local_call_dir(outdir, call_id)
    if os.path.isdir(d):
        import shutil
        shutil.rmtree(d, ignore_errors=True)
        local_removed = not os.path.exists(d)
    purged = bool(pg.purge_call(call_id))
    return purged, s3_removed, local_removed


def run_once(pg, outdir, limit=200, log=print):
    """Process up to ``limit`` expired calls; returns the count purged."""
    expired = pg.expired_calls(limit=limit)
    count = 0
    held = 0
    for row in expired:
        call_id = row["call_id"]
        try:
            purged, s3_removed, local_removed = purge_one(pg, call_id, outdir)
            if purged:
                count += 1
                log(f"[retention] purged {call_id} "
                    f"(s3={s3_removed} local={int(local_removed)})",
                    flush=True)
            else:
                # Gate C: either already gone or S3 deletion not confirmed. We
                # keep the metadata and retry on a later run (at-least-once).
                held += 1
                log(f"[retention] held {call_id} for retry "
                    f"(s3={s3_removed}/{len(pg.audio_keys_for(call_id))})",
                    flush=True)
        except Exception as e:  # noqa: BLE001
            log(f"[retention] purge {call_id} failed: {e}", flush=True)
    if held:
        log(f"[retention] {held} expired call(s) held for retry", flush=True)
    return count


def main():
    pg = maybe_pg_store()
    if not getattr(pg, "available", False):
        print("[retention] postgres unavailable", flush=True)
        sys.exit(1)
    outdir = os.environ.get("MOSS_CALLS_OUTDIR", "/tmp/mossvoice")
    interval = int(os.environ.get("MOSS_RETENTION_INTERVAL_SECONDS", "3600"))
    batch = int(os.environ.get("MOSS_RETENTION_BATCH", "200"))
    print(f"[retention] worker started (outdir={outdir} "
          f"interval={interval}s)", flush=True)
    while True:
        try:
            n = run_once(pg, outdir, limit=batch)
            if n:
                print(f"[retention] purged {n} expired call(s)", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[retention] run failed: {e}", flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    main()
