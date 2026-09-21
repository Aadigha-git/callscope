"""Unit tests for Event envelope and OpenAPI alignment."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import jsonschema
import pytest
import yaml

from callscope.events.models import EVENT_TYPES, Event, EventSource

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]


def _openapi_event_schema() -> dict[str, object]:
    spec = yaml.safe_load((ROOT / "docs/api/openapi.yaml").read_text(encoding="utf-8"))
    schemas = spec["components"]["schemas"]
    event = schemas["Event"]
    # Resolve local refs is unnecessary; Event has no $refs.
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        **event,
        "components": {"schemas": schemas},
    }


def test_event_validates_against_openapi_schema() -> None:
    event = Event(
        call_id=uuid4(),
        turn_id=None,
        t_ms=12345,
        ts=datetime(2026, 9, 19, 20, 1, 2, 123000, tzinfo=UTC),
        source=EventSource.WORKER,
        type="stt.final",
        payload={"text": "hello", "avg_conf": 0.9},
    )
    payload = event.model_dump(mode="json")
    jsonschema.validate(instance=payload, schema=_openapi_event_schema())


def test_event_catalogue_covers_design_6_6() -> None:
    expected = {
        "call.start",
        "call.end",
        "call.consent",
        "call.recording",
        "vad.speech_start",
        "vad.speech_end",
        "endpoint.decided",
        "stt.partial",
        "stt.final",
        "brain.request",
        "brain.first_token",
        "brain.done",
        "tool.call",
        "tool.result",
        "policy.denied",
        "tts.request",
        "tts.first_audio",
        "playback.start",
        "playback.stop",
        "barge_in.detected",
        "barge_in.applied",
        "filler.played",
        "provider.error",
    }
    assert expected == EVENT_TYPES


def test_event_source_enum_matches_openapi() -> None:
    assert {s.value for s in EventSource} == {"worker", "plugin", "client", "sim"}
