"""HermesBackend unit + contract tests against recorded SSE fixtures (no network)."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from callscope.providers.base import Msg, ProviderError, ProviderTimeout, ProviderUnavailable
from callscope.providers.budget import BudgetGuard
from callscope.providers.cassettes import CassetteBrain, CassetteMode, CassetteStore
from callscope.providers.hermes_backend import (
    HermesBackend,
    format_call_context,
    inject_call_context,
)

ROOT = Path(__file__).resolve().parents[2]
HERMES_CONFIG = ROOT / "infra" / "hermes" / "config.yaml"
SELFTEST = ROOT / "infra" / "hermes" / "toolset_selftest.py"

pytestmark = pytest.mark.contract


def _sse_chunk(content: str | None = None, **extra: Any) -> str:
    delta: dict[str, Any] = {}
    if content is not None:
        delta["content"] = content
    delta.update(extra)
    body = {"choices": [{"delta": delta, "index": 0}]}
    return f"data: {json.dumps(body)}\n\n"


def _sse_done() -> str:
    return "data: [DONE]\n\n"


def _make_app(
    handler: Callable[[Request], Any],
) -> Starlette:
    return Starlette(routes=[Route("/v1/chat/completions", handler, methods=["POST"])])


async def _collect(
    backend: HermesBackend,
    messages: list[Msg] | None = None,
    *,
    turn_id: str = "t1",
    interruption_note: str | None = None,
) -> list[Any]:
    msgs = messages or [Msg(role="user", content="hello")]
    out = []
    async for d in backend.stream_reply(
        msgs, call_id="call-1", turn_id=turn_id, interruption_note=interruption_note
    ):
        out.append(d)
    return out


@pytest.mark.asyncio
async def test_stream_normal_text_and_call_context() -> None:
    captured: dict[str, Any] = {}

    async def chat(request: Request) -> StreamingResponse:
        captured["body"] = await request.json()
        captured["headers"] = dict(request.headers)

        async def gen() -> AsyncIterator[bytes]:
            yield _sse_chunk("Hi ").encode()
            yield _sse_chunk("there").encode()
            yield _sse_done().encode()

        return StreamingResponse(gen(), media_type="text/event-stream")

    transport = httpx.ASGITransport(app=_make_app(chat))
    async with httpx.AsyncClient(transport=transport, base_url="http://hermes") as client:
        backend = HermesBackend("http://hermes", "test-key", client=client)
        deltas = await _collect(backend)

    assert [d.kind for d in deltas] == ["text", "text", "done"]
    assert "".join(d.text or "" for d in deltas if d.kind == "text") == "Hi there"
    msgs = captured["body"]["messages"]
    user = next(m for m in msgs if m["role"] == "user")
    assert format_call_context("call-1", "t1") in user["content"]
    assert "hello" in user["content"]
    assert captured["body"]["user"] == "call-1"
    assert captured["body"]["stream"] is True
    assert captured["headers"]["authorization"] == "Bearer test-key"
    assert captured["headers"]["x-call-id"] == "call-1"
    assert captured["headers"]["x-turn-id"] == "t1"


@pytest.mark.asyncio
async def test_interruption_note_prefixed() -> None:
    captured: dict[str, Any] = {}

    async def chat(request: Request) -> StreamingResponse:
        captured["body"] = await request.json()

        async def gen() -> AsyncIterator[bytes]:
            yield _sse_chunk("ok").encode()
            yield _sse_done().encode()

        return StreamingResponse(gen(), media_type="text/event-stream")

    transport = httpx.ASGITransport(app=_make_app(chat))
    async with httpx.AsyncClient(transport=transport, base_url="http://hermes") as client:
        backend = HermesBackend("http://hermes", "k", client=client)
        await _collect(backend, interruption_note="[INTERRUPTION] barge-in")

    user = next(m for m in captured["body"]["messages"] if m["role"] == "user")
    assert user["content"].startswith("[INTERRUPTION] barge-in")


@pytest.mark.asyncio
async def test_error_mid_stream() -> None:
    async def chat(_request: Request) -> StreamingResponse:
        async def gen() -> AsyncIterator[bytes]:
            yield _sse_chunk("partial").encode()
            yield f"data: {json.dumps({'error': {'message': 'boom'}})}\n\n".encode()

        return StreamingResponse(gen(), media_type="text/event-stream")

    transport = httpx.ASGITransport(app=_make_app(chat))
    async with httpx.AsyncClient(transport=transport, base_url="http://hermes") as client:
        backend = HermesBackend("http://hermes", "k", client=client)
        with pytest.raises(ProviderError, match="boom"):
            await _collect(backend)


@pytest.mark.asyncio
async def test_http_503_maps_unavailable() -> None:
    async def chat(_request: Request) -> JSONResponse:
        return JSONResponse({"error": "down"}, status_code=503)

    transport = httpx.ASGITransport(app=_make_app(chat))
    async with httpx.AsyncClient(transport=transport, base_url="http://hermes") as client:
        backend = HermesBackend("http://hermes", "k", client=client)
        with pytest.raises(ProviderUnavailable):
            await _collect(backend)


@pytest.mark.asyncio
async def test_slow_first_token_timeout() -> None:
    async def chat(_request: Request) -> StreamingResponse:
        async def gen() -> AsyncIterator[bytes]:
            await asyncio.sleep(0.5)
            yield _sse_chunk("late").encode()
            yield _sse_done().encode()

        return StreamingResponse(gen(), media_type="text/event-stream")

    transport = httpx.ASGITransport(app=_make_app(chat))
    async with httpx.AsyncClient(transport=transport, base_url="http://hermes") as client:
        backend = HermesBackend("http://hermes", "k", client=client, first_token_timeout_s=0.05)
        with pytest.raises(ProviderTimeout, match="first-token"):
            await _collect(backend)


@pytest.mark.asyncio
async def test_tool_call_heavy_stream() -> None:
    async def chat(_request: Request) -> StreamingResponse:
        async def gen() -> AsyncIterator[bytes]:
            # OpenAI-style fragmented tool call
            yield (
                "data: "
                + json.dumps(
                    {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "id": "call_1",
                                            "function": {"name": "lookup_hours", "arguments": ""},
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                )
                + "\n\n"
            ).encode()
            yield (
                "data: "
                + json.dumps(
                    {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "function": {"arguments": '{"call_id":"call-1"}'},
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                )
                + "\n\n"
            ).encode()
            yield _sse_done().encode()

        return StreamingResponse(gen(), media_type="text/event-stream")

    transport = httpx.ASGITransport(app=_make_app(chat))
    async with httpx.AsyncClient(transport=transport, base_url="http://hermes") as client:
        backend = HermesBackend("http://hermes", "k", client=client)
        deltas = await _collect(backend)

    kinds = [d.kind for d in deltas]
    assert "tool_event" in kinds
    assert kinds[-1] == "done"
    te = next(d.tool_event for d in deltas if d.kind == "tool_event")
    assert te is not None
    assert te.name == "lookup_hours"
    assert te.arguments.get("call_id") == "call-1"
    assert te.tool_call_id == "call_1"


@pytest.mark.asyncio
async def test_cancel_closes_stream() -> None:
    started = asyncio.Event()

    async def chat(_request: Request) -> StreamingResponse:
        async def gen() -> AsyncIterator[bytes]:
            yield _sse_chunk("one ").encode()
            started.set()
            await asyncio.sleep(2.0)
            yield _sse_chunk("two").encode()
            yield _sse_done().encode()

        return StreamingResponse(gen(), media_type="text/event-stream")

    transport = httpx.ASGITransport(app=_make_app(chat))
    async with httpx.AsyncClient(transport=transport, base_url="http://hermes") as client:
        backend = HermesBackend("http://hermes", "k", client=client)
        texts: list[str] = []
        kinds: list[str] = []
        async for d in backend.stream_reply(
            [Msg(role="user", content="hi")], call_id="c", turn_id="cancel-me"
        ):
            kinds.append(d.kind)
            if d.kind == "text" and d.text:
                texts.append(d.text)
                await started.wait()
                await backend.cancel("cancel-me")
        assert texts == ["one "]
        assert "done" not in kinds


@pytest.mark.asyncio
async def test_cassette_brain_wraps_hermes(tmp_path: Path) -> None:
    async def chat(_request: Request) -> StreamingResponse:
        async def gen() -> AsyncIterator[bytes]:
            yield _sse_chunk("cached").encode()
            yield _sse_done().encode()

        return StreamingResponse(gen(), media_type="text/event-stream")

    transport = httpx.ASGITransport(app=_make_app(chat))
    async with httpx.AsyncClient(transport=transport, base_url="http://hermes") as client:
        hermes = HermesBackend("http://hermes", "k", client=client, model="cassette-model")
        store = CassetteStore(tmp_path / "cassettes")
        budget = BudgetGuard(budget_usd=15.0, spend_usd=0.0)
        brain = CassetteBrain(
            hermes, store, mode=CassetteMode.RECORD, budget=budget, model="cassette-model"
        )
        # CassetteBrain hashes original messages; CALL_CONTEXT is added inside Hermes
        msgs = [Msg(role="user", content="cassette-prompt")]
        recorded = [d async for d in brain.stream_reply(msgs, call_id="c", turn_id="t0")]

    assert any(d.kind == "text" and d.text == "cached" for d in recorded)
    replay = CassetteBrain(
        HermesBackend("http://unused", "k"),  # must not be called
        store,
        mode=CassetteMode.REPLAY,
        model="cassette-model",
    )
    got = [d async for d in replay.stream_reply(msgs, call_id="other", turn_id="t1")]
    assert [(d.kind, d.text) for d in got] == [(d.kind, d.text) for d in recorded]


def test_inject_call_context_unit() -> None:
    msgs = [
        Msg(role="system", content="you are helpful"),
        Msg(role="user", content="hours?"),
    ]
    out = inject_call_context(msgs, call_id="c1", turn_id="t9")
    assert out[0].content == "you are helpful"
    assert "CALL_CONTEXT call_id=c1 turn_id=t9" in out[1].content
    assert out[1].content.endswith("hours?")


def test_toolset_selftest_passes_on_profile() -> None:
    proc = subprocess.run(
        [sys.executable, str(SELFTEST), "--config", str(HERMES_CONFIG)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "OK" in proc.stdout


def test_toolset_selftest_fails_on_dangerous_toolset(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "platform_toolsets:\n  api_server:\n    - hermes-api-server\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(SELFTEST), "--config", str(bad)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "FAIL" in proc.stderr


@pytest.mark.gpu
@pytest.mark.asyncio
async def test_live_hermes_optional() -> None:
    """Optional live smoke against local Hermes; skipped unless CALLSCOPE_HERMES_LIVE=1."""
    if os.environ.get("CALLSCOPE_HERMES_LIVE") != "1":
        pytest.skip("set CALLSCOPE_HERMES_LIVE=1 with a running Hermes API server")
    base = os.environ.get("CALLSCOPE_HERMES_BASE_URL", "http://127.0.0.1:8642")
    key = os.environ.get("CALLSCOPE_HERMES_API_KEY", "changeme-hermes-api")
    backend = HermesBackend(base, key, first_token_timeout_s=30.0)
    try:
        deltas = await _collect(backend, [Msg(role="user", content="Say hi in three words.")])
    finally:
        await backend.aclose()
    assert any(d.kind == "text" for d in deltas)
    assert deltas[-1].kind == "done"
