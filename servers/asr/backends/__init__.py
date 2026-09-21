"""ASR backend registry."""

from __future__ import annotations

import os

from servers.asr.backends.base import ASRBackend
from servers.asr.backends.fake import FakeASRBackend


def create_backend(name: str | None = None) -> ASRBackend:
    resolved = (name or os.environ.get("CALLSCOPE_ASR_BACKEND") or "fake").lower()
    if resolved == "fake":
        return FakeASRBackend()
    if resolved in {"mlx_whisper", "mlx-whisper", "whisper"}:
        from servers.asr.backends.mlx_whisper import MlxWhisperBackend

        return MlxWhisperBackend()
    raise ValueError(f"unknown ASR backend: {resolved!r}")
