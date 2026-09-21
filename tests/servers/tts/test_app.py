"""TTS server HTTP contract tests (fake backend)."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from servers.tts.app import create_app
from servers.tts.backends.fake import FakeTTSBackend

pytestmark = pytest.mark.unit


@pytest.fixture
def client() -> TestClient:
    app = create_app(FakeTTSBackend(ms_per_char=20.0), max_concurrency=2)
    with TestClient(app) as c:
        yield c


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["backend"] == "fake"
    assert body["loaded"] is True


def test_voices(client: TestClient) -> None:
    r = client.get("/v1/voices")
    assert r.status_code == 200
    ids = {v["id"] for v in r.json()["voices"]}
    assert "default" in ids


def test_stream_pcm_and_headers(client: TestClient) -> None:
    r = client.post(
        "/v1/tts/stream",
        json={"text": "hello lakeside", "voice": "default", "speed": 1.0, "sample_rate": 24000},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/L16")
    assert r.headers["x-sample-rate"] == "24000"
    assert len(r.content) >= 2
    assert len(r.content) % 2 == 0


def test_stream_rejects_sample_rate(client: TestClient) -> None:
    r = client.post(
        "/v1/tts/stream",
        json={"text": "x", "voice": "default", "speed": 1.0, "sample_rate": 44100},
    )
    assert r.status_code == 400
    assert r.json()["code"] == "unsupported_sample_rate"


def test_metrics_expose_ttfb(client: TestClient) -> None:
    assert (
        client.post(
            "/v1/tts/stream",
            json={"text": "metrics", "voice": "default", "speed": 1.0, "sample_rate": 16000},
        ).status_code
        == 200
    )
    text = client.get("/metrics").text
    assert "callscope_tts_ttfb_seconds" in text
    assert "callscope_tts_realtime_factor" in text
    assert "callscope_tts_chars_per_second" in text


@pytest.mark.asyncio
async def test_fake_cancel_stops_promptly() -> None:
    backend = FakeTTSBackend(ms_per_char=200.0, chunk_delay_s=0.01)
    backend.load()
    cancel = asyncio.Event()
    chunks = 0
    async for _ in backend.synthesize(
        "this is a fairly long utterance for cancel",
        voice="default",
        speed=1.0,
        sample_rate=24_000,
        cancel=cancel,
    ):
        chunks += 1
        if chunks >= 1:
            cancel.set()
    assert 1 <= chunks <= 3
