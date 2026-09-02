"""Consent grant / revoke / proof (ROADMAP E3).

Voice and DTMF scripts for the first consent call. Scheduler (E5) must call
``scheduler_may_call`` before originating — no active consent → no call.
"""

import hashlib
import secrets
import uuid

from core.call_status import CallStatus


CONSENT_SCRIPT_VERSION = "consent-v1"

CONSENT_VOICE_SCRIPT = (
    "Здравствуйте. Это Имвэра — сервис заботы. Мы хотим иногда звонить вам, "
    "чтобы спросить, как вы себя чувствуете, и при необходимости сообщать "
    "близким. Если вы согласны на такие звонки и запись разговора — скажите "
    "«согласна» или нажмите 1. Если не согласны — скажите «нет» или нажмите 2."
)

CONSENT_DTMF_SCRIPT = (
    "Для согласия нажмите 1. Чтобы отказаться — нажмите 2."
)

CONSENT_GRANT_ACK = (
    "Спасибо, согласие записано. Близкие смогут получать спокойные отчёты."
)

CONSENT_DECLINE_ACK = (
    "Хорошо, звонить не будем. Если передумаете — близкие смогут оформить "
    "согласие заново."
)

CONSENT_SILENCE_DECLINE_AFTER = 2  # empty turns on consent call → DECLINED

_GRANT_WORDS = (
    "соглас", "соглаш", "да", "можно", "разреш", "ок", "хорошо",
)
_REFUSE_WORDS = (
    "нет", "не надо", "не соглас", "отказ", "не хочу", "против",
)


def _new_consent_id():
    return "cns-" + uuid.uuid4().hex[:12]


def _proof_hash(person_id, method, script_version, proof_audio_key=None):
    material = "|".join([
        str(person_id or ""),
        str(method or ""),
        str(script_version or ""),
        str(proof_audio_key or ""),
        secrets.token_hex(8),
    ])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def grant_consent(pg, person_id, method, proof_audio_key=None,
                  script_version=CONSENT_SCRIPT_VERSION, household_id=None,
                  kind=None):
    """Insert an active consent row. Returns the new consent id.

    ``method`` is voice | dtmf | written. Legacy ``kind`` column is kept in
    sync (voice/written) for older readers.
    """
    person_id = str(person_id or "").strip()
    if not person_id:
        raise ValueError("person_id is required")
    method = str(method or "").strip().lower()
    if method not in ("voice", "dtmf", "written"):
        raise ValueError("method must be voice|dtmf|written")
    script_version = script_version or CONSENT_SCRIPT_VERSION
    kind = kind or ("written" if method == "written" else "voice")
    consent_id = _new_consent_id()
    proof_hash = _proof_hash(
        person_id, method, script_version, proof_audio_key)
    if hasattr(pg, "grant_consent"):
        pg.grant_consent(
            consent_id, person_id, method=method, kind=kind,
            proof_audio_key=proof_audio_key, proof_hash=proof_hash,
            script_version=script_version, household_id=household_id)
    else:
        raise TypeError("pg must implement grant_consent")
    if hasattr(pg, "audit"):
        pg.audit(
            "consent.grant", "system", entity="consent",
            entity_id=consent_id,
            detail={"person_id": person_id, "method": method,
                    "script_version": script_version})
    return consent_id


def revoke_consent(pg, person_id, reason=None):
    """Revoke all active consents for the person. Returns revoked count."""
    person_id = str(person_id or "").strip()
    if not person_id:
        raise ValueError("person_id is required")
    if hasattr(pg, "revoke_consent"):
        n = pg.revoke_consent(person_id, reason=reason)
    else:
        raise TypeError("pg must implement revoke_consent")
    if hasattr(pg, "audit"):
        pg.audit(
            "consent.revoke", "system", entity="person",
            entity_id=person_id,
            detail={"reason": reason or "", "revoked": n})
    return n


def has_active_consent(pg, person_id) -> bool:
    person_id = str(person_id or "").strip()
    if not person_id:
        return False
    if hasattr(pg, "has_active_consent"):
        return bool(pg.has_active_consent(person_id))
    raise TypeError("pg must implement has_active_consent")


def export_proof(pg, person_id) -> dict:
    """Export the latest consent proof bundle for the person (or empty)."""
    person_id = str(person_id or "").strip()
    if not person_id:
        return {"person_id": "", "active": False, "consents": []}
    if hasattr(pg, "export_consent_proof"):
        rows = pg.export_consent_proof(person_id) or []
    else:
        raise TypeError("pg must implement export_consent_proof")
    active = [r for r in rows if not r.get("revoked_at")]
    return {
        "person_id": person_id,
        "active": bool(active),
        "consents": rows,
        "script_version": (
            (active[0].get("script_version") if active else None)
            or CONSENT_SCRIPT_VERSION),
    }


def scheduler_may_call(pg, person_id) -> bool:
    """E5 guard stub: outbound call only with an active consent."""
    return has_active_consent(pg, person_id)


def classify_consent_reply(text=None, digit=None, empty_turns=0):
    """Classify one consent-call turn.

    Returns ``("granted"|"declined"|"pending", reply_text)``.
    Silence after ``CONSENT_SILENCE_DECLINE_AFTER`` empty turns → declined.
    """
    from core.dtmf import interpret_dtmf, DtmfEvent

    if digit is not None and str(digit).strip() != "":
        ev = interpret_dtmf(digit)
        if ev is DtmfEvent.OK:
            return "granted", CONSENT_GRANT_ACK
        if ev is DtmfEvent.HELP:
            # On consent call, digit 2 = refuse (not emergency help).
            return "declined", CONSENT_DECLINE_ACK

    low = (text or "").strip().lower()
    if low:
        if any(w in low for w in _REFUSE_WORDS):
            return "declined", CONSENT_DECLINE_ACK
        if any(w in low for w in _GRANT_WORDS):
            return "granted", CONSENT_GRANT_ACK
        # Unclear speech — keep pending, re-offer DTMF.
        return "pending", CONSENT_DTMF_SCRIPT

    if int(empty_turns or 0) >= CONSENT_SILENCE_DECLINE_AFTER:
        return "declined", CONSENT_DECLINE_ACK
    return "pending", CONSENT_DTMF_SCRIPT


def apply_consent_outcome(agent, decision, pg=None, person_id=None,
                          method="voice", proof_audio_key=None,
                          household_id=None):
    """Mutate Agent to record grant/decline; DECLINED → family status path.

    When ``pg`` + ``person_id`` are provided on grant, durable consent is
    written immediately (scheduler_may_call / may_originate depend on it).
    """
    if decision == "granted":
        agent.status = "ok"
        agent._consent_granted = True
        agent._note("согласие получено")
        agent._consent_method = method
        if pg is not None and person_id:
            try:
                cid = grant_consent(
                    pg, person_id, method=method,
                    proof_audio_key=proof_audio_key,
                    household_id=household_id)
                agent._consent_id = cid
            except Exception as e:  # noqa: BLE001
                agent._note(f"ошибка: consent persist {type(e).__name__}")
                agent.mark_technical(f"consent:{type(e).__name__}")
        return
    if decision == "declined":
        agent.status = "declined"
        agent._consent_declined = True
        agent._note("отказ от согласия")
        agent.done = True
        return
