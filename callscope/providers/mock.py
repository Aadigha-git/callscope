"""Deterministic mock providers for CI and offline replay (no model libraries)."""

from __future__ import annotations

import asyncio
import math
import struct
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence

from callscope.providers.base import (
    BrainDelta,
    Msg,
    ProviderError,
    ProviderTimeout,
    ProviderUnavailable,
    STTEvent,
    Transcript,
    WordTiming,
)

AsyncSleep = Callable[[float], Awaitable[None]]


async def _default_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


class MockSTT:
    """Scripted STT with injectable latency and optional N-th call failure."""

    def __init__(
        self,
        transcripts: Sequence[str] | None = None,
        *,
        events: Sequence[Sequence[STTEvent]] | None = None,
        latency_s: float = 0.0,
        fail_at_call: int | None = None,
        fail_with: type[ProviderError] = ProviderUnavailable,
        sleep: AsyncSleep = _default_sleep,
    ) -> None:
        if events is not None:
            self._scripts: list[list[STTEvent]] = [list(s) for s in events]
        else:
            texts = list(transcripts or ["hello"])
            self._scripts = [[_final_event(t)] for t in texts]
        self._latency_s = latency_s
        self._fail_at_call = fail_at_call
        self._fail_with = fail_with
        self._sleep = sleep
        self._calls = 0

    async def stream(
        self,
        pcm: AsyncIterator[bytes],
        *,
        sample_rate: int,
        hotwords: list[str] | None,
    ) -> AsyncIterator[STTEvent]:
        async for _chunk in pcm:
            pass
        self._calls += 1
        if self._fail_at_call is not None and self._calls == self._fail_at_call:
            raise self._fail_with(f"mock STT failed at call {self._calls}")
        idx = min(self._calls - 1, len(self._scripts) - 1)
        for event in self._scripts[idx]:
            if self._latency_s > 0:
                await self._sleep(self._latency_s)
            yield event

    async def transcribe(self, wav: bytes, *, sample_rate: int) -> Transcript:
        _ = (wav, sample_rate)
        self._calls += 1
        if self._fail_at_call is not None and self._calls == self._fail_at_call:
            raise self._fail_with(f"mock STT failed at call {self._calls}")
        idx = min(self._calls - 1, len(self._scripts) - 1)
        events = self._scripts[idx]
        for _event in events:
            if self._latency_s > 0:
                await self._sleep(self._latency_s)
        finals = [e for e in events if e.kind == "final"]
        if not finals:
            return Transcript(text="", duration_ms=0)
        last = finals[-1]
        return Transcript(
            text=last.text,
            words=last.words,
            avg_conf=last.avg_conf,
            duration_ms=last.t_end_ms,
        )


class MockTTS:
    """Deterministic PCM16 sine chunks sized from text length; cancellable."""

    def __init__(
        self,
        *,
        sample_rate: int = 24_000,
        chunk_ms: int = 20,
        ms_per_char: float = 40.0,
        frequency_hz: float = 440.0,
        latency_s: float = 0.0,
        sleep: AsyncSleep = _default_sleep,
    ) -> None:
        self.sample_rate = sample_rate
        self._chunk_ms = chunk_ms
        self._ms_per_char = ms_per_char
        self._frequency_hz = frequency_hz
        self._latency_s = latency_s
        self._sleep = sleep
        self._cancel = asyncio.Event()

    def request_cancel(self) -> None:
        self._cancel.set()

    def reset_cancel(self) -> None:
        self._cancel.clear()

    async def stream(self, text: str, *, voice: str, speed: float) -> AsyncIterator[bytes]:
        _ = voice
        if self._latency_s > 0:
            await self._sleep(self._latency_s)
        duration_ms = max(int(len(text) * self._ms_per_char / max(speed, 0.1)), self._chunk_ms)
        samples_total = int(self.sample_rate * duration_ms / 1000)
        chunk_samples = max(int(self.sample_rate * self._chunk_ms / 1000), 1)
        produced = 0
        phase = 0.0
        while produced < samples_total:
            if self._cancel.is_set():
                return
            n = min(chunk_samples, samples_total - produced)
            chunk, phase = _sine_pcm16(n, self.sample_rate, self._frequency_hz, phase)
            produced += n
            yield chunk


class MockBrain:
    """Scripted token stream with first-token delay and per-turn cancel."""

    def __init__(
        self,
        replies: Sequence[str] | None = None,
        *,
        deltas: Sequence[Sequence[BrainDelta]] | None = None,
        first_token_delay_s: float = 0.0,
        token_latency_s: float = 0.0,
        fail_at_call: int | None = None,
        fail_with: type[ProviderError] = ProviderTimeout,
        sleep: AsyncSleep = _default_sleep,
    ) -> None:
        if deltas is not None:
            self._scripts: list[list[BrainDelta]] = [list(s) for s in deltas]
        else:
            texts = list(replies or ["OK."])
            self._scripts = [_text_deltas(t) for t in texts]
        self._first_token_delay_s = first_token_delay_s
        self._token_latency_s = token_latency_s
        self._fail_at_call = fail_at_call
        self._fail_with = fail_with
        self._sleep = sleep
        self._calls = 0
        self._cancelled: set[str] = set()

    async def cancel(self, turn_id: str) -> None:
        self._cancelled.add(turn_id)

    async def stream_reply(
        self,
        messages: list[Msg],
        *,
        call_id: str,
        turn_id: str,
    ) -> AsyncIterator[BrainDelta]:
        _ = (messages, call_id)
        self._calls += 1
        if self._fail_at_call is not None and self._calls == self._fail_at_call:
            raise self._fail_with(f"mock brain failed at call {self._calls}")
        if self._first_token_delay_s > 0:
            await self._sleep(self._first_token_delay_s)
        idx = min(self._calls - 1, len(self._scripts) - 1)
        for delta in self._scripts[idx]:
            if turn_id in self._cancelled:
                return
            if self._token_latency_s > 0:
                await self._sleep(self._token_latency_s)
            yield delta
        if turn_id not in self._cancelled:
            yield BrainDelta(kind="done")


def _final_event(text: str) -> STTEvent:
    words = tuple(
        WordTiming(word=w, start_ms=i * 200, end_ms=i * 200 + 180)
        for i, w in enumerate(text.split())
    )
    return STTEvent(
        kind="final",
        text=text,
        words=words,
        avg_conf=0.95,
        t_start_ms=0,
        t_end_ms=max((words[-1].end_ms if words else 0), 0),
    )


def _text_deltas(text: str) -> list[BrainDelta]:
    parts = text.split(" ")
    out: list[BrainDelta] = []
    for i, part in enumerate(parts):
        token = part if i == len(parts) - 1 else f"{part} "
        if token:
            out.append(BrainDelta(kind="text", text=token))
    return out


def _sine_pcm16(
    n_samples: int, sample_rate: int, frequency_hz: float, phase: float
) -> tuple[bytes, float]:
    out = bytearray()
    two_pi_f = 2.0 * math.pi * frequency_hz / sample_rate
    for i in range(n_samples):
        sample = int(16000 * math.sin(phase + i * two_pi_f))
        out.extend(struct.pack("<h", max(-32768, min(32767, sample))))
    new_phase = phase + n_samples * two_pi_f
    return bytes(out), new_phase
