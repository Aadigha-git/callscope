"""File-backed eval run persistence (mirrors ``cs.eval_runs`` / item results)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from callscope.eval.types import EvalItemResult


@dataclass(slots=True)
class EvalRunRecord:
    run_id: str
    dataset_id: str
    stack_version_id: str
    mode: str
    git_sha: str
    status: str = "queued"
    thresholds_sha256: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
    estimated_usd: float | None = None
    started_at: str | None = None
    finished_at: str | None = None
    item_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    metrics: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvalRunRecord:
        return cls(
            run_id=str(data["run_id"]),
            dataset_id=str(data["dataset_id"]),
            stack_version_id=str(data["stack_version_id"]),
            mode=str(data["mode"]),
            git_sha=str(data["git_sha"]),
            status=str(data.get("status", "queued")),
            thresholds_sha256=data.get("thresholds_sha256"),
            config=dict(data.get("config") or {}),
            estimated_usd=data.get("estimated_usd"),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            item_results=dict(data.get("item_results") or {}),
            metrics=list(data.get("metrics") or []),
        )


class FileEvalStore:
    """JSON store under ``root/runs/<run_id>.json`` — CI / local default."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.runs_dir = root / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, run_id: str) -> Path:
        return self.runs_dir / f"{run_id}.json"

    def create_run(
        self,
        *,
        dataset_id: str,
        stack_version_id: str,
        mode: str,
        git_sha: str,
        config: dict[str, Any] | None = None,
        thresholds_sha256: str | None = None,
        estimated_usd: float | None = None,
    ) -> EvalRunRecord:
        run = EvalRunRecord(
            run_id=str(uuid4()),
            dataset_id=dataset_id,
            stack_version_id=stack_version_id,
            mode=mode,
            git_sha=git_sha,
            status="running",
            thresholds_sha256=thresholds_sha256,
            config=dict(config or {}),
            estimated_usd=estimated_usd,
            started_at=datetime.now(UTC).isoformat(),
        )
        self.save(run)
        return run

    def save(self, run: EvalRunRecord) -> None:
        self.path_for(run.run_id).write_text(
            json.dumps(run.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def load(self, run_id: str) -> EvalRunRecord:
        raw = json.loads(self.path_for(run_id).read_text(encoding="utf-8"))
        return EvalRunRecord.from_dict(raw)

    def finished_item_ids(self, run_id: str) -> set[str]:
        if not self.path_for(run_id).exists():
            return set()
        return set(self.load(run_id).item_results)

    def write_item(self, run_id: str, item_id: str, result: EvalItemResult) -> EvalRunRecord:
        run = self.load(run_id)
        row = result.to_row()
        row["detail"] = result.detail
        run.item_results[item_id] = row
        self.save(run)
        return run

    def finalize(
        self,
        run_id: str,
        *,
        status: str = "succeeded",
        metrics: list[dict[str, Any]] | None = None,
    ) -> EvalRunRecord:
        run = self.load(run_id)
        run.status = status
        run.finished_at = datetime.now(UTC).isoformat()
        if metrics is not None:
            run.metrics = metrics
        self.save(run)
        return run


def aggregate_metrics(item_results: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Simple mean WER / latency aggregates by slice labels in detail."""
    if not item_results:
        return []
    wers: list[float] = []
    by_cond: dict[str, list[float]] = {}
    for row in item_results.values():
        wer = row.get("wer")
        if wer is None:
            continue
        w = float(wer)
        wers.append(w)
        detail = row.get("detail") or {}
        cond = str(detail.get("condition") or "all")
        by_cond.setdefault(cond, []).append(w)
    out: list[dict[str, Any]] = []
    if wers:
        out.append(
            {
                "metric": "wer",
                "slice": "all",
                "value": sum(wers) / len(wers),
                "n": len(wers),
            }
        )
    for cond, vals in sorted(by_cond.items()):
        out.append(
            {
                "metric": "wer",
                "slice": f"cond={cond}",
                "value": sum(vals) / len(vals),
                "n": len(vals),
            }
        )
    return out


__all__ = [
    "EvalRunRecord",
    "FileEvalStore",
    "aggregate_metrics",
]
