"""Phase 3: outbound delivery channels for incident notifications.

Each channel implements ``send(contact, text) -> (ok, detail)``. Telegram is
REAL (Bot API via urllib — no new deps) when ``MOSS_TG_BOT_TOKEN`` is set.
SMS/call channels are structured but fail fast until their providers exist
(Exolve/Phase 4) — which is exactly what drives the escalation chain:
"Telegram недоступен -> fallback -> ...".
"""

import json
import os
import re
import urllib.parse
import urllib.request


MAX_PROVIDER_RESPONSE_BYTES = 64 * 1024


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _env_true(name):
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


def _validated_provider_url(value):
    parts = urllib.parse.urlsplit(value or "")
    if not parts.hostname or parts.username or parts.password or parts.fragment:
        raise ValueError("invalid provider URL")
    if parts.scheme != "https":
        if not (_env_true("MOSS_ALLOW_INSECURE_PROVIDER_HTTP")
                and parts.scheme == "http"
                and parts.hostname in ("127.0.0.1", "localhost", "::1")):
            raise ValueError("provider URL must use HTTPS")
    return parts.geturl()


def _normalized_phone(value):
    text = re.sub(r"[\s()\-]", "", str(value or ""))
    prefix = "+" if text.startswith("+") else ""
    digits = text[1:] if prefix else text
    if not digits.isdigit() or not 7 <= len(digits) <= 15:
        raise ValueError("invalid phone contact")
    return prefix + digits


def _post_provider(url, key, payload, timeout):
    if not key:
        raise ValueError("provider API key not set")
    endpoint = _validated_provider_url(url)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        endpoint, data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + key},
        method="POST")
    opener = urllib.request.build_opener(_NoRedirect)
    with opener.open(req, timeout=timeout) as resp:
        raw = resp.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
    if len(raw) > MAX_PROVIDER_RESPONSE_BYTES:
        raise ValueError("provider response too large")
    data = json.loads(raw.decode("utf-8", "strict"))
    if not isinstance(data, dict):
        raise ValueError("provider response must be an object")
    return data


class TelegramChannel:
    name = "telegram"

    def send(self, contact, text):
        token = os.environ.get("MOSS_TG_BOT_TOKEN", "")
        if not token:
            return False, "telegram: no MOSS_TG_BOT_TOKEN"
        if not str(contact or "").strip():
            return False, "telegram: contact not set"
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        body = json.dumps({"chat_id": contact, "text": str(text)[:4096]}).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
                if len(raw) > MAX_PROVIDER_RESPONSE_BYTES:
                    return False, "telegram: response too large"
                data = json.loads(raw.decode("utf-8", "strict"))
            if data.get("ok"):
                return True, f"telegram:ok:{data.get('result', {}).get('message_id')}"
            return False, f"telegram:{data.get('description', 'api error')}"
        except Exception as e:  # noqa: BLE001
            return False, f"telegram:{type(e).__name__}"


class SmsChannel:
    name = "sms"

    def send(self, contact, text):
        provider = os.environ.get("MOSS_SMS_PROVIDER", "")
        if not provider:
            return False, "sms: no MOSS_SMS_PROVIDER"
        url = os.environ.get("MOSS_SMS_PROVIDER_URL", "")
        key = os.environ.get("MOSS_SMS_PROVIDER_KEY", "")
        try:
            data = _post_provider(
                url, key,
                {"to": _normalized_phone(contact),
                 "from": os.environ.get("MOSS_SMS_PROVIDER_USER", ""),
                 "text": str(text)[:1600]},
                timeout=15)
            if data.get("ok") or data.get("status") == "success":
                message_id = data.get("id") or data.get("message_id") or ""
                return True, f"sms:{provider}:ok:{message_id}"
            return False, f"sms:{provider}:api error"
        except Exception as e:  # noqa: BLE001
            return False, f"sms:{provider}:{type(e).__name__}"


class VoiceChannel:
    name = "call"

    def send(self, contact, text):
        # Prefer FreeSWITCH ESL originate when MOSS_CALL_VIA_ESL=1 (ROADMAP E6).
        if _env_true("MOSS_CALL_VIA_ESL"):
            try:
                from adapters.esl import originate_to_number
                result = originate_to_number(_normalized_phone(contact))
                if result.get("ok"):
                    return True, f"call:esl:ok:{result.get('uuid', '')}"
                return False, f"call:esl:{result.get('error', 'failed')}"
            except Exception as e:  # noqa: BLE001
                return False, f"call:esl:{type(e).__name__}"
        provider = os.environ.get("MOSS_CALL_PROVIDER", "")
        if not provider:
            return False, "call: no MOSS_CALL_PROVIDER"
        url = os.environ.get("MOSS_CALL_PROVIDER_URL", "")
        key = os.environ.get("MOSS_CALL_PROVIDER_KEY", "")
        try:
            data = _post_provider(
                url, key,
                {"to": _normalized_phone(contact),
                 "from": os.environ.get("MOSS_CALL_PROVIDER_USER", ""),
                 "text": str(text)[:4000]},
                timeout=30)
            if data.get("ok") or data.get("status") == "success":
                call_id = data.get("id") or data.get("call_id") or ""
                return True, f"call:{provider}:ok:{call_id}"
            return False, f"call:{provider}:api error"
        except Exception as e:  # noqa: BLE001
            return False, f"call:{provider}:{type(e).__name__}"


class PushChannel:
    """APNs push via HTTP/2 provider API (token auth).

    Env:
      MOSS_APNS_KEY_ID, MOSS_APNS_TEAM_ID, MOSS_APNS_BUNDLE_ID,
      MOSS_APNS_KEY_PATH (p8 file), MOSS_APNS_PRODUCTION=0|1
    contact = device token hex string.
    Without keys returns fail-fast so escalation continues (E6).
    """
    name = "push"

    def send(self, contact, text):
        key_path = os.environ.get("MOSS_APNS_KEY_PATH", "")
        key_id = os.environ.get("MOSS_APNS_KEY_ID", "")
        team_id = os.environ.get("MOSS_APNS_TEAM_ID", "")
        bundle = os.environ.get("MOSS_APNS_BUNDLE_ID", "ru.imvera.app")
        if not (key_path and key_id and team_id and contact):
            return False, "push: APNs not configured"
        token = re.sub(r"[^0-9a-fA-F]", "", str(contact))
        if len(token) < 64:
            return False, "push: invalid device token"
        try:
            import time
            import jwt  # PyJWT optional; fall back below
        except ImportError:
            jwt = None
        try:
            with open(key_path, "rb") as f:
                secret = f.read()
            if jwt is None:
                return False, "push: PyJWT not installed"
            now = int(time.time())
            auth = jwt.encode(
                {"iss": team_id, "iat": now},
                secret,
                algorithm="ES256",
                headers={"kid": key_id},
            )
            host = ("api.push.apple.com" if _env_true("MOSS_APNS_PRODUCTION")
                    else "api.sandbox.push.apple.com")
            url = f"https://{host}/3/device/{token}"
            payload = json.dumps({
                "aps": {
                    "alert": {"title": "IMVERA", "body": str(text)[:500]},
                    "sound": "default",
                    "interruption-level": "time-sensitive",
                }
            }).encode("utf-8")
            req = urllib.request.Request(
                url, data=payload, method="POST",
                headers={
                    "authorization": "bearer " + auth,
                    "apns-topic": bundle,
                    "apns-push-type": "alert",
                    "apns-priority": "10",
                    "content-type": "application/json",
                })
            # stdlib cannot do HTTP/2; use provider gateway if set
            gateway = os.environ.get("MOSS_APNS_GATEWAY_URL", "")
            if gateway:
                data = _post_provider(
                    gateway, os.environ.get("MOSS_APNS_GATEWAY_KEY", "x"),
                    {"token": token, "title": "IMVERA",
                     "body": str(text)[:500], "bundle": bundle},
                    timeout=15)
                if data.get("ok"):
                    return True, "push:gateway:ok"
                return False, "push:gateway:error"
            # Without HTTP/2 gateway, document failure clearly
            return False, "push: set MOSS_APNS_GATEWAY_URL (HTTP/2 required)"
        except Exception as e:  # noqa: BLE001
            return False, f"push:{type(e).__name__}"


class DeliveryRouter:
    def __init__(self, channels=None):
        self._by_name = {}
        for ch in channels or _default_channels():
            self._by_name[ch.name] = ch

    def channel_names(self):
        order = (os.environ.get("MOSS_INCIDENT_CHANNELS",
                                "push,telegram,sms,call")
                 .replace(" ", "").split(","))
        return [n for n in order if n in self._by_name]

    def send(self, name, contact, text):
        ch = self._by_name.get(name)
        if ch is None:
            return False, f"channel {name} unavailable"
        return ch.send(contact, text)

    def resolve_contacts(self, household_contacts):
        """Map channel → contact from DB rows ``[{channel, address, order}]``.

        Falls back to ENV ``MOSS_FAMILY_CHAT_ID`` / ``MOSS_FAMILY_PHONE`` when
        the household list is empty (legacy single-family deploy).

        Returns an ordered list of ``(channel, address)`` pairs. Prefer
        ``contacts_dict`` for IncidentEngine plan building.
        """
        out = []
        for row in household_contacts or []:
            ch = (row.get("channel") or "").strip().lower()
            addr = (row.get("address") or "").strip()
            if ch and addr:
                out.append((ch, addr, int(row.get("escalate_order") or 0)))
        if out:
            out.sort(key=lambda x: x[2])
            return [(c, a) for c, a, _ in out]
        legacy = []
        chat = os.environ.get("MOSS_FAMILY_CHAT_ID", "").strip()
        phone = os.environ.get("MOSS_FAMILY_PHONE", "").strip()
        if chat:
            legacy.append(("telegram", chat))
        if phone:
            legacy.append(("sms", phone))
            legacy.append(("call", phone))
        return legacy

    def contacts_dict(self, household_contacts=None):
        """Channel → first address (ordered); ENV fallback when empty."""
        pairs = self.resolve_contacts(household_contacts)
        d = {}
        for ch, addr in pairs:
            if ch not in d:
                d[ch] = addr
        return d


def _default_channels():
    out = []
    for cls in (PushChannel, TelegramChannel, SmsChannel, VoiceChannel):
        try:
            out.append(cls())
        except Exception:  # noqa: BLE001
            pass
    return out