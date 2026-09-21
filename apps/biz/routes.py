"""Business API routes (design §6.4)."""

from __future__ import annotations

import os
import re
import secrets
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from apps.biz.schemas import (
    AppointmentCreate,
    AppointmentOut,
    CallbackCreate,
    CallbackOut,
    KbHit,
    RescheduleBody,
    ResetOut,
    SlotOut,
)
from apps.biz.store import (
    CODE_RE,
    Appointment,
    BizStore,
    Callback,
    kb_search,
    make_confirmation_code,
    phone_last4,
    seed_store,
)

router = APIRouter()


def get_store(request: Request) -> BizStore:
    return request.app.state.store  # type: ignore[no-any-return]


StoreDep = Annotated[BizStore, Depends(get_store)]


def require_admin(authorization: Annotated[str | None, Header()] = None) -> None:
    expected = os.environ.get("CALLSCOPE_BIZ_ADMIN_TOKEN", "changeme-biz-admin")
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing admin bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="invalid admin token")


def _appt_out(store: BizStore, appt: Appointment) -> AppointmentOut:
    slot = store.slots.get(appt.slot_id)
    return AppointmentOut(
        confirmation_code=appt.confirmation_code,
        customer_name=appt.customer_name,
        phone_last4=phone_last4(appt.phone),
        address=appt.address,
        service_type=appt.service_type,
        slot_id=appt.slot_id,
        starts_at=slot.starts_at if slot else None,
        status=appt.status,
        notes=appt.notes,
    )


def _authorize(store: BizStore, code: str, last4: str) -> Appointment:
    if not CODE_RE.match(code):
        raise HTTPException(status_code=404, detail="appointment not found")
    appt = store.appointments.get(code)
    if appt is None:
        raise HTTPException(status_code=404, detail="appointment not found")
    if phone_last4(appt.phone) != last4:
        raise HTTPException(status_code=403, detail="phone last-4 mismatch")
    return appt


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/availability", response_model=list[SlotOut])
def availability(
    store: StoreDep,
    service_type: str = Query(...),
    zip: str | None = Query(None, alias="zip"),
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
) -> list[SlotOut]:
    if service_type not in store.services:
        raise HTTPException(status_code=400, detail="unknown service_type")
    out: list[SlotOut] = []
    for slot in store.slots.values():
        if not slot.is_open or slot.service_type != service_type:
            continue
        if zip and zip not in slot.zip_scope:
            continue
        if from_ and slot.starts_at < from_:
            continue
        if to and slot.starts_at > to:
            continue
        out.append(
            SlotOut(
                slot_id=slot.slot_id,
                service_type=slot.service_type,
                starts_at=slot.starts_at,
                ends_at=slot.ends_at,
                zip_scope=slot.zip_scope,
            )
        )
    out.sort(key=lambda s: s.starts_at)
    return out


@router.post("/appointments", response_model=AppointmentOut, status_code=201)
def create_appointment(
    body: AppointmentCreate,
    store: StoreDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> AppointmentOut:
    if body.service_type not in store.services:
        raise HTTPException(status_code=400, detail="unknown service_type")
    if idempotency_key:
        existing_code = store.idempotency.get(idempotency_key)
        if existing_code and existing_code in store.appointments:
            return _appt_out(store, store.appointments[existing_code])

    slot = store.slots.get(body.slot_id)
    if slot is None:
        raise HTTPException(status_code=400, detail="unknown slot_id")
    if slot.service_type != body.service_type:
        raise HTTPException(status_code=400, detail="slot service_type mismatch")
    if not slot.is_open:
        raise HTTPException(status_code=409, detail="slot already booked")

    # Extract ZIP from address if present for soft check
    zips = re.findall(r"\b(\d{5})\b", body.address)
    if zips and zips[-1] not in slot.zip_scope:
        raise HTTPException(status_code=400, detail="address ZIP not in slot scope")

    rng = __import__("random").Random(
        hash((store.seed, body.phone, body.slot_id, idempotency_key or "")) & 0xFFFFFFFF
    )
    code = make_confirmation_code(rng)
    while code in store.appointments:
        code = make_confirmation_code(rng)

    appt = Appointment(
        confirmation_code=code,
        customer_name=body.customer_name.strip(),
        phone=body.phone,
        address=body.address.strip(),
        service_type=body.service_type,
        slot_id=body.slot_id,
        notes=body.notes,
        status="booked",
        idempotency_key=idempotency_key,
        created_call_id=body.call_id,
        created_at=datetime.now(UTC),
    )
    slot.is_open = False
    store.appointments[code] = appt
    if idempotency_key:
        store.idempotency[idempotency_key] = code
    return _appt_out(store, appt)


@router.get("/appointments/{code}", response_model=AppointmentOut)
def get_appointment(
    code: str,
    store: StoreDep,
    phone_last4: str = Query(..., min_length=4, max_length=4),
) -> AppointmentOut:
    appt = _authorize(store, code, phone_last4)
    return _appt_out(store, appt)


@router.patch("/appointments/{code}", response_model=AppointmentOut)
def reschedule(
    code: str,
    body: RescheduleBody,
    store: StoreDep,
) -> AppointmentOut:
    appt = _authorize(store, code, body.phone_last4)
    if appt.status == "cancelled":
        raise HTTPException(status_code=409, detail="appointment cancelled")
    new_slot = store.slots.get(body.new_slot_id)
    if new_slot is None:
        raise HTTPException(status_code=400, detail="unknown slot_id")
    if new_slot.service_type != appt.service_type:
        raise HTTPException(status_code=400, detail="slot service_type mismatch")
    if not new_slot.is_open:
        raise HTTPException(status_code=409, detail="slot already booked")
    old = store.slots.get(appt.slot_id)
    if old is not None:
        old.is_open = True
    new_slot.is_open = False
    appt.slot_id = body.new_slot_id
    appt.status = "rescheduled"
    return _appt_out(store, appt)


@router.delete("/appointments/{code}", response_model=AppointmentOut)
def cancel(
    code: str,
    store: StoreDep,
    phone_last4: str = Query(..., min_length=4, max_length=4),
) -> AppointmentOut:
    appt = _authorize(store, code, phone_last4)
    if appt.status == "cancelled":
        return _appt_out(store, appt)
    slot = store.slots.get(appt.slot_id)
    if slot is not None:
        slot.is_open = True
    appt.status = "cancelled"
    return _appt_out(store, appt)


@router.get("/kb/search", response_model=list[KbHit])
def search_kb(
    store: StoreDep,
    q: str = Query(..., min_length=1),
    k: int = Query(3, ge=1, le=10),
) -> list[KbHit]:
    return [KbHit(**hit) for hit in kb_search(store, q, k=k)]


@router.post("/callbacks", response_model=CallbackOut, status_code=201)
def create_callback(body: CallbackCreate, store: StoreDep) -> CallbackOut:
    tid = f"CB-{len(store.callbacks) + 1:05d}-{phone_last4(body.phone)}"
    cb = Callback(
        ticket_id=tid,
        customer_name=body.customer_name.strip(),
        phone=body.phone,
        reason=body.reason.strip(),
        preferred_window=body.preferred_window,
        created_call_id=body.call_id,
        created_at=datetime.now(UTC),
    )
    store.callbacks[tid] = cb
    return CallbackOut(
        ticket_id=cb.ticket_id,
        customer_name=cb.customer_name,
        phone_last4=phone_last4(cb.phone),
        reason=cb.reason,
        preferred_window=cb.preferred_window,
    )


@router.post("/admin/reset", response_model=ResetOut, dependencies=[Depends(require_admin)])
def admin_reset(
    store: StoreDep,
    request: Request,
    seed: int = Query(42, ge=0, le=10_000),
) -> ResetOut:
    new_store = seed_store(seed)
    request.app.state.store = new_store
    return ResetOut(
        seed=new_store.seed,
        fingerprint=new_store.fingerprint(),
        services=len(new_store.services),
        slots=len(new_store.slots),
        kb_docs=len(new_store.kb),
    )
