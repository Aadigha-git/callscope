"""Caller-sim oracle and mock runner tests (T-M4-04)."""

from __future__ import annotations

from pathlib import Path

import pytest

from callscope.eval.runner_sim import CallerSimConfig, run_caller_sim
from callscope.eval.scenarios import ScenarioTurn, expand_scenario, load_all_scenarios
from callscope.sim.caller import MockCallerTransport, SimulatedCaller, plan_actions
from callscope.sim.oracle import score_timeline

pytestmark = pytest.mark.unit


def test_plan_actions_includes_barge() -> None:
    turns = [
        ScenarioTurn(caller="hello", pause_ms=100),
        ScenarioTurn(caller="wait friday", barge_in_at_ms=500),
    ]
    actions = plan_actions(turns)
    assert any(a.kind == "barge" for a in actions)


def test_oracle_late_endpoint() -> None:
    events = [
        {"type": "stt.final", "t_ms": 0},
        {"type": "caller.stop", "t_ms": 0},
        {"type": "tts.first_audio", "t_ms": 3000},
    ]
    report = score_timeline(events)
    late = next(f for f in report.findings if f.metric == "late_endpoint")
    assert late.ok is False


def test_oracle_barge_stop_ok() -> None:
    events = [
        {"type": "stt.final", "t_ms": 0},
        {"type": "playback.start", "t_ms": 100},
        {"type": "barge_in", "t_ms": 200},
        {"type": "playback.stop", "t_ms": 350},
        {"type": "tts.first_audio", "t_ms": 100},
    ]
    report = score_timeline(events, expected_barge=True)
    barge = next(f for f in report.findings if f.metric == "barge_stop_latency_ms")
    assert barge.ok is True
    assert barge.value_ms == 150.0


def test_oracle_false_barge() -> None:
    events = [
        {"type": "stt.final", "t_ms": 0},
        {"type": "barge_in", "t_ms": 50},
        {"type": "tts.first_audio", "t_ms": 200},
    ]
    report = score_timeline(events, expected_barge=False)
    hit = next(f for f in report.findings if f.metric == "false_barge_in")
    assert hit.ok is False


@pytest.mark.asyncio
async def test_mock_caller_publishes() -> None:
    scenarios = load_all_scenarios()
    sc = expand_scenario(scenarios[0], seed=1, variant=0)
    transport = MockCallerTransport()
    caller = SimulatedCaller(transport=transport)
    result = await caller.run_scenario(sc, livekit_url="ws://x", token="t")
    assert result.connected is True
    assert transport.published
    assert any(e["type"] == "stt.final" for e in result.events)


@pytest.mark.asyncio
async def test_run_caller_sim_writes_metrics(tmp_path: Path) -> None:
    scenarios = load_all_scenarios()
    assert len(scenarios) == 16
    result = await run_caller_sim(
        CallerSimConfig(store_dir=tmp_path, stack_version_id="ci-mock", seed=7)
    )
    assert result["n_scenarios"] == 16
    assert result["metrics"]
    assert any(m["metric"] == "sim_pass" for m in result["metrics"])
