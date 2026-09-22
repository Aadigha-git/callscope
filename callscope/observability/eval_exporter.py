"""Export latest eval_run metrics as Prometheus gauges (T-M4-05)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from prometheus_client import CollectorRegistry, Gauge, generate_latest


@dataclass(frozen=True, slots=True)
class EvalMetricSample:
    metric: str
    slice: str
    value: float
    run_id: str


def load_latest_eval_metrics(store_dir: Path) -> list[EvalMetricSample]:
    """Read FileEvalStore run JSONs; return metrics from the newest finished run."""
    runs_dir = store_dir / "runs"
    if not runs_dir.is_dir():
        return []
    newest: tuple[str, dict[str, Any]] | None = None
    for path in runs_dir.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("status") not in {"succeeded", "failed"}:
            continue
        finished = str(data.get("finished_at") or path.stat().st_mtime)
        if newest is None or finished > newest[0]:
            newest = (finished, data)
    if newest is None:
        return []
    _, data = newest
    run_id = str(data.get("run_id") or "unknown")
    out: list[EvalMetricSample] = []
    for row in data.get("metrics") or []:
        out.append(
            EvalMetricSample(
                metric=str(row.get("metric") or "unknown"),
                slice=str(row.get("slice") or "all"),
                value=float(row.get("value") or 0.0),
                run_id=run_id,
            )
        )
    return out


def load_estimated_spend_usd(store_dir: Path) -> float:
    """Sum estimated_usd across finished runs (budget panel input)."""
    runs_dir = store_dir / "runs"
    if not runs_dir.is_dir():
        return 0.0
    total = 0.0
    for path in runs_dir.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("estimated_usd") is not None:
            total += float(data["estimated_usd"])
    return total


def build_registry(
    samples: list[EvalMetricSample],
    *,
    spend_usd: float = 0.0,
) -> CollectorRegistry:
    registry = CollectorRegistry()
    gauge = Gauge(
        "callscope_eval_metric_value",
        "Latest eval metric value from FileEvalStore",
        ["metric", "slice", "run_id"],
        registry=registry,
    )
    for s in samples:
        gauge.labels(metric=s.metric, slice=s.slice, run_id=s.run_id).set(s.value)
    spend = Gauge(
        "callscope_llm_spend_usd",
        "Cumulative estimated LLM spend from eval_runs",
        registry=registry,
    )
    spend.set(spend_usd)
    return registry


def render_metrics_text(store_dir: Path) -> bytes:
    samples = load_latest_eval_metrics(store_dir)
    spend = load_estimated_spend_usd(store_dir)
    return generate_latest(build_registry(samples, spend_usd=spend))
