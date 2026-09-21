"""Dataset builder package (synthetic + telephony augmentation + DQ)."""

from callscope.datasets.augment import AugmentationRecord, apply_condition
from callscope.datasets.conditions import ALL_CONDITIONS, CONDITION_SPECS
from callscope.datasets.dq import DqReport, run_dq
from callscope.datasets.registry import FileRegistry, RegistryError
from callscope.datasets.splits import SplitPlan, assign_splits
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
    "DqReport",
    "FileRegistry",
    "RegistryError",
    "SplitPlan",
    "apply_condition",
    "assign_splits",
    "build_dataset",
    "run_dq",
]
