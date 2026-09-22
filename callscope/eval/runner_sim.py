"""Caller-sim eval mode: run scenarios against local stack or mock transport."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from callscope.eval.persist import FileEvalStore
from callscope.eval.scenarios import ExpandedScenario, expand_scenario, load_all_scenarios
from callscope.eval.types import EvalItemResult
from callscope.sim.caller import MockCallerTransport, SimulatedCaller
from callscope.sim.oracle import OracleThresholds, score_timeline


@dataclass(frozen=True, slots=True)
class CallerSimConfig:
    store_dir: Path
    stack_version_id: str = "local-mock"
    seed: int = 42
    livekit_url: str = "ws://127.0.0.1:7880"
    livekit_jwt: str = "sim-token"


def _synthetic_agent_events(
    caller_events: list[dict[str, Any]], *, expected_barge: bool
) -> list[dict[str, Any]]:
    """Deterministic agent-side events for CI without a real worker."""
    out: list[dict[str, Any]] = []
    for ev in caller_events:
        if ev.get("type") != "stt.final":
            continue
        t = int(ev["t_ms"])
        out.append({"type": "brain.first_token", "t_ms": t + 350, "payload": {"text": "ok"}})
        out.append({"type": "tts.first_audio", "t_ms": t + 500, "payload": {}})
        out.append({"type": "playback.start", "t_ms": t + 520, "payload": {}})
        if expected_barge:
            barge_t = t + 200
            out.append({"type": "barge_in", "t_ms": barge_t, "payload": {}})
            out.append({"type": "playback.stop", "t_ms": barge_t + 180, "payload": {}})
        else:
            out.append({"type": "playback.stop", "t_ms": t + 1200, "payload": {}})
    return out


def aggregate_sim_metrics(item_results: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate caller-sim oracle metrics into eval_metrics-shaped rows."""
    if not item_results:
        return []
    keys = (
        "sim_pass",
        "sim.response_latency_ms",
        "sim.dead_air_ms",
        "sim.barge_stop_latency_ms",
    )
    buckets: dict[str, list[float]] = {k: [] for k in keys}
    for row in item_results.values():
        detail = row.get("detail") or {}
        scores = detail.get("sim_scores") or {}
        for k in keys:
            if k in scores:
                buckets[k].append(float(scores[k]))
        lat = (row.get("latencies_ms") or {}).get("response_latency_ms")
        if lat is not None:
            buckets["sim.response_latency_ms"].append(float(lat))
    out: list[dict[str, Any]] = []
    for metric, vals in buckets.items():
        if not vals:
            continue
        out.append(
            {
                "metric": metric,
                "slice": "all",
                "value": sum(vals) / len(vals),
                "ci_low": min(vals),
                "ci_high": max(vals),
                "n": len(vals),
            }
        )
    return out


async def run_one_scenario(
    scenario: ExpandedScenario,
    *,
    caller: SimulatedCaller,
    livekit_url: str,
    livekit_jwt: str,
    wall_clock: bool = False,
) -> tuple[str, EvalItemResult]:
    expected_barge = any(t.barge_in_at_ms is not None for t in scenario.turns)
    run = await caller.run_scenario(
        scenario, livekit_url=livekit_url, token=livekit_jwt, wall_clock=wall_clock
    )
    agent_ev = _synthetic_agent_events(run.events, expected_barge=expected_barge)
    all_events = sorted(run.events + agent_ev, key=lambda e: int(e.get("t_ms") or 0))
    report = score_timeline(
        all_events, thresholds=OracleThresholds(), expected_barge=expected_barge
    )
    metrics = report.metrics_dict()
    ok = all(f.ok for f in report.findings)
    metrics["sim_pass"] = 1.0 if ok else 0.0
    latencies = {
        k.replace("sim.", ""): v
        for k, v in metrics.items()
        if k.endswith("_ms") and not k.endswith(".ok")
    }
    item_id = f"{scenario.scenario_id}-v{scenario.variant}"
    item = EvalItemResult(
        hyp_transcript=" ".join(t.caller for t in scenario.turns),
        wer=0.0 if ok else 1.0,
        latencies_ms=latencies,
        flags=[] if ok else ["sim_fail"],
        detail={
            "condition": "sim",
            "scenario_id": scenario.scenario_id,
            "sim_scores": metrics,
            "findings": [f.metric for f in report.findings],
            "n_actions": len(run.actions),
            "channel": "sim",
        },
    )
    return item_id, item


async def run_caller_sim(config: CallerSimConfig) -> dict[str, Any]:
    """Run all YAML scenarios in caller_sim mode; write FileEvalStore metrics."""
    store = FileEvalStore(config.store_dir)
    run = store.create_run(
        dataset_id="scenarios@local",
        stack_version_id=config.stack_version_id,
        mode="caller_sim",
        git_sha="caller-sim",
        estimated_usd=0.0,
        config={"seed": config.seed},
    )
    transport = MockCallerTransport()
    caller = SimulatedCaller(transport=transport)
    scenarios = load_all_scenarios()
    for sc in scenarios:
        expanded = expand_scenario(sc, seed=config.seed, variant=0)
        item_id, item = await run_one_scenario(
            expanded,
            caller=caller,
            livekit_url=config.livekit_url,
            livekit_jwt=config.livekit_jwt,
            wall_clock=False,
        )
        store.write_item(run.run_id, item_id, item)
    finished = store.load(run.run_id)
    metrics = aggregate_sim_metrics(finished.item_results)
    store.finalize(run.run_id, status="succeeded", metrics=metrics)
    return {
        "run_id": run.run_id,
        "n_scenarios": len(scenarios),
        "metrics": metrics,
        "store_dir": str(config.store_dir),
    }
