"""Small per-process login throttle for single-instance deployments."""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict

WINDOW_SECONDS = 15 * 60
MAX_FAILURES_PER_ADDRESS = 60
MAX_FAILURES_PER_ACCOUNT_AND_ADDRESS = 10
MAX_TRACKED_KEYS = 20_000


class LoginRateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failures: OrderedDict[str, tuple[float, int]] = OrderedDict()

    def retry_after(self, address: str, username: str) -> int:
        now = time.monotonic()
        keys = (
            (f"address:{address}", MAX_FAILURES_PER_ADDRESS),
            (f"account:{address}:{username}", MAX_FAILURES_PER_ACCOUNT_AND_ADDRESS),
        )
        with self._lock:
            self._prune(now)
            waits = []
            for key, limit in keys:
                bucket = self._failures.get(key)
                if bucket and bucket[1] >= limit:
                    waits.append(max(1, math.ceil(WINDOW_SECONDS - (now - bucket[0]))))
            return max(waits, default=0)

    def record_failure(self, address: str, username: str) -> None:
        now = time.monotonic()
        keys = (f"address:{address}", f"account:{address}:{username}")
        with self._lock:
            self._prune(now)
            for key in keys:
                bucket = self._failures.get(key)
                if bucket is None:
                    self._failures[key] = (now, 1)
                elif now - bucket[0] >= WINDOW_SECONDS:
                    self._failures[key] = (now, 1)
                else:
                    self._failures[key] = (bucket[0], bucket[1] + 1)
                self._failures.move_to_end(key)
            while len(self._failures) > MAX_TRACKED_KEYS:
                self._failures.popitem(last=False)

    def record_success(self, address: str, username: str) -> None:
        key = f"account:{address}:{username}"
        with self._lock:
            self._failures.pop(key, None)

    def _prune(self, now: float) -> None:
        expired = [
            key for key, (started_at, _) in self._failures.items()
            if now - started_at >= WINDOW_SECONDS
        ]
        for key in expired:
            self._failures.pop(key, None)


login_rate_limiter = LoginRateLimiter()
