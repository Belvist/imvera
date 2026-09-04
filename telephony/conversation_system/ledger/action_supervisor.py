"""Action Supervisor scaffold — no unverified delivery claims (Phase 6)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Tuple

_UNVERIFIED_DELIVERY_RE = re.compile(
    r"(уже\s+)?(передал\w*|оповестил\w*|сообщил\w*\s+родн|"
    r"родн\w+\s+уже\s+знают|отправил\w*\s+родн|"
    r"уже\s+видят|близк\w+\s+(?:уже\s+)?видят|оповещ\w*\s+близк)",
    re.IGNORECASE,
)

_SAFE_RECORD_RE = re.compile(
    r"(записал\w*|сохран\w*|близкие\s+увидят|родные\s+увидят)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ActionCheck:
    allowed: bool
    reasons: Tuple[str, ...] = ()


class ActionSupervisor:
    """Blocks spoken claims of completed family actions without proof."""

    def __init__(self) -> None:
        self._succeeded: set[str] = set()

    def mark_succeeded(self, action_id: str) -> None:
        aid = (action_id or "").strip()
        if aid:
            self._succeeded.add(aid)

    def check_spoken(self, text: str, *, action_id: str = "notify_family") -> ActionCheck:
        t = (text or "").strip()
        if not t:
            return ActionCheck(allowed=True)
        if _UNVERIFIED_DELIVERY_RE.search(t):
            if action_id not in self._succeeded and not _SAFE_RECORD_RE.search(t):
                return ActionCheck(
                    allowed=False,
                    reasons=("unverified_family_delivery_claim",),
                )
        return ActionCheck(allowed=True)

    def sanitize(self, text: str, *, fallback: str = "") -> str:
        check = self.check_spoken(text)
        if check.allowed:
            return text
        return fallback or "Я всё записала, близкие увидят."


_DEFAULT_SUPERVISOR = ActionSupervisor()


def sanitize_delivery_claim(
    text: str,
    *,
    fallback: str = "",
    supervisor: ActionSupervisor | None = None,
) -> str:
    """Block unverified family-delivery claims before TTS (shared orchestrator path)."""
    sup = supervisor or _DEFAULT_SUPERVISOR
    return sup.sanitize(text, fallback=fallback)
