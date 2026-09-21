"""Pure pre_tool_call policy (design §4.4). T-M2-03."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Literal

PHONE_RE = re.compile(r"^\d{10}$")
CODE_RE = re.compile(r"^LHS-[A-Z0-9]{6}$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

MUTATING = frozenset(
    {
        "book_appointment",
        "reschedule_appointment",
        "cancel_appointment",
        "request_callback",
        "transfer_to_human",
    }
)

PER_CALL_BUDGET = 12
PER_TOOL_RATE = 6  # max invocations of the same tool per call
RATE_WINDOW_S = 600.0


@dataclass(frozen=True)
class Allow:
    kind: Literal["allow"] = "allow"


@dataclass(frozen=True)
class Deny:
    rule: str
    message: str
    kind: Literal["deny"] = "deny"


Decision = Allow | Deny


@dataclass
class CallToolState:
    """Per-call counters for budget / rate limits."""

    total: int = 0
    by_tool: dict[str, list[float]] = field(default_factory=dict)


@dataclass
class PolicyState:
    """Mutable policy context shared across turns of a call."""

    active_call_ids: set[str] = field(default_factory=set)
    calls: dict[str, CallToolState] = field(default_factory=dict)

    def register_call(self, call_id: str) -> None:
        self.active_call_ids.add(call_id)
        self.calls.setdefault(call_id, CallToolState())

    def end_call(self, call_id: str) -> None:
        self.active_call_ids.discard(call_id)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes"}


def evaluate(tool_name: str, args: dict[str, Any], state: PolicyState) -> Decision:
    """Return Allow or Deny for a tool invocation."""
    call_id = str(args.get("call_id") or "").strip()
    if not call_id:
        return Deny("missing_call_id", "call_id is required on every tool")
    if call_id not in state.active_call_ids:
        return Deny(
            "inactive_call",
            "call_id is not an active call; refuse and ask the caller to reconnect",
        )

    cts = state.calls.setdefault(call_id, CallToolState())
    if cts.total >= PER_CALL_BUDGET:
        return Deny(
            "tool_budget",
            f"tool budget exhausted ({PER_CALL_BUDGET} calls); offer a callback instead",
        )

    now = time.monotonic()
    stamps = [t for t in cts.by_tool.get(tool_name, []) if now - t < RATE_WINDOW_S]
    if len(stamps) >= PER_TOOL_RATE:
        return Deny(
            "tool_rate_limit",
            f"too many {tool_name} calls; slow down and confirm with the caller",
        )

    if tool_name in MUTATING and not _as_bool(args.get("confirmed")):
        return Deny(
            "missing_confirmation",
            "missing confirmation: read back the details and ask the caller to confirm "
            "before calling this tool again with confirmed=true",
        )

    # Schema / regex validation (lightweight; handlers still validate).
    if tool_name in {
        "book_appointment",
        "request_callback",
    }:
        phone = "".join(c for c in str(args.get("phone") or "") if c.isdigit())
        if not PHONE_RE.match(phone):
            return Deny("invalid_phone", "phone must be a 10-digit US number")

    if tool_name in {"reschedule_appointment", "cancel_appointment"}:
        code = str(args.get("confirmation_code") or "")
        if not CODE_RE.match(code):
            return Deny("invalid_confirmation_code", "confirmation_code format must be LHS-XXXXXX")
        last4 = str(args.get("phone_last4") or "")
        if not re.fullmatch(r"\d{4}", last4):
            return Deny("invalid_phone_last4", "phone_last4 must be exactly 4 digits")

    if tool_name == "check_availability":
        for key in ("date_from", "date_to"):
            raw = str(args.get(key) or "")
            if not ISO_DATE_RE.match(raw):
                return Deny("invalid_date", f"{key} must be an ISO date YYYY-MM-DD")
            try:
                d = date.fromisoformat(raw)
            except ValueError:
                return Deny("invalid_date", f"{key} is not a valid calendar date")
            if d < datetime.now(UTC).date():
                return Deny("date_in_past", f"{key} must be today or in the future")

    # Record usage only on Allow path (caller should call record_success after).
    return Allow()


def record_success(tool_name: str, call_id: str, state: PolicyState) -> None:
    cts = state.calls.setdefault(call_id, CallToolState())
    cts.total += 1
    cts.by_tool.setdefault(tool_name, []).append(time.monotonic())
