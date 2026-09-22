"""T-M6-05 write-up / release doc checks."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]


def test_readme_has_offline_eval_path() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "caller_sim" in text
    assert "make setup" in text
    assert "docs/img/topology-local-mac.svg" in text


def test_writeup_cites_real_run_ids() -> None:
    text = (ROOT / "docs" / "WRITEUP.md").read_text(encoding="utf-8")
    assert "39692d2c-4b41-4dd3-ba90-205df186a23d" in text
    assert "load-694f5a9867b5" in text
    assert "23f6d373" in text


def test_architecture_svgs_exist() -> None:
    assert (ROOT / "docs" / "img" / "topology-local-mac.svg").is_file()
    assert (ROOT / "docs" / "img" / "eval-improvement-flow.svg").is_file()
