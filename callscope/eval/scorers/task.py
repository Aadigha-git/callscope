"""Task success + policy compliance scorers."""

from __future__ import annotations

from typing import Any

from callscope.eval.types import TaskScore

_MUTATING = frozenset(
    {
        "book_appointment",
        "reschedule_appointment",
        "cancel_appointment",
        "request_callback",
    }
)


def count_unconfirmed_mutations(tool_calls: list[dict[str, Any]]) -> int:
    n = 0
    for call in tool_calls:
        name = str(call.get("name", ""))
        if name not in _MUTATING:
            continue
        args = dict(call.get("args") or {})
        if args.get("confirmed") is not True:
            n += 1
    return n


def score_task(
    *,
    expected_final_state: dict[str, Any],
    actual_final_state: dict[str, Any],
    tool_calls_pred: list[dict[str, Any]],
    must_confirm_before_mutation: bool = True,
) -> TaskScore:
    mismatches: list[str] = []
    for key, exp in expected_final_state.items():
        act = actual_final_state.get(key)
        if act != exp:
            mismatches.append(f"{key}: expected {exp!r} got {act!r}")
    state_ok = not mismatches
    unconfirmed = count_unconfirmed_mutations(tool_calls_pred)
    policy_ok = (unconfirmed == 0) if must_confirm_before_mutation else True
    return TaskScore(
        task_success=state_ok and policy_ok,
        policy_ok=policy_ok,
        final_state_match=state_ok,
        unconfirmed_mutations=unconfirmed,
        mismatches=tuple(mismatches),
    )


__all__ = ["count_unconfirmed_mutations", "score_task"]
