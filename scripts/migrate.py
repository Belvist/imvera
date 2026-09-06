#!/usr/bin/env python3
"""Apply SQL migrations to PostgreSQL."""

from __future__ import annotations

import os
import sys
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def main() -> int:
    url = os.environ.get("IMVERA_PG_URL")
    if not url:
        print("IMVERA_PG_URL not set", file=sys.stderr)
        return 1
    try:
        import psycopg
    except ImportError:
        print("psycopg not installed; pip install 'psycopg[binary]'", file=sys.stderr)
        return 1

    sql_files = sorted(MIGRATIONS.glob("*.sql"))
    if not sql_files:
        print("No migrations found")
        return 0

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            for path in sql_files:
                print(f"Applying {path.name}...")
                cur.execute(path.read_text())
        conn.commit()
    print("Migrations applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
