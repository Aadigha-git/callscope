"""Model lifecycle transition gates (T-M5-04)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from callscope.governance.cards import card_is_complete, card_path_for
from callscope.governance.risk import RiskRegister


class GateError(ValueError):
    """Lifecycle gate failed; ``unmet`` lists human-readable reasons."""

    def __init__(self, message: str, unmet: list[str]) -> None:
        super().__init__(message)
        self.unmet = unmet


ALLOWED: dict[str, set[str]] = {
    "candidate": {"validated", "rejected"},
    "validated": {"production", "retired", "rejected"},
    "production": {"retired"},
    "retired": set(),
    "rejected": set(),
}


@dataclass
class TransitionContext:
    report_passed: bool | None = None
    report_id: UUID | None = None
    card_dir: Path = field(default_factory=lambda: Path("docs/model_cards"))
    risk_register: RiskRegister | None = None
    monitoring_on: bool = True
    rollback_stack_id: str | None = None
    intended_use: str | None = None


def check_transition(
    *,
    status: str,
    to: str,
    model_version_id: UUID,
    ctx: TransitionContext,
) -> None:
    """Raise ``GateError`` if the transition is illegal or gates fail."""
    unmet: list[str] = []
    if to not in ALLOWED.get(status, set()):
        raise GateError(
            f"cannot transition {status} -> {to}",
            [f"illegal transition {status}->{to}"],
        )

    if status == "candidate" and to == "validated":
        if ctx.report_id is None:
            unmet.append("report_id required for candidate->validated")
        if ctx.report_passed is not True:
            unmet.append("passing frozen-test validation report required")
        if not (ctx.intended_use and ctx.intended_use.strip()):
            unmet.append("intended_use required on model before validation")

    if status == "validated" and to == "production":
        card = card_path_for(model_version_id, out_dir=ctx.card_dir)
        if card is None or not card_is_complete(card):
            unmet.append("complete model card required for production")
        if not ctx.monitoring_on:
            unmet.append("monitoring must be on for production")
        if not ctx.rollback_stack_id:
            unmet.append("rollback_stack_id required for production")
        if ctx.risk_register is not None and not ctx.risk_register.assessment_complete(
            model_version_id
        ):
            unmet.append("completed risk assessment required for production")

    if unmet:
        raise GateError(f"gate failed for {status}->{to}", unmet)


def transition_detail(unmet: list[str]) -> dict[str, Any]:
    return {"unmet": unmet}


__all__ = [
    "ALLOWED",
    "GateError",
    "TransitionContext",
    "check_transition",
    "transition_detail",
]
