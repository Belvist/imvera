"""Product Core persistence: households, elders, schedules, incidents, calls.

`MemoryProductStore` powers offline unit tests. `PgProductStore` wraps
psycopg against migration `006_product_core.sql`. Both expose the same
surface so the HTTP layer stays backend-agnostic.
"""

from __future__ import annotations

import copy
import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional
from core.family import normalize_phone, validate_question_text, FamilyValidationError
from product.auth import phone_hash


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProductError(Exception):
    """Domain error with HTTP status."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class ProductStore:
    """Abstract product data access."""

    # -- users ----------------------------------------------------------- #
    def get_or_create_user(self, phone_digits: str, name: str = "") -> dict:
        raise NotImplementedError

    def get_user(self, user_id: str) -> Optional[dict]:
        raise NotImplementedError

    def revoke_user(self, user_id: str, detail: Optional[dict] = None) -> dict:
        raise NotImplementedError

    # -- households / membership ----------------------------------------- #
    def create_household(self, owner_user_id: str, name: str) -> dict:
        raise NotImplementedError

    def list_households(self, user_id: str) -> list:
        raise NotImplementedError

    def membership(self, household_id: str, user_id: str) -> Optional[dict]:
        raise NotImplementedError

    def require_member(self, household_id: str, user_id: str,
                       roles: Optional[set] = None) -> dict:
        row = self.membership(household_id, user_id)
        if row is None:
            raise ProductError("forbidden", 403)
        if roles is not None and row.get("role") not in roles:
            raise ProductError("forbidden", 403)
        return row

    # -- elders ---------------------------------------------------------- #
    def add_elder(self, household_id: str, phone: str, display_name: str = "",
                  timezone: str = "Europe/Moscow", speech_notes: str = "",
                  call_goal: str = "") -> dict:
        raise NotImplementedError

    def list_elders(self, household_id: str) -> list:
        raise NotImplementedError

    def get_elder(self, elder_id: str) -> Optional[dict]:
        raise NotImplementedError

    def require_elder_access(self, elder_id: str, user_id: str,
                             roles: Optional[set] = None) -> dict:
        elder = self.get_elder(elder_id)
        if elder is None:
            raise ProductError("elder not found", 404)
        hid = elder.get("household_id")
        if not hid:
            raise ProductError("elder has no household", 403)
        self.require_member(hid, user_id, roles=roles)
        return elder

    # -- schedules ------------------------------------------------------- #
    def upsert_schedule(self, elder_id: str, payload: dict) -> dict:
        raise NotImplementedError

    def get_schedule(self, elder_id: str) -> Optional[dict]:
        raise NotImplementedError

    # -- calls / incidents / questions / consent ------------------------- #
    def list_calls_for_elder(self, elder_id: str, limit: int = 50) -> list:
        raise NotImplementedError

    def list_incidents_for_household(self, household_id: str,
                                     limit: int = 50) -> list:
        raise NotImplementedError

    def get_incident(self, incident_id: str) -> Optional[dict]:
        raise NotImplementedError

    def require_incident_access(self, incident_id: str, user_id: str) -> dict:
        inc = self.get_incident(incident_id)
        if inc is None:
            raise ProductError("incident not found", 404)
        hid = inc.get("household_id")
        if not hid:
            # Fall back: resolve via elder_id if present.
            elder_id = inc.get("elder_id")
            if elder_id:
                elder = self.get_elder(elder_id)
                hid = (elder or {}).get("household_id")
        if not hid:
            raise ProductError("forbidden", 403)
        self.require_member(hid, user_id)
        return inc

    def transition_incident(self, incident_id: str, to_status: str,
                            actor: str, reason: str = "",
                            note: Optional[str] = None) -> dict:
        raise NotImplementedError

    def add_family_question(self, elder_id: str, text: str,
                            author_user_id: str, author_label: str = ""
                            ) -> dict:
        raise NotImplementedError

    def get_consent(self, elder_id: str) -> dict:
        raise NotImplementedError

    def add_contact(self, household_id: str, channel: str, address: str,
                    escalate_order: int = 0, label: str = "",
                    elder_id: str = None, user_id: str = None) -> dict:
        raise NotImplementedError

    def list_contacts(self, household_id: str) -> list:
        raise NotImplementedError

    def register_device_token(self, user_id: str, platform: str,
                              token: str) -> dict:
        raise NotImplementedError

    def invite_member(self, household_id: str, phone: str,
                      role: str = "member") -> dict:
        raise NotImplementedError

    def enqueue_call_now(self, elder_id: str) -> dict:
        raise NotImplementedError

    def audit(self, actor: str, action: str, entity: str = None,
              entity_id: str = None, detail: Optional[dict] = None) -> None:
        raise NotImplementedError


# =========================================================================== #
# In-memory backend (unit tests / offline).
# =========================================================================== #


class MemoryProductStore(ProductStore):
    def __init__(self):
        self._lock = threading.RLock()
        self.users = {}
        self.households = {}
        self.members = {}  # (household_id, user_id) -> role
        self.elders = {}
        self.schedules = {}
        self.calls = []  # list of call session dicts
        self.incidents = {}
        self.questions = {}
        self.consents = {}  # elder_id -> list
        self.contacts = {}  # id -> row
        self.device_tokens = {}  # id -> row
        self.call_jobs = {}  # id -> row
        self.audit_log = []

    def get_or_create_user(self, phone_digits: str, name: str = "") -> dict:
        phone_digits = normalize_phone(phone_digits)
        if not phone_digits:
            raise ProductError("invalid phone", 400)
        with self._lock:
            for u in self.users.values():
                if u["phone"] == phone_digits and u.get("revoked_at") is None:
                    return copy.deepcopy(u)
            uid = _new_id("user")
            row = {
                "id": uid,
                "phone": phone_digits,
                "phone_hash": phone_hash(phone_digits),
                "name": name or "",
                "created_at": _now_iso(),
                "revoked_at": None,
            }
            self.users[uid] = row
            self.audit("system", "user.created", "user", uid,
                       {"phone_hash": row["phone_hash"]})
            return copy.deepcopy(row)

    def get_user(self, user_id: str) -> Optional[dict]:
        with self._lock:
            u = self.users.get(user_id)
            return copy.deepcopy(u) if u else None

    def revoke_user(self, user_id: str, detail: Optional[dict] = None) -> dict:
        with self._lock:
            u = self.users.get(user_id)
            if u is None:
                raise ProductError("user not found", 404)
            export = {
                "user_id": user_id,
                "households": [
                    hid for (hid, uid), _ in self.members.items()
                    if uid == user_id],
                "exported_at": _now_iso(),
                **(detail or {}),
            }
            u["revoked_at"] = _now_iso()
            self.audit(user_id, "user.export_and_revoke", "user", user_id,
                       export)
            return {"revoked": True, "export": export}

    def create_household(self, owner_user_id: str, name: str) -> dict:
        name = (name or "").strip()
        if not name:
            raise ProductError("name required", 400)
        with self._lock:
            if owner_user_id not in self.users:
                raise ProductError("user not found", 404)
            hid = _new_id("hh")
            row = {
                "id": hid,
                "name": name,
                "owner_user_id": owner_user_id,
                "created_at": _now_iso(),
            }
            self.households[hid] = row
            self.members[(hid, owner_user_id)] = "owner"
            self.audit(owner_user_id, "household.created", "household", hid,
                       {"name": name})
            return copy.deepcopy(row)

    def list_households(self, user_id: str) -> list:
        with self._lock:
            out = []
            for (hid, uid), role in self.members.items():
                if uid != user_id:
                    continue
                hh = self.households.get(hid)
                if hh:
                    item = copy.deepcopy(hh)
                    item["role"] = role
                    out.append(item)
            return out

    def membership(self, household_id: str, user_id: str) -> Optional[dict]:
        with self._lock:
            role = self.members.get((household_id, user_id))
            if role is None:
                return None
            return {"household_id": household_id, "user_id": user_id,
                    "role": role}

    def add_elder(self, household_id: str, phone: str, display_name: str = "",
                  timezone: str = "Europe/Moscow", speech_notes: str = "",
                  call_goal: str = "") -> dict:
        phone_digits = normalize_phone(phone)
        if not phone_digits:
            raise ProductError("invalid phone", 400)
        with self._lock:
            if household_id not in self.households:
                raise ProductError("household not found", 404)
            for e in self.elders.values():
                if e["phone"] == phone_digits:
                    raise ProductError("phone already registered", 409)
            eid = _new_id("elder")
            row = {
                "person_id": eid,
                "phone": phone_digits,
                "display_name": display_name or "",
                "timezone": timezone or "Europe/Moscow",
                "speech_notes": speech_notes or "",
                "call_goal": call_goal or "",
                "household_id": household_id,
                "created_at": _now_iso(),
            }
            self.elders[eid] = row
            return copy.deepcopy(row)

    def list_elders(self, household_id: str) -> list:
        with self._lock:
            return [copy.deepcopy(e) for e in self.elders.values()
                    if e.get("household_id") == household_id]

    def get_elder(self, elder_id: str) -> Optional[dict]:
        with self._lock:
            e = self.elders.get(elder_id)
            return copy.deepcopy(e) if e else None

    def upsert_schedule(self, elder_id: str, payload: dict) -> dict:
        with self._lock:
            if elder_id not in self.elders:
                raise ProductError("elder not found", 404)
            existing = self.schedules.get(elder_id) or {
                "id": _new_id("sched"),
                "elder_id": elder_id,
            }
            row = {
                **existing,
                "timezone": payload.get("timezone", existing.get(
                    "timezone", "Europe/Moscow")),
                "days_of_week": list(payload.get(
                    "days_of_week",
                    existing.get("days_of_week", [1, 2, 3, 4, 5, 6, 7]))),
                "window_start": payload.get(
                    "window_start", existing.get("window_start", "10:00")),
                "window_end": payload.get(
                    "window_end", existing.get("window_end", "13:00")),
                "frequency": payload.get(
                    "frequency", existing.get("frequency", "daily")),
                "quiet_start": payload.get(
                    "quiet_start", existing.get("quiet_start")),
                "quiet_end": payload.get(
                    "quiet_end", existing.get("quiet_end")),
                "attempt_policy": dict(payload.get(
                    "attempt_policy",
                    existing.get("attempt_policy",
                                 {"max_attempts": 3,
                                  "interval_minutes": 15}))),
                "paused": bool(payload.get(
                    "paused", existing.get("paused", False))),
                "enabled": bool(payload.get(
                    "enabled", existing.get("enabled", True))),
            }
            self.schedules[elder_id] = row
            return copy.deepcopy(row)

    def get_schedule(self, elder_id: str) -> Optional[dict]:
        with self._lock:
            s = self.schedules.get(elder_id)
            return copy.deepcopy(s) if s else None

    def list_calls_for_elder(self, elder_id: str, limit: int = 50) -> list:
        with self._lock:
            elder = self.elders.get(elder_id)
            if not elder:
                return []
            phone = elder["phone"]
            hid = elder.get("household_id")
            rows = []
            for c in self.calls:
                if c.get("elder_id") == elder_id:
                    rows.append(c)
                elif hid and c.get("household_id") == hid and (
                        c.get("caller_id") == phone):
                    rows.append(c)
            rows = sorted(rows, key=lambda r: r.get("created_at", ""),
                          reverse=True)[:limit]
            out = []
            for c in rows:
                result = c.get("result") or {}
                out.append({
                    "call_id": c.get("call_id"),
                    "status": c.get("status"),
                    "created_at": c.get("created_at"),
                    "ended_at": c.get("ended_at"),
                    "family_status": result.get("family_status") or result.get(
                        "verdict") or c.get("status"),
                    "summary": (
                        result.get("summary_for_family")
                        or result.get("summary")
                        or result.get("notes")),
                    "duration_seconds": result.get("duration_seconds"),
                })
            return copy.deepcopy(out)

    def seed_call(self, call_id: str, elder_id: str = None,
                  household_id: str = None, caller_id: str = None,
                  status: str = "completed", result: dict = None):
        """Test helper — insert a call history row."""
        with self._lock:
            self.calls.append({
                "call_id": call_id,
                "elder_id": elder_id,
                "household_id": household_id,
                "caller_id": caller_id,
                "status": status,
                "created_at": _now_iso(),
                "ended_at": _now_iso(),
                "result": result or {},
            })

    def list_incidents_for_household(self, household_id: str,
                                     limit: int = 50) -> list:
        with self._lock:
            rows = [copy.deepcopy(i) for i in self.incidents.values()
                    if i.get("household_id") == household_id]
            rows.sort(key=lambda r: r.get("opened_at", ""), reverse=True)
            return rows[:limit]

    def get_incident(self, incident_id: str) -> Optional[dict]:
        with self._lock:
            i = self.incidents.get(incident_id)
            return copy.deepcopy(i) if i else None

    def seed_incident(self, incident_id: str, household_id: str,
                      elder_id: str = None, status: str = "open",
                      call_id: str = None, reason: str = ""):
        with self._lock:
            self.incidents[incident_id] = {
                "id": incident_id,
                "household_id": household_id,
                "elder_id": elder_id,
                "call_id": call_id,
                "status": status,
                "severity": "red",
                "reason": reason,
                "notes": [],
                "opened_at": _now_iso(),
                "resolved_at": None,
            }

    def transition_incident(self, incident_id: str, to_status: str,
                            actor: str, reason: str = "",
                            note: Optional[str] = None) -> dict:
        allowed = {
            "ack": ("open", "ack", "checking"),
            "checking": ("open", "ack"),
            "resolved": ("open", "ack", "checking"),
            "false_alarm": ("open", "ack", "checking"),
        }
        with self._lock:
            inc = self.incidents.get(incident_id)
            if inc is None:
                raise ProductError("incident not found", 404)
            if to_status == "ack":
                # Mirror IncidentEngine: ack then checking.
                if inc["status"] not in allowed["ack"]:
                    raise ProductError("invalid transition", 409)
                if note:
                    notes = list(inc.get("notes") or [])
                    notes.append({"actor": actor, "note": note,
                                  "at": _now_iso()})
                    inc["notes"] = notes
                inc["status"] = "checking"
                self.audit(actor, "incident.ack", "incident", incident_id,
                           {"reason": reason or note or "family ack"})
            elif to_status in ("resolved", "false_alarm"):
                if inc["status"] not in allowed[to_status]:
                    raise ProductError("invalid transition", 409)
                inc["status"] = to_status
                if to_status == "resolved":
                    inc["resolved_at"] = _now_iso()
                self.audit(actor, f"incident.{to_status}", "incident",
                           incident_id, {"reason": reason})
            else:
                raise ProductError("unknown status", 400)
            return copy.deepcopy(inc)

    def add_family_question(self, elder_id: str, text: str,
                            author_user_id: str, author_label: str = ""
                            ) -> dict:
        try:
            clean = validate_question_text(text)
        except FamilyValidationError as exc:
            raise ProductError(str(exc), 400) from exc
        with self._lock:
            if elder_id not in self.elders:
                raise ProductError("elder not found", 404)
            qid = _new_id("q")
            row = {
                "q_id": qid,
                "person_id": elder_id,
                "author_account_id": author_user_id,
                "author_label": author_label or "",
                "text": clean,
                "status": "pending",
                "created_at": _now_iso(),
            }
            self.questions[qid] = row
            self.audit(author_user_id, "family.question.created", "question",
                       qid, {"elder_id": elder_id})
            return copy.deepcopy(row)

    def get_consent(self, elder_id: str) -> dict:
        with self._lock:
            rows = self.consents.get(elder_id) or []
            active = [r for r in rows if not r.get("revoked_at")]
            return {
                "elder_id": elder_id,
                "has_consent": bool(active),
                "consents": copy.deepcopy(active),
            }

    def add_contact(self, household_id: str, channel: str, address: str,
                    escalate_order: int = 0, label: str = "",
                    elder_id: str = None, user_id: str = None) -> dict:
        channel = (channel or "").strip().lower()
        address = (address or "").strip()
        if channel not in ("push", "telegram", "sms", "call", "email"):
            raise ProductError("invalid channel", 400)
        if not address:
            raise ProductError("address required", 400)
        with self._lock:
            if household_id not in self.households:
                raise ProductError("household not found", 404)
            cid = _new_id("ct")
            row = {
                "id": cid,
                "household_id": household_id,
                "elder_id": elder_id,
                "user_id": user_id,
                "channel": channel,
                "address": address,
                "escalate_order": int(escalate_order),
                "label": label or "",
            }
            self.contacts[cid] = row
            return copy.deepcopy(row)

    def list_contacts(self, household_id: str) -> list:
        with self._lock:
            rows = [copy.deepcopy(c) for c in self.contacts.values()
                    if c.get("household_id") == household_id]
            rows.sort(key=lambda r: (r.get("escalate_order", 0), r["id"]))
            return rows

    def register_device_token(self, user_id: str, platform: str,
                              token: str) -> dict:
        platform = (platform or "").strip().lower()
        token = (token or "").strip()
        if platform not in ("ios", "android"):
            raise ProductError("platform must be ios|android", 400)
        if not token or len(token) > 4096:
            raise ProductError("invalid token", 400)
        with self._lock:
            if user_id not in self.users:
                raise ProductError("user not found", 404)
            for existing in self.device_tokens.values():
                if existing.get("token") == token:
                    existing["revoked_at"] = None
                    existing["user_id"] = user_id
                    existing["platform"] = platform
                    return copy.deepcopy(existing)
            tid = _new_id("dt")
            row = {
                "id": tid,
                "user_id": user_id,
                "platform": platform,
                "token": token,
                "created_at": _now_iso(),
                "revoked_at": None,
            }
            self.device_tokens[tid] = row
            return copy.deepcopy(row)

    def invite_member(self, household_id: str, phone: str,
                      role: str = "member") -> dict:
        role = (role or "member").strip().lower()
        if role not in ("owner", "member", "viewer"):
            raise ProductError("invalid role", 400)
        user = self.get_or_create_user(phone)
        with self._lock:
            if household_id not in self.households:
                raise ProductError("household not found", 404)
            key = (household_id, user["id"])
            self.members[key] = role
            self.audit(user["id"], "household.member.invited", "household",
                       household_id, {"role": role})
            return {
                "household_id": household_id,
                "user_id": user["id"],
                "phone": user["phone"],
                "role": role,
            }

    def enqueue_call_now(self, elder_id: str) -> dict:
        with self._lock:
            if elder_id not in self.elders:
                raise ProductError("elder not found", 404)
            jid = _new_id("job")
            row = {
                "id": jid,
                "elder_id": elder_id,
                "schedule_id": None,
                "due_at": _now_iso(),
                "attempt_no": 1,
                "status": "pending",
                "created_at": _now_iso(),
            }
            self.call_jobs[jid] = row
            return copy.deepcopy(row)

    def audit(self, actor: str, action: str, entity: str = None,
              entity_id: str = None, detail: Optional[dict] = None) -> None:
        with self._lock:
            self.audit_log.append({
                "ts": _now_iso(),
                "actor": actor,
                "action": action,
                "entity": entity,
                "entity_id": entity_id,
                "detail": detail or {},
            })


# =========================================================================== #
# Postgres backend.
# =========================================================================== #


class PgProductStore(ProductStore):
    def __init__(self, url: Optional[str] = None, pg=None):
        if pg is not None:
            self._pg = pg
            return
        from adapters.pg import PgStore

        self._pg = PgStore(url=url)

    def _exec(self, sql, params=(), fetch=None, conn=None):
        return self._pg._exec(sql, params, conn=conn, fetch=fetch)

    def audit(self, actor: str, action: str, entity: str = None,
              entity_id: str = None, detail: Optional[dict] = None) -> None:
        self._pg.audit(action, actor, entity, entity_id, detail)

    def get_or_create_user(self, phone_digits: str, name: str = "") -> dict:
        phone_digits = normalize_phone(phone_digits)
        if not phone_digits:
            raise ProductError("invalid phone", 400)
        existing = self._exec(
            "SELECT id, phone, phone_hash, name, created_at, revoked_at "
            "FROM users WHERE phone = %s AND revoked_at IS NULL",
            (phone_digits,), fetch="one")
        if existing:
            return dict(existing)
        uid = _new_id("user")
        self._exec(
            "INSERT INTO users (id, phone, phone_hash, name) "
            "VALUES (%s, %s, %s, %s)",
            (uid, phone_digits, phone_hash(phone_digits), name or ""))
        self.audit("system", "user.created", "user", uid,
                   {"phone_hash": phone_hash(phone_digits)})
        return self.get_user(uid)

    def get_user(self, user_id: str) -> Optional[dict]:
        row = self._exec(
            "SELECT id, phone, phone_hash, name, created_at, revoked_at "
            "FROM users WHERE id = %s", (user_id,), fetch="one")
        return dict(row) if row else None

    def revoke_user(self, user_id: str, detail: Optional[dict] = None) -> dict:
        user = self.get_user(user_id)
        if user is None:
            raise ProductError("user not found", 404)
        households = self._exec(
            "SELECT household_id FROM household_members WHERE user_id = %s",
            (user_id,), fetch="all") or []
        export = {
            "user_id": user_id,
            "households": [r["household_id"] for r in households],
            "exported_at": _now_iso(),
            **(detail or {}),
        }
        self._exec(
            "UPDATE users SET revoked_at = now() "
            "WHERE id = %s AND revoked_at IS NULL", (user_id,))
        self.audit(user_id, "user.export_and_revoke", "user", user_id, export)
        return {"revoked": True, "export": export}

    def create_household(self, owner_user_id: str, name: str) -> dict:
        name = (name or "").strip()
        if not name:
            raise ProductError("name required", 400)
        hid = _new_id("hh")
        self._exec(
            "INSERT INTO households (id, name, owner_user_id) "
            "VALUES (%s, %s, %s)", (hid, name, owner_user_id))
        self._exec(
            "INSERT INTO household_members (household_id, user_id, role) "
            "VALUES (%s, %s, 'owner')", (hid, owner_user_id))
        self.audit(owner_user_id, "household.created", "household", hid,
                   {"name": name})
        row = self._exec(
            "SELECT id, name, owner_user_id, created_at FROM households "
            "WHERE id = %s", (hid,), fetch="one")
        return dict(row)

    def list_households(self, user_id: str) -> list:
        rows = self._exec(
            "SELECT h.id, h.name, h.owner_user_id, h.created_at, m.role "
            "FROM households h "
            "JOIN household_members m ON m.household_id = h.id "
            "WHERE m.user_id = %s ORDER BY h.created_at",
            (user_id,), fetch="all") or []
        return [dict(r) for r in rows]

    def membership(self, household_id: str, user_id: str) -> Optional[dict]:
        row = self._exec(
            "SELECT household_id, user_id, role FROM household_members "
            "WHERE household_id = %s AND user_id = %s",
            (household_id, user_id), fetch="one")
        return dict(row) if row else None

    def add_elder(self, household_id: str, phone: str, display_name: str = "",
                  timezone: str = "Europe/Moscow", speech_notes: str = "",
                  call_goal: str = "") -> dict:
        phone_digits = normalize_phone(phone)
        if not phone_digits:
            raise ProductError("invalid phone", 400)
        hh = self._exec(
            "SELECT id FROM households WHERE id = %s", (household_id,),
            fetch="one")
        if not hh:
            raise ProductError("household not found", 404)
        existing = self._exec(
            "SELECT person_id FROM elders WHERE phone = %s",
            (phone_digits,), fetch="one")
        if existing:
            raise ProductError("phone already registered", 409)
        eid = _new_id("elder")
        self._exec(
            "INSERT INTO elders (person_id, phone, display_name, timezone, "
            "speech_notes, call_goal, household_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (eid, phone_digits, display_name or "",
             timezone or "Europe/Moscow", speech_notes or "",
             call_goal or "", household_id))
        return self.get_elder(eid)

    def list_elders(self, household_id: str) -> list:
        rows = self._exec(
            "SELECT person_id, phone, display_name, timezone, speech_notes, "
            "call_goal, household_id, created_at FROM elders "
            "WHERE household_id = %s ORDER BY created_at",
            (household_id,), fetch="all") or []
        return [dict(r) for r in rows]

    def get_elder(self, elder_id: str) -> Optional[dict]:
        row = self._exec(
            "SELECT person_id, phone, display_name, timezone, speech_notes, "
            "call_goal, household_id, created_at FROM elders "
            "WHERE person_id = %s", (elder_id,), fetch="one")
        return dict(row) if row else None

    def upsert_schedule(self, elder_id: str, payload: dict) -> dict:
        if self.get_elder(elder_id) is None:
            raise ProductError("elder not found", 404)
        existing = self.get_schedule(elder_id)
        sid = (existing or {}).get("id") or _new_id("sched")
        days = payload.get("days_of_week")
        if days is None:
            days = (existing or {}).get("days_of_week") or [1, 2, 3, 4, 5, 6, 7]
        policy = payload.get("attempt_policy")
        if policy is None:
            policy = (existing or {}).get("attempt_policy") or {
                "max_attempts": 3, "interval_minutes": 15}
        row = {
            "id": sid,
            "elder_id": elder_id,
            "timezone": payload.get(
                "timezone", (existing or {}).get("timezone", "Europe/Moscow")),
            "days_of_week": list(days),
            "window_start": payload.get(
                "window_start",
                (existing or {}).get("window_start", "10:00")),
            "window_end": payload.get(
                "window_end",
                (existing or {}).get("window_end", "13:00")),
            "frequency": payload.get(
                "frequency", (existing or {}).get("frequency", "daily")),
            "quiet_start": payload.get(
                "quiet_start", (existing or {}).get("quiet_start")),
            "quiet_end": payload.get(
                "quiet_end", (existing or {}).get("quiet_end")),
            "attempt_policy": dict(policy),
            "paused": bool(payload.get(
                "paused", (existing or {}).get("paused", False))),
            "enabled": bool(payload.get(
                "enabled", (existing or {}).get("enabled", True))),
        }
        self._exec(
            "INSERT INTO schedules (id, elder_id, timezone, days_of_week, "
            "window_start, window_end, frequency, quiet_start, quiet_end, "
            "attempt_policy, paused, enabled) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s) "
            "ON CONFLICT (elder_id) DO UPDATE SET "
            "timezone = EXCLUDED.timezone, "
            "days_of_week = EXCLUDED.days_of_week, "
            "window_start = EXCLUDED.window_start, "
            "window_end = EXCLUDED.window_end, "
            "frequency = EXCLUDED.frequency, "
            "quiet_start = EXCLUDED.quiet_start, "
            "quiet_end = EXCLUDED.quiet_end, "
            "attempt_policy = EXCLUDED.attempt_policy, "
            "paused = EXCLUDED.paused, "
            "enabled = EXCLUDED.enabled",
            (row["id"], row["elder_id"], row["timezone"], row["days_of_week"],
             row["window_start"], row["window_end"], row["frequency"],
             row["quiet_start"], row["quiet_end"],
             json.dumps(row["attempt_policy"], ensure_ascii=False),
             row["paused"], row["enabled"]))
        return self.get_schedule(elder_id)

    def get_schedule(self, elder_id: str) -> Optional[dict]:
        row = self._exec(
            "SELECT id, elder_id, timezone, days_of_week, "
            "window_start::text AS window_start, "
            "window_end::text AS window_end, frequency, "
            "quiet_start::text AS quiet_start, "
            "quiet_end::text AS quiet_end, attempt_policy, paused, enabled "
            "FROM schedules WHERE elder_id = %s",
            (elder_id,), fetch="one")
        return dict(row) if row else None

    def list_calls_for_elder(self, elder_id: str, limit: int = 50) -> list:
        elder = self.get_elder(elder_id)
        if elder is None:
            return []
        rows = self._exec(
            "SELECT call_id, status, created_at, ended_at, result, "
            "caller_id, household_id "
            "FROM call_sessions "
            "WHERE household_id = %s AND ("
            "  caller_id = %s OR "
            "  COALESCE(result->>'elder_id', '') = %s"
            ") "
            "ORDER BY created_at DESC LIMIT %s",
            (elder.get("household_id"), elder["phone"], elder_id, limit),
            fetch="all") or []
        out = []
        for c in rows:
            result = c.get("result") or {}
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except Exception:  # noqa: BLE001
                    result = {}
            out.append({
                "call_id": c["call_id"],
                "status": c["status"],
                "created_at": c.get("created_at"),
                "ended_at": c.get("ended_at"),
                "family_status": (result.get("family_status")
                                  or result.get("verdict")
                                  or c.get("status")),
                "summary": result.get("summary") or result.get("notes"),
                "duration_seconds": result.get("duration_seconds"),
            })
        return out

    def list_incidents_for_household(self, household_id: str,
                                     limit: int = 50) -> list:
        rows = self._exec(
            "SELECT * FROM incidents WHERE household_id = %s "
            "ORDER BY opened_at DESC LIMIT %s",
            (household_id, limit), fetch="all") or []
        return [dict(r) for r in rows]

    def get_incident(self, incident_id: str) -> Optional[dict]:
        row = self._exec(
            "SELECT * FROM incidents WHERE id = %s", (incident_id,),
            fetch="one")
        return dict(row) if row else None

    def transition_incident(self, incident_id: str, to_status: str,
                            actor: str, reason: str = "",
                            note: Optional[str] = None) -> dict:
        inc = self.get_incident(incident_id)
        if inc is None:
            raise ProductError("incident not found", 404)
        if to_status == "ack":
            if note:
                self._exec(
                    "UPDATE incidents SET notes = COALESCE(notes, '[]'::jsonb) "
                    "|| %s::jsonb WHERE id = %s",
                    (json.dumps([{"actor": actor, "note": note,
                                  "at": _now_iso()}], ensure_ascii=False),
                     incident_id))
            n = self._pg.transition_incident(
                incident_id, ("open", "ack", "checking"), "ack", actor,
                reason or note or "family ack")
            self._pg.transition_incident(
                incident_id, ("open", "ack"), "checking", actor,
                reason or note or "family ack")
            if not n and self.get_incident(incident_id)["status"] not in (
                    "ack", "checking"):
                raise ProductError("invalid transition", 409)
        elif to_status == "resolved":
            n = self._pg.transition_incident(
                incident_id, ("open", "ack", "checking"), "resolved", actor,
                reason, assigns=(("resolved_at", "now()"),))
            if not n:
                raise ProductError("invalid transition", 409)
        elif to_status == "false_alarm":
            n = self._pg.transition_incident(
                incident_id, ("open", "ack", "checking"), "false_alarm",
                actor, reason)
            if not n:
                raise ProductError("invalid transition", 409)
        else:
            raise ProductError("unknown status", 400)
        return self.get_incident(incident_id)

    def add_family_question(self, elder_id: str, text: str,
                            author_user_id: str, author_label: str = ""
                            ) -> dict:
        try:
            clean = validate_question_text(text)
        except FamilyValidationError as exc:
            raise ProductError(str(exc), 400) from exc
        if self.get_elder(elder_id) is None:
            raise ProductError("elder not found", 404)
        qid = _new_id("q")
        # author_account_id FK → family_accounts (legacy API keys). Product
        # users live in `users`; pass NULL and keep identity in audit + label.
        label = author_label or ""
        self._pg.family_add_question(qid, elder_id, None, label, clean)
        self.audit(author_user_id, "family.question.created", "question", qid,
                   {"elder_id": elder_id, "author_user_id": author_user_id})
        row = self._exec(
            "SELECT q_id, person_id, author_account_id, author_label, text, "
            "status, created_at FROM family_questions WHERE q_id = %s",
            (qid,), fetch="one")
        return dict(row) if row else {
            "q_id": qid, "person_id": elder_id, "text": clean,
            "status": "pending"}

    def get_consent(self, elder_id: str) -> dict:
        rows = self._exec(
            "SELECT id, person_id, kind, scope, granted_at, revoked_at "
            "FROM consents WHERE person_id = %s ORDER BY granted_at DESC",
            (elder_id,), fetch="all") or []
        active = [dict(r) for r in rows if r.get("revoked_at") is None]
        return {
            "elder_id": elder_id,
            "has_consent": bool(active),
            "consents": [dict(r) for r in rows],
        }

    def add_contact(self, household_id: str, channel: str, address: str,
                    escalate_order: int = 0, label: str = "",
                    elder_id: str = None, user_id: str = None) -> dict:
        channel = (channel or "").strip().lower()
        address = (address or "").strip()
        if channel not in ("push", "telegram", "sms", "call", "email"):
            raise ProductError("invalid channel", 400)
        if not address:
            raise ProductError("address required", 400)
        cid = _new_id("ct")
        self._exec(
            "INSERT INTO contacts (id, household_id, elder_id, user_id, "
            "channel, address, escalate_order, label) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (cid, household_id, elder_id, user_id, channel, address,
             int(escalate_order), label or ""))
        row = self._exec(
            "SELECT * FROM contacts WHERE id = %s", (cid,), fetch="one")
        return dict(row) if row else {
            "id": cid, "household_id": household_id, "channel": channel,
            "address": address}

    def list_contacts(self, household_id: str) -> list:
        rows = self._exec(
            "SELECT * FROM contacts WHERE household_id = %s "
            "ORDER BY escalate_order ASC, id ASC",
            (household_id,), fetch="all") or []
        return [dict(r) for r in rows]

    def register_device_token(self, user_id: str, platform: str,
                              token: str) -> dict:
        platform = (platform or "").strip().lower()
        token = (token or "").strip()
        if platform not in ("ios", "android"):
            raise ProductError("platform must be ios|android", 400)
        if not token:
            raise ProductError("invalid token", 400)
        existing = self._exec(
            "SELECT * FROM device_tokens WHERE token = %s",
            (token,), fetch="one")
        if existing:
            self._exec(
                "UPDATE device_tokens SET user_id = %s, platform = %s, "
                "revoked_at = NULL WHERE token = %s",
                (user_id, platform, token))
            row = self._exec(
                "SELECT * FROM device_tokens WHERE token = %s",
                (token,), fetch="one")
            return dict(row)
        tid = _new_id("dt")
        self._exec(
            "INSERT INTO device_tokens (id, user_id, platform, token) "
            "VALUES (%s, %s, %s, %s)",
            (tid, user_id, platform, token))
        row = self._exec(
            "SELECT * FROM device_tokens WHERE id = %s", (tid,), fetch="one")
        return dict(row) if row else {
            "id": tid, "user_id": user_id, "platform": platform}

    def invite_member(self, household_id: str, phone: str,
                      role: str = "member") -> dict:
        role = (role or "member").strip().lower()
        if role not in ("owner", "member", "viewer"):
            raise ProductError("invalid role", 400)
        user = self.get_or_create_user(phone)
        self._exec(
            "INSERT INTO household_members (household_id, user_id, role) "
            "VALUES (%s, %s, %s) ON CONFLICT (household_id, user_id) "
            "DO UPDATE SET role = EXCLUDED.role",
            (household_id, user["id"], role))
        self.audit(user["id"], "household.member.invited", "household",
                   household_id, {"role": role})
        return {
            "household_id": household_id,
            "user_id": user["id"],
            "phone": user["phone"],
            "role": role,
        }

    def enqueue_call_now(self, elder_id: str) -> dict:
        if self.get_elder(elder_id) is None:
            raise ProductError("elder not found", 404)
        jid = _new_id("job")
        self._exec(
            "INSERT INTO call_jobs (id, elder_id, due_at, attempt_no, status) "
            "VALUES (%s, %s, now(), 1, 'pending')",
            (jid, elder_id))
        row = self._exec(
            "SELECT * FROM call_jobs WHERE id = %s", (jid,), fetch="one")
        return dict(row) if row else {"id": jid, "elder_id": elder_id,
                                      "status": "pending"}


def build_product_store(url: Optional[str] = None) -> ProductStore:
    """Prefer Postgres when `MOSS_PG_URL` is set; else in-memory."""
    import os

    pg_url = url if url is not None else os.environ.get("MOSS_PG_URL", "")
    if pg_url:
        try:
            return PgProductStore(url=pg_url)
        except Exception as exc:  # noqa: BLE001
            raise ProductError(f"postgres unavailable: {exc}", 503) from exc
    return MemoryProductStore()
