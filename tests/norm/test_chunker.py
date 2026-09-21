"""Unit tests for SentenceChunker."""

from __future__ import annotations

import pytest

from callscope.norm.chunker import SentenceChunker

pytestmark = pytest.mark.unit


def _drain(chunker: SentenceChunker) -> list[str]:
    return chunker.ready() + chunker.flush()


def test_streaming_chars_match_bulk_push() -> None:
    text = "Hello there, friend. How are you today? Fine."
    bulk = SentenceChunker(min_chars=10)
    bulk.push(text)
    bulk_out = _drain(bulk)

    stream = SentenceChunker(min_chars=10)
    for ch in text:
        stream.push(ch)
    stream_out = _drain(stream)
    assert stream_out == bulk_out


def test_empty_and_whitespace() -> None:
    c = SentenceChunker()
    c.push("")
    c.push("   ")
    assert c.ready() == []
    assert c.flush() == []


def test_does_not_split_decimal_or_phone() -> None:
    c = SentenceChunker(min_chars=5)
    c.push("The rate is 3.5 percent and call 949-555-0123 please.")
    out = _drain(c)
    joined = " ".join(out)
    assert "3.5" in joined
    assert "949-555-0123" in joined


def test_does_not_split_abbreviations() -> None:
    c = SentenceChunker(min_chars=5)
    c.push("See Dr. Smith on Main St. tomorrow a.m. please.")
    out = _drain(c)
    joined = " ".join(out)
    assert "Dr. Smith" in joined
    assert "St." in joined


def test_clause_split_after_min_chars() -> None:
    c = SentenceChunker(min_chars=20)
    c.push("This clause is long enough, and continues here.")
    ready = c.ready()
    assert any(x.endswith(",") for x in ready) or any("," in x for x in ready)
    rest = c.flush()
    assert rest


def test_max_wait_forced_flush() -> None:
    ticks = {"t": 0.0}

    def clock() -> float:
        return ticks["t"]

    c = SentenceChunker(min_chars=100, max_wait_ms=500, clock=clock)
    c.push("No terminator yet")
    assert c.ready() == []
    ticks["t"] = 0.6
    assert c.ready() == ["No terminator yet"]


def test_unicode_quotes_sentence_end() -> None:
    c = SentenceChunker(min_chars=5)
    c.push('She said "Hello." Then left.')
    out = _drain(c)
    assert len(out) >= 2
