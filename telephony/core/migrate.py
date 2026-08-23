"""Idempotent migration runner for the MossVoice data core.

Applies telephony/migrations/*.sql in filename order, recording each in
schema_migrations. Each SQL file is itself idempotent (CREATE ... IF NOT
EXISTS), so re-applying is harmless. Run standalone:

    python -m core.migrate [--pg-url URL] [--dry-run]

or call apply_migrations(pg) from Serve startup when Postgres is configured.
"""

import argparse
import glob
import os


def _default_url():
    return os.environ.get("MOSS_PG_URL", "")


def _connect(url):
    import psycopg

    conn = psycopg.connect(url, autocommit=True)
    return conn


def _applied_versions(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT version FROM schema_migrations ORDER BY version")
        return {row[0] for row in cur.fetchall()}


def _migration_files(migrations_dir=None):
    base = migrations_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "migrations")
    return sorted(glob.glob(os.path.join(base, "*.sql")))


def apply_migrations(pg_url=None, migrations_dir=None, log=print):
    """Apply pending migrations. Returns the list of applied versions."""
    url = pg_url or _default_url()
    if not url:
        log("[migrate] no MOSS_PG_URL; skipping")
        return []
    conn = _connect(url)
    applied = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                " version TEXT PRIMARY KEY,"
                " applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
        conn.commit()
        done = _applied_versions(conn)
        for path in _migration_files(migrations_dir):
            version = os.path.basename(path)
            if version in done:
                continue
            with open(path, encoding="utf-8") as f:
                sql = f.read()
            # The SQL and the version row must commit atomically: the
            # connection is autocommit, so recording the version first
            # would permanently skip a migration whose DDL failed.
            conn.autocommit = False
            try:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    cur.execute("INSERT INTO schema_migrations (version) "
                                "VALUES (%s)", (version,))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.autocommit = True
            applied.append(version)
            log(f"[migrate] applied {version}")
    finally:
        conn.close()
    return applied


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pg-url", default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="only list pending migrations, do not apply")
    args = ap.parse_args()

    if args.dry_run:
        conn = _connect(args.pg_url or _default_url())
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "CREATE TABLE IF NOT EXISTS schema_migrations ("
                    " version TEXT PRIMARY KEY,"
                    " applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
            conn.commit()
            done = _applied_versions(conn)
            for path in _migration_files():
                v = os.path.basename(path)
                print(("applied  " if v in done else "pending  ") + v)
        finally:
            conn.close()
        return

    apply_migrations(args.pg_url)


if __name__ == "__main__":
    main()