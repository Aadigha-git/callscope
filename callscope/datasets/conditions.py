"""Telephony condition codes C0-C5 (design 4.6)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ConditionCode = Literal["C0", "C1", "C2", "C3", "C4", "C5"]

ALL_CONDITIONS: tuple[ConditionCode, ...] = ("C0", "C1", "C2", "C3", "C4", "C5")

# SNR targets (dB) for noisy conditions on top of C1.
SNR_DB: dict[ConditionCode, float | None] = {
    "C0": None,
    "C1": None,
    "C2": 20.0,
    "C3": 10.0,
    "C4": 5.0,
    "C5": None,
}

FRAME_LOSS_RATE = 0.05
FRAME_LOSS_MS = 20


@dataclass(frozen=True, slots=True)
class ConditionSpec:
    code: ConditionCode
    description: str
    snr_db: float | None = None
    frame_loss_rate: float = 0.0
    frame_loss_ms: int = FRAME_LOSS_MS
    telephony: bool = False  # C1 chain (band-limit + 8 kHz mu-law)


CONDITION_SPECS: dict[ConditionCode, ConditionSpec] = {
    "C0": ConditionSpec("C0", "Clean 16 kHz"),
    "C1": ConditionSpec(
        "C1",
        "Telephony band-limit 300-3400 Hz, 8 kHz mu-law",
        telephony=True,
    ),
    "C2": ConditionSpec(
        "C2",
        "C1 + noise SNR 20 dB",
        snr_db=20.0,
        telephony=True,
    ),
    "C3": ConditionSpec(
        "C3",
        "C1 + noise SNR 10 dB",
        snr_db=10.0,
        telephony=True,
    ),
    "C4": ConditionSpec(
        "C4",
        "C1 + noise SNR 5 dB",
        snr_db=5.0,
        telephony=True,
    ),
    "C5": ConditionSpec(
        "C5",
        "C1 + 5% random 20 ms frame loss",
        frame_loss_rate=FRAME_LOSS_RATE,
        telephony=True,
    ),
}


__all__ = [
    "ALL_CONDITIONS",
    "CONDITION_SPECS",
    "FRAME_LOSS_MS",
    "FRAME_LOSS_RATE",
    "SNR_DB",
    "ConditionCode",
    "ConditionSpec",
]
