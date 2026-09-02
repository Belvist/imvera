"""MossVoice Product API v1 — FastAPI on MOSS_PRODUCT_PORT (default 9480).

Separate process from telephony `:9400` (read.md / ROADMAP Э4). Household
membership is checked on every household-scoped route (IDOR protection).
OTP codes and JWTs are never logged.

JWT: HS256 MVP via ``MOSS_JWT_SECRET``; next step is RS256 + JWKS.
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.family import normalize_phone
from core.rate_limit import TokenBucketLimiter
from product.auth import (
    AuthConfigError,
    AuthError,
    build_otp_store,
    issue_token_pair,
    request_otp,
    verify_jwt,
    verify_otp,
)
from product.db import (
    ProductError,
    ProductStore,
    build_product_store,
)

_RATE = TokenBucketLimiter(max_entries=10000)


class OtpRequest(BaseModel):
    phone: str


class OtpVerify(BaseModel):
    phone: str
    code: str


class HouseholdCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ElderCreate(BaseModel):
    phone: str
    display_name: str = ""
    timezone: str = "Europe/Moscow"
    speech_notes: str = ""
    call_goal: str = ""


class SchedulePut(BaseModel):
    timezone: Optional[str] = None
    days_of_week: Optional[list] = None
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    frequency: Optional[str] = None
    quiet_start: Optional[str] = None
    quiet_end: Optional[str] = None
    attempt_policy: Optional[dict] = None
    paused: Optional[bool] = None
    enabled: Optional[bool] = None


class IncidentNote(BaseModel):
    note: Optional[str] = None
    reason: Optional[str] = None


class QuestionCreate(BaseModel):
    text: str
    author_label: str = ""


class ContactCreate(BaseModel):
    channel: str
    address: str
    escalate_order: int = 0
    label: str = ""
    elder_id: Optional[str] = None


class DeviceTokenCreate(BaseModel):
    platform: str
    token: str


class InviteMember(BaseModel):
    phone: str
    role: str = "member"


def _rate_capacity(env_name: str, default: int) -> int:
    try:
        capacity = int(os.environ.get(env_name, str(default)))
    except ValueError:
        capacity = default
    return max(1, min(capacity, 100000))


def create_app(store: Optional[ProductStore] = None,
               otp_store=None) -> FastAPI:
    """App factory — inject store/otp for tests."""
    app = FastAPI(
        title="IMVERA Product API",
        version="1.0.0",
        description=(
            "Product Core API (ROADMAP Э4). Auth: OTP + JWT HS256 MVP; "
            "next: RS256 + JWKS + rotating refresh."),
    )
    app.state.store = store if store is not None else build_product_store()
    app.state.otp = otp_store if otp_store is not None else build_otp_store()

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        peer = request.client.host if request.client else "unknown"
        path = request.url.path
        if path.startswith("/api/v1/auth/otp"):
            scope, env_name, default = "otp", "MOSS_PRODUCT_OTP_RATE", 20
        else:
            scope, env_name, default = "product", "MOSS_PRODUCT_RATE_LIMIT", 300
        capacity = _rate_capacity(env_name, default)
        allowed, retry_after = _RATE.allow(f"{scope}:{peer}", capacity, 60)
        if not allowed:
            return JSONResponse(
                {"ok": False, "error": "rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": str(retry_after)})
        return await call_next(request)

    def _store() -> ProductStore:
        return app.state.store

    def current_user(
            authorization: Optional[str] = Header(default=None),
            store: ProductStore = Depends(_store)) -> dict:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, detail="missing bearer token")
        token = authorization[7:].strip()
        try:
            claims = verify_jwt(token, expected_typ="access")
        except AuthConfigError as exc:
            raise HTTPException(503, detail=str(exc)) from exc
        except AuthError as exc:
            raise HTTPException(401, detail=str(exc)) from exc
        user = store.get_user(claims["sub"])
        if user is None or user.get("revoked_at"):
            raise HTTPException(401, detail="user revoked or missing")
        return user

    def _http_error(exc: ProductError) -> HTTPException:
        return HTTPException(exc.status, detail=str(exc))

    @app.get("/health")
    def health():
        return {
            "ready": True,
            "service": "mossvoice-product",
            "protocol_version": 1,
        }

    @app.post("/api/v1/auth/otp/request")
    def auth_otp_request(body: OtpRequest):
        phone = normalize_phone(body.phone)
        if len(phone) < 10:
            raise HTTPException(400, detail="invalid phone")
        try:
            result = request_otp(app.state.otp, phone)
        except AuthConfigError as exc:
            raise HTTPException(503, detail=str(exc)) from exc
        return result

    @app.post("/api/v1/auth/otp/verify")
    def auth_otp_verify(body: OtpVerify, store: ProductStore = Depends(_store)):
        phone = normalize_phone(body.phone)
        if len(phone) < 10:
            raise HTTPException(400, detail="invalid phone")
        try:
            ok = verify_otp(app.state.otp, phone, body.code)
        except AuthConfigError as exc:
            raise HTTPException(503, detail=str(exc)) from exc
        if not ok:
            raise HTTPException(401, detail="invalid otp")
        try:
            user = store.get_or_create_user(phone)
            tokens = issue_token_pair(user["id"], phone)
        except AuthConfigError as exc:
            raise HTTPException(503, detail=str(exc)) from exc
        except ProductError as exc:
            raise _http_error(exc) from exc
        return tokens

    @app.get("/api/v1/me")
    def me(user: dict = Depends(current_user)):
        return {
            "id": user["id"],
            "phone": user["phone"],
            "name": user.get("name") or "",
            "created_at": user.get("created_at"),
        }

    @app.delete("/api/v1/me")
    def delete_me(user: dict = Depends(current_user),
                  store: ProductStore = Depends(_store)):
        try:
            return store.revoke_user(user["id"])
        except ProductError as exc:
            raise _http_error(exc) from exc

    @app.post("/api/v1/households", status_code=201)
    def create_household(body: HouseholdCreate,
                         user: dict = Depends(current_user),
                         store: ProductStore = Depends(_store)):
        try:
            return store.create_household(user["id"], body.name)
        except ProductError as exc:
            raise _http_error(exc) from exc

    @app.get("/api/v1/households")
    def list_households(user: dict = Depends(current_user),
                        store: ProductStore = Depends(_store)):
        return {"households": store.list_households(user["id"])}

    @app.post("/api/v1/households/{household_id}/elders", status_code=201)
    def add_elder(household_id: str, body: ElderCreate,
                  user: dict = Depends(current_user),
                  store: ProductStore = Depends(_store)):
        try:
            store.require_member(household_id, user["id"],
                                 roles={"owner", "member"})
            return store.add_elder(
                household_id, body.phone, body.display_name,
                timezone=body.timezone, speech_notes=body.speech_notes,
                call_goal=body.call_goal)
        except ProductError as exc:
            raise _http_error(exc) from exc

    @app.get("/api/v1/households/{household_id}/elders")
    def list_elders(household_id: str,
                    user: dict = Depends(current_user),
                    store: ProductStore = Depends(_store)):
        try:
            store.require_member(household_id, user["id"])
            return {"elders": store.list_elders(household_id)}
        except ProductError as exc:
            raise _http_error(exc) from exc

    @app.put("/api/v1/elders/{elder_id}/schedule")
    def put_schedule(elder_id: str, body: SchedulePut,
                     user: dict = Depends(current_user),
                     store: ProductStore = Depends(_store)):
        try:
            store.require_elder_access(elder_id, user["id"],
                                       roles={"owner", "member"})
            payload = body.model_dump(exclude_none=True)
            return store.upsert_schedule(elder_id, payload)
        except ProductError as exc:
            raise _http_error(exc) from exc

    @app.get("/api/v1/elders/{elder_id}/calls")
    def elder_calls(elder_id: str,
                    user: dict = Depends(current_user),
                    store: ProductStore = Depends(_store)):
        try:
            store.require_elder_access(elder_id, user["id"])
            return {"calls": store.list_calls_for_elder(elder_id)}
        except ProductError as exc:
            raise _http_error(exc) from exc

    @app.get("/api/v1/households/{household_id}/incidents")
    def list_incidents(household_id: str,
                       user: dict = Depends(current_user),
                       store: ProductStore = Depends(_store)):
        try:
            store.require_member(household_id, user["id"])
            return {
                "incidents": store.list_incidents_for_household(household_id)}
        except ProductError as exc:
            raise _http_error(exc) from exc

    @app.post("/api/v1/incidents/{incident_id}/ack")
    def incident_ack(incident_id: str,
                     body: IncidentNote = IncidentNote(),
                     user: dict = Depends(current_user),
                     store: ProductStore = Depends(_store)):
        try:
            store.require_incident_access(incident_id, user["id"])
            return store.transition_incident(
                incident_id, "ack", user["id"],
                reason=body.reason or "Я проверю", note=body.note)
        except ProductError as exc:
            raise _http_error(exc) from exc

    @app.post("/api/v1/incidents/{incident_id}/resolve")
    def incident_resolve(incident_id: str,
                         body: IncidentNote = IncidentNote(),
                         user: dict = Depends(current_user),
                         store: ProductStore = Depends(_store)):
        try:
            store.require_incident_access(incident_id, user["id"])
            return store.transition_incident(
                incident_id, "resolved", user["id"],
                reason=body.reason or body.note or "resolved")
        except ProductError as exc:
            raise _http_error(exc) from exc

    @app.post("/api/v1/incidents/{incident_id}/false-alarm")
    def incident_false_alarm(incident_id: str,
                             body: IncidentNote = IncidentNote(),
                             user: dict = Depends(current_user),
                             store: ProductStore = Depends(_store)):
        try:
            store.require_incident_access(incident_id, user["id"])
            return store.transition_incident(
                incident_id, "false_alarm", user["id"],
                reason=body.reason or body.note or "false_alarm")
        except ProductError as exc:
            raise _http_error(exc) from exc

    @app.post("/api/v1/elders/{elder_id}/questions", status_code=201)
    def add_question(elder_id: str, body: QuestionCreate,
                     user: dict = Depends(current_user),
                     store: ProductStore = Depends(_store)):
        try:
            store.require_elder_access(elder_id, user["id"],
                                       roles={"owner", "member"})
            return store.add_family_question(
                elder_id, body.text, user["id"],
                author_label=body.author_label)
        except ProductError as exc:
            raise _http_error(exc) from exc

    @app.get("/api/v1/elders/{elder_id}/consent")
    def elder_consent(elder_id: str,
                      user: dict = Depends(current_user),
                      store: ProductStore = Depends(_store)):
        try:
            store.require_elder_access(elder_id, user["id"])
            return store.get_consent(elder_id)
        except ProductError as exc:
            raise _http_error(exc) from exc

    @app.get("/api/v1/elders/{elder_id}/schedule")
    def get_schedule(elder_id: str,
                     user: dict = Depends(current_user),
                     store: ProductStore = Depends(_store)):
        try:
            store.require_elder_access(elder_id, user["id"])
            row = store.get_schedule(elder_id)
            return {"schedule": row}
        except ProductError as exc:
            raise _http_error(exc) from exc

    @app.post("/api/v1/households/{household_id}/contacts", status_code=201)
    def add_contact(household_id: str, body: ContactCreate,
                    user: dict = Depends(current_user),
                    store: ProductStore = Depends(_store)):
        try:
            store.require_member(household_id, user["id"],
                                 roles={"owner", "member"})
            return store.add_contact(
                household_id, body.channel, body.address,
                escalate_order=body.escalate_order, label=body.label,
                elder_id=body.elder_id, user_id=user["id"])
        except ProductError as exc:
            raise _http_error(exc) from exc

    @app.get("/api/v1/households/{household_id}/contacts")
    def list_contacts(household_id: str,
                      user: dict = Depends(current_user),
                      store: ProductStore = Depends(_store)):
        try:
            store.require_member(household_id, user["id"])
            return {"contacts": store.list_contacts(household_id)}
        except ProductError as exc:
            raise _http_error(exc) from exc

    @app.post("/api/v1/me/device-tokens", status_code=201)
    def register_device(body: DeviceTokenCreate,
                       user: dict = Depends(current_user),
                       store: ProductStore = Depends(_store)):
        try:
            return store.register_device_token(
                user["id"], body.platform, body.token)
        except ProductError as exc:
            raise _http_error(exc) from exc

    @app.post("/api/v1/households/{household_id}/members", status_code=201)
    def invite_member(household_id: str, body: InviteMember,
                      user: dict = Depends(current_user),
                      store: ProductStore = Depends(_store)):
        try:
            store.require_member(household_id, user["id"], roles={"owner"})
            return store.invite_member(
                household_id, body.phone, role=body.role)
        except ProductError as exc:
            raise _http_error(exc) from exc

    @app.post("/api/v1/elders/{elder_id}/call-now", status_code=201)
    def call_now(elder_id: str,
                 user: dict = Depends(current_user),
                 store: ProductStore = Depends(_store)):
        try:
            store.require_elder_access(elder_id, user["id"],
                                       roles={"owner", "member"})
            return store.enqueue_call_now(elder_id)
        except ProductError as exc:
            raise _http_error(exc) from exc

    @app.post("/api/v1/households/{household_id}/telegram-bind")
    def telegram_bind(household_id: str,
                      user: dict = Depends(current_user),
                      store: ProductStore = Depends(_store)):
        try:
            store.require_member(household_id, user["id"],
                                 roles={"owner", "member"})
            from core.tg_bind import mint_bind_token
            token = mint_bind_token(household_id)
            bot = os.environ.get("MOSS_TG_BOT_USERNAME", "imvera_bot")
            return {
                "token": token,
                "deep_link": f"https://t.me/{bot}?start=bind_{token}",
            }
        except ProductError as exc:
            raise _http_error(exc) from exc
        except RuntimeError as exc:
            raise HTTPException(503, detail=str(exc)) from exc

    return app


# Module-level app for `uvicorn product.api:app`.
app = create_app()


def main(argv=None):
    import argparse
    import uvicorn

    ap = argparse.ArgumentParser(description="IMVERA Product API")
    ap.add_argument("--host", default=os.environ.get(
        "MOSS_PRODUCT_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(
        os.environ.get("MOSS_PRODUCT_PORT", "9480")))
    args = ap.parse_args(argv)
    runtime_app = create_app()
    uvicorn.run(runtime_app, host=args.host, port=args.port,
                log_level="warning")


if __name__ == "__main__":
    main()
