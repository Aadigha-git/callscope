"""E3 endpointing / VAD grid search (T-M5-03)."""

from __future__ import annotations

import itertools
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from apps.worker.config import WorkerConfig
from callscope.eval.compare import paired_bootstrap
from callscope.eval.scenarios import expand_scenario, load_all_scenarios
from callscope.sim.oracle import OracleThresholds, score_timeline


@dataclass(frozen=True, slots=True)
class EndpointPoint:
    endpoint_min_delay_s: float
    endpoint_max_delay_s: float
    vad_threshold: float
    barge_in_min_duration_ms: int

    def to_worker(self) -> WorkerConfig:
        return WorkerConfig(
            endpoint_min_delay_s=self.endpoint_min_delay_s,
            endpoint_max_delay_s=self.endpoint_max_delay_s,
            vad_threshold=self.vad_threshold,
            barge_in_min_duration_ms=self.barge_in_min_duration_ms,
        )


DEFAULT_POINT = EndpointPoint(0.4, 1.2, 0.5, 250)
# Pre-E3 defaults used as control; adopted values land in WorkerConfig after decision.

# Small grid — train/dev selection only; one frozen eval afterward.
GRID: tuple[EndpointPoint, ...] = tuple(
    EndpointPoint(mn, mx, vad, barge)
    for mn, mx, vad, barge in itertools.product(
        (0.3, 0.4, 0.55),
        (0.9, 1.2, 1.5),
        (0.4, 0.5, 0.65),
        (200, 250, 350),
    )
    if mn < mx
)


def _synth_events(cfg: WorkerConfig, *, seed: int, barge: bool) -> list[dict[str, Any]]:
    """Build a timeline whose oracle scores depend on endpoint/VAD knobs."""
    t0 = 100 + (seed % 50)
    speak_ms = 800 + (seed % 400)
    caller_start = t0
    caller_end = t0 + speak_ms

    # Premature when VAD is aggressive and endpoint min is short (deterministic).
    premature_score = (0.55 - cfg.vad_threshold) * 2.5 + (0.5 - cfg.endpoint_min_delay_s) * 2.0
    premature = premature_score > 0.2

    delay_ms = int(cfg.endpoint_min_delay_s * 1000)
    delay_ms += int((cfg.vad_threshold - 0.35) * 600)
    agent_start = caller_end - 120 if premature else caller_end + delay_ms

    events: list[dict[str, Any]] = [
        {"type": "caller.start", "t_ms": caller_start, "t_end_ms": caller_end},
        {"type": "vad.start", "t_ms": caller_start},
        {"type": "vad.end", "t_ms": caller_end},
        {"type": "stt.final", "t_ms": caller_end + 40},
        {"type": "brain.first_token", "t_ms": agent_start},
        {"type": "tts.first_audio", "t_ms": agent_start + 80},
        {"type": "playback.start", "t_ms": agent_start + 80},
    ]
    if barge:
        barge_at = max(agent_start + 80 + 50, caller_end + 100)
        stop_at = barge_at + cfg.barge_in_min_duration_ms
        events.extend(
            [
                {"type": "barge_in", "t_ms": barge_at},
                {"type": "caller.start", "t_ms": barge_at, "t_end_ms": barge_at + 600},
                {"type": "vad.start", "t_ms": barge_at},
                {"type": "playback.stop", "t_ms": stop_at},
            ]
        )
    return events


def score_point(
    point: EndpointPoint,
    *,
    seeds: list[int],
    thresholds: OracleThresholds | None = None,
) -> dict[str, float]:
    cfg = point.to_worker()
    th = thresholds or OracleThresholds()
    premature_fails = 0
    late_fails = 0
    latencies: list[float] = []
    n = 0
    # Intended response delay from knobs (latency guardrail; independent of premature overlap).
    intended_ms = cfg.endpoint_min_delay_s * 1000.0 + (cfg.vad_threshold - 0.35) * 600.0
    for seed in seeds:
        barge = seed % 5 == 0
        events = _synth_events(cfg, seed=seed, barge=barge)
        report = score_timeline(events, thresholds=th, expected_barge=barge)
        metrics = report.metrics_dict()
        n += 1
        if metrics.get("sim.premature_endpoint.ok", 1.0) < 0.5:
            premature_fails += 1
        if metrics.get("sim.late_endpoint.ok", 1.0) < 0.5:
            late_fails += 1
        latencies.append(max(0.0, intended_ms))
    latencies.sort()
    p50 = latencies[len(latencies) // 2] if latencies else 0.0
    return {
        "n": float(n),
        "premature_rate": premature_fails / max(n, 1),
        "late_rate": late_fails / max(n, 1),
        "endpoint_error_rate": (premature_fails + late_fails) / max(n, 1),
        "latency_p50_ms": p50,
    }


def _dev_test_seeds() -> tuple[list[int], list[int]]:
    """Dev = odd scenario expansions; test = even (frozen stand-in)."""
    scenarios = load_all_scenarios()
    dev: list[int] = []
    test: list[int] = []
    for i, sc in enumerate(scenarios):
        for variant in range(2):
            exp = expand_scenario(sc, seed=42, variant=variant)
            seed = (hash(exp.scenario_id) & 0xFFFF) + variant * 17 + i
            if variant % 2 == 1:
                dev.append(seed)
            else:
                test.append(seed)
    return dev, test


def run_e3(
    *,
    out_dir: Path,
    log_mlflow: bool = True,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    dev_seeds, test_seeds = _dev_test_seeds()

    baseline = score_point(DEFAULT_POINT, seeds=dev_seeds)
    rows: list[dict[str, Any]] = []
    best: EndpointPoint | None = None
    best_score = math.inf

    for point in GRID:
        m = score_point(point, seeds=dev_seeds)
        lat_delta = m["latency_p50_ms"] - baseline["latency_p50_ms"]
        row = {
            **asdict(point),
            **m,
            "latency_p50_delta_ms": lat_delta,
            "feasible": lat_delta <= 100.0,
        }
        rows.append(row)
        if row["feasible"] and m["endpoint_error_rate"] < best_score:
            best_score = m["endpoint_error_rate"]
            best = point

    if best is None:
        best = DEFAULT_POINT

    # One frozen-test eval: default vs chosen
    control = score_point(DEFAULT_POINT, seeds=test_seeds)
    treatment = score_point(best, seeds=test_seeds)

    # Paired per-seed error (0/1) for bootstrap
    ctrl_errs: list[float] = []
    treat_errs: list[float] = []
    for seed in test_seeds:
        c = score_point(DEFAULT_POINT, seeds=[seed])
        t = score_point(best, seeds=[seed])
        ctrl_errs.append(c["endpoint_error_rate"])
        treat_errs.append(t["endpoint_error_rate"])

    cmp = paired_bootstrap(
        ctrl_errs,
        treat_errs,
        margin=0.05,
        direction="lower_better",
        seed=42,
    )
    delta_pp = (treatment["endpoint_error_rate"] - control["endpoint_error_rate"]) * 100.0
    lat_delta = treatment["latency_p50_ms"] - control["latency_p50_ms"]
    adopt = bool(delta_pp <= -5.0 and cmp.ci_high < 0 and lat_delta <= 100.0)
    decision = "adopt" if adopt else "reject"

    mlflow_run_id: str | None = None
    if log_mlflow:
        try:
            from callscope.governance.mlflow_utils import log_eval_run

            mlflow_run_id = log_eval_run(
                experiment="callscope-e3",
                run_name="e3-endpointing",
                params={**asdict(best), "n_test": str(len(test_seeds))},
                metrics={
                    "endpoint_error_control": control["endpoint_error_rate"],
                    "endpoint_error_treatment": treatment["endpoint_error_rate"],
                    "endpoint_error_delta_pp": delta_pp,
                    "latency_p50_delta_ms": lat_delta,
                    "ci_low": cmp.ci_low,
                    "ci_high": cmp.ci_high,
                },
                tags={"experiment": "E3", "decision": decision},
            )
        except Exception as exc:
            mlflow_run_id = f"skipped:{exc}"

    # Persist chosen config for worker adopt path
    chosen_path = out_dir / "chosen_endpoint.json"
    chosen_path.write_text(json.dumps(asdict(best), indent=2) + "\n", encoding="utf-8")
    (out_dir / "grid_dev.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )

    payload: dict[str, Any] = {
        "experiment": "E3",
        "decision": decision,
        "chosen": asdict(best),
        "control": control,
        "treatment": treatment,
        "endpoint_error_delta_pp": delta_pp,
        "paired_bootstrap": cmp.to_dict(),
        "latency_p50_delta_ms": lat_delta,
        "mlflow_run_id": mlflow_run_id,
        "n_grid": len(GRID),
        "n_dev": len(dev_seeds),
        "n_test": len(test_seeds),
    }
    (out_dir / "result.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if adopt:
        # Write overlay defaults for documentation (WorkerConfig still code-default;
        # adopt applies values into DECISIONS + optional env note).
        (out_dir / "ADOPT.md").write_text(
            f"Adopted EndpointPoint: {asdict(best)}\n", encoding="utf-8"
        )
    return payload


__all__ = ["DEFAULT_POINT", "GRID", "EndpointPoint", "run_e3", "score_point"]
