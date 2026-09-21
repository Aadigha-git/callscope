"""Optional mlx-whisper backend (skipped unless CALLSCOPE_RUN_GPU=1)."""

from __future__ import annotations

import os

import pytest

from servers.asr.backends import create_backend

pytestmark = pytest.mark.gpu


def test_create_backend_mlx_lazy() -> None:
    if os.environ.get("CALLSCOPE_RUN_GPU") != "1":
        pytest.skip("set CALLSCOPE_RUN_GPU=1 to exercise mlx-whisper")
    backend = create_backend("mlx_whisper")
    assert backend.name == "mlx_whisper"
    try:
        backend.load()
    except RuntimeError as exc:
        pytest.skip(str(exc))
    state = backend.begin(sample_rate=16_000, hotwords=["hello"])
    backend.transcribe_chunk(state, b"\x00\x00" * 3200)
    final = backend.finalize(state)
    assert final.audio_ms >= 0
