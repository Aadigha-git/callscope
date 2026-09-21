"""Optional Piper backend (lazy import; GPL-3.0-or-later voice — distribution caution)."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from servers.tts.backends.base import chunk_pcm, resample_pcm16
from servers.tts.models import CHUNK_MS


class PiperBackend:
    """Piper voice via ``piper`` package — API verified in spike T-M0-06."""

    name = "piper"
    native_sample_rate = 22_050

    def __init__(
        self,
        *,
        model_path: str | None = None,
        config_path: str | None = None,
    ) -> None:
        default_dir = Path(os.environ.get("CALLSCOPE_PIPER_VOICE_DIR", "data/models/piper"))
        self._model_path = Path(
            model_path
            or os.environ.get("CALLSCOPE_PIPER_ONNX", str(default_dir / "en_US-lessac-medium.onnx"))
        )
        self._config_path = Path(
            config_path
            or os.environ.get(
                "CALLSCOPE_PIPER_CONFIG",
                str(default_dir / "en_US-lessac-medium.onnx.json"),
            )
        )
        self._voice: Any = None

    def load(self) -> None:
        try:
            from piper import PiperVoice
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "piper is not installed; use CALLSCOPE_TTS_BACKEND=fake for CI"
            ) from exc
        if not self._model_path.is_file():
            raise RuntimeError(
                f"piper model not found at {self._model_path}; "
                "download en_US-lessac-medium or set CALLSCOPE_PIPER_ONNX"
            )
        self._voice = PiperVoice.load(
            str(self._model_path),
            config_path=str(self._config_path) if self._config_path.is_file() else None,
            use_cuda=False,
        )
        # Prefer the voice's configured sample rate when available.
        cfg_sr = getattr(getattr(self._voice, "config", None), "sample_rate", None)
        if isinstance(cfg_sr, int) and cfg_sr > 0:
            self.native_sample_rate = cfg_sr

    def voices(self) -> list[tuple[str, str]]:
        return [("en_US-lessac-medium", "Piper en_US lessac medium (GPL-3.0-or-later)")]

    async def warm_up(self) -> None:
        cancel = asyncio.Event()
        async for _ in self.synthesize(
            "ok",
            voice="en_US-lessac-medium",
            speed=1.0,
            sample_rate=self.native_sample_rate,
            cancel=cancel,
        ):
            break

    async def synthesize(
        self,
        text: str,
        *,
        voice: str,
        speed: float,
        sample_rate: int,
        cancel: asyncio.Event,
    ) -> AsyncIterator[bytes]:
        _ = (voice, speed)  # Piper voice is bound at load; speed not in spike path.
        if self._voice is None:
            self.load()
        voice_obj = self._voice
        if voice_obj is None:
            raise RuntimeError("piper backend not loaded")

        def _collect() -> bytes:
            buf = bytearray()
            native_sr = self.native_sample_rate
            for chunk in voice_obj.synthesize(text):
                buf.extend(chunk.audio_int16_bytes)
                native_sr = int(chunk.sample_rate)
            self.native_sample_rate = native_sr
            return bytes(buf)

        pcm = await asyncio.to_thread(_collect)
        if cancel.is_set():
            return
        if sample_rate != self.native_sample_rate:
            pcm = resample_pcm16(pcm, self.native_sample_rate, sample_rate)
        async for frame in chunk_pcm(
            pcm, sample_rate=sample_rate, chunk_ms=CHUNK_MS, cancel=cancel
        ):
            yield frame
