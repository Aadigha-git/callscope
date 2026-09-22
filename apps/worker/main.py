"""Voice worker entrypoint: metrics serve, mock CallSession smoke, LiveKit note.

Run:
  python -m apps.worker --serve      # metrics only (demo / Procfile)
  python -m apps.worker --mock-call  # headless smoke
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import tempfile
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

from apps.worker.config import WorkerConfig
from apps.worker.session import CallSession, NullMedia
from callscope.events.clock import CallClock
from callscope.events.models import Event
from callscope.events.writer import EventWriter
from callscope.observability.logging import configure_logging
from callscope.observability.metrics import start_metrics_server
from callscope.providers.mock import MockBrain, MockSTT, MockTTS

logger = logging.getLogger("callscope.worker")


async def run_mock_call(*, max_duration_s: float = 5.0) -> list[Event]:
    """Headless one-turn smoke using mock providers (no LiveKit)."""
    cfg = WorkerConfig.with_domain_hotwords(
        call_max_duration_s=max_duration_s, call_silence_timeout_s=30.0
    )
    collected: list[Event] = []

    async def sink(events: list[Event]) -> None:
        collected.extend(events)

    spill = Path(tempfile.mkdtemp(prefix="cs-worker-spill-"))
    writer = EventWriter(sink, spill_dir=spill)
    await writer.start()
    clock = CallClock()
    media = NullMedia()
    session = CallSession(
        call_id=uuid.uuid4(),
        stt=MockSTT(transcripts=["I need an appointment"]),
        tts=MockTTS(latency_s=0.0, ms_per_char=5.0),
        brain=MockBrain(replies=["Sure, I can help with that."]),
        writer=writer,
        clock=clock,
        config=cfg,
        media=media,
    )
    await session.start()
    await session.run_greeting()

    async def pcm_iter() -> AsyncGenerator[bytes, None]:
        yield b"\x00\x00" * 160

    await session.process_pcm(pcm_iter())
    if session.end_reason is None:
        await session.end("client_end")
    logger.info(
        "mock call done reason=%s transitions=%s data_msgs=%d events=%d",
        session.end_reason,
        [(a.value, e.value, b.value) for a, e, b in session.sm.history],
        len(media.messages),
        len(collected),
    )
    return collected


async def _serve_forever() -> None:
    stop = asyncio.Event()
    await stop.wait()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="CallScope voice worker")
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Expose Prometheus metrics and idle (demo / Procfile)",
    )
    parser.add_argument(
        "--mock-call",
        action="store_true",
        help="Run a headless mock call and exit (CI / smoke)",
    )
    parser.add_argument(
        "--livekit",
        action="store_true",
        help="Start LiveKit Agents server (requires uv sync --extra worker)",
    )
    args = parser.parse_args(argv)

    configure_logging(
        level=os.environ.get("CALLSCOPE_LOG_LEVEL", "INFO"),
        json_output=os.environ.get("CALLSCOPE_LOG_JSON", "true").lower() == "true",
    )
    metrics_port = int(os.environ.get("CALLSCOPE_METRICS_PORT", "9100"))
    start_metrics_server(metrics_port)
    logger.info("metrics listening on :%s", metrics_port)

    if args.mock_call:
        asyncio.run(run_mock_call())
        return

    if args.livekit:
        from apps.worker.livekit_agent import run_livekit_agent

        logger.info("starting LiveKit Agents worker (real ASR/TTS + Token Factory)")
        run_livekit_agent()
        return

    if args.serve:
        logger.info("worker serving metrics; Ctrl-C to stop")
        try:
            asyncio.run(_serve_forever())
        except KeyboardInterrupt:
            logger.info("worker stopped")
        return

    logger.info("Pass --serve (demo), --mock-call (smoke), or --livekit.")
    raise SystemExit(0)


if __name__ == "__main__":
    main()
