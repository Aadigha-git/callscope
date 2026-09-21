"""Optional real TTS backends (gated; no downloads in CI)."""

from __future__ import annotations

import os

import pytest

from servers.tts.backends import create_backend

pytestmark = pytest.mark.gpu


@pytest.mark.parametrize("name", ["piper", "kokoro_onnx"])
def test_optional_backend_lazy(name: str) -> None:
    if os.environ.get("CALLSCOPE_RUN_GPU") != "1":
        pytest.skip("set CALLSCOPE_RUN_GPU=1 to exercise real TTS backends")
    backend = create_backend(name)
    assert backend.name in {"piper", "kokoro_onnx"}
    try:
        backend.load()
    except RuntimeError as exc:
        pytest.skip(str(exc))
