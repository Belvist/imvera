"""Phase 3: outbound delivery channels for incident notifications.

Each channel implements ``send(contact, text) -> (ok, detail)``. Telegram is
REAL (Bot API via urllib — no new deps) when ``MOSS_TG_BOT_TOKEN`` is set.
SMS/call channels are structured but fail fast until their providers exist
(Exolve/Phase 4) — which is exactly what drives the escalation chain:
"Telegram недоступен -> fallback -> ...".
"""

import json
import os
import urllib.request


class TelegramChannel:
    name = "telegram"

    def send(self, contact, text):
        token = os.environ.get("MOSS_TG_BOT_TOKEN", "")
        if not token:
            return False, "telegram: no MOSS_TG_BOT_TOKEN"
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        body = json.dumps({"chat_id": contact, "text": text}).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
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
        # TODO(phase4): Exolve/other provider API.
        return False, f"sms: provider {provider} not implemented"


class VoiceChannel:
    name = "call"

    def send(self, contact, text):
        provider = os.environ.get("MOSS_CALL_PROVIDER", "")
        if not provider:
            return False, "call: no MOSS_CALL_PROVIDER"
        # TODO(phase4): Exolve outbound call API.
        return False, f"call: provider {provider} not implemented"


class DeliveryRouter:
    def __init__(self, channels=None):
        self._by_name = {}
        for ch in channels or _default_channels():
            self._by_name[ch.name] = ch

    def channel_names(self):
        order = (os.environ.get("MOSS_INCIDENT_CHANNELS",
                                "telegram,sms,call")
                 .replace(" ", "").split(","))
        return [n for n in order if n in self._by_name]

    def send(self, name, contact, text):
        ch = self._by_name.get(name)
        if ch is None:
            return False, f"channel {name} unavailable"
        return ch.send(contact, text)


def _default_channels():
    out = []
    for cls in (TelegramChannel, SmsChannel, VoiceChannel):
        try:
            out.append(cls())
        except Exception:  # noqa: BLE001
            pass
    return out