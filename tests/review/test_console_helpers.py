"""Tests for review console helpers and API client (mocked HTTP)."""

from __future__ import annotations

import httpx
import pytest

from apps.api.review_store import ReviewStore
from apps.api.store import MemoryCallStore
from apps.review.api_client import ReviewApiClient
from apps.review.helpers import escape_text, reference_diff, scrub_tool_args, timeline_lanes
from callscope.review.seed_demo import (
    attribution_agreement,
    build_seed_specs,
    root_cause_distribution,
)

pytestmark = pytest.mark.unit


def test_escape_text_blocks_html() -> None:
    assert escape_text("<script>x</script>") == "&lt;script&gt;x&lt;/script&gt;"


def test_timeline_lanes_orders_by_t_ms() -> None:
    events = [
        {"type": "stt.final", "t_ms": 200, "payload": {"text": "hi"}},
        {"type": "tool.call", "t_ms": 100, "payload": {"args": {}}},
    ]
    lanes = timeline_lanes(events)
    assert lanes[0]["lane"] == "tools"
    assert lanes[1]["lane"] == "asr"


def test_reference_diff_marks_mismatch() -> None:
    parts = reference_diff("book friday", "book tuesday")
    ops = {p["op"] for p in parts}
    assert "equal" in ops
    assert "insert" in ops or "delete" in ops


def test_scrub_tool_args() -> None:
    out = scrub_tool_args({"phone": "555", "slot": "am"})
    assert out["phone"] == "[redacted]"
    assert out["slot"] == "am"


def test_seed_specs_count_and_labels() -> None:
    specs = build_seed_specs(40)
    assert len(specs) == 40
    assert sum(1 for s in specs if s.flagged) >= 30


def test_root_cause_distribution_and_agreement() -> None:
    labels = [
        {"root_cause_code": "RC-ASR-ENT"},
        {"root_cause_code": "RC-ASR-ENT"},
        {"root_cause_code": "RC-TOOL-ERR"},
    ]
    dist = root_cause_distribution(labels)
    assert dist["RC-ASR-ENT"] == 2
    agr = attribution_agreement(["RC-ASR-ENT", "RC-TOOL-ERR"], ["RC-ASR-ENT"])
    assert agr["recall"] == 0.5
    assert agr["precision"] == 1.0


def test_api_client_list_calls_mocked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization") == "Bearer tok"
        assert "/v1/calls" in str(request.url)
        return httpx.Response(200, json={"items": [], "next_cursor": None})

    transport = httpx.MockTransport(handler)
    client = ReviewApiClient("http://example.test", "tok", client=httpx.Client(transport=transport))
    body = client.list_calls(flagged=True)
    assert body["items"] == []
    client.close()


def test_api_client_seed_demo_mocked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/v1/devtools/seed-review")
        return httpx.Response(201, json={"created": 40, "labelled": 32, "call_ids": []})

    transport = httpx.MockTransport(handler)
    client = ReviewApiClient("http://example.test", "tok", client=httpx.Client(transport=transport))
    assert client.seed_demo(40)["created"] == 40
    client.close()


def test_seed_via_review_store() -> None:
    store = MemoryCallStore()
    review = ReviewStore(calls=store)
    result = review.seed_review_demo(n=40)
    assert result["created"] == 40
    assert result["labelled"] >= 30
    items, _ = review.list_calls(flagged=True, limit=200)
    assert len(items) >= 30
    ds = review.export_labelled(name="seed-fails", version="v1")
    assert ds is not None
