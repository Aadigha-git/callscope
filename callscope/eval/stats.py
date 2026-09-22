"""Bootstrap confidence intervals over *calls* (design §4.6)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast

import numpy as np

DEFAULT_N_BOOT = 1_000
DEFAULT_SEED = 42
DEFAULT_ALPHA = 0.05

ArrayF = np.ndarray[Any, Any]


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    estimate: float
    ci_low: float
    ci_high: float
    n: int
    n_boot: int
    seed: int
    kind: Literal["mean", "ratio", "percentile"]

    def to_dict(self) -> dict[str, float | int | str]:
        return {
            "estimate": self.estimate,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "n": self.n,
            "n_boot": self.n_boot,
            "seed": self.seed,
            "kind": self.kind,
        }


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def _percentile_ci(samples: ArrayF, alpha: float) -> tuple[float, float]:
    lo = float(np.quantile(samples, alpha / 2.0))
    hi = float(np.quantile(samples, 1.0 - alpha / 2.0))
    return lo, hi


def bootstrap_mean(
    values: list[float] | ArrayF,
    *,
    n_boot: int = DEFAULT_N_BOOT,
    seed: int = DEFAULT_SEED,
    alpha: float = DEFAULT_ALPHA,
) -> BootstrapResult:
    """Mean of per-call values with percentile bootstrap CI."""
    x: ArrayF = cast(ArrayF, np.asarray(values, dtype=np.float64))
    n = int(x.size)
    if n == 0:
        return BootstrapResult(0.0, 0.0, 0.0, 0, n_boot, seed, "mean")
    est = float(np.mean(x))
    rng = _rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    samples = cast(ArrayF, np.mean(x[idx], axis=1))
    lo, hi = _percentile_ci(samples, alpha)
    return BootstrapResult(est, lo, hi, n, n_boot, seed, "mean")


def bootstrap_ratio(
    numerators: list[float] | ArrayF,
    denominators: list[float] | ArrayF,
    *,
    n_boot: int = DEFAULT_N_BOOT,
    seed: int = DEFAULT_SEED,
    alpha: float = DEFAULT_ALPHA,
) -> BootstrapResult:
    """Ratio metric Σnum / Σden over calls (correct for WER = errors/words)."""
    num: ArrayF = cast(ArrayF, np.asarray(numerators, dtype=np.float64))
    den: ArrayF = cast(ArrayF, np.asarray(denominators, dtype=np.float64))
    if num.shape != den.shape:
        raise ValueError("numerators and denominators must have the same length")
    n = int(num.size)
    if n == 0:
        return BootstrapResult(0.0, 0.0, 0.0, 0, n_boot, seed, "ratio")
    den_sum = float(np.sum(den))
    est = float(np.sum(num) / den_sum) if den_sum > 0 else 0.0
    rng = _rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    boot_num = np.sum(num[idx], axis=1)
    boot_den = np.sum(den[idx], axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        samples = cast(ArrayF, np.where(boot_den > 0, boot_num / boot_den, 0.0).astype(np.float64))
    lo, hi = _percentile_ci(samples, alpha)
    return BootstrapResult(est, lo, hi, n, n_boot, seed, "ratio")


def bootstrap_percentile(
    values: list[float] | ArrayF,
    *,
    q: float = 95.0,
    n_boot: int = DEFAULT_N_BOOT,
    seed: int = DEFAULT_SEED,
    alpha: float = DEFAULT_ALPHA,
) -> BootstrapResult:
    """Percentile (e.g. latency p95) with bootstrap CI over calls."""
    if not 0.0 <= q <= 100.0:
        raise ValueError("q must be in [0, 100]")
    x: ArrayF = cast(ArrayF, np.asarray(values, dtype=np.float64))
    n = int(x.size)
    if n == 0:
        return BootstrapResult(0.0, 0.0, 0.0, 0, n_boot, seed, "percentile")
    est = float(np.percentile(x, q))
    rng = _rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    samples = cast(ArrayF, np.percentile(x[idx], q, axis=1).astype(np.float64))
    lo, hi = _percentile_ci(samples, alpha)
    return BootstrapResult(est, lo, hi, n, n_boot, seed, "percentile")


def ci_width_note(*, n_calls: int, n_recorded: int = 30) -> str:
    """Document what smaller n means for CI width (acceptance for T-M3-06 / M3 docs)."""
    return (
        f"Bootstrap CIs over calls (n={n_calls} synthetic typical). "
        f"Recorded human sets are smaller (n≈{n_recorded}); expect substantially wider "
        f"intervals (roughly scaling as 1/sqrt(n)). Do not over-interpret slice CIs "
        f"with n<30."
    )


__all__ = [
    "DEFAULT_ALPHA",
    "DEFAULT_N_BOOT",
    "DEFAULT_SEED",
    "ArrayF",
    "BootstrapResult",
    "bootstrap_mean",
    "bootstrap_percentile",
    "bootstrap_ratio",
    "ci_width_note",
]
