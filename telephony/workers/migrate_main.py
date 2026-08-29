#!/usr/bin/env python3
"""Standalone schema-migration JOB (read.md rev-3).

Ownership rule: DDL is applied by THIS deployment/job only, never by the
realtime voice process. The voice process (Serve) performs a read-only
schema-compatibility check at startup and refuses to serve calls if the
expected tables are missing.

Run as its own deployment / compose one-shot service (the `migrate` compose
service, driven by `make migrate`), BEFORE the telephony/voice rollout:

    python workers/migrate_main.py [--dry-run]

Exits 0 when the schema is fully migrated, non-zero otherwise (so a rollout
orchestrator can gate on success). Idempotent — safe to re-run.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _paths import ensure_runtime_scripts  # noqa: E402

ensure_runtime_scripts()

from core.migrate import apply_migrations, schema_missing, _default_url  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="verify schema is complete (compat check) without "
                         "applying pending migrations")
    args = ap.parse_args()

    url = _default_url()
    if not url:
        print("[migrate] MOSS_PG_URL unset — nothing to do", flush=True)
        sys.exit(1 if not args.dry_run else 0)

    if args.dry_run:
        missing = schema_missing(url)
        if missing:
            print(f"[migrate] SCHEMA INCOMPLETE: missing={missing}",
                  flush=True)
            sys.exit(1)
        print("[migrate] schema OK", flush=True)
        return

    applied = apply_migrations(url)
    missing = schema_missing(url)
    if missing:
        print(f"[migrate] FAILED: still missing={missing}", flush=True)
        sys.exit(1)
    print(f"[migrate] DONE applied={applied or 'none'} (schema complete)",
          flush=True)


if __name__ == "__main__":
    main()
