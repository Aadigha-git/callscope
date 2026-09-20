"""Instrument async providers to emit request / first_byte / done / error events."""

from __future__ import annotations

import inspect
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from functools import wraps
from types import TracebackType
from typing import Any, ParamSpec
from uuid import UUID

from callscope.events.clock import CallClock
from callscope.events.models import Event, EventSource
from callscope.events.writer import EventWriter
from callscope.observability import metrics

P = ParamSpec("P")

_FIRST_BYTE_TYPE: dict[str, str] = {
    "brain": "brain.first_token",
    "tts": "tts.first_audio",
}


def _first_byte_type(stage: str) -> str:
    return _FIRST_BYTE_TYPE.get(stage, f"{stage}.first_byte")


def instrument(
    stage: str,
    writer: EventWriter | None = None,
    *,
    emitter: EventWriter | None = None,
    clock: CallClock,
    call_id: UUID,
    source: EventSource = EventSource.WORKER,
    turn_id: UUID | None = None,
) -> _Instrument:
    """Decorator or async context manager for provider-call instrumentation.

    Emits ``{stage}.request``, a first-byte event (``brain.first_token`` /
    ``tts.first_audio`` / ``{stage}.first_byte``), ``{stage}.done``, and
    ``provider.error`` on failure. Records ``observe_stage`` metrics.
    """
    sink = writer if writer is not None else emitter
    if sink is None:
        raise TypeError("instrument() requires writer= or emitter=")
    return _Instrument(
        stage=stage,
        sink=sink,
        clock=clock,
        call_id=call_id,
        source=source,
        turn_id=turn_id,
    )


class _Instrument(AbstractAsyncContextManager[None]):
    """Callable decorator that is also an async context manager."""

    def __init__(
        self,
        *,
        stage: str,
        sink: EventWriter,
        clock: CallClock,
        call_id: UUID,
        source: EventSource,
        turn_id: UUID | None,
    ) -> None:
        self._stage = stage
        self._sink = sink
        self._clock = clock
        self._call_id = call_id
        self._source = source
        self._turn_id = turn_id
        self._t0 = 0.0

    def __call__(self, fn: Callable[P, Any]) -> Callable[P, Any]:
        stage = self._stage
        sink = self._sink
        clock = self._clock
        call_id = self._call_id
        source = self._source
        turn_id = self._turn_id

        if inspect.isasyncgenfunction(fn):

            @wraps(fn)
            async def gen_wrapper(*args: P.args, **kwargs: P.kwargs) -> AsyncIterator[Any]:
                t0 = time.perf_counter()
                _emit(sink, clock, call_id, source, turn_id, f"{stage}.request", {})
                first = True
                try:
                    async for item in fn(*args, **kwargs):
                        if first:
                            first = False
                            metrics.observe_stage(f"{stage}_first_byte", time.perf_counter() - t0)
                            _emit(
                                sink,
                                clock,
                                call_id,
                                source,
                                turn_id,
                                _first_byte_type(stage),
                                {},
                            )
                        yield item
                    metrics.observe_stage(f"{stage}_total", time.perf_counter() - t0)
                    _emit(sink, clock, call_id, source, turn_id, f"{stage}.done", {})
                except Exception as exc:
                    _emit_error(sink, clock, call_id, source, turn_id, stage, exc)
                    raise

            return gen_wrapper

        @wraps(fn)
        async def coro_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            t0 = time.perf_counter()
            _emit(sink, clock, call_id, source, turn_id, f"{stage}.request", {})
            try:
                result = fn(*args, **kwargs)
                if inspect.isasyncgen(result):
                    return _wrap_async_iter(
                        result,
                        stage=stage,
                        writer=sink,
                        clock=clock,
                        call_id=call_id,
                        source=source,
                        turn_id=turn_id,
                        t0=t0,
                    )
                if isinstance(result, Awaitable):
                    out = await result
                    metrics.observe_stage(f"{stage}_total", time.perf_counter() - t0)
                    _emit(sink, clock, call_id, source, turn_id, f"{stage}.done", {})
                    return out
                metrics.observe_stage(f"{stage}_total", time.perf_counter() - t0)
                _emit(sink, clock, call_id, source, turn_id, f"{stage}.done", {})
                return result
            except Exception as exc:
                _emit_error(sink, clock, call_id, source, turn_id, stage, exc)
                raise

        return coro_wrapper

    async def __aenter__(self) -> None:
        self._t0 = time.perf_counter()
        _emit(
            self._sink,
            self._clock,
            self._call_id,
            self._source,
            self._turn_id,
            f"{self._stage}.request",
            {},
        )

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc is not None:
            _emit_error(
                self._sink,
                self._clock,
                self._call_id,
                self._source,
                self._turn_id,
                self._stage,
                exc,
            )
            return
        metrics.observe_stage(f"{self._stage}_total", time.perf_counter() - self._t0)
        _emit(
            self._sink,
            self._clock,
            self._call_id,
            self._source,
            self._turn_id,
            f"{self._stage}.done",
            {},
        )


def _emit(
    writer: EventWriter,
    clock: CallClock,
    call_id: UUID,
    source: EventSource,
    turn_id: UUID | None,
    type_: str,
    payload: dict[str, Any],
) -> None:
    writer.emit(
        Event(
            call_id=call_id,
            turn_id=turn_id,
            t_ms=clock.t_ms() if clock.started else 0,
            source=source,
            type=type_,
            payload=payload,
        )
    )


def _emit_error(
    writer: EventWriter,
    clock: CallClock,
    call_id: UUID,
    source: EventSource,
    turn_id: UUID | None,
    stage: str,
    exc: BaseException,
) -> None:
    metrics.PROVIDER_ERRORS.labels(stage=stage).inc()
    _emit(
        writer,
        clock,
        call_id,
        source,
        turn_id,
        "provider.error",
        {"stage": stage, "code": type(exc).__name__, "retryable": False},
    )


async def _wrap_async_iter(
    it: AsyncIterator[Any],
    *,
    stage: str,
    writer: EventWriter,
    clock: CallClock,
    call_id: UUID,
    source: EventSource,
    turn_id: UUID | None,
    t0: float,
) -> AsyncIterator[Any]:
    first = True
    try:
        async for item in it:
            if first:
                first = False
                metrics.observe_stage(f"{stage}_first_byte", time.perf_counter() - t0)
                _emit(writer, clock, call_id, source, turn_id, _first_byte_type(stage), {})
            yield item
        metrics.observe_stage(f"{stage}_total", time.perf_counter() - t0)
        _emit(writer, clock, call_id, source, turn_id, f"{stage}.done", {})
    except Exception as exc:
        _emit_error(writer, clock, call_id, source, turn_id, stage, exc)
        raise
