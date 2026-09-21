"""Hermes Agent API server as a BrainBackend (T-M1-09).

Verified against hermes-agent 0.19.0 spikes (T-M0-02 / T-M0-03):
OpenAI-compatible ``POST /v1/chat/completions`` with ``stream=true`` SSE.
CALL_CONTEXT lives in **user** message content (D-20260920-04).
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Mapping, MutableMapping
from typing import Any

import httpx

from callscope.providers.base import (
    BrainDelta,
    Msg,
    ProviderError,
    ProviderTimeout,
    ProviderUnavailable,
    ToolEvent,
)

DEFAULT_FIRST_TOKEN_TIMEOUT_S = 8.0
_CALL_CONTEXT_PREFIX = "CALL_CONTEXT"


def format_call_context(call_id: str, turn_id: str) -> str:
    """User-message prefix so hooks see CallScope IDs (D-20260920-04)."""
    return f"{_CALL_CONTEXT_PREFIX} call_id={call_id} turn_id={turn_id}"


def inject_call_context(
    messages: list[Msg],
    *,
    call_id: str,
    turn_id: str,
    interruption_note: str | None = None,
) -> list[Msg]:
    """Return a copy of ``messages`` with CALL_CONTEXT on the last user turn.

    If there is no user message, appends one containing only the context line.
    Optional ``interruption_note`` is prepended (barge-in / cancel recovery).
    """
    ctx = format_call_context(call_id, turn_id)
    parts: list[str] = []
    if interruption_note:
        parts.append(interruption_note.strip())
    parts.append(ctx)

    out = list(messages)
    for i in range(len(out) - 1, -1, -1):
        if out[i].role == "user":
            body = out[i].content.strip()
            prefix = "\n".join(parts)
            content = f"{prefix}\n{body}" if body else prefix
            out[i] = Msg(
                role="user",
                content=content,
                name=out[i].name,
                tool_call_id=out[i].tool_call_id,
            )
            return out
    out.append(Msg(role="user", content="\n".join(parts)))
    return out


def messages_to_openai(messages: list[Msg]) -> list[dict[str, Any]]:
    """Map CallScope ``Msg`` list to OpenAI chat message dicts."""
    payload: list[dict[str, Any]] = []
    for m in messages:
        item: dict[str, Any] = {"role": m.role, "content": m.content}
        if m.name is not None:
            item["name"] = m.name
        if m.tool_call_id is not None:
            item["tool_call_id"] = m.tool_call_id
        payload.append(item)
    return payload


def _parse_sse_data(payload: str) -> Mapping[str, Any] | None:
    if payload == "[DONE]":
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict):
        return data
    return None


class _ToolCallAssembler:
    """Accumulate streamed OpenAI-style tool_calls deltas into ToolEvents."""

    def __init__(self) -> None:
        self._by_index: dict[int, dict[str, Any]] = {}

    def feed(self, tool_calls: list[Any]) -> list[ToolEvent]:
        """Ingest a delta tool_calls list; emit events when JSON args become valid."""
        emitted: list[ToolEvent] = []
        for raw in tool_calls:
            if not isinstance(raw, Mapping):
                continue
            idx = int(raw.get("index") or 0)
            slot = self._by_index.setdefault(
                idx, {"id": None, "name": None, "arguments": "", "emitted": False}
            )
            if raw.get("id"):
                slot["id"] = str(raw["id"])
            fn = raw.get("function")
            if isinstance(fn, Mapping):
                if fn.get("name"):
                    slot["name"] = str(fn["name"])
                if fn.get("arguments"):
                    slot["arguments"] = str(slot["arguments"]) + str(fn["arguments"])
            if slot["emitted"] or not slot["name"]:
                continue
            args_text = str(slot["arguments"] or "").strip()
            if not args_text:
                continue
            try:
                args = json.loads(args_text)
            except json.JSONDecodeError:
                continue
            if not isinstance(args, dict):
                args = {"_raw": args}
            emitted.append(
                ToolEvent(
                    name=str(slot["name"]),
                    arguments=args,
                    tool_call_id=str(slot["id"]) if slot["id"] else None,
                )
            )
            slot["emitted"] = True
        return emitted

    def flush_partial(self) -> list[ToolEvent]:
        """Emit remaining tool calls with best-effort args at stream end."""
        out: list[ToolEvent] = []
        for slot in self._by_index.values():
            if slot["emitted"] or not slot["name"]:
                continue
            args_text = str(slot["arguments"] or "").strip()
            try:
                args: dict[str, Any] = json.loads(args_text) if args_text else {}
            except json.JSONDecodeError:
                args = {"_raw": args_text}
            if not isinstance(args, dict):
                args = {"_raw": args}
            out.append(
                ToolEvent(
                    name=str(slot["name"]),
                    arguments=args,
                    tool_call_id=str(slot["id"]) if slot["id"] else None,
                )
            )
            slot["emitted"] = True
        return out


class HermesBackend:
    """``BrainBackend`` over Hermes OpenAI-compatible API server."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        model: str = "nvidia/Nemotron-3_5-Lightning",
        first_token_timeout_s: float = DEFAULT_FIRST_TOKEN_TIMEOUT_S,
        timeout_s: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._first_token_timeout_s = first_token_timeout_s
        self._timeout_s = timeout_s
        self._client = client
        self._owns_client = client is None
        self._cancelled: set[str] = set()
        self._active: MutableMapping[str, httpx.Response] = {}

    @property
    def model(self) -> str:
        return self._model

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def cancel(self, turn_id: str) -> None:
        self._cancelled.add(turn_id)
        resp = self._active.pop(turn_id, None)
        if resp is not None:
            await resp.aclose()

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout_s)
        return self._client

    async def stream_reply(
        self,
        messages: list[Msg],
        *,
        call_id: str,
        turn_id: str,
        interruption_note: str | None = None,
    ) -> AsyncIterator[BrainDelta]:
        self._cancelled.discard(turn_id)
        prepared = inject_call_context(
            messages,
            call_id=call_id,
            turn_id=turn_id,
            interruption_note=interruption_note,
        )
        body = {
            "model": self._model,
            "messages": messages_to_openai(prepared),
            "stream": True,
            "user": call_id,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Call-Id": call_id,
            "X-Turn-Id": turn_id,
        }
        url = f"{self._base}/v1/chat/completions"
        client = self._get_client()
        deadline = time.monotonic() + self._first_token_timeout_s
        got_first = False
        assembler = _ToolCallAssembler()

        try:
            req = client.build_request("POST", url, headers=headers, json=body)
            resp = await client.send(req, stream=True)
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"Hermes connect/read timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"Hermes unreachable: {exc}") from exc

        self._active[turn_id] = resp
        try:
            if resp.status_code >= 400:
                err_body = (await resp.aread()).decode("utf-8", errors="replace")[:300]
                if resp.status_code in {502, 503, 504}:
                    raise ProviderUnavailable(f"Hermes HTTP {resp.status_code}: {err_body}")
                raise ProviderError(f"Hermes HTTP {resp.status_code}: {err_body}")

            line_iter = resp.aiter_lines().__aiter__()
            while True:
                if turn_id in self._cancelled:
                    break
                try:
                    if not got_first:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise ProviderTimeout(
                                f"Hermes first-token timeout ({self._first_token_timeout_s}s)"
                            )
                        line = await asyncio.wait_for(line_iter.__anext__(), timeout=remaining)
                    else:
                        line = await line_iter.__anext__()
                except StopAsyncIteration:
                    break
                except TimeoutError as exc:
                    raise ProviderTimeout(
                        f"Hermes first-token timeout ({self._first_token_timeout_s}s)"
                    ) from exc

                if not line or line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                chunk = _parse_sse_data(payload)
                if chunk is None:
                    continue

                # OpenAI error object mid-stream
                if "error" in chunk and not chunk.get("choices"):
                    err = chunk.get("error")
                    msg = err.get("message") if isinstance(err, Mapping) else str(err)
                    raise ProviderError(f"Hermes stream error: {msg}")

                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                if not isinstance(delta, Mapping):
                    continue

                content = delta.get("content")
                if content:
                    got_first = True
                    yield BrainDelta(kind="text", text=str(content))

                tool_calls = delta.get("tool_calls")
                if isinstance(tool_calls, list):
                    for te in assembler.feed(tool_calls):
                        got_first = True
                        yield BrainDelta(kind="tool_event", tool_event=te)

            for te in assembler.flush_partial():
                if turn_id in self._cancelled:
                    break
                got_first = True
                yield BrainDelta(kind="tool_event", tool_event=te)

            if turn_id not in self._cancelled:
                if not got_first:
                    raise ProviderTimeout(
                        f"Hermes first-token timeout ({self._first_token_timeout_s}s)"
                    )
                yield BrainDelta(kind="done")
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"Hermes stream timeout: {exc}") from exc
        except (ProviderError, ProviderTimeout, ProviderUnavailable):
            raise
        except httpx.HTTPError as exc:
            if turn_id in self._cancelled:
                return
            raise ProviderUnavailable(f"Hermes stream failed: {exc}") from exc
        finally:
            self._active.pop(turn_id, None)
            await resp.aclose()


__all__ = [
    "DEFAULT_FIRST_TOKEN_TIMEOUT_S",
    "HermesBackend",
    "format_call_context",
    "inject_call_context",
    "messages_to_openai",
]
