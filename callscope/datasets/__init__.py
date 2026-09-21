"""Dataset builder package (synthetic + telephony augmentation)."""

from callscope.datasets.augment import AugmentationRecord, apply_condition
from callscope.datasets.conditions import ALL_CONDITIONS, CONDITION_SPECS
from callscope.datasets.synth import (
    CI_WIDTH_NOTE,
    DEFAULT_N_CALLS,
    DEFAULT_VOICES,
    build_dataset,
)

__all__ = [
    "ALL_CONDITIONS",
    "CI_WIDTH_NOTE",
    "CONDITION_SPECS",
    "DEFAULT_N_CALLS",
    "DEFAULT_VOICES",
    "AugmentationRecord",
    "apply_condition",
    "build_dataset",
]
