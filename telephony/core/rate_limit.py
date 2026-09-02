"""Thread-safe bounded token-bucket limiter for single-node HTTP ingress.

This is an application-layer guard, not a replacement for a distributed API
gateway. It prevents one client from exhausting the stdlib ThreadingHTTPServer
and keeps its own memory bounded under high-cardinality hostile input.
"""

from collections import OrderedDict
import math
import threading
import time


class TokenBucketLimiter:
    def __init__(self, max_entries=10000, clock=time.monotonic):
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self.max_entries = max_entries
        self._clock = clock
        self._lock = threading.Lock()
        self._buckets = OrderedDict()

    def allow(self, key, capacity, window_seconds=60):
        """Consume one token and return ``(allowed, retry_after_seconds)``."""
        capacity = int(capacity)
        window_seconds = float(window_seconds)
        if capacity < 1 or window_seconds <= 0:
            raise ValueError("capacity and window_seconds must be positive")
        now = self._clock()
        refill_per_second = capacity / window_seconds
        with self._lock:
            previous = self._buckets.pop(key, None)
            if previous is None:
                tokens = float(capacity)
                updated_at = now
            else:
                tokens, updated_at = previous
                elapsed = max(0.0, now - updated_at)
                tokens = min(float(capacity),
                             tokens + elapsed * refill_per_second)

            allowed = tokens >= 1.0
            if allowed:
                tokens -= 1.0
                retry_after = 0
            else:
                retry_after = max(
                    1, math.ceil((1.0 - tokens) / refill_per_second))

            self._buckets[key] = (tokens, now)
            while len(self._buckets) > self.max_entries:
                self._buckets.popitem(last=False)
            return allowed, retry_after
