"""FastAPI TTS server — chunked PCM stream (design §4.3)."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import ValidationError

from servers.tts.backends import create_backend
from servers.tts.backends.base import TTSBackend
from servers.tts.models import (
    DEFAULT_CONCURRENCY,
    SUPPORTED_SAMPLE_RATES,
    StreamRequest,
    VoiceInfo,
)

logger = logging.getLogger("callscope.tts")

TTFB = Histogram(
    "callscope_tts_ttfb_seconds",
    "Time to first audio byte",
    buckets=(0.02, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)
RTF = Histogram(
    "callscope_tts_realtime_factor",
    "Processing time / audio duration",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)
CHARS_PER_S = Histogram(
    "callscope_tts_chars_per_second",
    "Characters synthesised per wall-clock second",
    buckets=(5, 10, 20, 40, 80, 160, 320),
)
ACTIVE_STREAMS = Gauge("callscope_tts_active_streams", "Active TTS streams")
STREAMS_TOTAL = Counter("callscope_tts_streams_total", "Completed TTS streams", ["status"])


def create_app(
    backend: TTSBackend | None = None, *, max_concurrency: int = DEFAULT_CONCURRENCY
) -> FastAPI:
    tts = backend or create_backend()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        tts.load()
        try:
            await tts.warm_up()
        except Exception:  # pragma: no cover - warm-up best effort
            logger.exception("tts warm-up failed")
        app.state.loaded = True
        yield

    app = FastAPI(title="CallScope TTS", version="0.0.1", lifespan=lifespan)
    app.state.backend = tts
    app.state.semaphore = asyncio.Semaphore(max_concurrency)
    app.state.loaded = False

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {
            "status": "ok",
            "backend": tts.name,
            "loaded": bool(app.state.loaded),
        }

    @app.get("/metrics")
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/v1/voices")
    async def voices() -> dict[str, Any]:
        return {
            "voices": [
                VoiceInfo(
                    id=vid,
                    sample_rate=tts.native_sample_rate,
                    description=desc,
                ).model_dump()
                for vid, desc in tts.voices()
            ]
        }

    @app.post("/v1/tts/stream")
    async def stream(request: Request) -> Response:
        try:
            body = StreamRequest.model_validate(await request.json())
        except ValidationError as exc:
            return JSONResponse(
                status_code=422,
                content={"type": "error", "code": "invalid_request", "message": str(exc)},
            )
        if body.sample_rate not in SUPPORTED_SAMPLE_RATES:
            return JSONResponse(
                status_code=400,
                content={
                    "type": "error",
                    "code": "unsupported_sample_rate",
                    "message": f"supported: {sorted(SUPPORTED_SAMPLE_RATES)}",
                },
            )

        await app.state.semaphore.acquire()
        ACTIVE_STREAMS.inc()
        cancel = asyncio.Event()
        t0 = time.perf_counter()
        first_byte_at: list[float | None] = [None]
        bytes_out = 0
        status = "ok"
        text_len = len(body.text)

        async def _gen() -> AsyncIterator[bytes]:
            nonlocal bytes_out, status
            try:
                async for chunk in tts.synthesize(
                    body.text,
                    voice=body.voice,
                    speed=body.speed,
                    sample_rate=body.sample_rate,
                    cancel=cancel,
                ):
                    if await request.is_disconnected():
                        cancel.set()
                        status = "disconnect"
                        break
                    if first_byte_at[0] is None:
                        t_first = time.perf_counter()
                        first_byte_at[0] = t_first
                        TTFB.observe(t_first - t0)
                    bytes_out += len(chunk)
                    yield chunk
            except Exception:
                logger.exception("tts stream failed")
                status = "error"
                raise
            finally:
                elapsed = time.perf_counter() - t0
                audio_s = (bytes_out / 2) / max(body.sample_rate, 1)
                if audio_s > 0:
                    RTF.observe(elapsed / audio_s)
                if elapsed > 0 and text_len > 0:
                    CHARS_PER_S.observe(text_len / elapsed)
                STREAMS_TOTAL.labels(status=status).inc()
                ACTIVE_STREAMS.dec()
                app.state.semaphore.release()

        return StreamingResponse(
            _gen(),
            media_type="audio/L16",
            headers={
                "X-Sample-Rate": str(body.sample_rate),
                "X-Content-Type-Options": "nosniff",
            },
        )

    return app


app = create_app()
