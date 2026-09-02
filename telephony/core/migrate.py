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
        # ROADMAP Э0: 002_family_questions.sql renamed to 003_*. If an old
        # DB already recorded the legacy filename, treat 003 as applied.
        _ALIASES = {
            "003_family_questions.sql": "002_family_questions.sql",
        }
        for path in _migration_files(migrations_dir):
            version = os.path.basename(path)
            legacy = _ALIASES.get(version)
            if version in done or (legacy and legacy in done):
                if legacy and legacy in done and version not in done:
                    # Record the new name so future runs stay clean.
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO schema_migrations (version) "
                            "VALUES (%s) ON CONFLICT DO NOTHING",
                            (version,))
                    log(f"[migrate] aliased {legacy} -> {version}")
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


# Tables the realtime voice process actually needs to function. The migration
# JOB owns DDL (read.md rev-3); a running Voice process must NOT run DDL — it
# only verifies the schema it expects is present (read-only SELECT).
_REQUIRED_TABLES = [
    "schema_migrations", "call_sessions", "call_attempts", "dialogue_turns",
    "dialogue_answers", "call_results", "provider_events", "outbox_messages",
    "incidents", "incident_actions", "consents", "person_memory",
    "audit_log",
]


def schema_missing(pg_url=None):
    """Read-only compatibility check: return the list of required tables that
    are MISSING. Empty list == the schema the voice process expects exists.

    Used by the realtime process at startup (read.md rev-3) instead of running
    piggyback DDL — DDL is the migration job's job, not a live call's.
    """
    url = pg_url or _default_url()
    if not url:
        raise RuntimeError("MOSS_PG_URL not set")
    conn = _connect(url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = current_schema()")
            present = {row[0] for row in cur.fetchall()}
    finally:
        conn.close()
    return [t for t in _REQUIRED_TABLES if t not in present]


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