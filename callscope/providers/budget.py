"""LLM budget guard for Nebius Token Factory spend (ADR-016, NFR-11).

Pricing and usage shapes are grounded in:
- Catalog $/1M tokens from D-20260920-12 (public Token Factory model catalog).
- OpenAI-compatible ``usage.prompt_tokens`` / ``usage.completion_tokens`` as observed
  in spikes (T-M0-07 / T-M0-03). We do **not** invent a ``usage.cost`` field.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from callscope.config import Settings, get_settings

# USD per 1M tokens — D-20260920-12 public catalog (fetched 2026-09-20).
CATALOG_PRICES_USD_PER_1M: dict[str, tuple[float, float]] = {
    "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B": (0.06, 0.24),
    "nvidia/Nemotron-3_5-Lightning": (0.06, 0.24),
    "Qwen/Qwen3-30B-A3B-Instruct-2507": (0.10, 0.30),
    "google/gemma-3-27b-it": (0.10, 0.30),
    "deepseek-ai/DeepSeek-V4-Flash-0731": (0.14, 0.28),
    "openai/gpt-oss-120b": (0.15, 0.60),
    "Qwen/Qwen3-235B-A22B-Instruct-2507": (0.20, 0.60),
}

DEFAULT_MODEL = "nvidia/Nemotron-3_5-Lightning"


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """Input/output price in USD per 1M tokens."""

    input_per_1m: float
    output_per_1m: float


@dataclass(frozen=True, slots=True)
class BudgetStatus:
    budget_usd: float
    spend_usd: float
    remaining_usd: float
    model: str

    @property
    def exhausted(self) -> bool:
        return self.remaining_usd <= 0.0


class BudgetExceededError(RuntimeError):
    """Raised when a live run would exceed CALLSCOPE_LLM_BUDGET_USD."""

    def __init__(self, message: str, *, status: BudgetStatus, projected_usd: float) -> None:
        super().__init__(message)
        self.status = status
        self.projected_usd = projected_usd


def price_for(model: str) -> ModelPrice:
    pair = CATALOG_PRICES_USD_PER_1M.get(model)
    if pair is None:
        raise KeyError(
            f"unknown Token Factory model pricing for {model!r}; "
            f"known: {sorted(CATALOG_PRICES_USD_PER_1M)}"
        )
    return ModelPrice(input_per_1m=pair[0], output_per_1m=pair[1])


def estimate_usd(
    prompt_tokens: int,
    completion_tokens: int,
    *,
    model: str = DEFAULT_MODEL,
) -> float:
    """Estimate USD from token counts x catalog $/1M (no network)."""
    if prompt_tokens < 0 or completion_tokens < 0:
        raise ValueError("token counts must be non-negative")
    p = price_for(model)
    return (prompt_tokens * p.input_per_1m + completion_tokens * p.output_per_1m) / 1_000_000.0


def cost_from_usage(usage: Mapping[str, Any], *, model: str = DEFAULT_MODEL) -> float:
    """Cost from an OpenAI-compatible ``usage`` object (prompt/completion tokens only)."""
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    return estimate_usd(prompt, completion, model=model)


@dataclass
class BudgetGuard:
    """Fail-closed guard for live Token Factory calls."""

    budget_usd: float = 15.0
    spend_usd: float = 0.0
    model: str = DEFAULT_MODEL
    _spend: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.budget_usd < 0:
            raise ValueError("budget_usd must be >= 0")
        if self.spend_usd < 0:
            raise ValueError("spend_usd must be >= 0")
        self._spend = float(self.spend_usd)

    @classmethod
    def from_settings(
        cls,
        settings: Settings | None = None,
        *,
        model: str | None = None,
    ) -> BudgetGuard:
        s = settings or get_settings()
        resolved = model or os.environ.get("TOKEN_FACTORY_MODEL") or DEFAULT_MODEL
        return cls(budget_usd=s.llm_budget_usd, spend_usd=s.llm_spend_usd, model=resolved)

    def status(self) -> BudgetStatus:
        remaining = self.budget_usd - self._spend
        return BudgetStatus(
            budget_usd=self.budget_usd,
            spend_usd=self._spend,
            remaining_usd=remaining,
            model=self.model,
        )

    def estimate(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        *,
        model: str | None = None,
    ) -> float:
        return estimate_usd(
            prompt_tokens,
            completion_tokens,
            model=model or self.model,
        )

    def cost_from_usage(self, usage: Mapping[str, Any], *, model: str | None = None) -> float:
        return cost_from_usage(usage, model=model or self.model)

    def would_exceed(self, projected_usd: float) -> bool:
        if projected_usd < 0:
            raise ValueError("projected_usd must be >= 0")
        return (self._spend + projected_usd) > self.budget_usd + 1e-12

    def check_live(self, projected_usd: float) -> BudgetStatus:
        """Refuse a live run when spend + projected would exceed the cap."""
        st = self.status()
        if self.would_exceed(projected_usd):
            raise BudgetExceededError(
                f"live LLM run refused: projected ${projected_usd:.6f} + spend "
                f"${st.spend_usd:.6f} exceeds budget ${st.budget_usd:.2f} "
                f"(remaining ${st.remaining_usd:.6f})",
                status=st,
                projected_usd=projected_usd,
            )
        return st

    def require_live_budget(self, projected_usd: float) -> None:
        """Eval/live entrypoint hook — fail closed before any network call."""
        self.check_live(projected_usd)

    def record_spend(self, usd: float) -> float:
        """Accumulate spend after a completed live call. Returns new total."""
        if usd < 0:
            raise ValueError("usd must be >= 0")
        self._spend += usd
        return self._spend

    def estimated_usd_for_eval_run(self, projected_usd: float) -> float:
        """Value to persist on ``cs.eval_runs.estimated_usd`` for an upcoming run."""
        return round(projected_usd, 8)


def format_status(status: BudgetStatus) -> str:
    pct = 0.0 if status.budget_usd <= 0 else (status.spend_usd / status.budget_usd) * 100.0
    return (
        f"LLM budget: ${status.spend_usd:.6f} spent / ${status.budget_usd:.2f} cap "
        f"(${status.remaining_usd:.6f} remaining, {pct:.1f}% used)\n"
        f"Default model: {status.model}"
    )
