"""Thin typed repositories for calls, turns, and events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from callscope.db import models


@dataclass(frozen=True, slots=True)
class CallFilters:
    flagged: bool | None = None
    channel: str | None = None
    stack_version_id: UUID | None = None
    started_after: datetime | None = None
    started_before: datetime | None = None


@dataclass(frozen=True, slots=True)
class CallCursor:
    """Keyset cursor on (started_at DESC, call_id DESC)."""

    started_at: datetime
    call_id: UUID


def build_list_calls_stmt(
    filters: CallFilters,
    *,
    limit: int = 50,
    cursor: CallCursor | None = None,
) -> Select[tuple[models.Call]]:
    """Pure query builder for ``list_calls`` (unit-testable without a DB)."""
    if limit < 1:
        raise ValueError("limit must be >= 1")
    stmt = select(models.Call)
    if filters.flagged is not None:
        stmt = stmt.where(models.Call.flagged.is_(filters.flagged))
    if filters.channel is not None:
        stmt = stmt.where(models.Call.channel == filters.channel)
    if filters.stack_version_id is not None:
        stmt = stmt.where(models.Call.stack_version_id == filters.stack_version_id)
    if filters.started_after is not None:
        stmt = stmt.where(models.Call.started_at >= filters.started_after)
    if filters.started_before is not None:
        stmt = stmt.where(models.Call.started_at <= filters.started_before)
    if cursor is not None:
        stmt = stmt.where(
            (models.Call.started_at < cursor.started_at)
            | (
                (models.Call.started_at == cursor.started_at)
                & (models.Call.call_id < cursor.call_id)
            )
        )
    return stmt.order_by(models.Call.started_at.desc(), models.Call.call_id.desc()).limit(limit)


class CallRepository:
    """Persistence helpers — no business logic."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_call(self, call: models.Call) -> models.Call:
        self._session.add(call)
        await self._session.flush()
        return call

    async def add_turns(self, turns: list[models.Turn]) -> list[models.Turn]:
        self._session.add_all(turns)
        await self._session.flush()
        return turns

    async def bulk_insert_events(self, events: list[models.Event]) -> int:
        """Insert events; ``ON CONFLICT (event_id) DO NOTHING``. Returns rows attempted."""
        if not events:
            return 0
        rows: list[dict[str, Any]] = [
            {
                "event_id": e.event_id,
                "call_id": e.call_id,
                "turn_id": e.turn_id,
                "t_ms": e.t_ms,
                "ts": e.ts,
                "source": e.source,
                "type": e.type,
                "payload": e.payload,
            }
            for e in events
        ]
        stmt = insert(models.Event).values(rows).on_conflict_do_nothing(index_elements=["event_id"])
        await self._session.execute(stmt)
        await self._session.flush()
        return len(rows)

    async def get_call_detail(self, call_id: UUID) -> models.Call | None:
        stmt = (
            select(models.Call)
            .where(models.Call.call_id == call_id)
            .options(
                selectinload(models.Call.turns),
                selectinload(models.Call.events),
                selectinload(models.Call.tool_calls),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_calls(
        self,
        filters: CallFilters | None = None,
        *,
        limit: int = 50,
        cursor: CallCursor | None = None,
    ) -> list[models.Call]:
        stmt = build_list_calls_stmt(filters or CallFilters(), limit=limit, cursor=cursor)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
