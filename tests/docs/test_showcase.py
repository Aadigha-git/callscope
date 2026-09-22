"""T-M6-03 showcase / runbook presence checks."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]


def test_demo_runbook_exists() -> None:
    text = (ROOT / "docs" / "runbooks" / "demo.md").read_text(encoding="utf-8")
    assert "make demo" in text
    assert "Consent" in text or "consent" in text


def test_showcase_landing_has_brand() -> None:
    html = (ROOT / "docs" / "showcase" / "index.html").read_text(encoding="utf-8")
    assert "CallScope" in html
    assert "styles.css" in html
    assert (ROOT / "docs" / "showcase" / "styles.css").is_file()


def test_video_script_exists() -> None:
    text = (ROOT / "docs" / "showcase" / "VIDEO.md").read_text(encoding="utf-8")
    assert "Shot list" in text
    assert "demo.mp4" in text
