"""Validate Compose + Prometheus/Grafana demo wiring (no Docker daemon)."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_compose_local_services() -> None:
    data = yaml.safe_load((ROOT / "docker-compose.local.yml").read_text(encoding="utf-8"))
    assert data["name"] == "callscope-local"
    services = data["services"]
    for name in ("postgres", "minio", "prometheus", "grafana", "mlflow"):
        assert name in services
    assert services["minio"]["image"].startswith("quay.io/minio/minio:")
    assert services["mlflow"]["depends_on"] == ["minio"]
    # Native Metal stack must NOT live in Compose.
    for forbidden in ("asr", "tts", "hermes", "worker", "livekit", "api"):
        assert forbidden not in services
    grafana_vols = " ".join(str(v) for v in services["grafana"]["volumes"])
    assert "infra/grafana/provisioning" in grafana_vols
    assert "infra/grafana/dashboards" in grafana_vols
    prom = services["prometheus"]
    assert "host.docker.internal:host-gateway" in prom.get("extra_hosts", [])


def test_prometheus_scrapes_native_ports() -> None:
    data = yaml.safe_load((ROOT / "infra/prometheus/prometheus.yml").read_text(encoding="utf-8"))
    targets: set[str] = set()
    for job in data["scrape_configs"]:
        for sc in job["static_configs"]:
            targets.update(sc["targets"])
    assert "host.docker.internal:8000" in targets
    assert "host.docker.internal:9100" in targets
    assert "host.docker.internal:8200" in targets
    assert "host.docker.internal:8300" in targets


def test_grafana_live_ops_dashboard_present() -> None:
    dash = ROOT / "infra/grafana/dashboards/live-ops.json"
    assert dash.is_file()
    text = dash.read_text(encoding="utf-8")
    assert "callscope_active_calls" in text
    assert "callscope_response_latency_seconds_bucket" in text
    ds = yaml.safe_load(
        (ROOT / "infra/grafana/provisioning/datasources/datasource.yml").read_text(encoding="utf-8")
    )
    assert ds["datasources"][0]["url"] == "http://prometheus:9090"


def test_procfile_lists_native_processes() -> None:
    text = (ROOT / "Procfile").read_text(encoding="utf-8")
    for name in ("livekit:", "api:", "asr:", "tts:", "worker:", "biz:", "web:"):
        assert name in text
