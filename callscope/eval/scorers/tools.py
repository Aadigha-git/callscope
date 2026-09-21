"""Tool-call exact-match and argument accuracy vs scenario expected."""

from __future__ import annotations

from typing import Any

from callscope.eval.normalize import normalize
from callscope.eval.types import ToolCallScore


def _norm_args(args: dict[str, Any]) -> dict[str, str]:
    return {str(k): normalize(str(v)) if v is not None else "" for k, v in args.items()}


def score_tools(
    expected: list[dict[str, Any]],
    predicted: list[dict[str, Any]],
) -> ToolCallScore:
    """``expected``/``predicted`` items: ``{name, args?}``."""
    exp_names = tuple(str(e.get("name", "")) for e in expected)
    pred_names = tuple(str(p.get("name", "")) for p in predicted)
    if not exp_names and not pred_names:
        return ToolCallScore(
            exact_match=True,
            name_accuracy=1.0,
            arg_accuracy=1.0,
            ordered_names_ref=exp_names,
            ordered_names_hyp=pred_names,
        )
    name_hits = sum(1 for a, b in zip(exp_names, pred_names, strict=False) if a == b)
    name_den = max(len(exp_names), len(pred_names), 1)
    name_acc = name_hits / name_den

    arg_hits = 0
    arg_total = 0
    for e, p in zip(expected, predicted, strict=False):
        if str(e.get("name", "")) != str(p.get("name", "")):
            eargs = _norm_args(dict(e.get("args") or {}))
            arg_total += max(len(eargs), 1)
            continue
        eargs = _norm_args(dict(e.get("args") or {}))
        pargs = _norm_args(dict(p.get("args") or {}))
        keys = set(eargs) | set(pargs)
        if not keys:
            arg_hits += 1
            arg_total += 1
            continue
        for k in keys:
            arg_total += 1
            if eargs.get(k) == pargs.get(k):
                arg_hits += 1
    arg_acc = arg_hits / arg_total if arg_total else 1.0

    exact = exp_names == pred_names and arg_acc == 1.0 and len(expected) == len(predicted)
    if exact:
        for e, p in zip(expected, predicted, strict=True):
            if _norm_args(dict(e.get("args") or {})) != _norm_args(dict(p.get("args") or {})):
                exact = False
                break

    return ToolCallScore(
        exact_match=exact,
        name_accuracy=name_acc,
        arg_accuracy=arg_acc,
        ordered_names_ref=exp_names,
        ordered_names_hyp=pred_names,
    )


__all__ = ["score_tools"]
