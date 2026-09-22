"""T-M6-01 local concurrency / latency load harness tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.api.ratelimit import SessionCapExceeded, SessionCapLimiter
from callscope.eval.load_test import (
    DEFAULT_SESSION_CAP,
    find_knee,
    probe_session_cap,
    run_level,
    run_load,
    write_report,
)

pytestmark = pytest.mark.unit


def test_session_cap_probe_blocks_overflow() -> None:
    probe = probe_session_cap(2)
    assert probe.acquired == 2
    assert probe.third_blocked is True
    assert probe.error is not None


def test_session_cap_limiter_unit() -> None:
    from uuid import uuid4

    lim = SessionCapLimiter(max_concurrent=DEFAULT_SESSION_CAP)
    a, b = uuid4(), uuid4()
    lim.try_acquire(a)
    lim.try_acquire(b)
    with pytest.raises(SessionCapExceeded):
        lim.try_acquire(uuid4())
    lim.release(a)
    lim.try_acquire(uuid4())


@pytest.mark.asyncio
async def test_run_level_concurrency_one() -> None:
    lv = await run_level(1, reps=2, seed=7, wall_clock=False)
    assert lv.concurrency == 1
    assert lv.n_calls == 2
    assert lv.p50_ms > 0
    assert lv.meets_nfr01_mock is True  # synthetic ~500 ms


@pytest.mark.asyncio
async def test_run_load_writes_report(tmp_path: Path) -> None:
    report = await run_load(levels=(1, 2), reps=2, seed=3)
    assert report.public_concurrency_cap == 2
    assert report.cap_probe.third_blocked is True
    assert len(report.levels) == 2
    paths = write_report(report, tmp_path)
    assert paths["raw"].is_file()
    assert paths["readme"].is_file()
    text = paths["readme"].read_text(encoding="utf-8")
    assert "T-M6-01" in text
    assert "Concurrency" in text


def test_find_knee_none_when_flat() -> None:
    from callscope.eval.load_test import LevelResult

    levels = [
        LevelResult(concurrency=1, n_calls=3, reps=3, p50_ms=500, p95_ms=500),
        LevelResult(concurrency=2, n_calls=6, reps=3, p50_ms=500, p95_ms=510),
    ]
    assert find_knee(levels) is None


def test_find_knee_detects_jump() -> None:
    from callscope.eval.load_test import LevelResult

    levels = [
        LevelResult(concurrency=1, n_calls=3, reps=3, p50_ms=500, p95_ms=500),
        LevelResult(concurrency=2, n_calls=6, reps=3, p50_ms=800, p95_ms=900),
    ]
    assert find_knee(levels) == 2
