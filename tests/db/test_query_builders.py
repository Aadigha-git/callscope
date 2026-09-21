"""Unit tests for DB URL helpers and list_calls query builder."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from callscope.db.repositories import CallCursor, CallFilters, build_list_calls_stmt
from callscope.db.urls import to_async_url, to_sync_url

pytestmark = pytest.mark.unit


def test_to_async_url_from_postgresql() -> None:
    assert to_async_url("postgresql://u:p@localhost:5432/db") == (
        "postgresql+psycopg://u:p@localhost:5432/db"
    )


def test_to_sync_url_strips_driver() -> None:
    assert to_sync_url("postgresql+psycopg://u:p@localhost/db") == "postgresql://u:p@localhost/db"


def test_list_calls_filters_compile() -> None:
    stack = uuid4()
    stmt = build_list_calls_stmt(
        CallFilters(flagged=True, channel="browser", stack_version_id=stack),
        limit=10,
    )
    sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": False}))
    assert "flagged" in sql
    assert "channel" in sql
    assert "stack_version_id" in sql
    assert "LIMIT" in sql.upper()


def test_list_calls_cursor_clause() -> None:
    cursor = CallCursor(started_at=datetime(2026, 1, 1, tzinfo=UTC), call_id=uuid4())
    stmt = build_list_calls_stmt(CallFilters(), limit=5, cursor=cursor)
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "started_at" in sql
    assert "call_id" in sql


def test_list_calls_rejects_bad_limit() -> None:
    with pytest.raises(ValueError, match="limit"):
        build_list_calls_stmt(CallFilters(), limit=0)
