"""Dataset registry: file-backed + SQLAlchemy models for ``cs.datasets`` / items."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4


class RegistryError(RuntimeError):
    """Publish/freeze refused (frozen or DQ failed)."""


@dataclass(slots=True)
class RegistryEntry:
    dataset_id: str
    name: str
    version: str
    kind: str
    manifest_uri: str
    manifest_sha256: str
    n_items: int
    dq_report: dict[str, Any]
    dq_passed: bool
    frozen: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "name": self.name,
            "version": self.version,
            "kind": self.kind,
            "manifest_uri": self.manifest_uri,
            "manifest_sha256": self.manifest_sha256,
            "n_items": self.n_items,
            "dq_report": self.dq_report,
            "dq_passed": self.dq_passed,
            "frozen": self.frozen,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RegistryEntry:
        return cls(
            dataset_id=str(data["dataset_id"]),
            name=str(data["name"]),
            version=str(data["version"]),
            kind=str(data.get("kind", "synthetic")),
            manifest_uri=str(data["manifest_uri"]),
            manifest_sha256=str(data["manifest_sha256"]),
            n_items=int(data["n_items"]),
            dq_report=dict(data.get("dq_report") or {}),
            dq_passed=bool(data["dq_passed"]),
            frozen=bool(data.get("frozen", False)),
            created_at=str(data.get("created_at") or datetime.now(UTC).isoformat()),
        )


class FileRegistry:
    """JSON registry under ``root/registry.json`` (local demo; mirrors cs.datasets)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / "registry.json"
        self.root.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"datasets": {}}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"datasets": {}}
        return cast(dict[str, Any], data)

    def _save(self, data: dict[str, Any]) -> None:
        text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        self.path.write_text(text, encoding="utf-8")

    def get(self, name: str, version: str) -> RegistryEntry | None:
        key = f"{name}@{version}"
        raw = self._load().get("datasets", {}).get(key)
        return RegistryEntry.from_dict(raw) if raw else None

    def publish(
        self,
        *,
        name: str,
        version: str,
        manifest_uri: str,
        manifest: dict[str, Any],
        kind: str = "synthetic",
    ) -> RegistryEntry:
        if not manifest.get("dq_passed"):
            raise RegistryError("refuse publish: dq_passed is false")
        existing = self.get(name, version)
        if existing is not None and existing.frozen:
            raise RegistryError(f"refuse publish: {name}@{version} is frozen")
        digest = str(manifest.get("manifest_sha256") or "")
        if not digest:
            raise RegistryError("manifest_sha256 missing")
        items = manifest.get("items") or []
        entry = RegistryEntry(
            dataset_id=str(uuid4()),
            name=name,
            version=version,
            kind=kind,
            manifest_uri=manifest_uri,
            manifest_sha256=digest,
            n_items=len(items),
            dq_report=dict(manifest.get("dq_report") or {}),
            dq_passed=True,
            frozen=bool(manifest.get("frozen", False)),
        )
        data = self._load()
        data.setdefault("datasets", {})[f"{name}@{version}"] = entry.to_dict()
        # Persist item index for freeze checks
        data.setdefault("items", {})[entry.dataset_id] = [
            {
                "item_id": i.get("item_id"),
                "split": i.get("split"),
                "scenario_id": i.get("scenario_id"),
                "variant": str(i.get("variant")),
                "audio_uri": i.get("wav_relpath") or i.get("audio_uri"),
                "audio_sha256": i.get("audio_sha256"),
                "condition_code": i.get("condition"),
                "voice_profile": i.get("voice"),
            }
            for i in items
            if isinstance(i, dict)
        ]
        self._save(data)
        return entry

    def freeze(self, name: str, version: str) -> RegistryEntry:
        entry = self.get(name, version)
        if entry is None:
            raise RegistryError(f"unknown dataset {name}@{version}")
        if entry.frozen:
            return entry
        data = self._load()
        key = f"{name}@{version}"
        data["datasets"][key]["frozen"] = True
        self._save(data)
        entry.frozen = True
        return entry

    def assert_mutable(self, name: str, version: str) -> None:
        entry = self.get(name, version)
        if entry is not None and entry.frozen:
            raise RegistryError(f"refuse modify: {name}@{version} is frozen")


def dataset_row_for_sql(entry: RegistryEntry) -> dict[str, Any]:
    """Shape matching ``cs.datasets`` insert (UUID as UUID type at call site)."""
    return {
        "dataset_id": UUID(entry.dataset_id),
        "name": entry.name,
        "version": entry.version,
        "kind": entry.kind,
        "manifest_uri": entry.manifest_uri,
        "manifest_sha256": entry.manifest_sha256,
        "n_items": entry.n_items,
        "dq_report": entry.dq_report,
        "dq_passed": entry.dq_passed,
        "frozen": entry.frozen,
    }


__all__ = [
    "FileRegistry",
    "RegistryEntry",
    "RegistryError",
    "dataset_row_for_sql",
]
