"""Optional LangSmith tracing (default off) — fictional scrubbed text only.

Never uploads audio or raw PII. Postgres / FileEvalStore remain source of truth
(ADR-006). Enable with ``CALLSCOPE_LANGSMITH_ENABLED=true`` and ``LANGSMITH_API_KEY``.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

from callscope.observability.logging import scrub
from callscope.providers.base import BrainBackend, BrainDelta, Msg


def langsmith_enabled() -> bool:
    raw = os.environ.get("CALLSCOPE_LANGSMITH_ENABLED", "false").lower()
    return raw in {"1", "true", "yes"}


def require_api_key_if_enabled() -> str | None:
    """Return API key when enabled; raise if enabled without a key."""
    if not langsmith_enabled():
        return None
    key = os.environ.get("LANGSMITH_API_KEY") or os.environ.get("CALLSCOPE_LANGSMITH_API_KEY")
    if not key:
        raise RuntimeError("CALLSCOPE_LANGSMITH_ENABLED is true but LANGSMITH_API_KEY is missing")
    return key


def scrub_messages(messages: list[Msg]) -> list[dict[str, str]]:
    """Serialize messages with scrub(); drop any binary/audio fields."""
    out: list[dict[str, str]] = []
    for m in messages:
        out.append({"role": m.role, "content": scrub(m.content)})
    return out


def scrub_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Copy mapping as JSON-safe scrubbed strings; reject audio keys."""
    blocked = {"audio", "wav", "pcm", "recording", "bytes", "raw_audio"}
    clean: dict[str, Any] = {}
    for k, v in payload.items():
        if k.lower() in blocked:
            continue
        if isinstance(v, (bytes, bytearray, memoryview)):
            continue
        if isinstance(v, str):
            clean[k] = scrub(v)
        elif isinstance(v, (int, float, bool)) or v is None:
            clean[k] = v
        else:
            clean[k] = scrub(str(v))
    return clean


@dataclass
class NullTracer:
    """No-op tracer used when LangSmith is disabled."""

    def trace_brain_turn(
        self,
        *,
        call_id: str,
        turn_id: str,
        messages: list[Msg],
        reply_text: str,
    ) -> None:
        _ = (call_id, turn_id, messages, reply_text)

    def trace_eval_item(
        self,
        *,
        run_id: str,
        item_id: str,
        payload: Mapping[str, Any],
    ) -> None:
        _ = (run_id, item_id, payload)


class LangSmithTracer:
    """Thin wrapper around langsmith Client.run / create_run for text spans."""

    def __init__(self, *, api_key: str, project: str = "callscope") -> None:
        from langsmith import Client

        self._client = Client(api_key=api_key)
        self._project = project

    def trace_brain_turn(
        self,
        *,
        call_id: str,
        turn_id: str,
        messages: list[Msg],
        reply_text: str,
    ) -> None:
        inputs = {"messages": scrub_messages(messages), "call_id": call_id, "turn_id": turn_id}
        outputs = {"text": scrub(reply_text)}
        self._client.create_run(
            "brain.turn",
            inputs,
            "llm",
            project_name=self._project,
            outputs=outputs,
            extra={"metadata": {"call_id": call_id, "turn_id": turn_id, "no_audio": True}},
        )

    def trace_eval_item(
        self,
        *,
        run_id: str,
        item_id: str,
        payload: Mapping[str, Any],
    ) -> None:
        self._client.create_run(
            "eval.item",
            scrub_payload({"run_id": run_id, "item_id": item_id, **dict(payload)}),
            "chain",
            project_name=self._project,
            outputs={"ok": True},
            extra={"metadata": {"run_id": run_id, "item_id": item_id, "no_audio": True}},
        )


def build_tracer() -> NullTracer | LangSmithTracer:
    key = require_api_key_if_enabled()
    if key is None:
        return NullTracer()
    project = os.environ.get("LANGSMITH_PROJECT", "callscope")
    return LangSmithTracer(api_key=key, project=project)


@dataclass
class TracingBrain:
    """BrainBackend decorator that emits a LangSmith span after each reply."""

    inner: BrainBackend
    tracer: NullTracer | LangSmithTracer

    async def stream_reply(
        self,
        messages: list[Msg],
        *,
        call_id: str,
        turn_id: str,
    ) -> AsyncIterator[BrainDelta]:
        parts: list[str] = []
        async for delta in self.inner.stream_reply(messages, call_id=call_id, turn_id=turn_id):
            if delta.kind == "text" and delta.text:
                parts.append(delta.text)
            yield delta
        self.tracer.trace_brain_turn(
            call_id=call_id,
            turn_id=turn_id,
            messages=messages,
            reply_text="".join(parts),
        )

    async def cancel(self, turn_id: str) -> None:
        await self.inner.cancel(turn_id)
