"""LangSmith tracing unit tests (no network)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from callscope.observability.langsmith_trace import (
    LangSmithTracer,
    NullTracer,
    TracingBrain,
    build_tracer,
    langsmith_enabled,
    require_api_key_if_enabled,
    scrub_messages,
    scrub_payload,
)
from callscope.providers.base import Msg
from callscope.providers.mock import MockBrain

pytestmark = pytest.mark.unit


def test_default_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CALLSCOPE_LANGSMITH_ENABLED", raising=False)
    assert langsmith_enabled() is False
    assert require_api_key_if_enabled() is None
    assert isinstance(build_tracer(), NullTracer)


def test_enabled_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CALLSCOPE_LANGSMITH_ENABLED", "true")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("CALLSCOPE_LANGSMITH_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="LANGSMITH_API_KEY"):
        require_api_key_if_enabled()


def test_scrub_messages_and_payload() -> None:
    msgs = scrub_messages([Msg(role="user", content="call me at 555-123-4567")])
    assert "[phone]" in msgs[0]["content"]
    clean = scrub_payload({"text": "a@b.com", "audio": b"wav", "pcm": "x", "n": 1})
    assert "audio" not in clean
    assert "pcm" not in clean
    assert clean["text"] == "[email]"
    assert clean["n"] == 1


def test_tracer_create_run_scrubbed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CALLSCOPE_LANGSMITH_ENABLED", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "ls-test-key")
    client = MagicMock()
    tracer = LangSmithTracer.__new__(LangSmithTracer)
    tracer._client = client
    tracer._project = "callscope"
    tracer.trace_brain_turn(
        call_id="c1",
        turn_id="t1",
        messages=[Msg(role="user", content="hi 555-000-1111")],
        reply_text="ok",
    )
    assert client.create_run.called
    args, kwargs = client.create_run.call_args
    # create_run(name, inputs, run_type, ...)
    inputs = args[1] if len(args) > 1 else kwargs.get("inputs", {})
    assert "[phone]" in inputs["messages"][0]["content"]
    blob = str(args) + str(kwargs)
    assert "wav" not in blob


@pytest.mark.asyncio
async def test_tracing_brain_delegates() -> None:
    brain = TracingBrain(inner=MockBrain(replies=["hello"], sleep=_noop), tracer=NullTracer())
    parts: list[str] = []
    async for d in brain.stream_reply([Msg(role="user", content="hi")], call_id="c", turn_id="t"):
        if d.kind == "text" and d.text:
            parts.append(d.text)
    assert "".join(parts) == "hello"


async def _noop(_s: float) -> None:
    return None
