"""Local recording retention: purge eligibility + filesystem deletes (T-M2-06)."""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_DAYS = 30


@dataclass
class RetentionRecord:
    call_id: str
    ended_at: str  # ISO-8601
    recording_dir: str | None = None
    mixed_uri: str | None = None
    consent_donate: bool = False
    reviewed: bool = False
    raw_purged_at: str | None = None
    events_payload_scrubbed: bool = False


@dataclass
class RetentionCatalog:
    """JSONL catalog under the recordings root (no Postgres required for local demo)."""

    path: Path
    _rows: dict[str, RetentionRecord] = field(default_factory=dict)

    def load(self) -> None:
        self._rows.clear()
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            rec = RetentionRecord(**data)
            self._rows[rec.call_id] = rec

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as fh:
            for rec in self._rows.values():
                fh.write(json.dumps(asdict(rec), sort_keys=True) + "\n")

    def upsert(self, rec: RetentionRecord) -> None:
        self._rows[rec.call_id] = rec

    def get(self, call_id: str) -> RetentionRecord | None:
        return self._rows.get(call_id)

    def all(self) -> list[RetentionRecord]:
        return list(self._rows.values())

    def remove(self, call_id: str) -> RetentionRecord | None:
        return self._rows.pop(call_id, None)


def eligible_for_purge(
    rec: RetentionRecord,
    *,
    now: datetime | None = None,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> bool:
    """True when raw audio/payloads may be deleted.

    Donated **and** reviewed calls are retained past the window.
    """
    if rec.raw_purged_at:
        return False
    if rec.consent_donate and rec.reviewed:
        return False
    if not rec.ended_at:
        return False
    ended = datetime.fromisoformat(rec.ended_at)
    if ended.tzinfo is None:
        ended = ended.replace(tzinfo=UTC)
    anchor = now or datetime.now(UTC)
    return anchor - ended >= timedelta(days=retention_days)


def purge_record(
    rec: RetentionRecord,
    *,
    dry_run: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Delete recording dir for an eligible call; mark purged. Idempotent."""
    stamp = (now or datetime.now(UTC)).isoformat()
    result: dict[str, Any] = {
        "call_id": rec.call_id,
        "dry_run": dry_run,
        "deleted_dir": None,
        "skipped": False,
    }
    if rec.raw_purged_at:
        result["skipped"] = True
        result["reason"] = "already_purged"
        return result
    if not eligible_for_purge(rec, now=now):
        result["skipped"] = True
        result["reason"] = "not_eligible"
        return result

    if rec.recording_dir:
        path = Path(rec.recording_dir)
        result["deleted_dir"] = str(path)
        if not dry_run and path.exists():
            shutil.rmtree(path)
            logger.info("purged recording dir call_id=%s path=%s", rec.call_id, path)

    if not dry_run:
        rec.raw_purged_at = stamp
        rec.mixed_uri = None
        rec.events_payload_scrubbed = True
    return result


def delete_call(
    catalog: RetentionCatalog,
    call_id: UUID,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Remove audio + catalog row for a call (right-to-delete)."""
    key = str(call_id)
    rec = catalog.get(key)
    result: dict[str, Any] = {"call_id": key, "dry_run": dry_run, "found": rec is not None}
    if rec is None:
        return result
    if rec.recording_dir:
        path = Path(rec.recording_dir)
        result["deleted_dir"] = str(path)
        if not dry_run and path.exists():
            shutil.rmtree(path)
    if not dry_run:
        catalog.remove(key)
        catalog.save()
    return result


def apply_purge(
    catalog: RetentionCatalog,
    *,
    dry_run: bool = True,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    now: datetime | None = None,
    audit_log: Path | None = None,
) -> list[dict[str, Any]]:
    """Purge all eligible rows; write one audit line per batch."""
    catalog.load()
    results: list[dict[str, Any]] = []
    for rec in catalog.all():
        if eligible_for_purge(rec, now=now, retention_days=retention_days):
            results.append(purge_record(rec, dry_run=dry_run, now=now))
    if not dry_run:
        catalog.save()
    if audit_log is not None and results:
        audit_log.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": (now or datetime.now(UTC)).isoformat(),
            "dry_run": dry_run,
            "retention_days": retention_days,
            "count": len(results),
            "call_ids": [r["call_id"] for r in results],
        }
        with audit_log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    return results
