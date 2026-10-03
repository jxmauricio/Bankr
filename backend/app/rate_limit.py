"""In-process sliding-window rate limiting.

Deliberately simple: state lives in this process's memory, which is correct
for the single-instance beta deploy (see render.yaml). Move to a shared store
(Redis) before running more than one instance.
"""

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Depends, HTTPException, Request, status

from app.auth import get_current_user
from app.db.models import User


class RateLimiter:
    def __init__(self, max_calls: int, window_seconds: float) -> None:
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._calls: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def hit(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            calls = self._calls[key]
            while calls and now - calls[0] > self.window_seconds:
                calls.popleft()
            if len(calls) >= self.max_calls:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests, try again shortly")
            calls.append(now)

    def reset(self) -> None:
        with self._lock:
            self._calls.clear()


# Password guessing / signup spam, keyed by client IP.
auth_limiter = RateLimiter(max_calls=10, window_seconds=60)
# LLM spend, keyed by user.
chat_limiter = RateLimiter(max_calls=30, window_seconds=60 * 60)


def limit_auth_by_ip(request: Request) -> None:
    auth_limiter.hit(request.client.host if request.client else "unknown")


def limit_chat_by_user(user: User = Depends(get_current_user)) -> None:
    chat_limiter.hit(str(user.id))
