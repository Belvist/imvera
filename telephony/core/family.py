"""Family app <-> call pipeline: keys, validation, admin CLI (2026-08-23).

The iPhone app authenticates with a per-account API key (``mv_...``, shown
ONCE at creation, stored as sha256 hex). A key alone AUTHENTICATES; the
``account_access`` grant table AUTHORIZES which elders' phones the account
may ask about. Phones are matched as normalized digits so FreeSWITCH/Lua
caller_id formatting never breaks the join.

Admin CLI (run inside the telephony container, workdir /app/telephony):

    python -m core.family add-account --name "Мария" --role дочь
    python -m core.family add-elder   --phone +79001234567 --name "Мама"
    python -m core.family grant       --account <id> --person <id>
    python -m core.family list-keys
"""

import argparse
import hashlib
import os
import re
import secrets
import uuid


MAX_QUESTION_LEN = 500
MIN_QUESTION_LEN = 2
MAX_PENDING_PER_CALL = 5  # enforced by pg.family_pending(limit=...)


class FamilyAuthError(Exception):
    """401: missing/unknown/revoked API key."""


class FamilyAccessError(Exception):
    """403: phone unknown, or no account_access grant for this account."""


class FamilyValidationError(Exception):
    """400: bad phone/text payload."""


def new_key():
    """Fresh API key. mv_ prefix = easy grep in logs / obvious rotation."""
    return "mv_" + secrets.token_urlsafe(24)


def hash_key(raw_key):
    """sha256 hex of the raw key — the ONLY form ever stored."""
    return hashlib.sha256((raw_key or "").encode("utf-8")).hexdigest()


def normalize_phone(raw):
    """Canonical RU phone: digits only, 8-XXXXXXXXXX folded to 7-XXXXXXXXXX.
    '+7 (900) 123-45-67', '89001234567' and '79001234567' all become
    '79001234567' — FreeSWITCH/Lua caller_id formatting must never break
    the join between the app's number and the call's caller_id."""
    d = re.sub(r"\D", "", str(raw or ""))
    if len(d) == 11 and d.startswith("8"):
        d = "7" + d[1:]
    return d


def validate_question_text(text):
    clean = str(text or "").strip()
    if len(clean) < MIN_QUESTION_LEN:
        raise FamilyValidationError("question text is too short")
    if len(clean) > MAX_QUESTION_LEN:
        raise FamilyValidationError(
            f"question text exceeds {MAX_QUESTION_LEN} chars")
    return clean


# --------------------------------------------------------------------- #
# Admin CLI — direct psycopg, independent of the runtime PgStore pool.
# --------------------------------------------------------------------- #
def _connect(url):
    import psycopg

    return psycopg.connect(url or os.environ.get("MOSS_PG_URL", ""),
                           autocommit=True)


def _cmd_add_account(conn, args):
    key = new_key()
    account_id = uuid.uuid4().hex[:12]
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO family_accounts "
            "(account_id, display_name, role, api_key_hash) "
            "VALUES (%s, %s, %s, %s)",
            (account_id, args.name, args.role, hash_key(key)))
    print(f"account_id: {account_id}")
    print(f"api_key (SHOW ONCE, store in the app): {key}")
    return 0


def _cmd_revoke_account(conn, args):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE family_accounts SET revoked_at = now() "
            "WHERE account_id = %s AND revoked_at IS NULL", (args.account,))
        n = cur.rowcount
    print(f"revoked: {n} account(s)")
    return 0 if n else 1


def _cmd_rotate_account(conn, args):
    key = new_key()
    with conn.cursor() as cur:
        # Atomic swap: old hash replaced -> old key dies instantly.
        cur.execute(
            "UPDATE family_accounts SET api_key_hash = %s, revoked_at = NULL "
            "WHERE account_id = %s", (hash_key(key), args.account))
        n = cur.rowcount
    if not n:
        print(f"no such account: {args.account}")
        return 1
    print(f"new api_key (SHOW ONCE): {key}")
    return 0


def _cmd_add_elder(conn, args):
    phone = normalize_phone(args.phone)
    if not phone:
        print("phone must contain digits")
        return 1
    person_id = args.person_id or ("elder-" + uuid.uuid4().hex[:8])
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO elders (person_id, phone, display_name) "
            "VALUES (%s, %s, %s) ON CONFLICT (phone) DO NOTHING",
            (person_id, phone, args.name))
        if cur.rowcount == 0:  # phone already bound — surface existing id
            cur.execute("SELECT person_id FROM elders WHERE phone = %s",
                        (phone,))
            person_id = cur.fetchone()[0]
            print(f"phone already bound to person_id: {person_id}")
            return 0
    print(f"person_id: {person_id}\nphone:     {phone}")
    return 0


def _cmd_grant(conn, args):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO account_access (account_id, person_id) "
            "VALUES (%s, %s) ON CONFLICT DO NOTHING", (args.account,
                                                      args.person))
        n = cur.rowcount
    print(f"granted: {n} new access row(s)")
    return 0


def _cmd_list_keys(conn, _args):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT a.account_id, a.display_name, a.role, "
            "       (a.revoked_at IS NULL) AS active, "
            "       COALESCE(string_agg(e.display_name, ', '), '') AS elders "
            "FROM family_accounts a "
            "LEFT JOIN account_access g ON g.account_id = a.account_id "
            "LEFT JOIN elders e ON e.person_id = g.person_id "
            "GROUP BY a.account_id ORDER BY a.created_at")
        for r in cur.fetchall():
            state = "active" if r[3] else "REVOKED"
            print(f"{r[0]}  {state:7}  {r[1]!r:20} role={r[2]!r} elders={r[4]}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="core.family",
                                description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("add-account")
    s.add_argument("--name", required=True)
    s.add_argument("--role", default="")
    s.set_defaults(fn=_cmd_add_account)

    s = sub.add_parser("revoke-account")
    s.add_argument("--account", required=True)
    s.set_defaults(fn=_cmd_revoke_account)

    s = sub.add_parser("rotate-account")
    s.add_argument("--account", required=True)
    s.set_defaults(fn=_cmd_rotate_account)

    s = sub.add_parser("add-elder")
    s.add_argument("--phone", required=True)
    s.add_argument("--name", default="")
    s.add_argument("--person-id", default="")
    s.set_defaults(fn=_cmd_add_elder)

    s = sub.add_parser("grant")
    s.add_argument("--account", required=True)
    s.add_argument("--person", required=True)
    s.set_defaults(fn=_cmd_grant)

    s = sub.add_parser("list-keys")
    s.set_defaults(fn=_cmd_list_keys)

    args = p.parse_args(argv)
    conn = _connect(args.pg_url if hasattr(args, "pg_url") else None)
    try:
        return args.fn(conn, args)
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
