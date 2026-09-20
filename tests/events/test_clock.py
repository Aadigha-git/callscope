"""Unit tests for CallClock."""

from __future__ import annotations

import pytest

from callscope.events.clock import CallClock

pytestmark = pytest.mark.unit


def test_t_ms_requires_start() -> None:
    clock = CallClock()
    with pytest.raises(RuntimeError, match="start"):
        clock.t_ms()


def test_t_ms_uses_injected_monotonic() -> None:
    ticks = iter([100.0, 100.5, 101.25])

    def mono() -> float:
        return next(ticks)

    clock = CallClock(monotonic=mono)
    clock.start()
    assert clock.t_ms() == 500
    assert clock.t_ms() == 1250
