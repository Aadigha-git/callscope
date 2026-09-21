"""CLI for `make budget` — spend vs CALLSCOPE_LLM_BUDGET_USD."""

from __future__ import annotations

import argparse
import sys

from callscope.providers.budget import (
    DEFAULT_MODEL,
    BudgetExceededError,
    BudgetGuard,
    format_status,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="callscope-budget",
        description="Show Token Factory LLM spend vs CALLSCOPE_LLM_BUDGET_USD (NFR-11).",
    )
    parser.add_argument(
        "--estimate",
        action="store_true",
        help="Print projected cost for token counts (no network).",
    )
    parser.add_argument("--prompt-tokens", type=int, default=0)
    parser.add_argument("--completion-tokens", type=int, default=0)
    parser.add_argument(
        "--model",
        default=None,
        help=f"Token Factory model id (default: TOKEN_FACTORY_MODEL or {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if spend + estimate would exceed the budget (live refusal).",
    )
    parser.add_argument(
        "--turns",
        type=int,
        default=1,
        help="Multiply estimate by N turns (for eval dry-runs).",
    )
    args = parser.parse_args(argv)

    guard = BudgetGuard.from_settings(model=args.model)
    st = guard.status()
    print(format_status(st))

    if args.estimate or args.check:
        per = guard.estimate(args.prompt_tokens, args.completion_tokens)
        projected = per * max(args.turns, 1)
        print(
            f"Estimate: {args.prompt_tokens} in + {args.completion_tokens} out "
            f"x {args.turns} turn(s) @ {guard.model} -> ${projected:.8f}"
        )
        print(f"After run (projected): ${st.spend_usd + projected:.6f} / ${st.budget_usd:.2f}")
        if args.check:
            try:
                guard.require_live_budget(projected)
            except BudgetExceededError as exc:
                print(f"REFUSED: {exc}", file=sys.stderr)
                return 1
            print("OK: within budget")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
