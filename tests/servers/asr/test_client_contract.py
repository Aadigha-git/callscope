"""ASRClient against a live uvicorn fake backend (STTProvider contract)."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import AsyncIterator, Iterator

import pytest
import uvicorn

from callscope.providers.asr_client import ASRClient
from callscope.providers.base import STTProvider
from servers.asr.app import create_app
from servers.asr.backends.fake import FakeASRBackend

pytestmark = pytest.mark.contract

_FRAME_20MS = b"\x00\x00" * 320


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def asr_base_url() -> Iterator[str]:
    port = _free_port()
    app = create_app(FakeASRBackend(default_text="contract ok"))
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)

    def _run() -> None:
        asyncio_run = __import__("asyncio").run
        asyncio_run(server.serve())

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
        pytest.fail("ASR uvicorn did not become ready")
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    t.join(timeout=5)


async def _pcm(*chunks: bytes) -> AsyncIterator[bytes]:
    for c in chunks:
        yield c


@pytest.mark.asyncio
async def test_asr_client_stream_contract(asr_base_url: str) -> None:
    client: STTProvider = ASRClient(asr_base_url)
    events = [
        e
        async for e in client.stream(_pcm(*([_FRAME_20MS] * 10)), sample_rate=16_000, hotwords=None)
    ]
    assert events
    assert events[-1].kind == "final"
    assert events[-1].text == "contract ok"
    assert events[-1].words
    assert any(e.kind == "partial" for e in events)


@pytest.mark.asyncio
async def test_asr_client_transcribe(asr_base_url: str) -> None:
    client = ASRClient(asr_base_url)
    tr = await client.transcribe(_FRAME_20MS * 5, sample_rate=16_000)
    assert tr.text == "contract ok"
    assert tr.words
    assert tr.avg_conf == 0.9


@pytest.mark.asyncio
async def test_asr_client_hotwords(asr_base_url: str) -> None:
    client = ASRClient(asr_base_url)
    events = [
        e
        async for e in client.stream(
            _pcm(_FRAME_20MS),
            sample_rate=16_000,
            hotwords=["lakeside", "plumbing"],
        )
    ]
    assert events[-1].text == "lakeside plumbing"
