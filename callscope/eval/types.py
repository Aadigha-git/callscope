"""Scorer result types aligned with ``cs.eval_item_results`` (plus detail payloads)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class AsrScore:
    wer: float
    cer: float
    substitutions: int
    deletions: int
    insertions: int
    hits: int
    ref_words: int
    hyp_words: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EntityScore:
    entity_type: str  # PHONE | DATE | TIME | NAME | ADDRESS | CODE
    ref: str
    hyp: str
    exact: bool
    score: float
    phonetic_match: bool | None = None
    partial: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class NluScore:
    intent_correct: bool
    intent_ref: str
    intent_hyp: str
    slot_f1: float
    slot_precision: float
    slot_recall: float
    macro_f1: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ToolCallScore:
    exact_match: bool
    name_accuracy: float
    arg_accuracy: float
    ordered_names_ref: tuple[str, ...]
    ordered_names_hyp: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ordered_names_ref"] = list(self.ordered_names_ref)
        d["ordered_names_hyp"] = list(self.ordered_names_hyp)
        return d


@dataclass(frozen=True, slots=True)
class TaskScore:
    task_success: bool
    policy_ok: bool
    final_state_match: bool
    unconfirmed_mutations: int
    mismatches: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["mismatches"] = list(self.mismatches)
        return d


@dataclass(slots=True)
class EvalItemResult:
    """Mirrors ``cs.eval_item_results`` columns; ``detail`` holds scorer payloads."""

    hyp_transcript: str | None = None
    wer: float | None = None
    slots_pred: dict[str, Any] = field(default_factory=dict)
    tool_calls_pred: list[dict[str, Any]] = field(default_factory=list)
    latencies_ms: dict[str, float] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    auto_root_cause: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> dict[str, Any]:
        """DB-shaped dict (excludes ``detail``)."""
        return {
            "hyp_transcript": self.hyp_transcript,
            "wer": self.wer,
            "slots_pred": self.slots_pred,
            "tool_calls_pred": self.tool_calls_pred,
            "latencies_ms": self.latencies_ms,
            "flags": list(self.flags),
            "auto_root_cause": self.auto_root_cause,
        }


__all__ = [
    "AsrScore",
    "EntityScore",
    "EvalItemResult",
    "NluScore",
    "TaskScore",
    "ToolCallScore",
]
