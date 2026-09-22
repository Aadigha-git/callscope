"""Dataset manifest JSON + stable sha256."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _canonical(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _canonical(obj[k]) for k in sorted(obj)}
    if isinstance(obj, list):
        return [_canonical(v) for v in obj]
    return obj


def manifest_sha256(manifest: dict[str, Any]) -> str:
    """Hash of sorted item audio hashes + key dataset fields (stable)."""
    items = manifest.get("items") or []
    item_hashes = sorted(str(i.get("audio_sha256", "")) for i in items if isinstance(i, dict))
    payload = {
        "version": manifest.get("version"),
        "n_calls": manifest.get("n_calls") or manifest.get("n_items"),
        "seed": manifest.get("seed"),
        "voices": manifest.get("voices"),
        "conditions": manifest.get("conditions"),
        "item_hashes": item_hashes,
        "splits": manifest.get("splits"),
        "held_voices": manifest.get("held_voices"),
        "held_variants": manifest.get("held_variants"),
    }
    blob = json.dumps(_canonical(payload), separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"manifest must be object: {path}")
    return data


def write_manifest(path: Path, manifest: dict[str, Any]) -> str:
    """Write manifest with embedded ``manifest_sha256``; return the hash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = dict(manifest)
    digest = manifest_sha256(body)
    body["manifest_sha256"] = digest
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return digest


def attach_splits_and_dq(
    manifest: dict[str, Any],
    *,
    items: list[dict[str, Any]],
    dq_report: dict[str, Any],
    held_voices: tuple[str, ...] | list[str],
    held_variants: tuple[str, ...] | list[str],
    frozen_test: bool = False,
) -> dict[str, Any]:
    out = dict(manifest)
    out["items"] = items
    out["n_items"] = len(items)
    out["dq_report"] = dq_report
    out["dq_passed"] = bool(dq_report.get("dq_passed"))
    out["held_voices"] = list(held_voices)
    out["held_variants"] = list(held_variants)
    out["frozen"] = bool(frozen_test)
    out["splits"] = {
        "train": sum(1 for i in items if i.get("split") == "train"),
        "dev": sum(1 for i in items if i.get("split") == "dev"),
        "test": sum(1 for i in items if i.get("split") == "test"),
    }
    out["manifest_sha256"] = manifest_sha256(out)
    return out


__all__ = [
    "attach_splits_and_dq",
    "load_manifest",
    "manifest_sha256",
    "write_manifest",
]
