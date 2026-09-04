"""Per-call variety rotation and dedupe guards."""
from __future__ import annotations

import re
from collections import deque
from typing import Deque, Iterable, List, Sequence, Tuple

from conversation_system.agenda.topics import TOPIC_KEYS

_REPEAT_STOP = frozenset(
    "и в а на с по к у о из за от для что как не да нет это я вы "
    "она он они мы вы".split()
)


def _normalize_reply(text: str) -> str:
    low = re.sub(r"[^\w\s]", " ", (text or "").lower())
    return " ".join(w for w in low.split() if w and w not in _REPEAT_STOP)


def reply_too_similar(a: str, b: str, *, threshold: float = 0.62) -> bool:
    """True when two spoken replies are near-duplicates."""
    if not a or not b:
        return False
    na, nb = _normalize_reply(a), _normalize_reply(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / max(len(ta), len(tb))
    return overlap >= threshold


def same_topic_question(a: str, b: str, topic: str = "") -> bool:
    if not a or not b or "?" not in a or "?" not in b:
        return False
    if reply_too_similar(a, b, threshold=0.45):
        return True
    keys = TOPIC_KEYS.get((topic or "").strip().lower(), ())
    la, lb = a.lower(), b.lower()
    if keys:
        a_keys = {k for k in keys if k in la}
        b_keys = {k for k in keys if k in lb}
        if a_keys and b_keys and a_keys & b_keys:
            return True
    return False


class VarietyEngine:
    """Per-call rotation — no cross-call pollution."""

    def __init__(self, *, per_call_max: int = 20) -> None:
        self._recent: Deque[str] = deque(maxlen=per_call_max)
        self._asked: Deque[str] = deque(maxlen=per_call_max)
        self._indices: dict[str, int] = {}

    def remember(self, text: str) -> None:
        t = (text or "").strip()
        if not t:
            return
        self._recent.append(t)

    def remember_question(self, text: str) -> None:
        t = (text or "").strip()
        if t and "?" in t:
            self._asked.append(t)

    def pick_from_pool(
        self,
        pool: Sequence[str],
        *,
        pool_key: str = "",
        avoid: Sequence[str] = (),
    ) -> str:
        if not pool:
            return ""
        key = pool_key or str(id(pool))
        idx = self._indices.get(key, 0)
        avoid_set = {a.strip().lower() for a in avoid if a}
        refs = list(self._recent) + list(self._asked)
        for offset in range(len(pool)):
            candidate = pool[(idx + offset) % len(pool)]
            low = candidate.strip().lower()
            if low in avoid_set:
                continue
            if self._too_close(candidate, refs):
                continue
            self._indices[key] = (idx + offset + 1) % len(pool)
            return candidate
        self._indices[key] = (idx + 1) % len(pool)
        return pool[idx % len(pool)]

    def _too_close(self, candidate: str, refs: Iterable[str]) -> bool:
        for ref in refs:
            if not ref:
                continue
            if candidate.strip() == ref.strip():
                return True
            if reply_too_similar(candidate, ref):
                return True
        return False

    def recent_snapshot(self) -> Tuple[str, ...]:
        return tuple(self._recent)


class DedupeGuard:
    """Reject or rotate replies that feel like repeats."""

    def __init__(self, variety: VarietyEngine) -> None:
        self._variety = variety

    def dedupe(
        self,
        candidate: str,
        *,
        last_reply: str = "",
        last_question: str = "",
        topic: str = "",
        pool: Sequence[str] = (),
        pool_key: str = "",
    ) -> str:
        refs: List[str] = []
        if last_reply:
            refs.append(last_reply)
        if last_question:
            refs.append(last_question)
        refs.extend(self._variety.recent_snapshot())
        if candidate and not self._is_repeat(candidate, refs, topic):
            return candidate
        if pool:
            alt = self._variety.pick_from_pool(
                pool, pool_key=pool_key, avoid=(candidate,))
            if alt and not self._is_repeat(alt, refs, topic):
                return alt
        return candidate

    def _is_repeat(
        self,
        candidate: str,
        refs: Sequence[str],
        topic: str,
    ) -> bool:
        for ref in refs:
            if not ref:
                continue
            if candidate.strip() == ref.strip():
                return True
            if reply_too_similar(candidate, ref):
                if not topic or same_topic_question(candidate, ref, topic):
                    return True
            if topic and same_topic_question(candidate, ref, topic):
                return True
        return False
