"""Unit tests for provider instrumentation."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from prometheus_client import REGISTRY

from callscope.events.clock import CallClock
from callscope.events.instrument import instrument
from callscope.events.models import Event
from callscope.events.writer import EventWriter

pytestmark = pytest.mark.unit


class RecordingSink:
    def __init__(self) -> None:
        self.batches: list[list[Event]] = []

    async def __call__(self, batch: list[Event]) -> None:
        self.batches.append(batch)


@pytest.mark.asyncio
async def test_instrument_streaming_brain_emits_first_token(tmp_path: Path) -> None:
    sink = RecordingSink()
    writer = EventWriter(sink, spill_dir=tmp_path, batch_size=10, flush_ms=20, backoff_s=0.0)
    await writer.start()

    ticks = iter([10.0, 10.0, 10.1, 10.2, 10.3])
    clock = CallClock(monotonic=lambda: next(ticks))
    clock.start()
    call_id = uuid4()

    @instrument("brain", writer=writer, clock=clock, call_id=call_id)
    async def stream_tokens() -> object:
        await asyncio.sleep(0)
        yield "hello"
        await asyncio.sleep(0)
        yield " world"

    out: list[str] = []
    async for chunk in stream_tokens():
        out.append(chunk)
    await writer.aclose()

    assert out == ["hello", " world"]
    types = [e.type for batch in sink.batches for e in batch]
    assert types == ["brain.request", "brain.first_token", "brain.done"]
    first = REGISTRY.get_sample_value(
        "callscope_stage_latency_seconds_count", {"stage": "brain_first_byte"}
    )
    total = REGISTRY.get_sample_value(
        "callscope_stage_latency_seconds_count", {"stage": "brain_total"}
    )
    assert first is not None and first >= 1
    assert total is not None and total >= 1


@pytest.mark.asyncio
async def test_instrument_context_manager(tmp_path: Path) -> None:
    sink = RecordingSink()
    writer = EventWriter(sink, spill_dir=tmp_path, batch_size=10, flush_ms=20, backoff_s=0.0)
    await writer.start()
    clock = CallClock(monotonic=lambda: 1.0)
    clock.start()
    call_id = uuid4()

    async with instrument("stt", emitter=writer, clock=clock, call_id=call_id):
        await asyncio.sleep(0)

    await writer.aclose()
    types = [e.type for batch in sink.batches for e in batch]
    assert types == ["stt.request", "stt.done"]


@pytest.mark.asyncio
async def test_instrument_error_emits_provider_error(tmp_path: Path) -> None:
    sink = RecordingSink()
    writer = EventWriter(sink, spill_dir=tmp_path, batch_size=10, flush_ms=20, backoff_s=0.0)
    await writer.start()
    clock = CallClock(monotonic=lambda: 1.0)
    clock.start()
    call_id = uuid4()

    @instrument("tts", writer=writer, clock=clock, call_id=call_id)
    async def boom() -> None:
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError, match="nope"):
        await boom()
    await writer.aclose()
    types = [e.type for batch in sink.batches for e in batch]
    assert "tts.request" in types
    assert "provider.error" in types
