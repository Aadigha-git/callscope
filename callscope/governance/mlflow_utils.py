"""MLflow helpers for eval/experiment runs (T-M5-01).

Default tracking URI is a local SQLite store under ``artifacts/mlruns`` so CI never
needs a server. Compose can point ``MLFLOW_TRACKING_URI`` at a MinIO-backed server.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def default_tracking_uri(root: Path | None = None) -> str:
    env = os.environ.get("MLFLOW_TRACKING_URI")
    if env:
        return env
    base = root or Path("artifacts/mlruns")
    base.mkdir(parents=True, exist_ok=True)
    db = (base / "mlflow.db").resolve()
    return f"sqlite:///{db}"


def log_eval_run(
    *,
    experiment: str,
    run_name: str,
    params: dict[str, Any],
    metrics: dict[str, float],
    tags: dict[str, str] | None = None,
    tracking_uri: str | None = None,
) -> str:
    """Start/end an MLflow run; return ``run_id``.

    Imports mlflow lazily so default CI without ``--extra governance`` still works
    when this helper is not called.
    """
    import mlflow
    from mlflow.tracking import MlflowClient

    uri = tracking_uri or default_tracking_uri()
    mlflow.set_tracking_uri(uri)
    mlflow.set_experiment(experiment)
    with mlflow.start_run(run_name=run_name) as run:
        for k, v in params.items():
            mlflow.log_param(k, v)
        for k, v in metrics.items():
            mlflow.log_metric(k, float(v))
        if tags:
            mlflow.set_tags(tags)
        run_id = run.info.run_id
    MlflowClient(tracking_uri=uri).get_run(run_id)
    return str(run_id)
