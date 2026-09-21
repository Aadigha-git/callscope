"""Fake TTS + registry unit tests."""

from __future__ import annotations

import asyncio

import pytest

from servers.tts.backends import create_backend
from servers.tts.backends.base import resample_pcm16
from servers.tts.backends.fake import FakeTTSBackend

pytestmark = pytest.mark.unit


def test_create_backend_default_fake() -> None:
    assert create_backend().name == "fake"
    assert create_backend("fake").name == "fake"
    with pytest.raises(ValueError, match="unknown"):
        create_backend("nope")


def test_resample_identity_and_up() -> None:
    pcm = b"\x00\x01\x00\x02\x00\x03\x00\x04"
    assert resample_pcm16(pcm, 16_000, 16_000) == pcm
    up = resample_pcm16(pcm, 8_000, 16_000)
    assert len(up) >= len(pcm)
    assert len(up) % 2 == 0


@pytest.mark.asyncio
async def test_fake_warm_up() -> None:
    b = FakeTTSBackend()
    b.load()
    await b.warm_up()


@pytest.mark.asyncio
async def test_disconnect_cancel_via_event() -> None:
    """Client disconnect path sets cancel; backend must stop within a few chunks."""
    b = FakeTTSBackend(ms_per_char=300.0, chunk_delay_s=0.005)
    b.load()
    cancel = asyncio.Event()
    n = 0
    async for _ in b.synthesize(
        "abcdefghijklmnopqrstuvwxyz",
        voice="default",
        speed=1.0,
        sample_rate=16_000,
        cancel=cancel,
    ):
        n += 1
        cancel.set()
    assert n <= 2
