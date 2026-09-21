"""Pydantic request/response models for the Business API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from apps.biz.store import PHONE_RE


class SlotOut(BaseModel):
    slot_id: str
    service_type: str
    starts_at: datetime
    ends_at: datetime
    zip_scope: list[str]


class AppointmentCreate(BaseModel):
    customer_name: str = Field(min_length=1, max_length=120)
    phone: str
    address: str = Field(min_length=3, max_length=240)
    service_type: str
    slot_id: str
    notes: str | None = None
    call_id: str | None = None

    @field_validator("phone")
    @classmethod
    def _phone10(cls, v: str) -> str:
        digits = "".join(c for c in v if c.isdigit())
        if not PHONE_RE.match(digits):
            raise ValueError("phone must be 10 digits")
        return digits


class AppointmentOut(BaseModel):
    confirmation_code: str
    customer_name: str
    phone_last4: str
    address: str
    service_type: str
    slot_id: str
    starts_at: datetime | None = None
    status: str
    notes: str | None = None


class RescheduleBody(BaseModel):
    new_slot_id: str
    phone_last4: str = Field(min_length=4, max_length=4)


class CancelQuery(BaseModel):
    phone_last4: str = Field(min_length=4, max_length=4)


class CallbackCreate(BaseModel):
    customer_name: str = Field(min_length=1, max_length=120)
    phone: str
    reason: str = Field(min_length=1, max_length=500)
    preferred_window: str | None = None
    call_id: str | None = None

    @field_validator("phone")
    @classmethod
    def _phone10(cls, v: str) -> str:
        digits = "".join(c for c in v if c.isdigit())
        if not PHONE_RE.match(digits):
            raise ValueError("phone must be 10 digits")
        return digits


class CallbackOut(BaseModel):
    ticket_id: str
    customer_name: str
    phone_last4: str
    reason: str
    preferred_window: str | None = None


class KbHit(BaseModel):
    doc_id: str
    title: str
    snippet: str
    score: float


class ResetOut(BaseModel):
    seed: int
    fingerprint: str
    services: int
    slots: int
    kb_docs: int
