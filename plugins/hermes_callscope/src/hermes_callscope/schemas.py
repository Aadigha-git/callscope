"""Pydantic models + JSON Schema for receptionist tools (design §4.4)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

SERVICE_TYPES = ("hvac_repair", "plumbing_repair", "maintenance_visit")


class CallIdMixin(BaseModel):
    call_id: str = Field(min_length=1, description="Active call_id from CALL_CONTEXT")


class CheckAvailabilityArgs(CallIdMixin):
    service_type: Literal["hvac_repair", "plumbing_repair", "maintenance_visit"]
    date_from: str = Field(description="ISO date YYYY-MM-DD")
    date_to: str = Field(description="ISO date YYYY-MM-DD")
    zip: str = Field(min_length=5, max_length=10)


class BookAppointmentArgs(CallIdMixin):
    customer_name: str = Field(min_length=1)
    phone: str
    service_type: Literal["hvac_repair", "plumbing_repair", "maintenance_visit"]
    slot_id: str
    address: str = Field(min_length=3)
    notes: str | None = None
    confirmed: bool = False

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        digits = "".join(c for c in v if c.isdigit())
        if len(digits) != 10:
            raise ValueError("phone must be 10 digits")
        return digits


class RescheduleArgs(CallIdMixin):
    confirmation_code: str
    new_slot_id: str
    phone_last4: str = Field(min_length=4, max_length=4)
    confirmed: bool = False


class CancelArgs(CallIdMixin):
    confirmation_code: str
    phone_last4: str = Field(min_length=4, max_length=4)
    confirmed: bool = False


class LookupFaqArgs(CallIdMixin):
    query: str = Field(min_length=1)


class RequestCallbackArgs(CallIdMixin):
    customer_name: str = Field(min_length=1)
    phone: str
    reason: str = Field(min_length=1)
    preferred_window: str | None = None
    confirmed: bool = False

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        digits = "".join(c for c in v if c.isdigit())
        if len(digits) != 10:
            raise ValueError("phone must be 10 digits")
        return digits


class TransferArgs(CallIdMixin):
    reason: str = Field(min_length=1)
    confirmed: bool = False


TOOL_MODELS: dict[str, type[BaseModel]] = {
    "check_availability": CheckAvailabilityArgs,
    "book_appointment": BookAppointmentArgs,
    "reschedule_appointment": RescheduleArgs,
    "cancel_appointment": CancelArgs,
    "lookup_faq": LookupFaqArgs,
    "request_callback": RequestCallbackArgs,
    "transfer_to_human": TransferArgs,
}

MUTATING_TOOLS = frozenset(
    {
        "book_appointment",
        "reschedule_appointment",
        "cancel_appointment",
        "request_callback",
        "transfer_to_human",
    }
)


def tool_json_schema(name: str, description: str) -> dict[str, Any]:
    model = TOOL_MODELS[name]
    schema = model.model_json_schema()
    # Hermes expects OpenAI-ish {name, description, parameters}
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": schema.get("properties", {}),
            "required": schema.get("required", []),
        },
    }
