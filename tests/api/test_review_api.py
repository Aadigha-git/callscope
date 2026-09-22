"""Review / eval / model API contract tests (T-M4-02)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.deps import WorkerStatus, build_api_state
from apps.api.livekit_tokens import LiveKitTokenMinter
from apps.api.main import create_app
from apps.api.ratelimit import SessionCapLimiter
from apps.api.review_store import EvalRunRecord, ReviewStore
from apps.api.store import MemoryCallStore
from callscope.config import Settings

pytestmark = pytest.mark.unit

POLICY = "2026-09-20"
SERVICE = "test-service-token"
AUTH = {"Authorization": f"Bearer {SERVICE}"}


@pytest.fixture
def store() -> MemoryCallStore:
    return MemoryCallStore()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, store: MemoryCallStore) -> TestClient:
    monkeypatch.setenv("CALLSCOPE_POLICY_VERSION", POLICY)
    monkeypatch.setenv("CALLSCOPE_SERVICE_TOKEN", SERVICE)
    monkeypatch.setenv("CALLSCOPE_AUDIO_SIGNING_SECRET", "test-audio-secret")
    settings = Settings(
        livekit_url="ws://127.0.0.1:7880",
        livekit_api_key="devkey",
        livekit_api_secret="secret",
    )
    review = ReviewStore(calls=store, audio_hmac_key="test-audio-secret")
    state = build_api_state(
        settings=settings,
        store=store,
        review=review,
        limiter=SessionCapLimiter(max_concurrent=10),
        tokens=LiveKitTokenMinter("devkey", "secret"),
        worker=WorkerStatus(online=True, stack_label="test-stack"),
    )
    app = create_app(state)
    with TestClient(app) as c:
        yield c


def _seed_call(store: MemoryCallStore, review: ReviewStore, *, flagged: bool = False) -> str:
    rec = store.create_session(consent_recording=True, consent_donate=False, policy_version=POLICY)
    store.end_session(rec.call_id)
    store.register_recording(rec.call_id, mixed_uri=f"file:///tmp/{rec.call_id}.wav")
    review.set_call_meta(
        rec.call_id,
        flagged=flagged,
        flag_reasons=["low_asr_confidence"] if flagged else [],
        root_causes=["RC-ASR-ENT"] if flagged else [],
    )
    return str(rec.call_id)


def test_calls_require_auth(client: TestClient) -> None:
    r = client.get("/v1/calls")
    assert r.status_code == 401


def test_list_calls_pagination(client: TestClient, store: MemoryCallStore) -> None:
    review = client.app.state.api.review  # type: ignore[attr-defined]
    ids = [_seed_call(store, review) for _ in range(5)]
    r1 = client.get("/v1/calls", params={"limit": 2}, headers=AUTH)
    assert r1.status_code == 200
    body1 = r1.json()
    assert len(body1["items"]) == 2
    assert body1["next_cursor"] is not None
    r2 = client.get(
        "/v1/calls",
        params={"limit": 2, "cursor": body1["next_cursor"]},
        headers=AUTH,
    )
    assert r2.status_code == 200
    body2 = r2.json()
    page_ids = {x["call_id"] for x in body1["items"]} | {x["call_id"] for x in body2["items"]}
    assert len(page_ids) == 4
    assert page_ids.issubset(set(ids))


def test_list_flagged_filter(client: TestClient, store: MemoryCallStore) -> None:
    review = client.app.state.api.review  # type: ignore[attr-defined]
    flagged_id = _seed_call(store, review, flagged=True)
    _seed_call(store, review, flagged=False)
    r = client.get("/v1/calls", params={"flagged": True}, headers=AUTH)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["call_id"] == flagged_id
    assert items[0]["flagged"] is True


def test_call_detail_and_label(client: TestClient, store: MemoryCallStore) -> None:
    review = client.app.state.api.review  # type: ignore[attr-defined]
    call_id = _seed_call(store, review, flagged=True)
    r = client.get(f"/v1/calls/{call_id}", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["call_id"] == call_id
    lab = client.post(
        f"/v1/calls/{call_id}/labels",
        headers=AUTH,
        json={
            "root_cause_code": "RC-LLM-INTENT",
            "severity": 2,
            "reviewer": "bag",
            "notes": "missed intent",
            "add_to_dataset": "train",
        },
    )
    assert lab.status_code == 201
    body = lab.json()
    assert body["root_cause_code"] == "RC-LLM-INTENT"
    assert "label_id" in body
    detail = client.get(f"/v1/calls/{call_id}", headers=AUTH).json()
    assert len(detail["labels"]) == 1
    assert "RC-LLM-INTENT" in detail["root_causes"]
    assert any(a.get("action") == "label" for a in review._audit)


def test_label_rejects_unknown_code(client: TestClient, store: MemoryCallStore) -> None:
    review = client.app.state.api.review  # type: ignore[attr-defined]
    call_id = _seed_call(store, review)
    r = client.post(
        f"/v1/calls/{call_id}/labels",
        headers=AUTH,
        json={"root_cause_code": "RC-FAKE", "severity": 1, "reviewer": "bag"},
    )
    assert r.status_code == 422


def test_audio_signed_url_and_expiry(client: TestClient, store: MemoryCallStore) -> None:
    review = client.app.state.api.review  # type: ignore[attr-defined]
    call_id = _seed_call(store, review)
    r = client.get(f"/v1/calls/{call_id}/audio", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert "token=" in body["url"]
    expires = datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
    assert expires - datetime.now(UTC) <= timedelta(minutes=5, seconds=5)
    assert expires > datetime.now(UTC)
    # Expired token rejected by verifier
    payload = ReviewStore.verify_audio_token(body["url"].split("token=", 1)[1], "test-audio-secret")
    assert payload is not None
    assert payload["call_id"] == call_id
    bad = ReviewStore.verify_audio_token("not-a-token", "test-audio-secret")
    assert bad is None


def test_audio_unauthenticated(client: TestClient, store: MemoryCallStore) -> None:
    review = client.app.state.api.review  # type: ignore[attr-defined]
    call_id = _seed_call(store, review)
    r = client.get(f"/v1/calls/{call_id}/audio")
    assert r.status_code == 401


def test_export_labelled(client: TestClient, store: MemoryCallStore) -> None:
    review = client.app.state.api.review  # type: ignore[attr-defined]
    call_id = _seed_call(store, review, flagged=True)
    client.post(
        f"/v1/calls/{call_id}/labels",
        headers=AUTH,
        json={"root_cause_code": "RC-ASR-ENT", "severity": 3, "reviewer": "bag"},
    )
    r = client.post(
        "/v1/datasets:export-labelled",
        headers=AUTH,
        json={"name": "failures", "version": "v1"},
    )
    assert r.status_code == 202
    assert "dataset_id" in r.json()


def test_eval_runs_and_compare(client: TestClient) -> None:
    review = client.app.state.api.review  # type: ignore[attr-defined]
    a_id = uuid4()
    b_id = uuid4()
    ds = uuid4()
    stack = uuid4()
    review.seed_eval_run(
        EvalRunRecord(
            run_id=a_id,
            dataset_id=ds,
            stack_version_id=stack,
            mode="baseline",
            status="succeeded",
            metrics=[
                {
                    "metric": "task_success",
                    "slice": "all",
                    "value": 0.8,
                    "ci_low": 0.7,
                    "ci_high": 0.9,
                    "n": 10,
                }
            ],
        )
    )
    review.seed_eval_run(
        EvalRunRecord(
            run_id=b_id,
            dataset_id=ds,
            stack_version_id=stack,
            mode="baseline",
            status="succeeded",
            metrics=[
                {
                    "metric": "task_success",
                    "slice": "all",
                    "value": 0.85,
                    "ci_low": 0.75,
                    "ci_high": 0.95,
                    "n": 10,
                }
            ],
        )
    )
    listed = client.get("/v1/eval/runs", headers=AUTH)
    assert listed.status_code == 200
    assert len(listed.json()) == 2
    detail = client.get(f"/v1/eval/runs/{a_id}", headers=AUTH)
    assert detail.status_code == 200
    assert len(detail.json()["metrics"]) == 1
    cmp = client.get("/v1/eval/compare", params={"a": str(a_id), "b": str(b_id)}, headers=AUTH)
    assert cmp.status_code == 200
    deltas = cmp.json()
    assert len(deltas) == 1
    assert abs(deltas[0]["delta"] - 0.05) < 1e-9
    queued = client.post(
        "/v1/eval/runs",
        headers=AUTH,
        json={
            "dataset_id": str(ds),
            "stack_version_id": str(stack),
            "mode": "stage_replay",
        },
    )
    assert queued.status_code == 202
    assert queued.json()["status"] == "queued"


def test_models_inventory(client: TestClient) -> None:
    r = client.post(
        "/v1/models",
        headers=AUTH,
        json={
            "component": "asr",
            "name": "whisper-tiny",
            "revision": "1",
            "owner": "bag",
            "license": "MIT",
            "intended_use": "demo ASR",
        },
    )
    assert r.status_code == 201
    mid = r.json()["model_version_id"]
    listed = client.get("/v1/models", params={"component": "asr"}, headers=AUTH)
    assert listed.status_code == 200
    assert any(m["model_version_id"] == mid for m in listed.json())
    tr = client.post(
        f"/v1/models/{mid}/transition",
        headers=AUTH,
        json={"to": "validated"},
    )
    assert tr.status_code == 200
    assert tr.json()["status"] == "validated"
    bad = client.post(
        f"/v1/models/{mid}/transition",
        headers=AUTH,
        json={"to": "candidate"},
    )
    assert bad.status_code == 422  # enum rejection or 409
