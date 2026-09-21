"""Plugin schema + handler tests (fake Business API via ASGI)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from apps.biz.main import create_app


@pytest.fixture
def biz_url(monkeypatch: pytest.MonkeyPatch) -> str:
    """Point BizClient at an in-process ASGI transport via env + shared client."""
    app = create_app(seed=42)
    transport = httpx.ASGITransport(app=app)
    # Sync TestClient for slot discovery in tests; handlers use AsyncClient.
    # Override BizClient base via env; inject AsyncClient through monkeypatch.
    monkeypatch.setenv("CALLSCOPE_BIZ_BASE_URL", "http://biz")

    real_client = httpx.AsyncClient(transport=transport, base_url="http://biz")

    import hermes_callscope.client as client_mod

    class Patched(client_mod.BizClient):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._client = real_client
            self._owns = False

    monkeypatch.setattr("hermes_callscope.tools.BizClient", Patched)
    monkeypatch.setattr("hermes_callscope.client.BizClient", Patched)
    return "http://biz"


def test_all_tool_schemas_have_call_id() -> None:
    from hermes_callscope.schemas import TOOL_MODELS, tool_json_schema

    for name in TOOL_MODELS:
        schema = tool_json_schema(name, "x")
        assert "call_id" in schema["parameters"]["properties"]
        assert "call_id" in schema["parameters"]["required"]


def test_book_requires_confirmation(biz_url: str) -> None:
    from hermes_callscope.tools import book_appointment

    raw = book_appointment(
        {
            "call_id": "c1",
            "customer_name": "A",
            "phone": "2065550100",
            "service_type": "hvac_repair",
            "slot_id": "nope",
            "address": "1 Main 98101",
            "confirmed": False,
        }
    )
    data = json.loads(raw)
    assert data["ok"] is False
    assert data["error"] == "missing_confirmation"


def test_lookup_faq_success(biz_url: str) -> None:
    from hermes_callscope.tools import lookup_faq

    raw = lookup_faq({"call_id": "c1", "query": "cancellation policy"})
    data = json.loads(raw)
    assert data["ok"] is True
    assert data["passages"]


def test_check_availability_and_book(biz_url: str) -> None:
    from hermes_callscope.tools import book_appointment, check_availability

    # Discover a real slot via biz TestClient for address ZIP
    with TestClient(create_app(seed=42)) as c:
        slots = c.get("/availability", params={"service_type": "hvac_repair"}).json()
    assert slots
    slot = slots[0]
    avail = json.loads(
        check_availability(
            {
                "call_id": "c1",
                "service_type": "hvac_repair",
                "date_from": "2026-09-21",
                "date_to": "2026-10-05",
                "zip": slot["zip_scope"][0],
            }
        )
    )
    assert avail["ok"] is True
    booked = json.loads(
        book_appointment(
            {
                "call_id": "c1",
                "customer_name": "Alex",
                "phone": "2065550100",
                "service_type": "hvac_repair",
                "slot_id": slot["slot_id"],
                "address": f"100 Main {slot['zip_scope'][0]}",
                "confirmed": True,
            }
        )
    )
    assert booked["ok"] is True
    assert booked["confirmation_code"].startswith("LHS-")


def test_entry_point_register() -> None:
    from hermes_callscope import TOOLSET, register

    registered: list[str] = []

    class Ctx:
        def register_tool(self, **kwargs: Any) -> None:
            registered.append(kwargs["name"])
            assert kwargs["toolset"] == TOOLSET

        def register_hook(self, _name: str, _fn: Any) -> None:
            return None

    register(Ctx())
    assert set(registered) == {
        "check_availability",
        "book_appointment",
        "reschedule_appointment",
        "cancel_appointment",
        "lookup_faq",
        "request_callback",
        "transfer_to_human",
    }


@pytest.mark.gpu
def test_hermes_discovers_plugin_optional() -> None:
    pytest.importorskip("hermes_agent")
    # Discovery against a live Hermes install is environment-specific.
    from importlib.metadata import entry_points

    eps = entry_points(group="hermes_agent.plugins")
    names = {e.name for e in eps}
    assert "callscope" in names
