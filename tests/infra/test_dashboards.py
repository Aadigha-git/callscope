"""Dashboard JSON lint, alert rule shape, and eval exporter unit tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from callscope.observability.eval_exporter import (
    build_registry,
    load_estimated_spend_usd,
    load_latest_eval_metrics,
    render_metrics_text,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]


def test_grafana_dashboards_are_valid_json() -> None:
    dash_dir = ROOT / "infra" / "grafana" / "dashboards"
    files = list(dash_dir.glob("*.json"))
    assert {p.name for p in files} >= {"live-ops.json", "quality-drift.json", "cost.json"}
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "panels" in data
        assert isinstance(data["panels"], list)
        assert data["panels"], path.name


def test_quality_dashboard_queries_eval_exporter() -> None:
    text = (ROOT / "infra/grafana/dashboards/quality-drift.json").read_text(encoding="utf-8")
    assert "callscope_eval_metric_value" in text
    assert "callscope_asr_confidence" in text


def test_cost_dashboard_reads_llm_spend() -> None:
    text = (ROOT / "infra/grafana/dashboards/cost.json").read_text(encoding="utf-8")
    assert "callscope_llm_spend_usd" in text


def test_alert_rules_parse() -> None:
    data = yaml.safe_load((ROOT / "infra/prometheus/alerts.yml").read_text(encoding="utf-8"))
    names = {r["alert"] for g in data["groups"] for r in g["rules"]}
    assert "CallScopeHighResponseLatencyP95" in names
    assert "CallScopeProviderErrorRateHigh" in names
    assert "CallScopeLLMBudgetBurn" in names


def test_prometheus_loads_alerts_and_eval_job() -> None:
    data = yaml.safe_load((ROOT / "infra/prometheus/prometheus.yml").read_text(encoding="utf-8"))
    assert "rule_files" in data
    jobs = {j["job_name"] for j in data["scrape_configs"]}
    assert "callscope-eval" in jobs


def test_eval_exporter_from_fixture(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "r1.json").write_text(
        json.dumps(
            {
                "run_id": "r1",
                "status": "succeeded",
                "finished_at": "2026-09-22T00:00:00+00:00",
                "estimated_usd": 1.25,
                "metrics": [
                    {"metric": "sim_pass", "slice": "all", "value": 0.9, "n": 16},
                    {"metric": "wer", "slice": "all", "value": 0.1, "n": 16},
                ],
            }
        ),
        encoding="utf-8",
    )
    samples = load_latest_eval_metrics(tmp_path)
    assert len(samples) == 2
    assert samples[0].run_id == "r1"
    assert load_estimated_spend_usd(tmp_path) == 1.25
    registry = build_registry(samples, spend_usd=1.25)
    text = render_metrics_text(tmp_path).decode()
    assert "callscope_eval_metric_value" in text
    assert "callscope_llm_spend_usd" in text
    assert registry is not None


def test_promtool_check_rules_if_available() -> None:
    import shutil
    import subprocess

    promtool = shutil.which("promtool")
    if promtool is None:
        pytest.skip("promtool not installed")
    res = subprocess.run(
        [promtool, "check", "rules", str(ROOT / "infra/prometheus/alerts.yml")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stderr
