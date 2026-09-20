"""Unit tests for EventWriter: batching, spill/replay, dedupe, queue policy."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from prometheus_client import REGISTRY

from callscope.events.models import Event, EventSource
from callscope.events.writer import EventWriter

pytestmark = pytest.mark.unit


def _event(call_id: UUID | None = None, event_id: UUID | None = None, t_ms: int = 0) -> Event:
    return Event(
        event_id=event_id or uuid4(),
        call_id=call_id or uuid4(),
        t_ms=t_ms,
        source=EventSource.WORKER,
        type="stt.final",
        payload={"text": "x"},
    )


class RecordingSink:
    def __init__(self, *, fail_times: int = 0) -> None:
        self.batches: list[list[Event]] = []
        self._fail_times = fail_times
        self._calls = 0

    async def __call__(self, batch: list[Event]) -> None:
        self._calls += 1
        if self._calls <= self._fail_times:
            raise RuntimeError("sink down")
        self.batches.append(batch)


@pytest.mark.asyncio
async def test_batching_by_size(tmp_path: Path) -> None:
    sink = RecordingSink()
    writer = EventWriter(sink, spill_dir=tmp_path, batch_size=3, flush_ms=5_000, backoff_s=0.0)
    await writer.start()
    call_id = uuid4()
    for i in range(3):
        writer.emit(_event(call_id=call_id, t_ms=i))
    await asyncio.sleep(0.05)
    assert len(sink.batches) == 1
    assert [e.t_ms for e in sink.batches[0]] == [0, 1, 2]
    await writer.aclose()


@pytest.mark.asyncio
async def test_batching_by_time(tmp_path: Path) -> None:
    sink = RecordingSink()
    writer = EventWriter(sink, spill_dir=tmp_path, batch_size=100, flush_ms=30, backoff_s=0.0)
    await writer.start()
    writer.emit(_event(t_ms=1))
    writer.emit(_event(t_ms=2))
    await asyncio.sleep(0.08)
    assert len(sink.batches) == 1
    assert [e.t_ms for e in sink.batches[0]] == [1, 2]
    await writer.aclose()


@pytest.mark.asyncio
async def test_ordering_preserved(tmp_path: Path) -> None:
    sink = RecordingSink()
    writer = EventWriter(sink, spill_dir=tmp_path, batch_size=10, flush_ms=20, backoff_s=0.0)
    await writer.start()
    for i in range(5):
        writer.emit(_event(t_ms=i))
    await writer.aclose()
    flat = [e.t_ms for batch in sink.batches for e in batch]
    assert flat == [0, 1, 2, 3, 4]


@pytest.mark.asyncio
async def test_dedupe_by_event_id(tmp_path: Path) -> None:
    sink = RecordingSink()
    writer = EventWriter(sink, spill_dir=tmp_path, batch_size=10, flush_ms=20, backoff_s=0.0)
    await writer.start()
    eid = uuid4()
    writer.emit(_event(event_id=eid, t_ms=1))
    writer.emit(_event(event_id=eid, t_ms=2))
    await writer.aclose()
    flat = [e for batch in sink.batches for e in batch]
    assert len(flat) == 1
    assert flat[0].t_ms == 1
    dropped = REGISTRY.get_sample_value("callscope_events_dropped_total", {"reason": "dedupe"})
    assert dropped is not None and dropped >= 1


class ControllableSink:
    def __init__(self) -> None:
        self.up = False
        self.batches: list[list[Event]] = []

    async def __call__(self, batch: list[Event]) -> None:
        if not self.up:
            raise RuntimeError("sink down")
        self.batches.append(batch)


@pytest.mark.asyncio
async def test_sink_failure_spills_then_replays(tmp_path: Path) -> None:
    sink = ControllableSink()
    writer = EventWriter(
        sink,
        spill_dir=tmp_path,
        batch_size=2,
        flush_ms=5_000,
        max_retries=2,
        backoff_s=0.0,
    )
    await writer.start()
    writer.emit(_event(t_ms=1))
    writer.emit(_event(t_ms=2))
    await asyncio.sleep(0.05)
    spill = writer._debug_spill_path()
    assert spill.exists() and spill.stat().st_size > 0
    assert sink.batches == []

    sink.up = True
    writer.emit(_event(t_ms=3))
    writer.emit(_event(t_ms=4))
    await asyncio.sleep(0.05)
    await writer.aclose()

    flat = [e.t_ms for batch in sink.batches for e in batch]
    assert set(flat) == {1, 2, 3, 4}
    assert spill.stat().st_size == 0


@pytest.mark.asyncio
async def test_queue_full_drops_oldest(tmp_path: Path) -> None:
    sink = RecordingSink()
    # Keep flusher from draining: huge flush_ms and never fill batch.
    writer = EventWriter(
        sink,
        spill_dir=tmp_path,
        batch_size=100,
        flush_ms=60_000,
        queue_size=2,
        backoff_s=0.0,
    )
    await writer.start()
    writer.emit(_event(t_ms=1))
    writer.emit(_event(t_ms=2))
    writer.emit(_event(t_ms=3))  # drops oldest (1)
    assert writer._debug_queue_size() == 2
    before = (
        REGISTRY.get_sample_value("callscope_events_dropped_total", {"reason": "queue_full"}) or 0.0
    )
    assert before >= 1.0
    await writer.aclose()
