"""Local session concurrency limiter (ADR-010 — no public per-IP abuse limits)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from uuid import UUID


class SessionCapExceeded(RuntimeError):
    """Raised when concurrent active sessions would exceed the local cap."""


@dataclass
class SessionCapLimiter:
    """In-process concurrent session cap (stretch = 2)."""

    max_concurrent: int = 2
    _active: set[UUID] = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._active)

    def try_acquire(self, call_id: UUID) -> None:
        with self._lock:
            if call_id in self._active:
                return
            if len(self._active) >= self.max_concurrent:
                raise SessionCapExceeded(f"max concurrent sessions ({self.max_concurrent}) reached")
            self._active.add(call_id)

    def release(self, call_id: UUID) -> None:
        with self._lock:
            self._active.discard(call_id)

    def reset(self) -> None:
        with self._lock:
            self._active.clear()
