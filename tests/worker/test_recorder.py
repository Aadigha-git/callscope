"""CallRecorder + retention purge/delete-call tests (T-M2-06)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import create_app
from apps.worker.config import WorkerConfig
from apps.worker.recorder import CallRecorder
from apps.worker.session import CallSession, NullMedia
from callscope.events.clock import CallClock
from callscope.events.models import Event
from callscope.events.writer import EventWriter
from callscope.providers.mock import MockBrain, MockSTT, MockTTS
from callscope.retention import (
    RetentionCatalog,
    RetentionRecord,
    apply_purge,
    delete_call,
    eligible_for_purge,
)


def test_no_consent_writes_nothing(tmp_path: Path) -> None:
    root = tmp_path / "rec"
    rec = CallRecorder(
        call_id=uuid.uuid4(),
        consent_recording=False,
        root=root,
    )
    rec.append_caller(b"\x00\x01" * 80)
    rec.append_agent(b"\x00\x02" * 80)
    assert rec.finalize() is None
    assert not root.exists() or not any(root.iterdir())


def test_consent_writes_wavs(tmp_path: Path) -> None:
    root = tmp_path / "rec"
    call_id = uuid.uuid4()
    rec = CallRecorder(call_id=call_id, consent_recording=True, root=root)
    rec.append_caller(b"\x01\x00" * 160)
    rec.append_agent(b"\x02\x00" * 160)
    uris = rec.finalize()
    assert uris is not None
    assert (root / str(call_id) / "mixed.wav").is_file()
    assert (root / str(call_id) / "caller.wav").is_file()
    assert uris.mixed_uri.startswith("file:")


def test_eligibility_matrix() -> None:
    now = datetime(2026, 9, 20, tzinfo=UTC)
    old = (now - timedelta(days=31)).isoformat()
    recent = (now - timedelta(days=5)).isoformat()
    base = RetentionRecord(call_id="a", ended_at=old, recording_dir="rec/a")
    assert eligible_for_purge(base, now=now)
    donated = RetentionRecord(
        call_id="b", ended_at=old, consent_donate=True, reviewed=True, recording_dir="rec/b"
    )
    assert not eligible_for_purge(donated, now=now)
    donated_unreviewed = RetentionRecord(
        call_id="c", ended_at=old, consent_donate=True, reviewed=False, recording_dir="rec/c"
    )
    assert eligible_for_purge(donated_unreviewed, now=now)
    fresh = RetentionRecord(call_id="d", ended_at=recent, recording_dir="rec/d")
    assert not eligible_for_purge(fresh, now=now)
    purged = RetentionRecord(
        call_id="e", ended_at=old, raw_purged_at=now.isoformat(), recording_dir="rec/e"
    )
    assert not eligible_for_purge(purged, now=now)


def test_purge_idempotent(tmp_path: Path) -> None:
    now = datetime(2026, 9, 20, tzinfo=UTC)
    call_dir = tmp_path / "c1"
    call_dir.mkdir()
    (call_dir / "mixed.wav").write_bytes(b"RIFF")
    catalog = RetentionCatalog(tmp_path / "index.jsonl")
    catalog.upsert(
        RetentionRecord(
            call_id="c1",
            ended_at=(now - timedelta(days=40)).isoformat(),
            recording_dir=str(call_dir),
        )
    )
    catalog.save()
    audit = tmp_path / "audit.jsonl"
    r1 = apply_purge(catalog, dry_run=False, now=now, audit_log=audit)
    assert len(r1) == 1
    assert not call_dir.exists()
    catalog.load()
    r2 = apply_purge(catalog, dry_run=False, now=now, audit_log=audit)
    assert r2 == [] or all(x.get("skipped") for x in r2)
    # already purged → not eligible
    assert catalog.get("c1") is not None
    assert catalog.get("c1") and catalog.get("c1").raw_purged_at  # type: ignore[union-attr]
    assert audit.exists()


def test_delete_call_removes_row(tmp_path: Path) -> None:
    call_id = uuid.uuid4()
    call_dir = tmp_path / str(call_id)
    call_dir.mkdir()
    (call_dir / "mixed.wav").write_bytes(b"x")
    catalog = RetentionCatalog(tmp_path / "index.jsonl")
    catalog.upsert(
        RetentionRecord(
            call_id=str(call_id),
            ended_at=datetime.now(UTC).isoformat(),
            recording_dir=str(call_dir),
        )
    )
    catalog.save()
    result = delete_call(catalog, call_id, dry_run=False)
    assert result["found"]
    assert not call_dir.exists()
    catalog.load()
    assert catalog.get(str(call_id)) is None


@pytest.mark.asyncio
async def test_session_respects_no_consent(tmp_path: Path) -> None:
    events: list[Event] = []

    async def sink(batch: list[Event]) -> None:
        events.extend(batch)

    writer = EventWriter(sink, spill_dir=tmp_path / "spill", flush_ms=5.0)
    await writer.start()
    recorder = CallRecorder(
        call_id=uuid.uuid4(),
        consent_recording=False,
        root=tmp_path / "rec",
    )
    session = CallSession(
        call_id=recorder.call_id,
        stt=MockSTT(transcripts=["hi"]),
        tts=MockTTS(ms_per_char=1.0),
        brain=MockBrain(replies=["ok."]),
        writer=writer,
        clock=CallClock(),
        config=WorkerConfig(greeting_text="", chunker_min_chars=1),
        media=NullMedia(),
        recorder=recorder,
    )
    await session.start()
    await session.connect()

    async def pcm():
        yield b"\x00\x00" * 80

    await session.process_pcm(pcm())
    await session.end("client_end")
    assert session.recording_uris is None
    assert not (tmp_path / "rec").exists() or not any((tmp_path / "rec").rglob("*.wav"))


@pytest.mark.asyncio
async def test_api_register_recording_consent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CALLSCOPE_SERVICE_TOKEN", "tok")
    monkeypatch.setenv("CALLSCOPE_POLICY_VERSION", "2026-09-20")
    from apps.api.deps import WorkerStatus, build_api_state
    from apps.api.livekit_tokens import LiveKitTokenMinter
    from apps.api.ratelimit import SessionCapLimiter
    from apps.api.store import MemoryCallStore
    from callscope.config import Settings

    store = MemoryCallStore()
    state = build_api_state(
        settings=Settings(
            livekit_url="ws://127.0.0.1:7880",
            livekit_api_key="devkey",
            livekit_api_secret="secret",
        ),
        store=store,
        limiter=SessionCapLimiter(max_concurrent=2),
        tokens=LiveKitTokenMinter("devkey", "secret"),
        worker=WorkerStatus(online=True, stack_label="test"),
    )
    assert state.service_token == "tok"
    app = create_app(state)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        rec = store.create_session(
            consent_recording=True,
            consent_donate=False,
            policy_version=state.policy_version,
        )
        resp = await client.post(
            f"/v1/calls/{rec.call_id}/recording",
            json={"mixed_uri": "file:///tmp/mixed.wav"},
            headers={"Authorization": "Bearer tok"},
        )
        assert resp.status_code == 204
        assert store.get(rec.call_id).recording_uri == "file:///tmp/mixed.wav"  # type: ignore[union-attr]

        rec2 = store.create_session(
            consent_recording=True,
            consent_donate=False,
            policy_version=state.policy_version,
        )
        rec2.consent_recording = False
        resp2 = await client.post(
            f"/v1/calls/{rec2.call_id}/recording",
            json={"mixed_uri": "file:///tmp/x.wav"},
            headers={"Authorization": "Bearer tok"},
        )
        assert resp2.status_code == 403
