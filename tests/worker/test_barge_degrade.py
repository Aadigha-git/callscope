"""Barge-in, filler, and degradation integration against CallSession."""

from __future__ import annotations

import asyncio
import math
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from apps.worker.config import WorkerConfig
from apps.worker.degrade import DegradeAction, FailureKind
from apps.worker.session import CallSession, NullMedia
from apps.worker.state import TurnEvent, TurnState
from callscope.events.clock import CallClock
from callscope.events.models import Event
from callscope.events.writer import EventWriter
from callscope.providers.base import BrainDelta, ProviderError, ProviderTimeout
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

    w = EventWriter(sink, spill_dir=tmp_path / "spill", flush_ms=5.0)
    await w.start()
    return w


async def _pcm() -> AsyncIterator[bytes]:
    yield b"\x00\x00" * 80


@pytest.mark.asyncio
async def test_barge_in_stop_latency_p95(tmp_path: Path) -> None:
    """Scripted barge-in: worker-side stop latency p95 ≤ 250 ms (fake clock)."""
    latencies: list[float] = []
    for _ in range(20):
        mono = FakeMono()

        async def sleep(seconds: float, m: FakeMono = mono) -> None:
            m.advance(seconds)

        events: list[Event] = []
        writer = await _writer(tmp_path / str(uuid.uuid4()), events)
        session = CallSession(
            call_id=uuid.uuid4(),
            stt=MockSTT(transcripts=["hi"]),
            tts=MockTTS(ms_per_char=1.0),
            brain=MockBrain(replies=["Long sentence that keeps going."]),
            writer=writer,
            clock=CallClock(monotonic=mono),
            config=WorkerConfig(
                greeting_text="",
                barge_in_min_duration_ms=250,
                barge_in_grace_ms_after_playback_start=0,
            ),
            media=NullMedia(),
            sleep=sleep,
        )
        await session.start()
        await session.connect()
        session.sm.handle(TurnEvent.ENDPOINT_FINAL)
        session._active_turn_id = uuid.uuid4()
        session._spoken_prefix = "Long sentence"
        mono.advance(0.5)
        session.gate.mark_playback_start(session._clock.t_ms())
        # Sustained speech samples
        onset = session._clock.t_ms()
        session.gate.observe(t_ms=onset, speaking=True, agent_active=True)
        mid = onset + 260
        mono.t = 100.0 + mid / 1000.0
        sample = session.gate.observe(t_ms=mid, speaking=True, agent_active=True)
        assert sample.should_interrupt
        session._barge_speech_onset_ms = onset
        clock_mono = mono

        async def cancel_brain(turn_id: str, m: FakeMono = clock_mono) -> None:
            _ = turn_id
            m.advance(0.02)

        session._brain.cancel = cancel_brain  # type: ignore[method-assign]
        await session.interrupt(speech_ms=sample.speech_ms)
        await session.end("client_end")
        applied = next(e for e in events if e.type == "barge_in.applied")
        latencies.append(float(applied.payload["stop_latency_ms"]))

    latencies.sort()
    p95 = latencies[math.ceil(0.95 * len(latencies)) - 1]
    assert p95 <= 250.0


@pytest.mark.asyncio
async def test_false_trigger_short_burst(tmp_path: Path) -> None:
    mono = FakeMono()
    events: list[Event] = []
    writer = await _writer(tmp_path, events)
    session = CallSession(
        call_id=uuid.uuid4(),
        stt=MockSTT(),
        tts=MockTTS(),
        brain=MockBrain(),
        writer=writer,
        clock=CallClock(monotonic=mono),
        config=WorkerConfig(greeting_text="", barge_in_grace_ms_after_playback_start=0),
        media=NullMedia(),
    )
    await session.start()
    await session.connect()
    session.sm.handle(TurnEvent.ENDPOINT_FINAL)
    session.sm.handle(TurnEvent.FIRST_AUDIO)
    session.gate.mark_playback_start(session._clock.t_ms())
    applied = await session.observe_caller_speech(speaking=True)
    assert not applied  # below min duration
    await session.end("client_end")
    assert not any(e.type == "barge_in.applied" for e in events)


@pytest.mark.asyncio
async def test_filler_after_delay(tmp_path: Path) -> None:
    hang = asyncio.Event()

    class HangBrain:
        async def stream_reply(self, messages, *, call_id: str, turn_id: str):
            _ = (messages, call_id, turn_id)
            await hang.wait()
            yield BrainDelta(kind="done")

        async def cancel(self, turn_id: str) -> None:
            _ = turn_id
            hang.set()

    events: list[Event] = []
    writer = await _writer(tmp_path, events)
    session = CallSession(
        call_id=uuid.uuid4(),
        stt=MockSTT(transcripts=["hi"]),
        tts=MockTTS(ms_per_char=1.0),
        brain=HangBrain(),
        writer=writer,
        clock=CallClock(),
        config=WorkerConfig(
            greeting_text="",
            chunker_min_chars=1,
            filler_after_ms=50,
            turn_abort_ms=30_000,
        ),
        media=NullMedia(),
    )
    await session.start()
    await session.connect()
    turn_task = asyncio.create_task(session.process_pcm(_pcm()))
    await asyncio.sleep(0.15)
    hang.set()
    await turn_task
    if session.end_reason is None:
        await session.end("client_end")
    assert any(e.type == "filler.played" for e in events)


@pytest.mark.asyncio
async def test_asr_degrade_two_failures(tmp_path: Path) -> None:
    events: list[Event] = []
    writer = await _writer(tmp_path, events)
    media = NullMedia()

    class AlwaysFailSTT:
        async def stream(self, pcm, *, sample_rate: int, hotwords):
            async for _ in pcm:
                pass
            raise ProviderError("asr down")
            yield  # pragma: no cover

        async def transcribe(self, wav: bytes, *, sample_rate: int):
            raise ProviderError("asr down")

    session = CallSession(
        call_id=uuid.uuid4(),
        stt=AlwaysFailSTT(),
        tts=MockTTS(),
        brain=MockBrain(),
        writer=writer,
        clock=CallClock(),
        config=WorkerConfig(greeting_text=""),
        media=media,
    )
    await session.start()
    await session.connect()
    await session.process_pcm(_pcm())
    assert session.end_reason is None
    assert session.degrade.count(FailureKind.ASR) == 1
    await session.process_pcm(_pcm())
    assert session.end_reason == "asr_error"


@pytest.mark.asyncio
async def test_brain_degrade_retry_then_handoff(tmp_path: Path) -> None:
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
    assert session.end_reason is None
    assert session.state is TurnState.LISTENING

    # Second brain failure ends
    from apps.worker.degrade import FailureKind

    assert session.degrade.count(FailureKind.BRAIN) == 1
    decision = session.degrade.record(FailureKind.BRAIN)
    assert decision.action is DegradeAction.HANDOFF


@pytest.mark.asyncio
async def test_tts_switches_to_text_only(tmp_path: Path) -> None:
    class BoomTTS:
        sample_rate = 24_000

        async def stream(self, text: str, *, voice: str, speed: float):
            _ = (text, voice, speed)
            raise ProviderError("tts boom")
            yield b""  # pragma: no cover

    events: list[Event] = []
    writer = await _writer(tmp_path, events)
    media = NullMedia()
    session = CallSession(
        call_id=uuid.uuid4(),
        stt=MockSTT(transcripts=["hi"]),
        tts=BoomTTS(),
        brain=MockBrain(replies=["Hello world."]),
        writer=writer,
        clock=CallClock(),
        config=WorkerConfig(greeting_text="", chunker_min_chars=5),
        media=media,
    )
    await session.start()
    await session.connect()
    await session.process_pcm(_pcm())
    assert session.end_reason is None or session.end_reason == "client_end"
    assert session.text_only is True
    assert any(m.get("type") == "agent.text" for m in media.messages)
    if session.end_reason is None:
        await session.end("client_end")


@pytest.mark.asyncio
async def test_biz_down_stores_callback(tmp_path: Path) -> None:
    events: list[Event] = []
    writer = await _writer(tmp_path, events)
    session = CallSession(
        call_id=uuid.uuid4(),
        stt=MockSTT(),
        tts=MockTTS(),
        brain=MockBrain(),
        writer=writer,
        clock=CallClock(),
        config=WorkerConfig(greeting_text=""),
        media=NullMedia(),
    )
    await session.start()
    await session.connect()
    await session.note_biz_unavailable()
    assert session._pending_callbacks
    await session.end("client_end")
    assert any(e.type == "provider.error" and e.payload.get("stage") == "biz" for e in events)


@pytest.mark.asyncio
async def test_tool_and_events_matrix_rows(tmp_path: Path) -> None:
    events: list[Event] = []
    writer = await _writer(tmp_path, events)
    session = CallSession(
        call_id=uuid.uuid4(),
        stt=MockSTT(),
        tts=MockTTS(),
        brain=MockBrain(),
        writer=writer,
        clock=CallClock(),
        config=WorkerConfig(greeting_text=""),
        media=NullMedia(),
    )
    await session.start()
    assert session.note_tool_failure() is DegradeAction.CONTINUE
    assert session.note_tool_failure() is DegradeAction.OFFER_CALLBACK
    assert session.note_event_ingest_down() is DegradeAction.BUFFER_EVENTS
    await session.end("client_end")


@pytest.mark.asyncio
async def test_observe_caller_speech_applies_barge_in(tmp_path: Path) -> None:
    mono = FakeMono()
    events: list[Event] = []
    writer = await _writer(tmp_path, events)
    session = CallSession(
        call_id=uuid.uuid4(),
        stt=MockSTT(),
        tts=MockTTS(),
        brain=MockBrain(),
        writer=writer,
        clock=CallClock(monotonic=mono),
        config=WorkerConfig(
            greeting_text="",
            barge_in_min_duration_ms=250,
            barge_in_grace_ms_after_playback_start=0,
        ),
        media=NullMedia(),
    )
    await session.start()
    await session.connect()
    session.sm.handle(TurnEvent.ENDPOINT_FINAL)
    session.sm.handle(TurnEvent.FIRST_AUDIO)
    session._spoken_prefix = "Hello"
    session.gate.mark_playback_start(session._clock.t_ms())
    t0 = session._clock.t_ms()
    session.gate.observe(t_ms=t0, speaking=True, agent_active=True)
    mono.advance(0.26)
    ok = await session.observe_caller_speech(speaking=True)
    assert ok
    assert session.state is TurnState.LISTENING
    await session.end("client_end")
    assert any(e.type == "barge_in.detected" for e in events)
    assert any(e.type == "barge_in.applied" for e in events)
