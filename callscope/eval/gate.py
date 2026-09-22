"""Load thresholds.yaml and gate an eval run (absolute + optional baseline)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

import yaml

from callscope.eval.compare import Direction, paired_bootstrap
from callscope.eval.persist import EvalRunRecord, FileEvalStore

DEFAULT_THRESHOLDS = Path("eval/thresholds.yaml")
DEFAULT_LOCK = Path("docs/thresholds.lock")

Op = Literal["lte", "gte", "eq"]


@dataclass(frozen=True, slots=True)
class GateSpec:
    id: str
    metric: str
    slice: str
    op: Op
    value: float
    description: str = ""


@dataclass(frozen=True, slots=True)
class MarginSpec:
    metric: str
    margin: float
    direction: Direction
    relative: bool = False


@dataclass(frozen=True, slots=True)
class Thresholds:
    version: int
    gates: tuple[GateSpec, ...]
    margins: tuple[MarginSpec, ...]
    raw: dict[str, Any]
    sha256: str

    def gate_by_id(self, gate_id: str) -> GateSpec | None:
        for g in self.gates:
            if g.id == gate_id:
                return g
        return None


@dataclass(slots=True)
class GateCheck:
    gate_id: str
    metric: str
    slice: str
    op: Op
    threshold: float
    observed: float | None
    passed: bool
    detail: str = ""


@dataclass(slots=True)
class GateReport:
    thresholds_sha256: str
    checks: list[GateCheck] = field(default_factory=list)
    compare_checks: list[GateCheck] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks) and all(c.passed for c in self.compare_checks)

    def to_table(self) -> str:
        lines = [
            f"thresholds_sha256={self.thresholds_sha256}",
            f"{'GATE':<28} {'METRIC':<18} {'SLICE':<14} {'OP':<4} {'THR':>8} {'OBS':>8} {'PASS'}",
            "-" * 96,
        ]
        for c in self.checks + self.compare_checks:
            obs = "n/a" if c.observed is None else f"{c.observed:.4f}"
            lines.append(
                f"{c.gate_id:<28} {c.metric:<18} {c.slice:<14} {c.op:<4} "
                f"{c.threshold:8.4f} {obs:>8} {'OK' if c.passed else 'FAIL'}"
            )
            if c.detail:
                lines.append(f"  {c.detail}")
        lines.append("-" * 96)
        lines.append("OVERALL: PASS" if self.passed else "OVERALL: FAIL")
        return "\n".join(lines)


def thresholds_file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_thresholds(path: Path | None = None) -> Thresholds:
    p = path or DEFAULT_THRESHOLDS
    text = p.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"thresholds must be a mapping: {p}")
    gates: list[GateSpec] = []
    for row in data.get("gates") or []:
        if not isinstance(row, dict):
            continue
        gates.append(
            GateSpec(
                id=str(row["id"]),
                metric=str(row["metric"]),
                slice=str(row.get("slice") or "all"),
                op=cast(Op, str(row["op"])),
                value=float(row["value"]),
                description=str(row.get("description") or ""),
            )
        )
    margins: list[MarginSpec] = []
    ni = data.get("non_inferiority") or {}
    if isinstance(ni, dict):
        for metric, spec in ni.items():
            if not isinstance(spec, dict):
                continue
            if "margin_rel" in spec:
                margins.append(
                    MarginSpec(
                        metric=str(metric),
                        margin=float(spec["margin_rel"]),
                        direction=cast(Direction, str(spec.get("direction") or "lower_better")),
                        relative=True,
                    )
                )
            else:
                margins.append(
                    MarginSpec(
                        metric=str(metric),
                        margin=float(spec["margin"]),
                        direction=cast(Direction, str(spec.get("direction") or "lower_better")),
                        relative=False,
                    )
                )
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return Thresholds(
        version=int(data.get("version") or 1),
        gates=tuple(gates),
        margins=tuple(margins),
        raw=data,
        sha256=digest,
    )


def _eval_op(op: Op, observed: float, threshold: float) -> bool:
    if op == "lte":
        return observed <= threshold + 1e-12
    if op == "gte":
        return observed >= threshold - 1e-12
    return abs(observed - threshold) <= 1e-12


def metric_lookup(run: EvalRunRecord, metric: str, slice_key: str) -> float | None:
    for row in run.metrics:
        if row.get("metric") == metric and str(row.get("slice") or "all") == slice_key:
            return float(row["value"])
    return None


def gate_run(
    run: EvalRunRecord,
    thresholds: Thresholds,
    *,
    require_metric: bool = False,
) -> GateReport:
    """Absolute gates against ``run.metrics``. Missing metrics → skip unless require_metric."""
    report = GateReport(thresholds_sha256=thresholds.sha256)
    for g in thresholds.gates:
        obs = metric_lookup(run, g.metric, g.slice)
        if obs is None:
            check = GateCheck(
                gate_id=g.id,
                metric=g.metric,
                slice=g.slice,
                op=g.op,
                threshold=g.value,
                observed=None,
                passed=not require_metric,
                detail="metric missing" + (" (fail)" if require_metric else " (skipped)"),
            )
        else:
            check = GateCheck(
                gate_id=g.id,
                metric=g.metric,
                slice=g.slice,
                op=g.op,
                threshold=g.value,
                observed=obs,
                passed=_eval_op(g.op, obs, g.value),
            )
        report.checks.append(check)
    return report


def gate_vs_baseline(
    baseline: EvalRunRecord,
    candidate: EvalRunRecord,
    thresholds: Thresholds,
    *,
    per_call_baseline: dict[str, list[float]] | None = None,
    per_call_candidate: dict[str, list[float]] | None = None,
) -> GateReport:
    """Non-inferiority vs baseline using aggregate metrics or paired per-call series."""
    report = gate_run(candidate, thresholds)
    for m in thresholds.margins:
        b_val = metric_lookup(baseline, m.metric, "all")
        c_val = metric_lookup(candidate, m.metric, "all")
        if per_call_baseline and per_call_candidate and m.metric in per_call_baseline:
            pb = per_call_baseline[m.metric]
            pc = per_call_candidate[m.metric]
            if m.relative:
                # relative margin on mean: treat as absolute margin = margin_rel * baseline mean
                base_mean = float(sum(pb) / len(pb)) if pb else 0.0
                abs_margin = m.margin * base_mean
            else:
                abs_margin = m.margin
            cmp = paired_bootstrap(pb, pc, margin=abs_margin, direction=m.direction)
            report.compare_checks.append(
                GateCheck(
                    gate_id=f"ni_{m.metric}",
                    metric=m.metric,
                    slice="all",
                    op="lte" if m.direction == "lower_better" else "gte",
                    threshold=abs_margin,
                    observed=cmp.delta,
                    passed=cmp.non_inferior,
                    detail=(
                        f"paired delta={cmp.delta:.4f} CI=[{cmp.ci_low:.4f},{cmp.ci_high:.4f}] "
                        f"margin={abs_margin:.4f}"
                    ),
                )
            )
            continue
        if b_val is None or c_val is None:
            report.compare_checks.append(
                GateCheck(
                    gate_id=f"ni_{m.metric}",
                    metric=m.metric,
                    slice="all",
                    op="lte",
                    threshold=m.margin,
                    observed=None,
                    passed=True,
                    detail="aggregate missing; skipped",
                )
            )
            continue
        delta = c_val - b_val
        abs_margin = m.margin * b_val if m.relative else m.margin
        if m.direction == "lower_better":
            ok = delta <= abs_margin + 1e-12
        else:
            ok = delta >= abs_margin - 1e-12
        report.compare_checks.append(
            GateCheck(
                gate_id=f"ni_{m.metric}",
                metric=m.metric,
                slice="all",
                op="lte" if m.direction == "lower_better" else "gte",
                threshold=abs_margin,
                observed=delta,
                passed=ok,
                detail=f"aggregate delta={delta:.4f} (no paired series)",
            )
        )
    return report


def load_run(store: FileEvalStore, run_id: str) -> EvalRunRecord:
    return store.load(run_id)


def write_thresholds_lock(path: Path | None = None, thresholds_path: Path | None = None) -> str:
    digest = thresholds_file_sha256(thresholds_path or DEFAULT_THRESHOLDS)
    lock = path or DEFAULT_LOCK
    lock.write_text(digest + "\n", encoding="utf-8")
    return digest


def read_thresholds_lock(path: Path | None = None) -> str:
    return (path or DEFAULT_LOCK).read_text(encoding="utf-8").strip()


__all__ = [
    "DEFAULT_LOCK",
    "DEFAULT_THRESHOLDS",
    "GateCheck",
    "GateReport",
    "GateSpec",
    "Thresholds",
    "gate_run",
    "gate_vs_baseline",
    "load_thresholds",
    "metric_lookup",
    "read_thresholds_lock",
    "thresholds_file_sha256",
    "write_thresholds_lock",
]
