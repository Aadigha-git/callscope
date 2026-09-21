"""STTProvider client over the ASR server WebSocket (design §4.3)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import websockets

from callscope.providers.base import (
    ProviderError,
    ProviderUnavailable,
    STTEvent,
    Transcript,
    WordTiming,
)


class ASRClient:
    """HTTP + WebSocket client implementing ``STTProvider``."""

    def __init__(self, base_url: str, *, timeout_s: float = 30.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s

    async def stream(
        self,
        pcm: AsyncIterator[bytes],
        *,
        sample_rate: int,
        hotwords: list[str] | None,
    ) -> AsyncIterator[STTEvent]:
        ws_url = self._base.replace("http://", "ws://").replace("https://", "wss://")
        uri = f"{ws_url}/v1/stream"
        try:
            async with websockets.connect(uri, open_timeout=self._timeout) as ws:
                await ws.send(
                    json.dumps(
                        {
                            "type": "start",
                            "sample_rate": sample_rate,
                            "encoding": "pcm_s16le",
                            "hotwords": hotwords,
                        }
                    )
                )
                async for frame in pcm:
                    await ws.send(frame)
                await ws.send(json.dumps({"type": "end"}))
                while True:
                    raw = await ws.recv()
                    if not isinstance(raw, str):
                        continue
                    msg: dict[str, Any] = json.loads(raw)
                    kind = msg.get("type")
                    if kind == "partial":
                        yield STTEvent(
                            kind="partial",
                            text=str(msg.get("text", "")),
                            t_start_ms=int(msg.get("t_start_ms") or 0),
                        )
                    elif kind == "final":
                        words = tuple(
                            WordTiming(
                                word=str(w.get("w", "")),
                                start_ms=int(w.get("start_ms") or 0),
                                end_ms=int(w.get("end_ms") or 0),
                                conf=w.get("conf"),
                            )
                            for w in (msg.get("words") or [])
                        )
                        yield STTEvent(
                            kind="final",
                            text=str(msg.get("text", "")),
                            words=words,
                            avg_conf=msg.get("avg_conf"),
                            t_end_ms=words[-1].end_ms if words else 0,
                        )
                        return
                    elif kind == "error":
                        raise ProviderError(str(msg.get("message") or msg.get("code")))
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderUnavailable(f"ASR stream failed: {exc}") from exc

    async def transcribe(self, wav: bytes, *, sample_rate: int) -> Transcript:
        url = f"{self._base}/v1/transcribe"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                files = {"audio": ("audio.wav", wav, "application/octet-stream")}
                resp = await client.post(url, files=files, params={"sample_rate": sample_rate})
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            raise ProviderUnavailable(f"ASR transcribe failed: {exc}") from exc
        if data.get("type") == "error":
            raise ProviderError(str(data.get("message") or data.get("code")))
        words = tuple(
            WordTiming(
                word=str(w.get("w", "")),
                start_ms=int(w.get("start_ms") or 0),
                end_ms=int(w.get("end_ms") or 0),
                conf=w.get("conf"),
            )
            for w in (data.get("words") or [])
        )
        return Transcript(
            text=str(data.get("text", "")),
            words=words,
            avg_conf=data.get("avg_conf"),
            duration_ms=words[-1].end_ms if words else 0,
        )
