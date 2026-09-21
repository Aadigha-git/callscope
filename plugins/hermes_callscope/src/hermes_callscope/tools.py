"""Tool handlers — return JSON strings for Hermes 0.19.0."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from hermes_callscope.client import BizClient
from hermes_callscope.schemas import (
    BookAppointmentArgs,
    CancelArgs,
    CheckAvailabilityArgs,
    LookupFaqArgs,
    RequestCallbackArgs,
    RescheduleArgs,
    TransferArgs,
)

logger = logging.getLogger("hermes_callscope.tools")

# Optional metrics (available when callscope is installed).
try:
    from callscope.observability import metrics as _metrics
except Exception:
    _metrics = None


def _ok(payload: dict[str, Any]) -> str:
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)


def _err(code: str, message: str, **extra: Any) -> str:
    return json.dumps({"ok": False, "error": code, "message": message, **extra}, ensure_ascii=False)


def _run(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Hermes may call sync handlers from an async context — use a bridge thread.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _inc(name: str, status: str) -> None:
    if _metrics is None:
        return
    try:
        _metrics.TOOL_CALLS.labels(name=name, status=status).inc()
    except Exception:
        pass


def _client() -> BizClient:
    return BizClient()


def check_availability(args: dict[str, Any], **_kwargs: Any) -> str:
    try:
        a = CheckAvailabilityArgs.model_validate(args)
    except Exception as exc:
        _inc("check_availability", "error")
        return _err("validation", str(exc))

    async def _go() -> str:
        client = _client()
        try:
            res = await client.get_json(
                "/availability",
                params={
                    "service_type": a.service_type,
                    "from": f"{a.date_from}T00:00:00Z",
                    "to": f"{a.date_to}T23:59:59Z",
                    "zip": a.zip,
                },
            )
            if res["status_code"] >= 400:
                _inc("check_availability", "error")
                return _err("biz_error", str(res["body"]), status_code=res["status_code"])
            slots = [
                {
                    "slot_id": s["slot_id"],
                    "start": s["starts_at"],
                    "end": s["ends_at"],
                }
                for s in res["body"]
            ]
            _inc("check_availability", "ok")
            return _ok({"slots": slots})
        finally:
            await client.aclose()

    return _run(_go())


def book_appointment(args: dict[str, Any], **_kwargs: Any) -> str:
    try:
        a = BookAppointmentArgs.model_validate(args)
    except Exception as exc:
        _inc("book_appointment", "error")
        return _err("validation", str(exc))
    if not a.confirmed:
        _inc("book_appointment", "denied")
        return _err(
            "missing_confirmation",
            "missing confirmation: read back the details and ask the caller to confirm before booking",
        )

    async def _go() -> str:
        client = _client()
        try:
            res = await client.post_json(
                "/appointments",
                json={
                    "customer_name": a.customer_name,
                    "phone": a.phone,
                    "service_type": a.service_type,
                    "slot_id": a.slot_id,
                    "address": a.address,
                    "notes": a.notes,
                    "call_id": a.call_id,
                },
                headers={"Idempotency-Key": f"{a.call_id}:{a.slot_id}:{a.phone}"},
            )
            if res["status_code"] >= 400:
                _inc("book_appointment", "error")
                return _err("biz_error", str(res["body"]), status_code=res["status_code"])
            body = res["body"]
            _inc("book_appointment", "ok")
            return _ok(
                {
                    "confirmation_code": body.get("confirmation_code"),
                    "start": body.get("starts_at"),
                    "status": body.get("status"),
                }
            )
        finally:
            await client.aclose()

    return _run(_go())


def reschedule_appointment(args: dict[str, Any], **_kwargs: Any) -> str:
    try:
        a = RescheduleArgs.model_validate(args)
    except Exception as exc:
        _inc("reschedule_appointment", "error")
        return _err("validation", str(exc))
    if not a.confirmed:
        _inc("reschedule_appointment", "denied")
        return _err(
            "missing_confirmation",
            "missing confirmation: read back the new time and ask the caller to confirm",
        )

    async def _go() -> str:
        client = _client()
        try:
            res = await client.patch_json(
                f"/appointments/{a.confirmation_code}",
                json={"new_slot_id": a.new_slot_id, "phone_last4": a.phone_last4},
            )
            if res["status_code"] >= 400:
                _inc("reschedule_appointment", "error")
                return _err("biz_error", str(res["body"]), status_code=res["status_code"])
            _inc("reschedule_appointment", "ok")
            return _ok(res["body"] if isinstance(res["body"], dict) else {"result": res["body"]})
        finally:
            await client.aclose()

    return _run(_go())


def cancel_appointment(args: dict[str, Any], **_kwargs: Any) -> str:
    try:
        a = CancelArgs.model_validate(args)
    except Exception as exc:
        _inc("cancel_appointment", "error")
        return _err("validation", str(exc))
    if not a.confirmed:
        _inc("cancel_appointment", "denied")
        return _err(
            "missing_confirmation",
            "missing confirmation: confirm the caller wants to cancel before proceeding",
        )

    async def _go() -> str:
        client = _client()
        try:
            res = await client.delete(
                f"/appointments/{a.confirmation_code}",
                params={"phone_last4": a.phone_last4},
            )
            if res["status_code"] >= 400:
                _inc("cancel_appointment", "error")
                return _err("biz_error", str(res["body"]), status_code=res["status_code"])
            _inc("cancel_appointment", "ok")
            return _ok({"status": res["body"].get("status", "cancelled")})
        finally:
            await client.aclose()

    return _run(_go())


def lookup_faq(args: dict[str, Any], **_kwargs: Any) -> str:
    try:
        a = LookupFaqArgs.model_validate(args)
    except Exception as exc:
        _inc("lookup_faq", "error")
        return _err("validation", str(exc))

    async def _go() -> str:
        client = _client()
        try:
            res = await client.get_json("/kb/search", params={"q": a.query, "k": 3})
            if res["status_code"] >= 400:
                _inc("lookup_faq", "error")
                return _err("biz_error", str(res["body"]), status_code=res["status_code"])
            passages = [
                {"doc_id": h["doc_id"], "text": h.get("snippet") or h.get("title", "")}
                for h in res["body"]
            ]
            _inc("lookup_faq", "ok")
            return _ok({"passages": passages})
        finally:
            await client.aclose()

    return _run(_go())


def request_callback(args: dict[str, Any], **_kwargs: Any) -> str:
    try:
        a = RequestCallbackArgs.model_validate(args)
    except Exception as exc:
        _inc("request_callback", "error")
        return _err("validation", str(exc))
    if not a.confirmed:
        _inc("request_callback", "denied")
        return _err(
            "missing_confirmation",
            "missing confirmation: confirm callback details with the caller first",
        )

    async def _go() -> str:
        client = _client()
        try:
            res = await client.post_json(
                "/callbacks",
                json={
                    "customer_name": a.customer_name,
                    "phone": a.phone,
                    "reason": a.reason,
                    "preferred_window": a.preferred_window,
                    "call_id": a.call_id,
                },
            )
            if res["status_code"] >= 400:
                _inc("request_callback", "error")
                return _err("biz_error", str(res["body"]), status_code=res["status_code"])
            _inc("request_callback", "ok")
            return _ok({"ticket_id": res["body"].get("ticket_id")})
        finally:
            await client.aclose()

    return _run(_go())


def transfer_to_human(args: dict[str, Any], **_kwargs: Any) -> str:
    try:
        a = TransferArgs.model_validate(args)
    except Exception as exc:
        _inc("transfer_to_human", "error")
        return _err("validation", str(exc))
    if not a.confirmed:
        _inc("transfer_to_human", "denied")
        return _err(
            "missing_confirmation",
            "missing confirmation: confirm the caller wants a human before transferring",
        )
    _inc("transfer_to_human", "ok")
    return _ok({"status": "simulated", "reason": a.reason, "handoff_id": str(uuid.uuid4())})


HANDLERS = {
    "check_availability": check_availability,
    "book_appointment": book_appointment,
    "reschedule_appointment": reschedule_appointment,
    "cancel_appointment": cancel_appointment,
    "lookup_faq": lookup_faq,
    "request_callback": request_callback,
    "transfer_to_human": transfer_to_human,
}

DESCRIPTIONS = {
    "check_availability": "List open appointment slots for a service type and ZIP.",
    "book_appointment": "Book a slot. Mutating: requires confirmed=true after read-back.",
    "reschedule_appointment": "Move a booking to a new slot. Requires confirmed=true.",
    "cancel_appointment": "Cancel a booking. Requires confirmed=true.",
    "lookup_faq": "Search the Lakeside FAQ knowledge base (grounding source).",
    "request_callback": "Open a human callback ticket. Requires confirmed=true.",
    "transfer_to_human": "Simulate handoff to a human agent. Requires confirmed=true.",
}
