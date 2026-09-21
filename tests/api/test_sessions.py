"""CallScope API unit + contract tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from openapi_spec_validator import validate
from openapi_spec_validator.readers import read_from_filename

from apps.api.deps import WorkerStatus, build_api_state
from apps.api.livekit_tokens import LiveKitTokenMinter
from apps.api.main import create_app
from apps.api.ratelimit import SessionCapLimiter
from apps.api.store import MemoryCallStore
from callscope.config import Settings

pytestmark = pytest.mark.unit

POLICY = "2026-09-20"
SERVICE = "test-service-token"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("CALLSCOPE_POLICY_VERSION", POLICY)
    monkeypatch.setenv("CALLSCOPE_SERVICE_TOKEN", SERVICE)
    settings = Settings(
        livekit_url="ws://127.0.0.1:7880",
        livekit_api_key="devkey",
        livekit_api_secret="secret",
    )
    state = build_api_state(
        settings=settings,
        store=MemoryCallStore(),
        limiter=SessionCapLimiter(max_concurrent=2),
        tokens=LiveKitTokenMinter("devkey", "secret"),
        worker=WorkerStatus(online=True, stack_label="test-stack"),
    )
    assert state.policy_version == POLICY
    assert state.service_token == SERVICE
    app = create_app(state)
    with TestClient(app) as c:
        yield c


def test_status_online(client: TestClient) -> None:
    r = client.get("/v1/status")
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "online"
    assert body["max_concurrent"] == 2
    assert body["stack_label"] == "test-stack"


def test_session_requires_consent(client: TestClient) -> None:
    r = client.post(
        "/v1/sessions",
        json={"consent_recording": False, "policy_version": POLICY},
    )
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")


def test_session_policy_mismatch(client: TestClient) -> None:
    r = client.post(
        "/v1/sessions",
        json={"consent_recording": True, "policy_version": "wrong"},
    )
    assert r.status_code == 403
    assert r.json()["code"] == "policy_mismatch"


def test_session_creates_token_ttl_5_min(client: TestClient) -> None:
    r = client.post(
        "/v1/sessions",
        json={"consent_recording": True, "policy_version": POLICY, "consent_donate": False},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["max_duration_s"] == 240
    assert body["livekit_url"].startswith("ws://")
    assert body["room"].startswith("call-")
    claims = jwt.decode(body["token"], options={"verify_signature": False})
    video = claims["video"]
    assert video["room"] == body["room"]
    assert video["roomJoin"] is True
    assert video["canPublish"] is True
    assert video["canSubscribe"] is True
    exp = datetime.fromtimestamp(claims["exp"], tz=UTC)
    now = datetime.now(UTC)
    assert timedelta(seconds=250) <= (exp - now) <= timedelta(seconds=310)


def test_session_cap(client: TestClient) -> None:
    for _ in range(2):
        assert (
            client.post(
                "/v1/sessions",
                json={"consent_recording": True, "policy_version": POLICY},
            ).status_code
            == 201
        )
    r = client.post(
        "/v1/sessions",
        json={"consent_recording": True, "policy_version": POLICY},
    )
    assert r.status_code == 429
    assert r.json()["code"] == "session_cap"


def test_worker_offline_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CALLSCOPE_POLICY_VERSION", POLICY)
    settings = Settings(livekit_api_key="devkey", livekit_api_secret="secret")
    state = build_api_state(
        settings=settings,
        store=MemoryCallStore(),
        limiter=SessionCapLimiter(max_concurrent=2),
        tokens=LiveKitTokenMinter("devkey", "secret"),
        worker=WorkerStatus(online=False),
    )
    app = create_app(state)
    with TestClient(app) as c:
        assert c.get("/v1/status").json()["state"] == "offline"
        r = c.post(
            "/v1/sessions",
            json={"consent_recording": True, "policy_version": POLICY},
        )
        assert r.status_code == 503


def test_end_session_releases_cap(client: TestClient) -> None:
    ids = []
    for _ in range(2):
        body = client.post(
            "/v1/sessions",
            json={"consent_recording": True, "policy_version": POLICY},
        ).json()
        ids.append(body["call_id"])
    assert (
        client.post(
            "/v1/sessions",
            json={"consent_recording": True, "policy_version": POLICY},
        ).status_code
        == 429
    )
    assert client.post(f"/v1/sessions/{ids[0]}/end").status_code == 204
    assert (
        client.post(
            "/v1/sessions",
            json={"consent_recording": True, "policy_version": POLICY},
        ).status_code
        == 201
    )


def test_events_batch_auth_and_idempotent(client: TestClient) -> None:
    assert client.post("/v1/events:batch", json={"events": []}).status_code == 401
    eid = str(uuid4())
    cid = str(uuid4())
    ev = {
        "event_id": eid,
        "call_id": cid,
        "t_ms": 0,
        "ts": datetime.now(UTC).isoformat(),
        "source": "worker",
        "type": "call.start",
        "payload": {},
    }
    headers = {"Authorization": f"Bearer {SERVICE}"}
    r1 = client.post("/v1/events:batch", json={"events": [ev]}, headers=headers)
    assert r1.status_code == 202
    assert r1.json() == {"accepted": 1, "duplicates": 0}
    r2 = client.post("/v1/events:batch", json={"events": [ev]}, headers=headers)
    assert r2.status_code == 202
    assert r2.json() == {"accepted": 0, "duplicates": 1}


@pytest.mark.contract
def test_openapi_spec_validates() -> None:
    spec, _ = read_from_filename("docs/api/openapi.yaml")
    validate(spec)


@pytest.mark.contract
def test_status_response_matches_schema(client: TestClient) -> None:
    body = client.get("/v1/status").json()
    assert set(body.keys()) >= {"state", "active_calls", "max_concurrent", "stack_label"}
    assert body["state"] in {"online", "warming_up", "offline"}
