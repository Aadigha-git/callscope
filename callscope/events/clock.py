"""Monotonic call-relative clock (ADR-006: worker is latency source of truth)."""

from __future__ import annotations

import time
from collections.abc import Callable


class CallClock:
    """Call-scoped clock: ``t_ms()`` is milliseconds since ``start()`` via monotonic time."""

    def __init__(self, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._monotonic = monotonic
        self._t0: float | None = None

    def start(self) -> None:
        self._t0 = self._monotonic()

    @property
    def started(self) -> bool:
        return self._t0 is not None

    def t_ms(self) -> int:
        if self._t0 is None:
            raise RuntimeError("CallClock.start() must be called before t_ms()")
        return int((self._monotonic() - self._t0) * 1000.0)
