"""Apply C0-C5 conditions and optional tempo perturbation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from callscope.datasets.conditions import CONDITION_SPECS, ConditionCode
from callscope.datasets.io_audio import (
    SAMPLE_RATE_HZ,
    ArrayF,
    apply_c1,
    apply_frame_loss,
    coloured_noise,
    mix_snr,
    tempo_stretch,
)


@dataclass(slots=True)
class AugmentationRecord:
    condition: ConditionCode
    seed: int
    sample_rate_hz: int
    snr_db_target: float | None = None
    frame_loss_rate: float = 0.0
    frame_loss_measured: float | None = None
    tempo: float = 1.0
    noise_licence: str = "synthetic-coloured (generated; no third-party audio)"
    telephony: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def apply_condition(
    audio: np.ndarray,
    *,
    condition: ConditionCode,
    seed: int,
    sr: int = SAMPLE_RATE_HZ,
    tempo: float = 1.0,
) -> tuple[np.ndarray, AugmentationRecord]:
    """Deterministically augment ``audio`` for ``condition``."""
    spec = CONDITION_SPECS[condition]
    rng = np.random.default_rng(seed)
    out: ArrayF = audio.astype(np.float32)
    if abs(tempo - 1.0) >= 1e-6:
        out = tempo_stretch(out, tempo)

    measured_loss: float | None = None
    if spec.telephony:
        out, sr = apply_c1(out, sr)

    if spec.snr_db is not None:
        noise = coloured_noise(len(out), rng, beta=1.0)
        out = mix_snr(out, noise, spec.snr_db)

    if spec.frame_loss_rate > 0:
        out, measured_loss = apply_frame_loss(
            out,
            sr,
            rate=spec.frame_loss_rate,
            frame_ms=spec.frame_loss_ms,
            rng=rng,
        )

    peak_v = float(np.max(np.abs(out)) + 1e-12)
    if peak_v > 0.98:
        out = (out * (0.98 / peak_v)).astype(np.float32)

    rec = AugmentationRecord(
        condition=condition,
        seed=seed,
        sample_rate_hz=sr,
        snr_db_target=spec.snr_db,
        frame_loss_rate=spec.frame_loss_rate,
        frame_loss_measured=measured_loss,
        tempo=tempo,
        telephony=spec.telephony,
    )
    return out.astype(np.float32), rec


__all__ = ["AugmentationRecord", "apply_condition"]
