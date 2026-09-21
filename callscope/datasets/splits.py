"""Group-based train/dev/test splits with voice and scenario-variant holdout."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from random import Random
from typing import Any, Literal

SplitName = Literal["train", "dev", "test"]

# Design default targets (scaled when n < 300).
DEFAULT_TRAIN = 200
DEFAULT_DEV = 50
DEFAULT_TEST = 50


@dataclass(frozen=True, slots=True)
class SplitPlan:
    train: list[dict[str, Any]]
    dev: list[dict[str, Any]]
    test: list[dict[str, Any]]
    held_voices: tuple[str, ...]
    held_variants: tuple[str, ...]
    frozen_test: bool = False

    def all_items(self) -> list[dict[str, Any]]:
        return [*self.train, *self.dev, *self.test]

    def counts(self) -> dict[str, int]:
        return {"train": len(self.train), "dev": len(self.dev), "test": len(self.test)}


def _variant_key(item: dict[str, Any]) -> str:
    return f"{item.get('scenario_id')}:{item.get('variant')}"


def assign_splits(
    items: list[dict[str, Any]],
    *,
    seed: int = 42,
    holdout_voices: int = 2,
    holdout_variants: int = 2,
    train_n: int = DEFAULT_TRAIN,
    dev_n: int = DEFAULT_DEV,
    test_n: int = DEFAULT_TEST,
    frozen_test: bool = False,
) -> SplitPlan:
    """Assign each voice and each scenario-variant to exactly one split.

    ``holdout_voices`` / ``holdout_variants`` are reserved for dev/test (split
    evenly between them). Remaining groups are train-only. An item is kept only
    when its voice and variant agree on the same split — guaranteeing no
    cross-split leakage.
    """
    if not items:
        return SplitPlan([], [], [], (), (), frozen_test=frozen_test)

    rng = Random(seed)  # noqa: S311 — deterministic fixture RNG
    voices = sorted({str(i.get("voice", "")) for i in items if i.get("voice")})
    variants = sorted({_variant_key(i) for i in items})

    n_hv = min(holdout_voices, max(0, len(voices) - 1)) if len(voices) > 1 else 0
    n_hvar = min(holdout_variants, max(0, len(variants) - 1)) if len(variants) > 1 else 0
    held_voices_list = rng.sample(voices, n_hv) if n_hv else []
    held_variants_list = rng.sample(variants, n_hvar) if n_hvar else []
    held_voices = tuple(sorted(held_voices_list))
    held_variants = tuple(sorted(held_variants_list))

    voice_split: dict[str, SplitName] = {v: "train" for v in voices}
    variant_split: dict[str, SplitName] = {v: "train" for v in variants}

    # First half of held groups -> test, second half -> dev (exclusive).
    mid_v = (len(held_voices_list) + 1) // 2
    for v in held_voices_list[:mid_v]:
        voice_split[v] = "test"
    for v in held_voices_list[mid_v:]:
        voice_split[v] = "dev"

    mid_var = (len(held_variants_list) + 1) // 2
    for v in held_variants_list[:mid_var]:
        variant_split[v] = "test"
    for v in held_variants_list[mid_var:]:
        variant_split[v] = "dev"

    buckets: dict[SplitName, list[dict[str, Any]]] = {"train": [], "dev": [], "test": []}
    for raw in items:
        item = deepcopy(raw)
        voice = str(item.get("voice", ""))
        vkey = _variant_key(item)
        vs = voice_split.get(voice, "train")
        vars_ = variant_split.get(vkey, "train")
        if vs != vars_:
            # Conflicting group assignments — drop to avoid leakage.
            continue
        item["split"] = vs
        if vs == "test" and frozen_test:
            item["frozen"] = True
        buckets[vs].append(item)

    for split in buckets:
        rng.shuffle(buckets[split])

    total = len(items)
    target_sum = train_n + dev_n + test_n
    if total < target_sum and target_sum > 0:
        scale = total / target_sum
        train_n = max(1, round(train_n * scale))
        dev_n = max(1, round(dev_n * scale))
        test_n = max(0, total - train_n - dev_n)

    train = buckets["train"][:train_n]
    dev = buckets["dev"][:dev_n]
    test = buckets["test"][:test_n]

    plan = SplitPlan(
        train=train,
        dev=dev,
        test=test,
        held_voices=held_voices,
        held_variants=held_variants,
        frozen_test=frozen_test,
    )
    from callscope.datasets.dq import check_split_leakage

    leaks = check_split_leakage(plan.all_items())
    if leaks:
        msgs = "; ".join(f.message for f in leaks)
        raise ValueError(f"split leakage: {msgs}")
    return plan


__all__ = [
    "DEFAULT_DEV",
    "DEFAULT_TEST",
    "DEFAULT_TRAIN",
    "SplitName",
    "SplitPlan",
    "assign_splits",
]
