"""Optional kokoro-onnx backend (lazy import; Apache-2.0 weights)."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from servers.tts.backends.base import chunk_pcm, float_to_pcm16, resample_pcm16
from servers.tts.models import CHUNK_MS, DEFAULT_SAMPLE_RATE


class KokoroOnnxBackend:
    """kokoro-onnx ``Kokoro.create`` — API verified in spike T-M0-06 (non-stream)."""

    name = "kokoro_onnx"
    native_sample_rate = DEFAULT_SAMPLE_RATE

    def __init__(
        self,
        *,
        model_path: str | None = None,
        voices_path: str | None = None,
    ) -> None:
        default_dir = Path(os.environ.get("CALLSCOPE_KOKORO_DIR", "data/models/kokoro"))
        self._model_path = Path(
            model_path
            or os.environ.get("CALLSCOPE_KOKORO_ONNX", str(default_dir / "kokoro-v1.0.onnx"))
        )
        self._voices_path = Path(
            voices_path
            or os.environ.get("CALLSCOPE_KOKORO_VOICES", str(default_dir / "voices-v1.0.bin"))
        )
        self._kokoro: Any = None

    def load(self) -> None:
        try:
            from kokoro_onnx import Kokoro
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "kokoro-onnx is not installed; use CALLSCOPE_TTS_BACKEND=fake for CI"
            ) from exc
        if not self._model_path.is_file() or not self._voices_path.is_file():
            raise RuntimeError(
                f"kokoro model/voices not found under {self._model_path.parent}; "
                "download kokoro-v1.0.onnx + voices-v1.0.bin or set CALLSCOPE_KOKORO_*"
            )
        self._kokoro = Kokoro(str(self._model_path), str(self._voices_path))

    def voices(self) -> list[tuple[str, str]]:
        return [("af_sarah", "Kokoro af_sarah (Apache-2.0)")]

    async def warm_up(self) -> None:
        cancel = asyncio.Event()
        async for _ in self.synthesize(
            "ok", voice="af_sarah", speed=1.0, sample_rate=self.native_sample_rate, cancel=cancel
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
        if self._kokoro is None:
            self.load()
        kokoro = self._kokoro
        if kokoro is None:
            raise RuntimeError("kokoro-onnx backend not loaded")

        def _create() -> tuple[bytes, int]:
            samples, sr = kokoro.create(text, voice=voice or "af_sarah", speed=speed)
            return float_to_pcm16(samples), int(sr)

        pcm, native_sr = await asyncio.to_thread(_create)
        self.native_sample_rate = native_sr
        if cancel.is_set():
            return
        if sample_rate != native_sr:
            pcm = resample_pcm16(pcm, native_sr, sample_rate)
        async for frame in chunk_pcm(
            pcm, sample_rate=sample_rate, chunk_ms=CHUNK_MS, cancel=cancel
        ):
            yield frame
