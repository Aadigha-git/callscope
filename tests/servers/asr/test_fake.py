"""Fake ASR backend unit tests."""

from __future__ import annotations

import pytest

from servers.asr.backends.fake import FakeASRBackend

pytestmark = pytest.mark.unit


def test_fake_partial_grows_then_final() -> None:
    b = FakeASRBackend(default_text="one two three")
    b.load()
    state = b.begin(sample_rate=16_000, hotwords=None)
    p1 = b.transcribe_chunk(state, b"\x00\x00" * 1600)  # 100 ms → 1 word
    assert p1 == "one"
    p2 = b.transcribe_chunk(state, b"\x00\x00" * 3200)  # +200 ms
    assert p2 is not None
    assert "two" in p2
    final = b.finalize(state)
    assert final.text == "one two three"
    assert len(final.words) == 3
    assert final.avg_conf == 0.9


def test_fake_hotwords() -> None:
    b = FakeASRBackend()
    b.load()
    state = b.begin(sample_rate=16_000, hotwords=["acme", "plumbing"])
    b.transcribe_chunk(state, b"\x00\x00" * 100)
    assert b.finalize(state).text == "acme plumbing"


def test_create_backend_default_fake() -> None:
    from servers.asr.backends import create_backend

    assert create_backend().name == "fake"
    assert create_backend("fake").name == "fake"
    with pytest.raises(ValueError, match="unknown"):
        create_backend("nope")
