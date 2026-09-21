"""TTS backend registry."""

from __future__ import annotations

import os

from servers.tts.backends.base import TTSBackend
from servers.tts.backends.fake import FakeTTSBackend


def create_backend(name: str | None = None) -> TTSBackend:
    resolved = (name or os.environ.get("CALLSCOPE_TTS_BACKEND") or "fake").lower()
    if resolved == "fake":
        return FakeTTSBackend()
    if resolved in {"piper"}:
        from servers.tts.backends.piper import PiperBackend

        return PiperBackend()
    if resolved in {"kokoro_onnx", "kokoro-onnx", "kokoro"}:
        from servers.tts.backends.kokoro_onnx import KokoroOnnxBackend

        return KokoroOnnxBackend()
    raise ValueError(f"unknown TTS backend: {resolved!r}")
