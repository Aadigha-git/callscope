"""Thresholds lock: changing eval/thresholds.yaml requires lock + DECISIONS update."""

from __future__ import annotations

from pathlib import Path

import pytest

from callscope.eval.gate import DEFAULT_LOCK, DEFAULT_THRESHOLDS, thresholds_file_sha256

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]


def test_thresholds_lock_in_sync() -> None:
    lock = (REPO / DEFAULT_LOCK).read_text(encoding="utf-8").strip()
    digest = thresholds_file_sha256(REPO / DEFAULT_THRESHOLDS)
    assert lock == digest, (
        "eval/thresholds.yaml hash drifted from docs/thresholds.lock; "
        "update the lock in the same PR and add a DECISIONS.md rationale"
    )


def test_decisions_mentions_thresholds_when_lock_present() -> None:
    # Smoke: lock file and thresholds exist; decisions log has §10.2 / thresholds entry.
    decisions = (REPO / "docs" / "DECISIONS.md").read_text(encoding="utf-8")
    assert "thresholds" in decisions.lower()
