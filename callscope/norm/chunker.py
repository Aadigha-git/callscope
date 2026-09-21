"""Incremental sentence/clause chunker for streaming TTS (design §4.2)."""

from __future__ import annotations

import re
import time
from collections.abc import Callable

_ABBREVIATIONS = frozenset(
    {
        "dr",
        "mr",
        "mrs",
        "ms",
        "st",
        "ave",
        "rd",
        "blvd",
        "dept",
        "fig",
        "vol",
        "vs",
        "etc",
        "approx",
        "no",
        "nos",
        "jr",
        "sr",
        "gen",
        "gov",
        "sen",
        "rep",
        "prof",
        "rev",
        "sgt",
        "capt",
        "col",
        "lt",
        "mt",
        "ft",
        "inc",
        "ltd",
        "co",
        "corp",
        "univ",
    }
)

_MULTI_DOT_SUFFIX = re.compile(r"(?i)(?:a\.m|p\.m|u\.s|e\.g|i\.e|ph\.d|m\.d)$")
_SENTENCE_END = frozenset(".!?")
_CLAUSE_END = frozenset(",;:")


class SentenceChunker:
    """Buffer streaming text and emit speakable chunks.

    Emits at sentence end (``.!?`` + space/end) or clause boundary (``,;:``)
    once ``min_chars`` is reached, or after ``max_wait_ms`` (injectable clock).
    Does not strip content; never splits inside numbers, abbreviations, or codes.
    """

    def __init__(
        self,
        *,
        min_chars: int = 24,
        max_wait_ms: int = 800,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if min_chars < 1:
            raise ValueError("min_chars must be >= 1")
        if max_wait_ms < 0:
            raise ValueError("max_wait_ms must be >= 0")
        self._min_chars = min_chars
        self._max_wait_s = max_wait_ms / 1000.0
        self._clock = clock
        self._buf = ""
        self._ready: list[str] = []
        self._segment_started_at: float | None = None

    def push(self, delta: str) -> None:
        if not delta:
            return
        if self._segment_started_at is None:
            self._segment_started_at = self._clock()
        self._buf += delta
        self._extract()

    def ready(self) -> list[str]:
        self._maybe_timeout_flush()
        out = self._ready
        self._ready = []
        return out

    def flush(self) -> list[str]:
        if self._buf.strip():
            self._emit(self._buf.strip())
        self._buf = ""
        self._segment_started_at = None
        out = self._ready
        self._ready = []
        return out

    def _maybe_timeout_flush(self) -> None:
        if not self._buf.strip() or self._segment_started_at is None:
            return
        if self._max_wait_s <= 0:
            return
        if self._clock() - self._segment_started_at >= self._max_wait_s:
            self._emit(self._buf.strip())
            self._buf = ""
            self._segment_started_at = None

    def _emit(self, chunk: str) -> None:
        text = chunk.strip()
        if text:
            self._ready.append(text)

    def _extract(self) -> None:
        while True:
            split_at = self._find_split(self._buf)
            if split_at is None:
                return
            chunk = self._buf[: split_at + 1]
            rest = self._buf[split_at + 1 :]
            if rest.startswith(" "):
                rest = rest[1:]
            self._emit(chunk)
            self._buf = rest
            self._segment_started_at = self._clock() if self._buf.strip() else None

    def _find_split(self, text: str) -> int | None:
        i = 0
        while i < len(text):
            ch = text[i]
            if ch in _SENTENCE_END:
                if ch == "." and self._is_protected_period(text, i):
                    i += 1
                    continue
                nxt = text[i + 1] if i + 1 < len(text) else ""
                # Mid-stream trailing punct with no follower yet → wait for more.
                if nxt == "" and i == len(text) - 1:
                    return None
                if nxt.isspace() or nxt in "\"')":
                    return i
            elif ch in _CLAUSE_END:
                left = text[: i + 1].strip()
                nxt = text[i + 1] if i + 1 < len(text) else ""
                digit_comma = (
                    i > 0 and i + 1 < len(text) and text[i - 1].isdigit() and text[i + 1].isdigit()
                )
                if len(left) >= self._min_chars and not digit_comma and nxt != "" and nxt.isspace():
                    return i
            i += 1
        return None

    def _is_protected_period(self, text: str, idx: int) -> bool:
        if text[idx] != ".":
            return False
        if idx > 0 and idx + 1 < len(text) and text[idx - 1].isdigit() and text[idx + 1].isdigit():
            return True
        start = idx - 1
        while start >= 0 and (text[start].isalnum() or text[start] in ".-'"):
            start -= 1
        token_body = text[start + 1 : idx]
        lower = token_body.lower()
        if lower in _ABBREVIATIONS:
            return True
        if _MULTI_DOT_SUFFIX.search(token_body):
            return True
        if len(token_body) == 1 and token_body.isalpha():
            return True
        return bool(
            re.fullmatch(r"[\d\-]+", token_body) and len(re.sub(r"\D", "", token_body)) >= 3
        )
