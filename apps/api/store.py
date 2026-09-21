"""In-memory call/session + event store for the API (CI-friendly).

SQLAlchemy repositories (T-M1-02) remain available for DB-backed deploys; this store
keeps the walking-skeleton API testable without Postgres.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Protocol
from uuid import UUID, uuid4

from callscope.events.models import Event as EventModel


@dataclass
class SessionRecord:
    call_id: UUID
    room: str
    started_at: datetime
    ended_at: datetime | None = None
    consent_recording: bool = True
    consent_donate: bool = False
    consent_policy_v: str = ""
    channel: str = "browser"
    end_reason: str | None = None
    recording_uri: str | None = None
    caller_uri: str | None = None
    agent_uri: str | None = None
    reviewed: bool = False
    raw_purged_at: datetime | None = None


class CallStore(Protocol):
    def create_session(
        self,
        *,
        consent_recording: bool,
        consent_donate: bool,
        policy_version: str,
    ) -> SessionRecord: ...

    def end_session(self, call_id: UUID, *, reason: str = "client_end") -> bool: ...

    def get(self, call_id: UUID) -> SessionRecord | None: ...

    def active_count(self) -> int: ...

    def insert_events(self, events: list[EventModel]) -> tuple[int, int]:
        """Return (accepted, duplicates)."""

    def register_recording(
        self,
        call_id: UUID,
        *,
        mixed_uri: str,
        caller_uri: str | None = None,
        agent_uri: str | None = None,
    ) -> bool: ...


@dataclass
class MemoryCallStore:
    """Thread-safe in-memory store used by default in tests and local dev without DB."""

    _sessions: dict[UUID, SessionRecord] = field(default_factory=dict)
    _event_ids: set[UUID] = field(default_factory=set)
    _events: list[dict[str, Any]] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock)

    def create_session(
        self,
        *,
        consent_recording: bool,
        consent_donate: bool,
        policy_version: str,
    ) -> SessionRecord:
        call_id = uuid4()
        rec = SessionRecord(
            call_id=call_id,
            room=f"call-{call_id}",
            started_at=datetime.now(UTC),
            consent_recording=consent_recording,
            consent_donate=consent_donate,
            consent_policy_v=policy_version,
        )
        with self._lock:
            self._sessions[call_id] = rec
        return rec

    def end_session(self, call_id: UUID, *, reason: str = "client_end") -> bool:
        with self._lock:
            rec = self._sessions.get(call_id)
            if rec is None:
                return False
            if rec.ended_at is None:
                rec.ended_at = datetime.now(UTC)
                rec.end_reason = reason
            return True

    def get(self, call_id: UUID) -> SessionRecord | None:
        with self._lock:
            return self._sessions.get(call_id)

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for s in self._sessions.values() if s.ended_at is None)

    def insert_events(self, events: list[EventModel]) -> tuple[int, int]:
        accepted = 0
        duplicates = 0
        with self._lock:
            for ev in events:
                if ev.event_id in self._event_ids:
                    duplicates += 1
                    continue
                self._event_ids.add(ev.event_id)
                self._events.append(ev.model_dump(mode="json"))
                accepted += 1
        return accepted, duplicates

    def register_recording(
        self,
        call_id: UUID,
        *,
        mixed_uri: str,
        caller_uri: str | None = None,
        agent_uri: str | None = None,
    ) -> bool:
        with self._lock:
            rec = self._sessions.get(call_id)
            if rec is None:
                return False
            if not rec.consent_recording:
                return False
            rec.recording_uri = mixed_uri
            rec.caller_uri = caller_uri
            rec.agent_uri = agent_uri
            return True
