"""TTSClient against uvicorn fake backend (TTSProvider contract)."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator

import pytest
import uvicorn

from callscope.providers.base import TTSProvider
from callscope.providers.tts_client import TTSClient
from servers.tts.app import create_app
from servers.tts.backends.fake import FakeTTSBackend

pytestmark = pytest.mark.contract


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def tts_base_url() -> Iterator[str]:
    port = _free_port()
    app = create_app(FakeTTSBackend(ms_per_char=15.0))
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)

    def _run() -> None:
        __import__("asyncio").run(server.serve())

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)
    else:
        server.should_exit = True
        pytest.fail("TTS uvicorn did not become ready")
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    t.join(timeout=5)


@pytest.mark.asyncio
async def test_tts_client_stream_contract(tts_base_url: str) -> None:
    client: TTSProvider = TTSClient(tts_base_url, sample_rate=24_000)
    chunks = [c async for c in client.stream("contract ok", voice="default", speed=1.0)]
    assert chunks
    assert all(len(c) % 2 == 0 for c in chunks)
    assert client.sample_rate == 24_000


@pytest.mark.asyncio
async def test_tts_client_voices(tts_base_url: str) -> None:
    client = TTSClient(tts_base_url)
    voices = await client.voices()
    assert any(v.get("id") == "default" for v in voices)
