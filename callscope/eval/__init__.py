"""Evaluation harness: scenarios, scorers, runner (M3)."""

from callscope.eval.normalize import NORMALIZER_VERSION, normalize
from callscope.eval.runner import EvalRunConfig, estimate_eval_usd, run_eval
from callscope.eval.scenarios import (
    ExpandedScenario,
    Scenario,
    expand_scenario,
    load_all_scenarios,
    validate_library,
)
from callscope.eval.types import EvalItemResult

__all__ = [
    "NORMALIZER_VERSION",
    "EvalItemResult",
    "EvalRunConfig",
    "ExpandedScenario",
    "Scenario",
    "estimate_eval_usd",
    "expand_scenario",
    "load_all_scenarios",
    "normalize",
    "run_eval",
    "validate_library",
]
