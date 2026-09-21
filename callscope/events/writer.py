"""Async batched event writer with spill/replay (never blocks the caller)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from uuid import UUID

from callscope.events.models import Event
from callscope.observability import metrics

logger = logging.getLogger(__name__)

Sink = Callable[[list[Event]], Awaitable[None]]

_DEFAULT_BATCH_SIZE = 100
_DEFAULT_FLUSH_MS = 250.0
_DEFAULT_QUEUE_SIZE = 10_000
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_BACKOFF_S = 0.05
_DEFAULT_SPILL_MAX_BYTES = 32 * 1024 * 1024


class EventWriter:
    """Non-blocking event emitter with batch flush, spill, and replay."""

    def __init__(
        self,
        sink: Sink,
        *,
        spill_dir: Path,
        batch_size: int = _DEFAULT_BATCH_SIZE,
        flush_ms: float = _DEFAULT_FLUSH_MS,
        queue_size: int = _DEFAULT_QUEUE_SIZE,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        backoff_s: float = _DEFAULT_BACKOFF_S,
        spill_max_bytes: int = _DEFAULT_SPILL_MAX_BYTES,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._sink = sink
        self._spill_dir = spill_dir
        self._spill_dir.mkdir(parents=True, exist_ok=True)
        self._spill_path = self._spill_dir / "events_spill.jsonl"
        self._batch_size = batch_size
        self._flush_s = flush_ms / 1000.0
        self._max_retries = max_retries
        self._backoff_s = backoff_s
        self._spill_max_bytes = spill_max_bytes
        self._sleep = sleep or asyncio.sleep
        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=queue_size)
        self._seen: set[UUID] = set()
        self._task: asyncio.Task[None] | None = None
        self._closed = False
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="event-writer")

    def emit(self, event: Event) -> None:
        """Enqueue an event. Never raises; drops oldest when the queue is full."""
        if self._closed:
            metrics.EVENTS_DROPPED.labels(reason="closed").inc()
            return
        if event.event_id in self._seen:
            metrics.EVENTS_DROPPED.labels(reason="dedupe").inc()
            return
        self._seen.add(event.event_id)
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            with contextlib.suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
                metrics.EVENTS_DROPPED.labels(reason="queue_full").inc()
            try:
                self._queue.put_nowait(event)
            except asyncio.QueueFull:
                metrics.EVENTS_DROPPED.labels(reason="queue_full").inc()
                self._seen.discard(event.event_id)

    async def aclose(self) -> None:
        """Flush remaining events and stop the background task."""
        self._closed = True
        self._stopping.set()
        if self._task is not None:
            try:
                await self._task
            finally:
                self._task = None

    async def _await_event_or_stop(self) -> Event | None:
        """Return next event, or None on flush timeout / stop."""
        get_task = asyncio.create_task(self._queue.get())
        stop_task = asyncio.create_task(self._stopping.wait())
        try:
            done, pending = await asyncio.wait(
                {get_task, stop_task},
                timeout=self._flush_s,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            if get_task in done:
                return get_task.result()
            return None
        except Exception:
            get_task.cancel()
            stop_task.cancel()
            raise

    async def _run(self) -> None:
        batch: list[Event] = []
        while not self._stopping.is_set():
            item = await self._await_event_or_stop()
            if item is not None:
                batch.append(item)
                while len(batch) < self._batch_size:
                    try:
                        batch.append(self._queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break
                if len(batch) < self._batch_size and not self._stopping.is_set():
                    continue
            if batch:
                if await self._flush(batch):
                    await self._replay_spill()
                batch = []

        while True:
            try:
                batch.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        if batch:
            if await self._flush(batch):
                await self._replay_spill()
        elif not self._spill_path.exists() or self._spill_path.stat().st_size == 0:
            pass
        else:
            await self._replay_spill()

    async def _flush(self, batch: list[Event]) -> bool:
        """Deliver batch to sink. Returns True on success (including after replay opportunity)."""
        if not batch:
            return True
        last_exc: BaseException | None = None
        for attempt in range(self._max_retries):
            try:
                await self._sink(list(batch))
                metrics.EVENTS_FLUSHED.inc(len(batch))
                return True
            except Exception as exc:
                last_exc = exc
                metrics.EVENTS_SINK_ERRORS.inc()
                await self._sleep(self._backoff_s * (2**attempt))
        logger.warning("event sink failed after retries; spilling %s events", len(batch))
        self._spill(batch)
        if last_exc is not None:
            logger.debug("last sink error: %s", last_exc)
        return False

    def _spill(self, batch: Sequence[Event]) -> None:
        lines = [json.dumps(e.model_dump(mode="json"), separators=(",", ":")) + "\n" for e in batch]
        data = "".join(lines).encode("utf-8")
        if self._spill_path.exists() and self._spill_path.stat().st_size + len(data) > (
            self._spill_max_bytes
        ):
            metrics.EVENTS_DROPPED.labels(reason="spill_full").inc(len(batch))
            return
        with self._spill_path.open("a", encoding="utf-8") as fh:
            fh.write("".join(lines))
        metrics.EVENTS_SPILLED.inc(len(lines))

    async def _replay_spill(self) -> None:
        if not self._spill_path.exists() or self._spill_path.stat().st_size == 0:
            return
        try:
            raw = self._spill_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            logger.warning("cannot read spill file: %s", exc)
            return
        events: list[Event] = []
        for line in raw:
            if not line.strip():
                continue
            try:
                events.append(Event.model_validate_json(line))
            except Exception:
                metrics.EVENTS_DROPPED.labels(reason="spill_corrupt").inc()
        if not events:
            self._spill_path.write_text("", encoding="utf-8")
            return
        try:
            await self._sink(events)
            self._spill_path.write_text("", encoding="utf-8")
            metrics.EVENTS_REPLAYED.inc(len(events))
        except Exception as exc:
            logger.debug("spill replay deferred: %s", exc)

    def _debug_queue_size(self) -> int:
        return self._queue.qsize()

    def _debug_seen(self) -> set[UUID]:
        return set(self._seen)

    def _debug_spill_path(self) -> Path:
        return self._spill_path
