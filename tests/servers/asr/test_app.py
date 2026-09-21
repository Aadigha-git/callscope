"""ASR server HTTP/WebSocket contract tests (fake backend)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from servers.asr.app import create_app
from servers.asr.backends.fake import FakeASRBackend
from servers.asr.models import MAX_FRAME_BYTES

pytestmark = pytest.mark.unit

# 20 ms of PCM16 mono @ 16 kHz
_FRAME_20MS = b"\x00\x00" * 320


@pytest.fixture
def client() -> TestClient:
    app = create_app(FakeASRBackend(default_text="hello world"), max_concurrency=2)
    with TestClient(app) as c:
        yield c


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["backend"] == "fake"
    assert body["loaded"] is True


def test_metrics_exposes_rtf_and_latency(client: TestClient) -> None:
    pcm = _FRAME_20MS * 5
    assert (
        client.post(
            "/v1/transcribe",
            files={"audio": ("a.pcm", pcm, "application/octet-stream")},
            params={"sample_rate": 16000},
        ).status_code
        == 200
    )
    r = client.get("/metrics")
    assert r.status_code == 200
    text = r.text
    assert "callscope_asr_request_latency_seconds" in text
    assert "callscope_asr_realtime_factor" in text
    assert "callscope_asr_active_streams" in text
    assert "callscope_asr_queue_depth" in text


def test_transcribe(client: TestClient) -> None:
    pcm = _FRAME_20MS * 5  # 100 ms
    r = client.post(
        "/v1/transcribe",
        files={"audio": ("a.pcm", pcm, "application/octet-stream")},
        params={"sample_rate": 16000},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "final"
    assert data["text"] == "hello world"
    assert data["words"]
    assert data["avg_conf"] == 0.9


def test_transcribe_rejects_sample_rate(client: TestClient) -> None:
    r = client.post(
        "/v1/transcribe",
        files={"audio": ("a.pcm", _FRAME_20MS, "application/octet-stream")},
        params={"sample_rate": 44100},
    )
    assert r.json()["type"] == "error"
    assert r.json()["code"] == "unsupported_sample_rate"


def test_websocket_stream_partial_and_final(client: TestClient) -> None:
    with client.websocket_connect("/v1/stream") as ws:
        ws.send_json(
            {"type": "start", "sample_rate": 16000, "encoding": "pcm_s16le", "hotwords": None}
        )
        for _ in range(15):  # 300 ms in 20 ms frames
            ws.send_bytes(_FRAME_20MS)
        ws.send_json({"type": "end"})
        messages = []
        while True:
            msg = ws.receive_json()
            messages.append(msg)
            if msg.get("type") in {"final", "error"}:
                break
    types = [m["type"] for m in messages]
    assert "final" in types
    assert messages[-1]["text"] == "hello world"
    assert any(m["type"] == "partial" for m in messages)


def test_websocket_hotwords(client: TestClient) -> None:
    with client.websocket_connect("/v1/stream") as ws:
        ws.send_json(
            {
                "type": "start",
                "sample_rate": 16000,
                "encoding": "pcm_s16le",
                "hotwords": ["lakeside", "plumbing"],
            }
        )
        ws.send_bytes(_FRAME_20MS)
        ws.send_json({"type": "end"})
        final = None
        while True:
            msg = ws.receive_json()
            if msg.get("type") == "final":
                final = msg
                break
            if msg.get("type") == "error":
                pytest.fail(msg["message"])
    assert final is not None
    assert final["text"] == "lakeside plumbing"


def test_websocket_frame_too_large(client: TestClient) -> None:
    with client.websocket_connect("/v1/stream") as ws:
        ws.send_json({"type": "start", "sample_rate": 16000, "encoding": "pcm_s16le"})
        ws.send_bytes(b"\x00" * (MAX_FRAME_BYTES + 2))
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert msg["code"] == "frame_too_large"


def test_websocket_odd_frame_rejected(client: TestClient) -> None:
    with client.websocket_connect("/v1/stream") as ws:
        ws.send_json({"type": "start", "sample_rate": 16000, "encoding": "pcm_s16le"})
        ws.send_bytes(b"\x00")
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert msg["code"] == "frame_invalid"
