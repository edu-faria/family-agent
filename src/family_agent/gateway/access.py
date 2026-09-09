"""Identity allowlist + a simple sliding-window rate limiter.

The allowlist is the hard gate: a Telegram user id not in it never reaches the
agent, the router, or any model call.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque


class Allowlist:
    def __init__(self, ids: frozenset[int]) -> None:
        self._ids = ids

    def permits(self, telegram_user_id: int) -> bool:
        return telegram_user_id in self._ids


class RateLimiter:
    """Per-user: at most `limit` events per `window_seconds`."""

    def __init__(self, limit: int = 20, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window = window_seconds
        self._events: dict[int, deque[float]] = defaultdict(deque)

    def allow(self, key: int) -> bool:
        now = time.monotonic()
        q = self._events[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True
