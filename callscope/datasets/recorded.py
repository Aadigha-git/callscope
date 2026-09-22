"""Ingest consented recorded calls: draft ASR transcripts + CSV correction."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from callscope.datasets.io_audio import SAMPLE_RATE_HZ, read_wav, write_wav
from callscope.datasets.manifest import load_manifest, write_manifest


@dataclass(slots=True)
class RecordedItem:
    item_id: str
    audio_relpath: str
    scenario_id: str
    condition_label: str  # laptop | phone
    split: str  # dev | test | unset
    draft_transcript: str = ""
    corrected_transcript: str = ""
    transcript_verified: bool = False
    consent_batch: str = ""
    audio_sha256: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "audio_relpath": self.audio_relpath,
            "scenario_id": self.scenario_id,
            "condition_label": self.condition_label,
            "split": self.split,
            "draft_transcript": self.draft_transcript,
            "corrected_transcript": self.corrected_transcript,
            "transcript_verified": self.transcript_verified,
            "consent_batch": self.consent_batch,
            "audio_sha256": self.audio_sha256,
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecordedItem:
        return cls(
            item_id=str(data["item_id"]),
            audio_relpath=str(data["audio_relpath"]),
            scenario_id=str(data.get("scenario_id") or ""),
            condition_label=str(data.get("condition_label") or "laptop"),
            split=str(data.get("split") or "unset"),
            draft_transcript=str(data.get("draft_transcript") or ""),
            corrected_transcript=str(data.get("corrected_transcript") or ""),
            transcript_verified=bool(data.get("transcript_verified")),
            consent_batch=str(data.get("consent_batch") or ""),
            audio_sha256=str(data.get("audio_sha256") or ""),
            meta=dict(data.get("meta") or {}),
        )


def _parse_filename(name: str) -> tuple[str, str, str]:
    """``rec_001_book_plumbing_laptop.wav`` → id stub, scenario, condition."""
    stem = Path(name).stem
    parts = stem.split("_")
    if len(parts) < 3:
        return stem, "unknown", "laptop"
    condition = parts[-1] if parts[-1] in {"laptop", "phone"} else "laptop"
    scenario = "_".join(parts[2:-1]) if parts[-1] in {"laptop", "phone"} else "_".join(parts[2:])
    return stem, scenario or "unknown", condition


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def draft_transcript_from_audio(path: Path, *, hint: str = "") -> str:
    """Best-effort draft text. Without a live ASR, use filename hint / empty.

    Live Mac runs may pass an STT callable via ``ingest_recorded(..., stt_draft=...)``.
    """
    if hint:
        return hint
    _ = path
    return ""


def ingest_recorded(
    root: Path,
    *,
    consent_file: Path,
    stt_draft: Any | None = None,
    default_split: str = "unset",
) -> dict[str, Any]:
    """Scan ``root/audio/*.wav``, copy consent, write/update ``manifest.json``."""
    audio_dir = root / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    consent_dir = root / "consent"
    consent_dir.mkdir(parents=True, exist_ok=True)
    drafts = root / "drafts"
    drafts.mkdir(parents=True, exist_ok=True)

    if not consent_file.is_file():
        raise FileNotFoundError(f"consent file required: {consent_file}")
    dest_consent = consent_dir / consent_file.name
    if consent_file.resolve() != dest_consent.resolve():
        shutil.copy2(consent_file, dest_consent)

    man_path = root / "manifest.json"
    existing: dict[str, Any] = {}
    if man_path.is_file():
        existing = load_manifest(man_path)
    by_audio = {
        str(i.get("audio_relpath")): RecordedItem.from_dict(i)
        for i in (existing.get("items") or [])
        if isinstance(i, dict)
    }

    items: list[RecordedItem] = []
    for wav in sorted(audio_dir.glob("*.wav")):
        rel = f"audio/{wav.name}"
        if rel in by_audio:
            item = by_audio[rel]
        else:
            _, scenario, condition = _parse_filename(wav.name)
            item = RecordedItem(
                item_id=str(uuid4()),
                audio_relpath=rel,
                scenario_id=scenario,
                condition_label=condition,
                split=default_split,
                consent_batch=dest_consent.name,
            )
        item.audio_sha256 = _sha256_file(wav)
        # Normalise to 16 kHz mono float→wav if readable
        try:
            audio, sr = read_wav(wav)
            if sr != SAMPLE_RATE_HZ:
                write_wav(wav, audio, SAMPLE_RATE_HZ)
                item.audio_sha256 = _sha256_file(wav)
                item.meta["resampled_to_hz"] = SAMPLE_RATE_HZ
        except (OSError, ValueError, wave.Error) as exc:
            item.meta["audio_warning"] = str(exc)

        if not item.draft_transcript:
            if stt_draft is not None:
                item.draft_transcript = str(stt_draft(wav))
            else:
                item.draft_transcript = draft_transcript_from_audio(
                    wav, hint=item.scenario_id.replace("_", " ")
                )
        items.append(item)

    manifest = {
        "kind": "recorded",
        "n_calls": len(items),
        "consent_file": str(dest_consent.relative_to(root)),
        "consent_policy": "consent_policy_v1",
        "items": [i.to_dict() for i in items],
        "frozen_test": bool(existing.get("frozen_test")),
        "protocol": "docs/recording_protocol.md",
    }
    write_manifest(man_path, manifest)
    return manifest


def export_transcripts_csv(root: Path, out_csv: Path) -> int:
    man = load_manifest(root / "manifest.json")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    rows = list(man.get("items") or [])
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "item_id",
                "audio_relpath",
                "scenario_id",
                "split",
                "draft_transcript",
                "corrected_transcript",
                "transcript_verified",
            ],
        )
        w.writeheader()
        for row in rows:
            if not isinstance(row, dict):
                continue
            w.writerow(
                {
                    "item_id": row.get("item_id"),
                    "audio_relpath": row.get("audio_relpath"),
                    "scenario_id": row.get("scenario_id"),
                    "split": row.get("split"),
                    "draft_transcript": row.get("draft_transcript"),
                    "corrected_transcript": row.get("corrected_transcript")
                    or row.get("draft_transcript"),
                    "transcript_verified": row.get("transcript_verified"),
                }
            )
    return len(rows)


def import_corrections_csv(root: Path, csv_path: Path) -> dict[str, Any]:
    man_path = root / "manifest.json"
    man = load_manifest(man_path)
    if man.get("frozen_test"):
        raise RuntimeError("recorded test set is frozen; refuse transcript imports")
    by_id = {
        str(i["item_id"]): i
        for i in (man.get("items") or [])
        if isinstance(i, dict) and "item_id" in i
    }
    updated = 0
    with csv_path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            iid = str(row.get("item_id") or "")
            if iid not in by_id:
                continue
            item = by_id[iid]
            item["corrected_transcript"] = str(row.get("corrected_transcript") or "").strip()
            verified_raw = str(row.get("transcript_verified") or "").lower()
            explicit = verified_raw in {"1", "true", "yes", "y"}
            # Verified when explicitly marked or corrected text is non-empty
            item["transcript_verified"] = explicit or bool(item["corrected_transcript"])
            updated += 1
    write_manifest(man_path, man)
    n_verified = sum(
        1 for i in man["items"] if isinstance(i, dict) and i.get("transcript_verified")
    )
    return {"updated": updated, "n_verified": n_verified, "n_items": len(man["items"])}


def freeze_recorded_test(root: Path, *, seed: int = 42) -> dict[str, Any]:
    """Assign splits if needed; require 100% verified; freeze test half hashes."""
    from random import Random

    man_path = root / "manifest.json"
    man = load_manifest(man_path)
    items = [i for i in (man.get("items") or []) if isinstance(i, dict)]
    if not items:
        raise RuntimeError("no recorded items to freeze")
    unverified = [i["item_id"] for i in items if not i.get("transcript_verified")]
    if unverified:
        raise RuntimeError(
            f"{len(unverified)} transcripts not verified; refuse freeze "
            f"(examples: {unverified[:3]})"
        )
    # If splits unset, shuffle with seed then half test / half dev.
    if any(str(i.get("split") or "unset") == "unset" for i in items):
        ordered = list(items)
        Random(seed).shuffle(ordered)  # noqa: S311
        mid = len(ordered) // 2
        for idx, i in enumerate(ordered):
            i["split"] = "test" if idx < mid else "dev"
        items = ordered

    for i in items:
        if i.get("split") == "train":
            i["split"] = "dev"
    test_items = [i for i in items if i.get("split") == "test"]
    payload = json.dumps(
        [{"item_id": i["item_id"], "audio_sha256": i.get("audio_sha256")} for i in test_items],
        sort_keys=True,
    )
    freeze_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    man["items"] = items
    man["frozen_test"] = True
    man["frozen_test_sha256"] = freeze_hash
    man["n_dev"] = sum(1 for i in items if i.get("split") == "dev")
    man["n_test"] = len(test_items)
    write_manifest(man_path, man)
    return {
        "frozen_test_sha256": freeze_hash,
        "n_dev": man["n_dev"],
        "n_test": man["n_test"],
    }


__all__ = [
    "RecordedItem",
    "export_transcripts_csv",
    "freeze_recorded_test",
    "import_corrections_csv",
    "ingest_recorded",
]
