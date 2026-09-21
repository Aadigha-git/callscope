"""Provider contract suite — parametrised over mock implementations.

Real providers (ASR/TTS/Hermes) must pass the same cases when plugged in later.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable

import pytest

from callscope.providers.base import (
    BrainBackend,
    Msg,
    ProviderError,
    ProviderTimeout,
    ProviderUnavailable,
    STTEvent,
    STTProvider,
    TTSProvider,
)
from callscope.providers.mock import MockBrain, MockSTT, MockTTS

pytestmark = pytest.mark.unit

AsyncSleep = Callable[[float], Awaitable[None]]


async def _pcm_chunks(*chunks: bytes) -> AsyncIterator[bytes]:
    for c in chunks:
        yield c


@pytest.fixture
def instant_sleep() -> AsyncSleep:
    async def _sleep(_seconds: float) -> None:
        return None

    return _sleep


@pytest.fixture
def mock_stt(instant_sleep: AsyncSleep) -> MockSTT:
    return MockSTT(
        events=[
            [
                STTEvent(kind="partial", text="hel"),
                STTEvent(kind="final", text="hello", avg_conf=0.9, t_end_ms=400),
            ]
        ],
        sleep=instant_sleep,
    )


@pytest.fixture
def mock_tts(instant_sleep: AsyncSleep) -> MockTTS:
    return MockTTS(sleep=instant_sleep, chunk_ms=20, ms_per_char=20)


@pytest.fixture
def mock_brain(instant_sleep: AsyncSleep) -> MockBrain:
    return MockBrain(replies=["hi there"], sleep=instant_sleep)


@pytest.mark.asyncio
async def test_stt_stream_yields_in_order(mock_stt: MockSTT) -> None:
    stt: STTProvider = mock_stt
    events = [
        e async for e in stt.stream(_pcm_chunks(b"\x00\x00"), sample_rate=16_000, hotwords=None)
    ]
    assert [e.kind for e in events] == ["partial", "final"]
    assert events[-1].text == "hello"


@pytest.mark.asyncio
async def test_stt_scripted_sequence_and_failure(instant_sleep: AsyncSleep) -> None:
    stt = MockSTT(transcripts=["one", "two"], fail_at_call=3, sleep=instant_sleep)
    e1 = [e async for e in stt.stream(_pcm_chunks(b"\x00"), sample_rate=16_000, hotwords=None)]
    e2 = [e async for e in stt.stream(_pcm_chunks(b"\x00"), sample_rate=16_000, hotwords=["x"])]
    assert e1[0].text == "one"
    assert e2[0].text == "two"
    with pytest.raises(ProviderUnavailable):
        async for _ in stt.stream(_pcm_chunks(b"\x00"), sample_rate=16_000, hotwords=None):
            pass


@pytest.mark.asyncio
async def test_stt_transcribe(instant_sleep: AsyncSleep) -> None:
    stt = MockSTT(transcripts=["ok"], sleep=instant_sleep)
    tr = await stt.transcribe(b"RIFF", sample_rate=16_000)
    assert tr.text == "ok"
    assert tr.avg_conf == 0.95


@pytest.mark.asyncio
async def test_tts_stream_pcm16_and_sample_rate(mock_tts: MockTTS) -> None:
    tts: TTSProvider = mock_tts
    assert tts.sample_rate == 24_000
    chunks = [c async for c in tts.stream("abcd", voice="default", speed=1.0)]
    assert chunks
    assert all(len(c) % 2 == 0 for c in chunks)


@pytest.mark.asyncio
async def test_tts_cancel_stops_within_one_chunk(instant_sleep: AsyncSleep) -> None:
    tts = MockTTS(sleep=instant_sleep, ms_per_char=200, chunk_ms=20)
    chunks: list[bytes] = []
    async for chunk in tts.stream("this is a fairly long utterance", voice="v", speed=1.0):
        chunks.append(chunk)
        tts.request_cancel()
    assert 1 <= len(chunks) <= 2


@pytest.mark.asyncio
async def test_brain_stream_order_and_done(mock_brain: MockBrain) -> None:
    brain: BrainBackend = mock_brain
    deltas = [
        d
        async for d in brain.stream_reply(
            [Msg(role="user", content="hi")], call_id="c1", turn_id="t1"
        )
    ]
    assert deltas[-1].kind == "done"
    text = "".join(d.text or "" for d in deltas if d.kind == "text")
    assert text == "hi there"


@pytest.mark.asyncio
async def test_brain_cancel_stops_generation(instant_sleep: AsyncSleep) -> None:
    brain = MockBrain(replies=["one two three four five"], sleep=instant_sleep)
    turn_id = "t-cancel"
    out: list[str] = []
    kinds: list[str] = []
    async for delta in brain.stream_reply(
        [Msg(role="user", content="x")], call_id="c", turn_id=turn_id
    ):
        kinds.append(delta.kind)
        if delta.kind == "text" and delta.text:
            out.append(delta.text)
            await brain.cancel(turn_id)
    assert 1 <= len(out) <= 2
    assert "done" not in kinds


@pytest.mark.asyncio
async def test_brain_error_surfaces(instant_sleep: AsyncSleep) -> None:
    brain = MockBrain(fail_at_call=1, fail_with=ProviderTimeout, sleep=instant_sleep)
    with pytest.raises(ProviderTimeout):
        async for _ in brain.stream_reply([], call_id="c", turn_id="t"):
            pass


@pytest.mark.asyncio
async def test_first_byte_latency_measurable() -> None:
    ticks = {"n": 0.0}

    async def fake_sleep(seconds: float) -> None:
        ticks["n"] += seconds

    brain = MockBrain(replies=["x"], first_token_delay_s=0.05, sleep=fake_sleep)
    t0 = ticks["n"]
    saw_text = False
    async for delta in brain.stream_reply([], call_id="c", turn_id="t"):
        if not saw_text and delta.kind == "text":
            saw_text = True
            assert ticks["n"] - t0 == pytest.approx(0.05)


def test_provider_error_hierarchy() -> None:
    assert issubclass(ProviderTimeout, ProviderError)
    assert issubclass(ProviderUnavailable, ProviderError)
