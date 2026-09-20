"""T-M0-02 probe plugin — log hook kwargs (keys + truncated values).

Hook names and PluginContext.register_hook were verified against installed
hermes-agent 0.19.0 (`hermes_cli.plugins.VALID_HOOKS` / `PluginContext`).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

_LOG_PATH = Path(os.environ.get("CALLSCOPE_S1_HOOK_LOG", "") or "results/hook_kwargs.jsonl")
_MAX = 240


def _truncate(value: Any) -> Any:
    if isinstance(value, str):
        return value if len(value) <= _MAX else value[:_MAX] + f"…(+{len(value) - _MAX} chars)"
    if isinstance(value, (list, tuple)):
        return [_truncate(v) for v in value[:8]] + ([f"…(+{len(value) - 8} items)"] if len(value) > 8 else [])
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for i, (k, v) in enumerate(value.items()):
            if i >= 24:
                out["…"] = f"+{len(value) - 24} keys"
                break
            out[str(k)] = _truncate(v)
        return out
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _truncate(repr(value))


def _write(hook: str, kwargs: dict[str, Any]) -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": time.time(),
        "hook": hook,
        "keys": sorted(kwargs.keys()),
        "kwargs": _truncate(kwargs),
    }
    with _LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _make(hook: str):
    def _cb(**kwargs: Any) -> None:
        _write(hook, kwargs)

    return _cb


def register(ctx: Any) -> None:
    for name in (
        "pre_llm_call",
        "post_llm_call",
        "pre_tool_call",
        "post_tool_call",
        "on_session_start",
        "on_session_end",
    ):
        ctx.register_hook(name, _make(name))

    def probe_echo_call_id(call_id: str = "", **_kwargs: Any) -> dict[str, str]:
        _write(
            "tool.probe_echo_call_id",
            {"call_id_arg": call_id, "tool_kwargs_keys": sorted(_kwargs.keys())},
        )
        return {"ok": "true", "echoed_call_id": call_id}

    ctx.register_tool(
        name="probe_echo_call_id",
        toolset="hermes-api-server",
        schema={
            "name": "probe_echo_call_id",
            "description": "Spike probe: echo call_id tool argument",
            "parameters": {
                "type": "object",
                "properties": {
                    "call_id": {"type": "string", "description": "Correlation id"},
                },
                "required": ["call_id"],
            },
        },
        handler=probe_echo_call_id,
        description="Spike probe: echo call_id tool argument",
    )
