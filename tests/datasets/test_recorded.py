"""Recorded-set ingest / correction / freeze (T-M3-07)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from callscope.datasets.io_audio import SAMPLE_RATE_HZ, write_wav
from callscope.datasets.recorded import (
    export_transcripts_csv,
    freeze_recorded_test,
    import_corrections_csv,
    ingest_recorded,
)

pytestmark = pytest.mark.unit


def _tone_wav(path: Path) -> None:
    t = np.linspace(0, 0.4, int(SAMPLE_RATE_HZ * 0.4), endpoint=False)
    audio = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    write_wav(path, audio, SAMPLE_RATE_HZ)


def test_ingest_export_import_freeze(tmp_path: Path) -> None:
    root = tmp_path / "recorded"
    audio = root / "audio"
    audio.mkdir(parents=True)
    _tone_wav(audio / "rec_001_book_plumbing_laptop.wav")
    _tone_wav(audio / "rec_002_hours_saturday_phone.wav")
    _tone_wav(audio / "rec_003_cancel_code_laptop.wav")
    _tone_wav(audio / "rec_004_callback_leak_phone.wav")
    consent = root / "consent_in.md"
    consent.write_text("volunteer alias A agrees (fictional data only)\n", encoding="utf-8")

    man = ingest_recorded(root, consent_file=consent)
    assert man["n_calls"] == 4
    assert (root / "manifest.json").is_file()

    csv_path = root / "drafts" / "transcripts.csv"
    n = export_transcripts_csv(root, csv_path)
    assert n == 4

    import csv

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            r["corrected_transcript"] = f"verified text for {r['scenario_id']}"
            r["transcript_verified"] = "true"
            w.writerow(r)

    stats = import_corrections_csv(root, csv_path)
    assert stats["n_verified"] == 4

    frozen = freeze_recorded_test(root, seed=7)
    assert frozen["n_test"] + frozen["n_dev"] == 4
    assert frozen["frozen_test_sha256"]
    # Re-import refused
    with pytest.raises(RuntimeError, match="frozen"):
        import_corrections_csv(root, csv_path)


def test_freeze_refuses_unverified(tmp_path: Path) -> None:
    root = tmp_path / "rec2"
    audio = root / "audio"
    audio.mkdir(parents=True)
    _tone_wav(audio / "rec_001_book_laptop.wav")
    consent = tmp_path / "c.md"
    consent.write_text("ok\n", encoding="utf-8")
    ingest_recorded(root, consent_file=consent)
    with pytest.raises(RuntimeError, match="not verified"):
        freeze_recorded_test(root)
