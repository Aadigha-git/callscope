"""Caller simulator package."""

from callscope.sim.caller import (
    CallerAction,
    CallerRunResult,
    LiveKitCallerTransport,
    MockCallerTransport,
    SimulatedCaller,
    plan_actions,
)
from callscope.sim.oracle import OracleFinding, OracleReport, OracleThresholds, score_timeline

__all__ = [
    "CallerAction",
    "CallerRunResult",
    "LiveKitCallerTransport",
    "MockCallerTransport",
    "OracleFinding",
    "OracleReport",
    "OracleThresholds",
    "SimulatedCaller",
    "plan_actions",
    "score_timeline",
]
