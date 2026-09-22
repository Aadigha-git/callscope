"""E3 endpointing experiment tests (T-M5-03)."""

from __future__ import annotations

from pathlib import Path

import pytest

from callscope.experiments.e3 import DEFAULT_POINT, GRID, run_e3, score_point

pytestmark = pytest.mark.unit


def test_grid_non_empty() -> None:
    assert len(GRID) > 10
    assert DEFAULT_POINT.endpoint_min_delay_s < DEFAULT_POINT.endpoint_max_delay_s


def test_score_point_returns_rates() -> None:
    m = score_point(DEFAULT_POINT, seeds=[1, 2, 3, 4, 5])
    assert 0.0 <= m["endpoint_error_rate"] <= 1.0
    assert m["latency_p50_ms"] >= 0.0


def test_run_e3(tmp_path: Path) -> None:
    result = run_e3(out_dir=tmp_path, log_mlflow=False)
    assert result["decision"] in {"adopt", "reject"}
    assert (tmp_path / "result.json").is_file()
    assert "chosen" in result
