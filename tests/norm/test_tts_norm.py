"""Golden / unit tests for tts_norm."""

from __future__ import annotations

import pytest

from callscope.norm.tts_norm import tts_norm

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", ""),
        ("   ", ""),
        (
            "Call me at (949) 555-0123 thanks",
            "Call me at nine four nine, five five five, zero one two three thanks",
        ),
        (
            "Your code is AB12CD",
            "Your code is A B one two C D",
        ),
        (
            "See you Tuesday, October 6th",
            "See you Tuesday, October sixth",
        ),
        (
            "Arrive at 2:30pm",
            "Arrive at two thirty p m",
        ),
        (
            "Price is between $150 and $250",
            "Price is between one hundred fifty dollars and two hundred fifty dollars",
        ),
        (
            "**Bold** and *italic* and `code`",
            "Bold and italic and code",
        ),
        (
            "Hello <think>secret</think> world",
            "Hello world",
        ),
        (
            "Meet at 123 Main Street",
            "Meet at one hundred twenty three Main Street",
        ),
    ],
)
def test_tts_norm_goldens(raw: str, expected: str) -> None:
    assert tts_norm(raw) == expected


def test_strips_tool_traces() -> None:
    raw = "OK\nTool call: book_appointment\nDone"
    assert "Tool call" not in tts_norm(raw)
    assert "OK" in tts_norm(raw)


def test_currency_range_dash() -> None:
    out = tts_norm("Costs $150-$250 total")
    assert "between" in out
    assert "dollars" in out
