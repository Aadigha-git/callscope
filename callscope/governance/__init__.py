"""Governance: model/stack registry, MLflow, cards, reports, lifecycle."""

from callscope.governance.cards import card_is_complete, render_model_card
from callscope.governance.lifecycle import GateError, TransitionContext, check_transition
from callscope.governance.mlflow_utils import default_tracking_uri, log_eval_run
from callscope.governance.registry import (
    CI_STACK_ALIASES,
    ModelStackRegistry,
    ModelVersionRecord,
    RegistryError,
    StackVersionRecord,
    backfill_m0_inventory,
    config_sha256,
    ensure_eval_stack,
)
from callscope.governance.reports import render_validation_report, report_repro_fingerprint
from callscope.governance.risk import RiskRegister

__all__ = [
    "CI_STACK_ALIASES",
    "GateError",
    "ModelStackRegistry",
    "ModelVersionRecord",
    "RegistryError",
    "RiskRegister",
    "StackVersionRecord",
    "TransitionContext",
    "backfill_m0_inventory",
    "card_is_complete",
    "check_transition",
    "config_sha256",
    "default_tracking_uri",
    "ensure_eval_stack",
    "log_eval_run",
    "render_model_card",
    "render_validation_report",
    "report_repro_fingerprint",
]
