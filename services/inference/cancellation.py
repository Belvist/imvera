"""Active cancellation survives bounded, expiring early/late cancel messages."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field

from services.inference.common import QueueFullError


class DuplicateRequestError(ValueError):
    """Request identity belongs to an unsettled producer or consumer."""


@dataclass
class CancellationLease:
    request_id: str
    generation_id: str
    cancelled: threading.Event = field(default_factory=threading.Event)


class CancellationRegistry:
    def __init__(
        self,
        *,
        max_tombstones: int = 2048,
        max_active_requests: int = 32,
        ttl_s: float = 120,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_tombstones < 1 or max_active_requests < 1 or ttl_s <= 0:
            raise ValueError("cancellation limits must be positive")
        self._max_tombstones = max_tombstones
        self._max_active_requests = max_active_requests
        self._ttl_s = ttl_s
        self._clock = clock
        self._lock = threading.Lock()
        self._active: dict[str, CancellationLease] = {}
        self._tombstones: OrderedDict[tuple[str, str], float] = OrderedDict()

    def _prune(self) -> None:
        now = self._clock()
        while self._tombstones:
            key = next(iter(self._tombstones))
            if self._tombstones[key] > now:
                break
            self._tombstones.popitem(last=False)

    def _remember(self, kind: str, value: str) -> None:
        key = (kind, value)
        self._tombstones.pop(key, None)
        self._tombstones[key] = self._clock() + self._ttl_s
        while len(self._tombstones) > self._max_tombstones:
            self._tombstones.popitem(last=False)

    def register(self, request_id: str, generation_id: str) -> CancellationLease:
        with self._lock:
            self._prune()
            if request_id in self._active:
                raise DuplicateRequestError("request_id already active")
            if len(self._active) >= self._max_active_requests:
                raise QueueFullError("inference HTTP streams full")
            lease = CancellationLease(request_id, generation_id)
            if ("request", request_id) in self._tombstones or (
                "generation",
                generation_id,
            ) in self._tombstones:
                lease.cancelled.set()
            self._active[request_id] = lease
            return lease

    def release(self, lease: CancellationLease) -> None:
        with self._lock:
            if self._active.get(lease.request_id) is lease:
                self._active.pop(lease.request_id)

    def is_cancelled(self, request_id: str, generation_id: str) -> bool:
        with self._lock:
            self._prune()
            lease = self._active.get(request_id)
            return bool(
                (lease and lease.cancelled.is_set())
                or ("request", request_id) in self._tombstones
                or ("generation", generation_id) in self._tombstones
            )

    def cancel(self, *, request_id: str | None = None, generation_id: str | None = None) -> None:
        with self._lock:
            self._prune()
            for lease in self._active.values():
                if lease.request_id == request_id or lease.generation_id == generation_id:
                    lease.cancelled.set()
            if request_id is not None:
                self._remember("request", request_id)
            if generation_id is not None:
                self._remember("generation", generation_id)

    def cancel_all_active(self) -> None:
        with self._lock:
            for lease in self._active.values():
                lease.cancelled.set()

    def stats(self) -> dict[str, int]:
        with self._lock:
            self._prune()
            return {"active": len(self._active), "tombstones": len(self._tombstones)}
