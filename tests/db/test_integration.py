"""Integration tests: Alembic baseline, schema snapshot, repositories."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession

from callscope.db.catalog import catalog_fingerprint
from callscope.db.engine import create_async_engine, session_factory
from callscope.db.models import Call, Event, ModelVersion, StackVersion, Turn
from callscope.db.repositories import CallCursor, CallFilters, CallRepository
from callscope.db.urls import to_sync_url

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("CALLSCOPE_TEST_DATABASE_URL"), reason="no test database"
    ),
]

ROOT = Path(__file__).resolve().parents[2]
DB_URL = os.environ.get("CALLSCOPE_TEST_DATABASE_URL", "")


def _alembic_cfg() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    return cfg


def _reset_schemas() -> None:
    with psycopg.connect(to_sync_url(DB_URL), autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS cs CASCADE")
        conn.execute("DROP SCHEMA IF EXISTS biz CASCADE")
        conn.execute("DROP TABLE IF EXISTS public.alembic_version")


def test_alembic_upgrade_head_on_empty_postgres() -> None:
    _reset_schemas()
    os.environ["CALLSCOPE_TEST_DATABASE_URL"] = DB_URL
    command.upgrade(_alembic_cfg(), "head")
    with psycopg.connect(to_sync_url(DB_URL)) as conn:
        n = conn.execute("SELECT count(*) FROM cs.root_cause_codes").fetchone()
        assert n is not None and n[0] == 21


def test_migrated_catalog_matches_schema_sql_snapshot() -> None:
    """Alembic baseline must produce the same cs/biz catalog as db/schema.sql."""
    _reset_schemas()
    os.environ["CALLSCOPE_TEST_DATABASE_URL"] = DB_URL
    command.upgrade(_alembic_cfg(), "head")
    with psycopg.connect(to_sync_url(DB_URL)) as conn:
        migrated = catalog_fingerprint(conn)

    _reset_schemas()
    with psycopg.connect(to_sync_url(DB_URL), autocommit=True) as conn:
        conn.execute((ROOT / "db" / "schema.sql").read_text(encoding="utf-8"))
        from_file = catalog_fingerprint(conn)

    assert migrated == from_file


async def _seed_stack(session: AsyncSession) -> StackVersion:
    asr = ModelVersion(
        component="asr", name="whisper-base", revision="test", owner="BAG", status="candidate"
    )
    tts = ModelVersion(
        component="tts", name="kokoro", revision="test", owner="BAG", status="candidate"
    )
    llm = ModelVersion(
        component="llm",
        name="nemotron",
        revision="test",
        owner="BAG",
        status="candidate",
    )
    session.add_all([asr, tts, llm])
    await session.flush()
    stack = StackVersion(
        label=f"stack-test-{uuid4().hex[:8]}",
        asr_mv=asr.model_version_id,
        tts_mv=tts.model_version_id,
        llm_mv=llm.model_version_id,
        hermes_version="0.19.0",
        plugin_version="0.0.1",
        prompt_sha256="abc",
        worker_config={},
        git_sha="deadbeef",
    )
    session.add(stack)
    await session.flush()
    return stack


@pytest.mark.asyncio
async def test_call_repository_create_detail_list_and_event_dedupe() -> None:
    _reset_schemas()
    os.environ["CALLSCOPE_TEST_DATABASE_URL"] = DB_URL
    command.upgrade(_alembic_cfg(), "head")

    engine = create_async_engine(DB_URL)
    factory = session_factory(engine)
    async with factory() as session:
        repo = CallRepository(session)
        stack = await _seed_stack(session)
        t0 = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
        call = Call(
            started_at=t0,
            channel="browser",
            stack_version_id=stack.stack_version_id,
            consent_recording=True,
            consent_policy_v="v1",
            flagged=True,
            flag_reasons=["latency"],
        )
        await repo.create_call(call)
        turn = Turn(
            call_id=call.call_id,
            idx=0,
            speaker="caller",
            t_start_ms=0,
            t_end_ms=500,
            text="hello",
        )
        await repo.add_turns([turn])
        eid = uuid4()
        ev = Event(
            event_id=eid,
            call_id=call.call_id,
            turn_id=turn.turn_id,
            t_ms=10,
            ts=t0,
            source="worker",
            type="stt.final",
            payload={"text": "hello"},
        )
        assert await repo.bulk_insert_events([ev]) == 1
        assert await repo.bulk_insert_events([ev]) == 1  # conflict ignored
        await session.commit()

        detail = await repo.get_call_detail(call.call_id)
        assert detail is not None
        assert len(detail.turns) == 1
        assert len(detail.events) == 1

        # second call for cursor pagination
        call2 = Call(
            started_at=t0 + timedelta(minutes=1),
            channel="sim",
            stack_version_id=stack.stack_version_id,
            consent_recording=True,
            consent_policy_v="v1",
            is_synthetic=True,
        )
        await repo.create_call(call2)
        await session.commit()

        listed = await repo.list_calls(CallFilters(flagged=True), limit=10)
        assert len(listed) == 1
        assert listed[0].call_id == call.call_id

        page = await repo.list_calls(limit=1)
        assert len(page) == 1
        nxt = await repo.list_calls(
            limit=1,
            cursor=CallCursor(started_at=page[0].started_at, call_id=page[0].call_id),
        )
        assert len(nxt) == 1
        assert nxt[0].call_id != page[0].call_id

    await engine.dispose()
