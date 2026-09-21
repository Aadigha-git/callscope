"""Intent / slot NLU scorers from tool-call args vs scenario expected."""

from __future__ import annotations

from typing import Any

from callscope.eval.normalize import normalize
from callscope.eval.types import NluScore


def _norm_val(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool | int | float):
        return str(v)
    return normalize(str(v))


def slot_prf(
    ref_slots: dict[str, Any],
    hyp_slots: dict[str, Any],
) -> tuple[float, float, float]:
    if not ref_slots and not hyp_slots:
        return 1.0, 1.0, 1.0
    keys = set(ref_slots) | set(hyp_slots)
    tp = 0
    for k in keys:
        if k in ref_slots and k in hyp_slots and _norm_val(ref_slots[k]) == _norm_val(hyp_slots[k]):
            tp += 1
    pred = sum(1 for k in hyp_slots if k in keys)
    gold = sum(1 for k in ref_slots if k in keys)
    precision = tp / pred if pred else (1.0 if gold == 0 else 0.0)
    recall = tp / gold if gold else (1.0 if pred == 0 else 0.0)
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return precision, recall, f1


def score_nlu(
    *,
    intent_ref: str,
    intent_hyp: str,
    slots_ref: dict[str, Any],
    slots_hyp: dict[str, Any],
    intent_labels: list[str] | None = None,
) -> NluScore:
    intent_ok = normalize(intent_ref) == normalize(intent_hyp)
    precision, recall, f1 = slot_prf(slots_ref, slots_hyp)
    # Macro-F1 over intents: with a single example, equals intent accuracy as 0/1 F1.
    if intent_labels:
        f1s: list[float] = []
        ref_n = normalize(intent_ref)
        hyp_n = normalize(intent_hyp)
        for label in intent_labels:
            lab = normalize(label)
            tp = int(ref_n == lab and hyp_n == lab)
            fp = int(hyp_n == lab and ref_n != lab)
            fn = int(ref_n == lab and hyp_n != lab)
            p = tp / (tp + fp) if (tp + fp) else 1.0
            r = tp / (tp + fn) if (tp + fn) else 1.0
            f1s.append(0.0 if p + r == 0 else 2 * p * r / (p + r))
        macro = sum(f1s) / len(f1s) if f1s else 0.0
    else:
        macro = 1.0 if intent_ok else 0.0
    return NluScore(
        intent_correct=intent_ok,
        intent_ref=intent_ref,
        intent_hyp=intent_hyp,
        slot_f1=f1,
        slot_precision=precision,
        slot_recall=recall,
        macro_f1=macro,
    )


__all__ = ["score_nlu", "slot_prf"]
