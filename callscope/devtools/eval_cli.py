"""CLI: ``python -m callscope.devtools.eval_cli run|estimate``."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from callscope.eval.persist import FileEvalStore
from callscope.eval.replay import ReplayMode
from callscope.eval.runner import (
    EvalRunConfig,
    estimate_eval_usd,
    load_golden_items,
    resolve_git_sha,
    run_eval,
)
from callscope.providers.budget import BudgetExceededError, BudgetGuard
from callscope.providers.cassettes import (
    CassetteBrain,
    CassetteLiveForbiddenError,
    CassetteMode,
    CassetteStore,
    resolve_mode,
)
from callscope.providers.mock import MockBrain, MockSTT, MockTTS


def _parse_mode(raw: str) -> ReplayMode:
    key = raw.replace("-", "_")
    if key not in {"stage_replay", "text_replay"}:
        raise argparse.ArgumentTypeError(f"mode must be stage_replay|text_replay, got {raw!r}")
    return key  # type: ignore[return-value]


async def _seed_cassettes(
    store: CassetteStore,
    items: list[Any],
    *,
    model: str,
    budget: BudgetGuard,
) -> None:
    """Record mock replies so CI can replay without network."""
    for item in items:
        reply = f"OK. Regarding: {item.text[:40]}"
        brain = CassetteBrain(
            MockBrain(replies=[reply], sleep=_instant),
            store,
            mode=CassetteMode.RECORD,
            budget=budget,
            model=model,
            projected_usd=0.0,
        )
        from callscope.providers.base import Msg

        msgs = [Msg(role="user", content=item.text)]
        async for _ in brain.stream_reply(msgs, call_id="seed", turn_id=item.item_id):
            pass


async def _instant(_s: float) -> None:
    return None


async def cmd_run(args: argparse.Namespace) -> int:
    items_path = Path(args.dataset) if args.dataset.endswith(".json") else None
    if items_path is None:
        # Treat as name@version label; load golden when name starts with golden
        if str(args.dataset).startswith("golden"):
            items_path = Path("tests/golden/eval_items.json")
        else:
            print(
                "dataset path must be a JSON items file or golden* label for CI",
                file=sys.stderr,
            )
            return 2
    items = load_golden_items(items_path)
    mode = _parse_mode(args.mode)
    git_sha = resolve_git_sha(explicit=args.git_sha)
    store = FileEvalStore(Path(args.out))
    cassette_root = Path(args.cassettes)
    cassette_store = CassetteStore(cassette_root)
    budget = BudgetGuard.from_settings(model=None if args.model == "mock" else args.model)
    estimated = estimate_eval_usd(len(items), model=budget.model)

    try:
        cassette_mode = resolve_mode(live=bool(args.live))
    except CassetteLiveForbiddenError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1

    if args.live:
        try:
            budget.require_live_budget(estimated)
        except BudgetExceededError as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 1

    if cassette_mode is CassetteMode.REPLAY:
        # Seed missing golden cassettes from MockBrain (still offline).
        missing = False
        from callscope.providers.base import Msg
        from callscope.providers.cassettes import request_hash

        for item in items:
            h = request_hash([Msg(role="user", content=item.text)], model=args.model or "mock")
            if not cassette_store.exists(h):
                missing = True
                break
        if missing:
            seed_budget = BudgetGuard(
                budget_usd=budget.budget_usd,
                spend_usd=0.0,
                model=budget.model,
            )
            await _seed_cassettes(
                cassette_store,
                items,
                model=args.model or "mock",
                budget=seed_budget,
            )

    fail_at = 1 if cassette_mode is CassetteMode.REPLAY else None
    inner = MockBrain(replies=["UNUSED"], fail_at_call=fail_at)
    brain: Any
    if cassette_mode is CassetteMode.REPLAY:
        brain = CassetteBrain(
            inner,
            cassette_store,
            mode=CassetteMode.REPLAY,
            model=args.model or "mock",
        )
    else:
        brain = CassetteBrain(
            MockBrain(replies=["Live mock reply."], sleep=_instant),
            cassette_store,
            mode=cassette_mode,
            budget=budget,
            model=args.model or "mock",
            projected_usd=max(estimated / max(len(items), 1), 0.0),
        )

    def stt_factory(item: Any) -> MockSTT:
        return MockSTT(transcripts=[item.text], sleep=_instant)

    tts = MockTTS(sleep=_instant)
    config = EvalRunConfig(
        dataset_id=str(args.dataset),
        stack_version_id=str(args.stack),
        mode=mode,
        git_sha=git_sha,
        live=bool(args.live),
        seed=int(args.seed),
        concurrency=int(args.concurrency),
        thresholds_path=Path(args.thresholds) if args.thresholds else None,
        estimated_usd=estimated if args.live else 0.0,
        config={"dataset_path": str(items_path)},
    )
    result = await run_eval(
        items,
        store=store,
        stt=MockSTT(transcripts=["unused"], sleep=_instant),
        brain=brain,
        tts=tts,
        config=config,
        stt_factory=stt_factory,
        budget=budget,
    )
    print(
        json.dumps(
            {
                "run_id": result.run_id,
                "status": result.status,
                "n_items": result.n_items,
                "n_finished": result.n_finished,
                "git_sha": git_sha,
                "dataset_id": config.dataset_id,
                "stack_version_id": config.stack_version_id,
                "estimated_usd": result.estimated_usd,
                "metrics": result.metrics[:5],
                "path": str(result.store_path),
            },
            indent=2,
        )
    )
    return 0 if result.status == "succeeded" else 1


def cmd_estimate(args: argparse.Namespace) -> int:
    n = int(args.n_items)
    guard = BudgetGuard.from_settings(model=args.model)
    projected = estimate_eval_usd(n, model=guard.model)
    print(
        json.dumps(
            {
                "n_items": n,
                "model": guard.model,
                "estimated_usd": projected,
                "budget_usd": guard.budget_usd,
                "spend_usd": guard.status().spend_usd,
                "remaining_usd": guard.status().remaining_usd,
            },
            indent=2,
        )
    )
    if args.check:
        try:
            guard.require_live_budget(projected)
        except BudgetExceededError as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 1
        print("OK: within budget")
    return 0


def cmd_gate(args: argparse.Namespace) -> int:
    from callscope.eval.gate import gate_run, gate_vs_baseline, load_thresholds
    from callscope.eval.persist import FileEvalStore

    store = FileEvalStore(Path(args.out))
    thr = load_thresholds(Path(args.thresholds) if args.thresholds else None)
    run = store.load(args.run)
    if args.baseline:
        baseline = store.load(args.baseline)
        report = gate_vs_baseline(baseline, run, thr)
    else:
        report = gate_run(run, thr, require_metric=bool(args.require_metric))
    print(report.to_table())
    return 0 if report.passed else 1


def cmd_compare(args: argparse.Namespace) -> int:
    from callscope.eval.compare import paired_bootstrap
    from callscope.eval.persist import FileEvalStore

    store = FileEvalStore(Path(args.out))
    a = store.load(args.baseline)
    b = store.load(args.candidate)

    # Compare mean WER from item_results when present
    def _wers(run: Any) -> list[float]:
        out: list[float] = []
        for row in run.item_results.values():
            if row.get("wer") is not None:
                out.append(float(row["wer"]))
        return out

    wa, wb = _wers(a), _wers(b)
    if len(wa) != len(wb) or not wa:
        # Fall back to aggregate metric delta
        from callscope.eval.gate import metric_lookup

        va = metric_lookup(a, args.metric, "all")
        vb = metric_lookup(b, args.metric, "all")
        payload = {
            "metric": args.metric,
            "baseline": va,
            "candidate": vb,
            "delta": None if va is None or vb is None else vb - va,
            "note": "unpaired aggregate (item counts differ or empty)",
        }
        print(json.dumps(payload, indent=2))
        return 0
    cmp = paired_bootstrap(
        wa,
        wb,
        margin=float(args.margin),
        direction=args.direction,
    )
    print(json.dumps(cmp.to_dict(), indent=2))
    return 0 if cmp.non_inferior else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="callscope-eval")
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Run stage_replay or text_replay eval")
    run.add_argument("--stack", required=True, help="Stack version label/id")
    run.add_argument(
        "--dataset",
        required=True,
        help="JSON items path or golden* label",
    )
    run.add_argument(
        "--mode",
        default="stage_replay",
        type=_parse_mode,
        help="stage_replay | text_replay",
    )
    run.add_argument("--out", default="artifacts/eval_runs", help="Eval run store root")
    run.add_argument("--cassettes", default="eval/cassettes", help="Cassette directory")
    run.add_argument("--live", action="store_true", help="Allow live LLM (budgeted)")
    run.add_argument("--seed", type=int, default=42)
    run.add_argument("--concurrency", type=int, default=1)
    run.add_argument("--git-sha", default=None)
    run.add_argument("--model", default="mock")
    run.add_argument("--thresholds", default=None)
    run.set_defaults(func=lambda a: asyncio.run(cmd_run(a)))

    est = sub.add_parser("estimate", help="Estimate Token Factory USD for N items")
    est.add_argument("--n-items", type=int, required=True)
    est.add_argument("--model", default=None)
    est.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if spend + estimate would exceed budget",
    )
    est.set_defaults(func=cmd_estimate)

    gate = sub.add_parser("gate", help="Gate a run against eval/thresholds.yaml")
    gate.add_argument("--run", required=True, help="Eval run id")
    gate.add_argument("--baseline", default=None, help="Baseline run id for NI margins")
    gate.add_argument("--out", default="artifacts/eval_runs")
    gate.add_argument("--thresholds", default=None)
    gate.add_argument(
        "--require-metric",
        action="store_true",
        help="Fail when a gated metric is missing",
    )
    gate.set_defaults(func=cmd_gate)

    cmp = sub.add_parser("compare", help="Paired bootstrap compare two runs")
    cmp.add_argument("--baseline", required=True)
    cmp.add_argument("--candidate", required=True)
    cmp.add_argument("--out", default="artifacts/eval_runs")
    cmp.add_argument("--metric", default="wer")
    cmp.add_argument("--margin", type=float, default=0.01)
    cmp.add_argument(
        "--direction",
        default="lower_better",
        choices=["lower_better", "higher_better"],
    )
    cmp.set_defaults(func=cmd_compare)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
