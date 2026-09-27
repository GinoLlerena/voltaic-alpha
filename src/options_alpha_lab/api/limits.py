"""A per-client rate limit for the public API.

The API was built to listen on loopback only, with no authentication, because
nothing off the host could reach it. Serving the React UI means publishing it
(owner decision, 26 September 2026): same origin as the UI, read-only, and
rate-limited. The records it returns are the ones the public dashboard already
shows, so the risk being managed is not disclosure but load: every request
reaches PostgreSQL on a small instance that also runs the worker.

A token bucket per client address. The defaults admit a person comfortably -
a page subscribes to up to about ten resources refreshed every 15 seconds,
roughly 0.7 requests a second per tab plus a burst of about ten on each load -
while stopping a scraper from monopolising the database.

Only `/api/` is limited. Static assets never touch the database.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass

#: Requests a client may make at once, e.g. several tabs loading together.
DEFAULT_BURST = 60
#: Sustained requests per second per client once the burst is spent.
DEFAULT_RATE = 3.0
#: Buckets idle this long are dropped, so the table cannot grow without bound.
IDLE_SECONDS = 600


@dataclass
class _Bucket:
    tokens: float
    updated: float


class RateLimiter:
    def __init__(
        self,
        *,
        burst: int = DEFAULT_BURST,
        rate: float = DEFAULT_RATE,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.burst, self.rate, self.clock = burst, rate, clock
        self._buckets: dict[str, _Bucket] = {}
        self._last_sweep = clock()

    def check(self, client: str) -> float:
        """Admit one request: 0.0 when allowed, else seconds until one would be."""
        now = self.clock()
        self._sweep(now)
        bucket = self._buckets.get(client)
        if bucket is None:
            bucket = self._buckets[client] = _Bucket(tokens=float(self.burst), updated=now)
        bucket.tokens = min(self.burst, bucket.tokens + (now - bucket.updated) * self.rate)
        bucket.updated = now
        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
            return 0.0
        return (1.0 - bucket.tokens) / self.rate

    def _sweep(self, now: float) -> None:
        if now - self._last_sweep < IDLE_SECONDS:
            return
        self._last_sweep = now
        stale = [k for k, b in self._buckets.items() if now - b.updated > IDLE_SECONDS]
        for key in stale:
            del self._buckets[key]


def retry_after_header(seconds: float) -> str:
    """Retry-After is whole seconds, and never 0 for a refused request."""
    return str(max(1, math.ceil(seconds)))
