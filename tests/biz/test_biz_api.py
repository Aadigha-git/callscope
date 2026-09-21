"""Business API contract + behaviour tests (T-M2-01)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openapi_spec_validator import validate

from apps.biz.main import create_app
from apps.biz.store import seed_store

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def client() -> TestClient:
    app = create_app(seed=42)
    with TestClient(app) as c:
        yield c


def test_same_seed_identical_fingerprint() -> None:
    a = seed_store(42)
    b = seed_store(42)
    assert a.fingerprint() == b.fingerprint()
    assert len(a.kb) >= 25
    assert len(a.services) == 3
    assert len(a.slots) > 20


def test_different_seed_different_fingerprint() -> None:
    assert seed_store(1).fingerprint() != seed_store(2).fingerprint()


def test_availability_and_book_idempotent(client: TestClient) -> None:
    slots = client.get("/availability", params={"service_type": "hvac_repair"}).json()
    assert isinstance(slots, list)
    assert slots
    slot_id = slots[0]["slot_id"]
    zip_code = slots[0]["zip_scope"][0]
    body = {
        "customer_name": "Alex Rivera",
        "phone": "2065550100",
        "address": f"100 Main St, Seattle WA {zip_code}",
        "service_type": "hvac_repair",
        "slot_id": slot_id,
    }
    r1 = client.post("/appointments", json=body, headers={"Idempotency-Key": "k-1"})
    assert r1.status_code == 201, r1.text
    code = r1.json()["confirmation_code"]
    r2 = client.post("/appointments", json=body, headers={"Idempotency-Key": "k-1"})
    assert r2.status_code == 201
    assert r2.json()["confirmation_code"] == code
    # Double-book same slot without idempotency key
    r3 = client.post(
        "/appointments",
        json={**body, "phone": "2065550199"},
        headers={"Idempotency-Key": "k-2"},
    )
    assert r3.status_code == 409


def test_auth_phone_last4(client: TestClient) -> None:
    slots = client.get("/availability", params={"service_type": "plumbing_repair"}).json()
    slot_id = slots[0]["slot_id"]
    created = client.post(
        "/appointments",
        json={
            "customer_name": "Sam",
            "phone": "4255550199",
            "address": "12 Pine Ave, Seattle WA " + slots[0]["zip_scope"][0],
            "service_type": "plumbing_repair",
            "slot_id": slot_id,
        },
    )
    assert created.status_code == 201
    code = created.json()["confirmation_code"]
    ok = client.get(f"/appointments/{code}", params={"phone_last4": "0199"})
    assert ok.status_code == 200
    bad = client.get(f"/appointments/{code}", params={"phone_last4": "0000"})
    assert bad.status_code == 403


def test_cancel_and_reschedule(client: TestClient) -> None:
    slots = client.get("/availability", params={"service_type": "maintenance_visit"}).json()
    assert len(slots) >= 2
    a, b = slots[0], slots[1]
    created = client.post(
        "/appointments",
        json={
            "customer_name": "Jo",
            "phone": "2065550111",
            "address": f"9 Oak Rd {a['zip_scope'][0]}",
            "service_type": "maintenance_visit",
            "slot_id": a["slot_id"],
        },
    )
    code = created.json()["confirmation_code"]
    rs = client.patch(
        f"/appointments/{code}",
        json={"new_slot_id": b["slot_id"], "phone_last4": "0111"},
    )
    assert rs.status_code == 200
    assert rs.json()["slot_id"] == b["slot_id"]
    assert rs.json()["status"] == "rescheduled"
    canc = client.delete(f"/appointments/{code}", params={"phone_last4": "0111"})
    assert canc.status_code == 200
    assert canc.json()["status"] == "cancelled"


def test_kb_search_and_gaps_doc(client: TestClient) -> None:
    hits = client.get("/kb/search", params={"q": "cancellation fee", "k": 3}).json()
    assert hits
    assert "cancel" in hits[0]["doc_id"] or "cancel" in hits[0]["title"].lower()
    gaps = (ROOT / "docs" / "kb_gaps.md").read_text(encoding="utf-8")
    assert "GAP-PRICE-EXACT" in gaps
    assert "GAP-WEEKEND-SURCHARGE" in gaps


def test_admin_reset(client: TestClient) -> None:
    denied = client.post("/admin/reset", params={"seed": 7})
    assert denied.status_code == 401
    ok = client.post(
        "/admin/reset",
        params={"seed": 7},
        headers={"Authorization": "Bearer changeme-biz-admin"},
    )
    assert ok.status_code == 200
    assert ok.json()["seed"] == 7
    assert ok.json()["fingerprint"] == seed_store(7).fingerprint()


def test_callback(client: TestClient) -> None:
    r = client.post(
        "/callbacks",
        json={
            "customer_name": "Pat",
            "phone": "2065550122",
            "reason": "No open slots this week",
        },
    )
    assert r.status_code == 201
    assert r.json()["ticket_id"].startswith("CB-")


def test_biz_openapi_valid() -> None:
    spec = __import__("yaml").safe_load(
        (ROOT / "docs" / "api" / "biz.openapi.yaml").read_text(encoding="utf-8")
    )
    validate(spec)


def test_no_list_all_endpoint(client: TestClient) -> None:
    assert client.get("/appointments").status_code in {404, 405}
