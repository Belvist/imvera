"""PostgreSQL backup for Stage 0 stabilization (ops only, no prod imports).

Usage:
    python3 scripts/pg_backup.py [--keep 14]

Reads IMVERA_PG_URL (default: local dev DB), writes a timestamped
pg_dump custom-format file to IMVERA_BACKUP_DIR (default .run/backups),
verifies it with pg_restore --list, prunes older backups.
Exit non-zero on any failure — never a silent missing backup.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = "postgresql://imvera:imvera_dev_change_me@127.0.0.1:5432/imvera"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", type=int, default=14)
    args = ap.parse_args()

    dsn = os.environ.get("IMVERA_PG_URL", DEFAULT_URL)
    backup_dir = Path(os.environ.get("IMVERA_BACKUP_DIR", ROOT / ".run" / "backups"))
    backup_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = backup_dir / f"imvera-{stamp}.dump"

    env = dict(os.environ, PGCONNECT_TIMEOUT="10")
    proc = subprocess.run(
        ["pg_dump", "--format=custom", f"--file={path}", f"--dbname={dsn}"],
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        print(f"pg_dump FAILED\n{proc.stderr.strip()}", file=sys.stderr)
        raise SystemExit(1)

    verify = subprocess.run(
        ["pg_restore", "--list", str(path)], capture_output=True, text=True
    )
    entries = [ln for ln in verify.stdout.splitlines() if ln and not ln.startswith(";")]
    if verify.returncode != 0 or not entries:
        print(f"backup {path} FAILED verification (empty listing)", file=sys.stderr)
        path.unlink(missing_ok=True)
        raise SystemExit(1)

    for old in sorted(backup_dir.glob("imvera-*.dump"))[: -args.keep]:
        old.unlink()

    size_mb = path.stat().st_size / (1024 * 1024)
    print(f"backup ok: {path} ({size_mb:.1f} MB, {len(entries)} entries)")


if __name__ == "__main__":
    main()
