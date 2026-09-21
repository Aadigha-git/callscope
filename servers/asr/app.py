"""FastAPI ASR server — WebSocket stream + HTTP transcribe (design §4.3)."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Annotated, Any

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import ValidationError

from servers.asr.backends import create_backend
from servers.asr.backends.base import ASRBackend, ASRFinal
from servers.asr.models import (
    DEFAULT_CONCURRENCY,
    MAX_FRAME_BYTES,
    SUPPORTED_SAMPLE_RATES,
    ErrorOut,
    FinalOut,
    PartialOut,
    StreamEnd,
    StreamStart,
    WordTimingOut,
)
from servers.asr.vad import EnergyVAD

logger = logging.getLogger("callscope.asr")

REQUEST_LATENCY = Histogram(
    "callscope_asr_request_latency_seconds",
    "ASR request latency",
    ["route"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)
RTF = Histogram(
    "callscope_asr_realtime_factor",
    "Processing time / audio duration",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)
ACTIVE_STREAMS = Gauge("callscope_asr_active_streams", "Active WebSocket ASR streams")
QUEUE_DEPTH = Gauge("callscope_asr_queue_depth", "Streams waiting on concurrency semaphore")
STREAMS_TOTAL = Counter("callscope_asr_streams_total", "Completed ASR streams", ["status"])


def create_app(
    backend: ASRBackend | None = None, *, max_concurrency: int = DEFAULT_CONCURRENCY
) -> FastAPI:
    asr = backend or create_backend()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Load weights only at process start — never at import time.
        asr.load()
        app.state.loaded = True
        yield

    app = FastAPI(title="CallScope ASR", version="0.0.1", lifespan=lifespan)
    app.state.backend = asr
    app.state.semaphore = asyncio.Semaphore(max_concurrency)
    app.state.loaded = False

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {
            "status": "ok",
            "backend": asr.name,
            "loaded": bool(app.state.loaded),
        }

    @app.get("/metrics")
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.post("/v1/transcribe")
    async def transcribe(
        audio: Annotated[UploadFile, File()],
        sample_rate: int = 16_000,
        hotwords: str | None = None,
    ) -> dict[str, Any]:
        if sample_rate not in SUPPORTED_SAMPLE_RATES:
            return _error_dict(
                "unsupported_sample_rate", f"supported: {sorted(SUPPORTED_SAMPLE_RATES)}"
            )
        raw = await audio.read()
        if not raw:
            return _error_dict("empty_audio", "no audio bytes")
        hw = [h.strip() for h in hotwords.split(",") if h.strip()] if hotwords else None
        t0 = time.perf_counter()
        state = asr.begin(sample_rate=sample_rate, hotwords=hw)
        asr.transcribe_chunk(state, raw)
        final = asr.finalize(state)
        elapsed = time.perf_counter() - t0
        REQUEST_LATENCY.labels(route="transcribe").observe(elapsed)
        if final.audio_ms > 0:
            RTF.observe(elapsed / (final.audio_ms / 1000.0))
        STREAMS_TOTAL.labels(status="ok").inc()
        return _final_payload(final)

    @app.websocket("/v1/stream")
    async def stream(ws: WebSocket) -> None:
        await ws.accept()
        QUEUE_DEPTH.inc()
        await app.state.semaphore.acquire()
        QUEUE_DEPTH.dec()
        ACTIVE_STREAMS.inc()
        status = "ok"
        t0 = time.perf_counter()
        audio_ms = 0
        try:
            first = await ws.receive()
            if first.get("type") == "websocket.disconnect":
                status = "disconnect"
                return
            text = first.get("text")
            if not text:
                await ws.send_json(
                    ErrorOut(
                        code="expected_start", message="first message must be JSON start"
                    ).model_dump()
                )
                status = "error"
                return
            try:
                start = StreamStart.model_validate_json(text)
            except ValidationError as exc:
                await ws.send_json(ErrorOut(code="invalid_start", message=str(exc)).model_dump())
                status = "error"
                return
            if start.sample_rate not in SUPPORTED_SAMPLE_RATES:
                await ws.send_json(
                    ErrorOut(
                        code="unsupported_sample_rate",
                        message=f"supported: {sorted(SUPPORTED_SAMPLE_RATES)}",
                    ).model_dump()
                )
                status = "error"
                return

            state = asr.begin(sample_rate=start.sample_rate, hotwords=start.hotwords)
            vad = EnergyVAD(sample_rate=start.sample_rate)
            ended = False
            while not ended:
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    status = "disconnect"
                    break
                if "bytes" in msg and msg["bytes"] is not None:
                    frame: bytes = msg["bytes"]
                    if len(frame) > MAX_FRAME_BYTES:
                        await ws.send_json(
                            ErrorOut(
                                code="frame_too_large",
                                message=f"max {MAX_FRAME_BYTES} bytes",
                            ).model_dump()
                        )
                        status = "error"
                        break
                    if len(frame) % 2 != 0:
                        await ws.send_json(
                            ErrorOut(
                                code="frame_invalid",
                                message="PCM16 frames must be even-length",
                            ).model_dump()
                        )
                        status = "error"
                        break
                    # VAD tracks segment boundaries for non-streaming backends;
                    # all PCM is also fed to the rolling buffer for partials.
                    _segments = vad.push(frame)
                    partial = asr.transcribe_chunk(state, frame)
                    if partial is not None:
                        await ws.send_json(PartialOut(text=partial, t_start_ms=0).model_dump())
                    _ = _segments
                elif "text" in msg and msg["text"] is not None:
                    try:
                        StreamEnd.model_validate_json(msg["text"])
                    except ValidationError:
                        await ws.send_json(
                            ErrorOut(code="invalid_message", message="expected end").model_dump()
                        )
                        status = "error"
                        break
                    # Frames were already buffered; flush only clears VAD state.
                    vad.flush()
                    final = asr.finalize(state)
                    audio_ms = final.audio_ms
                    await ws.send_json(_final_payload(final))
                    ended = True
                else:
                    await ws.send_json(
                        ErrorOut(
                            code="invalid_message", message="expected bytes or JSON"
                        ).model_dump()
                    )
                    status = "error"
                    break
        except WebSocketDisconnect:
            status = "disconnect"
        except Exception:
            logger.exception("asr stream failed")
            status = "error"
            with suppress(Exception):
                await ws.send_json(ErrorOut(code="internal", message="stream failed").model_dump())
        finally:
            elapsed = time.perf_counter() - t0
            REQUEST_LATENCY.labels(route="stream").observe(elapsed)
            if audio_ms > 0:
                RTF.observe(elapsed / (audio_ms / 1000.0))
            STREAMS_TOTAL.labels(status=status).inc()
            ACTIVE_STREAMS.dec()
            app.state.semaphore.release()

    return app


def _final_payload(final: ASRFinal) -> dict[str, Any]:
    return FinalOut(
        text=final.text,
        words=[
            WordTimingOut(w=w.w, start_ms=w.start_ms, end_ms=w.end_ms, conf=w.conf)
            for w in final.words
        ],
        avg_conf=final.avg_conf,
    ).model_dump()


def _error_dict(code: str, message: str) -> dict[str, Any]:
    return ErrorOut(code=code, message=message).model_dump()


app = create_app()
