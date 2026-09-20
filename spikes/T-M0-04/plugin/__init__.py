"""T-M0-04 stub receptionist tools + tool-call logging.

Tool registration verified against hermes-agent 0.19.0
(`PluginContext.register_tool` / `register_hook`).
Handlers receive ``(args: dict, **kwargs)`` per tools.registry.dispatch
and must return a JSON **string** (not a dict).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

_LOG_PATH = Path(
    os.environ.get("CALLSCOPE_S3_TOOL_LOG", "") or "results/tool_hooks.jsonl"
)
_TOOLSET = os.environ.get("CALLSCOPE_S3_TOOLSET", "callscope-s3")
_MAX = 400


def _truncate(value: Any) -> Any:
    if isinstance(value, str):
        return value if len(value) <= _MAX else value[:_MAX] + f"…(+{len(value) - _MAX})"
    if isinstance(value, (list, tuple)):
        return [_truncate(v) for v in value[:12]] + (
            [f"…(+{len(value) - 12} items)"] if len(value) > 12 else []
        )
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for i, (k, v) in enumerate(value.items()):
            if i >= 32:
                out["…"] = f"+{len(value) - 32} keys"
                break
            out[str(k)] = _truncate(v)
        return out
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _truncate(repr(value))


def _write(hook: str, payload: dict[str, Any]) -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": time.time(), "hook": hook, **payload}
    with _LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _schema(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str],
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


def _call_id_prop() -> dict[str, Any]:
    return {"type": "string", "description": "Active call_id from CALL_CONTEXT"}


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes"}


def _ok(payload: dict[str, Any]) -> str:
    """Hermes 0.19 tool handlers must return a string (JSON), not a dict."""
    return json.dumps(payload, ensure_ascii=False)


def register(ctx: Any) -> None:
    def pre_tool_call(**kwargs: Any) -> None:
        _write(
            "pre_tool_call",
            {
                "keys": sorted(kwargs.keys()),
                "kwargs": _truncate(kwargs),
            },
        )

    def post_tool_call(**kwargs: Any) -> None:
        _write(
            "post_tool_call",
            {
                "tool_name": kwargs.get("tool_name"),
                "args": _truncate(kwargs.get("args")),
                "status": kwargs.get("status"),
                "duration_ms": kwargs.get("duration_ms"),
                "error_type": kwargs.get("error_type"),
                "error_message": _truncate(kwargs.get("error_message")),
                "keys": sorted(kwargs.keys()),
            },
        )

    ctx.register_hook("pre_tool_call", pre_tool_call)
    ctx.register_hook("post_tool_call", post_tool_call)
    ctx.register_hook(
        "on_session_start",
        lambda **kw: _write("on_session_start", {"keys": sorted(kw.keys())}),
    )
    ctx.register_hook(
        "on_session_end",
        lambda **kw: _write("on_session_end", {"keys": sorted(kw.keys())}),
    )

    def lookup_faq(args: dict[str, Any], **_: Any) -> str:
        query = str(args.get("query") or "")
        call_id = str(args.get("call_id") or "")
        q = query.lower()
        if "hour" in q or "open" in q:
            answer = "Lakeside Home Services is open Mon–Sat 8:00–18:00."
        elif "area" in q or "service area" in q:
            answer = "We serve fictional Lakeside County within 25 miles of downtown."
        elif "price" in q or "cost" in q:
            answer = "Standard visit starts at $89; HVAC tune-up $149 (fictional)."
        else:
            answer = "I don't have that in the FAQ; I can take a callback."
        return _ok({"ok": True, "answer": answer, "call_id": call_id})

    def check_availability(args: dict[str, Any], **_: Any) -> str:
        return _ok(
            {
                "ok": True,
                "service": args.get("service", ""),
                "date": args.get("date", ""),
                "slots": ["09:00", "11:30", "15:00"],
                "call_id": args.get("call_id", ""),
            }
        )

    def book_appointment(args: dict[str, Any], **_: Any) -> str:
        call_id = args.get("call_id", "")
        if not _as_bool(args.get("confirmed")):
            return _ok(
                {
                    "ok": False,
                    "error": "missing_confirmation",
                    "message": "Set confirmed=true after read-back.",
                    "call_id": call_id,
                }
            )
        return _ok(
            {
                "ok": True,
                "confirmation_code": "LHS-1001",
                "service": args.get("service", ""),
                "date": args.get("date", ""),
                "time": args.get("time", ""),
                "name": args.get("name", ""),
                "phone": args.get("phone", ""),
                "call_id": call_id,
            }
        )

    def reschedule_appointment(args: dict[str, Any], **_: Any) -> str:
        call_id = args.get("call_id", "")
        if not _as_bool(args.get("confirmed")):
            return _ok(
                {
                    "ok": False,
                    "error": "missing_confirmation",
                    "message": "Set confirmed=true after read-back.",
                    "call_id": call_id,
                }
            )
        return _ok(
            {
                "ok": True,
                "confirmation_code": args.get("confirmation_code", ""),
                "new_date": args.get("new_date", ""),
                "new_time": args.get("new_time", ""),
                "call_id": call_id,
            }
        )

    def cancel_appointment(args: dict[str, Any], **_: Any) -> str:
        call_id = args.get("call_id", "")
        if not _as_bool(args.get("confirmed")):
            return _ok(
                {
                    "ok": False,
                    "error": "missing_confirmation",
                    "message": "Set confirmed=true after read-back.",
                    "call_id": call_id,
                }
            )
        return _ok(
            {
                "ok": True,
                "cancelled": args.get("confirmation_code", ""),
                "call_id": call_id,
            }
        )

    def take_callback(args: dict[str, Any], **_: Any) -> str:
        return _ok(
            {
                "ok": True,
                "ticket": "CB-42",
                "name": args.get("name", ""),
                "phone": args.get("phone", ""),
                "reason": args.get("reason", ""),
                "call_id": args.get("call_id", ""),
            }
        )

    def handoff_human(args: dict[str, Any], **_: Any) -> str:
        return _ok(
            {
                "ok": True,
                "queued": True,
                "reason": args.get("reason", ""),
                "call_id": args.get("call_id", ""),
            }
        )

    tools: list[tuple[str, str, dict[str, Any], list[str], Any]] = [
        (
            "lookup_faq",
            "Answer hours, service area, or price-range FAQs from the fictional KB.",
            {
                "query": {"type": "string", "description": "Caller question"},
                "call_id": _call_id_prop(),
            },
            ["query", "call_id"],
            lookup_faq,
        ),
        (
            "check_availability",
            "List open appointment slots for a service and date (YYYY-MM-DD).",
            {
                "service": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "call_id": _call_id_prop(),
            },
            ["service", "date", "call_id"],
            check_availability,
        ),
        (
            "book_appointment",
            "Book an appointment. Mutating: requires confirmed=true after read-back.",
            {
                "service": {"type": "string"},
                "date": {"type": "string"},
                "time": {"type": "string"},
                "name": {"type": "string"},
                "phone": {"type": "string", "description": "Digits only preferred"},
                "confirmed": {"type": "boolean"},
                "call_id": _call_id_prop(),
            },
            ["service", "date", "time", "name", "phone", "confirmed", "call_id"],
            book_appointment,
        ),
        (
            "reschedule_appointment",
            "Reschedule an existing booking. Mutating: requires confirmed=true.",
            {
                "confirmation_code": {"type": "string"},
                "new_date": {"type": "string"},
                "new_time": {"type": "string"},
                "confirmed": {"type": "boolean"},
                "call_id": _call_id_prop(),
            },
            ["confirmation_code", "new_date", "new_time", "confirmed", "call_id"],
            reschedule_appointment,
        ),
        (
            "cancel_appointment",
            "Cancel an existing booking. Mutating: requires confirmed=true.",
            {
                "confirmation_code": {"type": "string"},
                "confirmed": {"type": "boolean"},
                "call_id": _call_id_prop(),
            },
            ["confirmation_code", "confirmed", "call_id"],
            cancel_appointment,
        ),
        (
            "take_callback",
            "Record a callback request for a human dispatcher.",
            {
                "name": {"type": "string"},
                "phone": {"type": "string"},
                "reason": {"type": "string"},
                "call_id": _call_id_prop(),
            },
            ["name", "phone", "reason", "call_id"],
            take_callback,
        ),
        (
            "handoff_human",
            "Hand the caller to a human when out of scope or they insist.",
            {
                "reason": {"type": "string"},
                "call_id": _call_id_prop(),
            },
            ["reason", "call_id"],
            handoff_human,
        ),
    ]

    for name, desc, props, required, handler in tools:
        ctx.register_tool(
            name=name,
            toolset=_TOOLSET,
            schema=_schema(name, desc, props, required),
            handler=handler,
            description=desc,
        )
