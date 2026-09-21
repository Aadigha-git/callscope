"""CallSession orchestration with mock providers."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from apps.worker.config import WorkerConfig
from apps.worker.session import CallSession, NullMedia
from apps.worker.state import TurnState
from callscope.events.clock import CallClock
from callscope.events.models import Event
from callscope.events.writer import EventWriter
from callscope.providers.base import ProviderError, ProviderTimeout
from callscope.providers.mock import MockBrain, MockSTT, MockTTS


class FakeMono:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


async def _writer(tmp_path: Path, bucket: list[Event]) -> EventWriter:
    async def sink(events: list[Event]) -> None:
        bucket.extend(events)

    w = EventWriter(sink, spill_dir=tmp_path / "spill", flush_ms=10.0)
    await w.start()
    return w


async def _pcm() -> AsyncIterator[bytes]:
    yield b"\x00\x00" * 80


@pytest.mark.asyncio
async def test_greeting_and_turn(tmp_path: Path) -> None:
    events: list[Event] = []
    mono = FakeMono()
    clock = CallClock(monotonic=mono)
    media = NullMedia()
    writer = await _writer(tmp_path, events)
    session = CallSession(
        call_id=uuid.uuid4(),
        stt=MockSTT(transcripts=["Book me Tuesday"]),
        tts=MockTTS(ms_per_char=2.0),
        brain=MockBrain(replies=["Tuesday at three works."]),
        writer=writer,
        clock=clock,
        config=WorkerConfig(chunker_min_chars=5, greeting_text="Hello there."),
        media=media,
    )
    await session.start()
    await session.run_greeting()
    assert session.state is TurnState.LISTENING
    assert any(m.get("type") == "agent.state" for m in media.messages)
    mono.advance(0.5)
    await session.process_pcm(_pcm())
    if session.end_reason is None:
        await session.end("client_end")
    types = [e.type for e in events]
    assert "call.start" in types
    assert "stt.final" in types
    assert "brain.request" in types
    assert "tts.request" in types
    assert "call.end" in types
    assert session.end_reason == "client_end"
    assert media.frames  # greeting + reply audio


@pytest.mark.asyncio
async def test_empty_transcript(tmp_path: Path) -> None:
    events: list[Event] = []
    clock = CallClock()
    writer = await _writer(tmp_path, events)
    session = CallSession(
        call_id=uuid.uuid4(),
        stt=MockSTT(transcripts=["   "]),
        tts=MockTTS(),
        brain=MockBrain(replies=["unused"]),
        writer=writer,
        clock=clock,
        config=WorkerConfig(greeting_text=""),
        media=NullMedia(),
    )
    await session.start()
    await session.connect()
    await session.process_pcm(_pcm())
    assert session.state is TurnState.LISTENING
    await session.end("client_end")
    assert "brain.request" not in [e.type for e in events]


@pytest.mark.asyncio
async def test_asr_error(tmp_path: Path) -> None:
    events: list[Event] = []
    writer = await _writer(tmp_path, events)
    session = CallSession(
        call_id=uuid.uuid4(),
        stt=MockSTT(fail_at_call=1, fail_with=ProviderError),
        tts=MockTTS(),
        brain=MockBrain(),
        writer=writer,
        clock=CallClock(),
        config=WorkerConfig(greeting_text=""),
        media=NullMedia(),
    )
    await session.start()
    await session.connect()
    await session.process_pcm(_pcm())
    assert session.end_reason == "asr_error"
    assert session.state is TurnState.ENDED


@pytest.mark.asyncio
async def test_brain_timeout(tmp_path: Path) -> None:
    events: list[Event] = []
    writer = await _writer(tmp_path, events)
    session = CallSession(
        call_id=uuid.uuid4(),
        stt=MockSTT(transcripts=["hi"]),
        tts=MockTTS(),
        brain=MockBrain(fail_at_call=1, fail_with=ProviderTimeout),
        writer=writer,
        clock=CallClock(),
        config=WorkerConfig(greeting_text=""),
        media=NullMedia(),
    )
    await session.start()
    await session.connect()
    await session.process_pcm(_pcm())
    assert session.end_reason == "brain_timeout"


@pytest.mark.asyncio
async def test_tts_error(tmp_path: Path) -> None:
    class BoomTTS:
        sample_rate = 24_000

        async def stream(self, text: str, *, voice: str, speed: float):
            _ = (text, voice, speed)
            raise ProviderError("tts boom")
            yield b""  # pragma: no cover

    events: list[Event] = []
    writer = await _writer(tmp_path, events)
    session = CallSession(
        call_id=uuid.uuid4(),
        stt=MockSTT(transcripts=["hi"]),
        tts=BoomTTS(),
        brain=MockBrain(replies=["Hello world."]),
        writer=writer,
        clock=CallClock(),
        config=WorkerConfig(greeting_text="", chunker_min_chars=5),
        media=NullMedia(),
    )
    await session.start()
    await session.connect()
    await session.process_pcm(_pcm())
    assert session.end_reason == "tts_error"


@pytest.mark.asyncio
async def test_response_latency_metric(tmp_path: Path) -> None:
    mono = FakeMono()

    async def advance_sleep(seconds: float) -> None:
        mono.advance(seconds)

    clock = CallClock(monotonic=mono)
    events: list[Event] = []
    writer = await _writer(tmp_path, events)
    session = CallSession(
        call_id=uuid.uuid4(),
        stt=MockSTT(transcripts=["ping"], latency_s=0.01, sleep=advance_sleep),
        tts=MockTTS(ms_per_char=1.0, latency_s=0.05, sleep=advance_sleep),
        brain=MockBrain(replies=["pong."], first_token_delay_s=0.02, sleep=advance_sleep),
        writer=writer,
        clock=clock,
        config=WorkerConfig(greeting_text="", chunker_min_chars=1),
        media=NullMedia(),
    )
    await session.start()
    await session.connect()
    await session.process_pcm(_pcm())
    if session.end_reason is None:
        await session.end("client_end")
    by_type = {e.type: e.t_ms for e in events}
    assert "stt.final" in by_type
    assert "tts.first_audio" in by_type
    assert by_type["stt.final"] < by_type["tts.first_audio"]


@pytest.mark.asyncio
async def test_interrupt_hook(tmp_path: Path) -> None:
    from apps.worker.state import TurnEvent

    events: list[Event] = []
    writer = await _writer(tmp_path, events)
    media = NullMedia()
    session = CallSession(
        call_id=uuid.uuid4(),
        stt=MockSTT(transcripts=["hi"]),
        tts=MockTTS(),
        brain=MockBrain(replies=["Long reply."]),
        writer=writer,
        clock=CallClock(),
        config=WorkerConfig(greeting_text=""),
        media=media,
    )
    await session.start()
    await session.connect()
    session.sm.handle(TurnEvent.ENDPOINT_FINAL)
    session._spoken_prefix = "Long"
    await session.interrupt()
    assert session.state is TurnState.LISTENING
    assert session._interruption_note is not None
    await session.end("client_end")
    assert any(e.type == "barge_in.applied" for e in events)
