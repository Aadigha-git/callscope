"""Paired bootstrap comparison between two eval runs on the same dataset."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast

import numpy as np

from callscope.eval.stats import DEFAULT_ALPHA, DEFAULT_N_BOOT, DEFAULT_SEED

Direction = Literal["lower_better", "higher_better"]
ArrayF = np.ndarray[Any, Any]


@dataclass(frozen=True, slots=True)
class PairedCompareResult:
    delta: float  # candidate - baseline
    ci_low: float
    ci_high: float
    non_inferior: bool
    margin: float
    n: int
    n_boot: int
    seed: int
    direction: Direction

    def to_dict(self) -> dict[str, float | int | bool | str]:
        return {
            "delta": self.delta,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "non_inferior": self.non_inferior,
            "margin": self.margin,
            "n": self.n,
            "n_boot": self.n_boot,
            "seed": self.seed,
            "direction": self.direction,
        }


def _ci(samples: ArrayF, alpha: float) -> tuple[float, float]:
    return (
        float(np.quantile(samples, alpha / 2.0)),
        float(np.quantile(samples, 1.0 - alpha / 2.0)),
    )


def paired_bootstrap(
    baseline: list[float] | ArrayF,
    candidate: list[float] | ArrayF,
    *,
    margin: float,
    direction: Direction = "lower_better",
    n_boot: int = DEFAULT_N_BOOT,
    seed: int = DEFAULT_SEED,
    alpha: float = DEFAULT_ALPHA,
) -> PairedCompareResult:
    """Paired bootstrap on per-call deltas (candidate - baseline).

    Non-inferiority:
    - ``lower_better`` (WER, latency): non-inferior if CI high <= margin
      (margin is the allowed absolute worsening, e.g. +0.01 WER).
    - ``higher_better`` (task success): non-inferior if CI low >= margin
      (margin is typically negative, e.g. -0.02).
    """
    a: ArrayF = cast(ArrayF, np.asarray(baseline, dtype=np.float64))
    b: ArrayF = cast(ArrayF, np.asarray(candidate, dtype=np.float64))
    if a.shape != b.shape:
        raise ValueError("baseline and candidate must be paired (same length)")
    n = int(a.size)
    if n == 0:
        return PairedCompareResult(0.0, 0.0, 0.0, True, margin, 0, n_boot, seed, direction)
    deltas = b - a
    est = float(np.mean(deltas))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    samples = cast(ArrayF, np.mean(deltas[idx], axis=1))
    lo, hi = _ci(samples, alpha)
    non_inf = hi <= margin + 1e-12 if direction == "lower_better" else lo >= margin - 1e-12
    return PairedCompareResult(est, lo, hi, non_inf, margin, n, n_boot, seed, direction)


def paired_bootstrap_ratio(
    baseline_num: list[float] | ArrayF,
    baseline_den: list[float] | ArrayF,
    candidate_num: list[float] | ArrayF,
    candidate_den: list[float] | ArrayF,
    *,
    margin: float,
    direction: Direction = "lower_better",
    n_boot: int = DEFAULT_N_BOOT,
    seed: int = DEFAULT_SEED,
    alpha: float = DEFAULT_ALPHA,
) -> PairedCompareResult:
    """Paired bootstrap of ratio deltas (e.g. WER) recomputed per resample."""
    bn: ArrayF = cast(ArrayF, np.asarray(baseline_num, dtype=np.float64))
    bd: ArrayF = cast(ArrayF, np.asarray(baseline_den, dtype=np.float64))
    cn: ArrayF = cast(ArrayF, np.asarray(candidate_num, dtype=np.float64))
    cd: ArrayF = cast(ArrayF, np.asarray(candidate_den, dtype=np.float64))
    if not (bn.shape == bd.shape == cn.shape == cd.shape):
        raise ValueError("all paired ratio arrays must share length")
    n = int(bn.size)
    if n == 0:
        return PairedCompareResult(0.0, 0.0, 0.0, True, margin, 0, n_boot, seed, direction)

    def _ratio(num: ArrayF, den: ArrayF) -> float:
        s = float(np.sum(den))
        return float(np.sum(num) / s) if s > 0 else 0.0

    est = _ratio(cn, cd) - _ratio(bn, bd)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    samples: ArrayF = cast(ArrayF, np.empty(n_boot, dtype=np.float64))
    for i in range(n_boot):
        j = idx[i]
        samples[i] = _ratio(cn[j], cd[j]) - _ratio(bn[j], bd[j])
    lo, hi = _ci(samples, alpha)
    non_inf = hi <= margin + 1e-12 if direction == "lower_better" else lo >= margin - 1e-12
    return PairedCompareResult(est, lo, hi, non_inf, margin, n, n_boot, seed, direction)


__all__ = [
    "Direction",
    "PairedCompareResult",
    "paired_bootstrap",
    "paired_bootstrap_ratio",
]
