"""CLI: ``python -m callscope.devtools.load_cli`` (T-M6-01)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="callscope-load")
    p.add_argument(
        "--out",
        default="docs/reports/load",
        help="Directory for raw JSON + README chart",
    )
    p.add_argument("--reps", type=int, default=3)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--levels",
        default="1,2",
        help="Comma-separated concurrency levels (local-Mac: 1 required, 2 stretch)",
    )
    p.add_argument("--session-cap", type=int, default=2)
    p.add_argument(
        "--wall-clock",
        action="store_true",
        help="Sleep on scenario schedule (slower; optional local pressure check)",
    )
    return p


async def _async_main(args: argparse.Namespace) -> int:
    from callscope.eval.load_test import run_load, write_report

    levels = tuple(int(x.strip()) for x in str(args.levels).split(",") if x.strip())
    report = await run_load(
        levels=levels,
        reps=int(args.reps),
        seed=int(args.seed),
        wall_clock=bool(args.wall_clock),
        session_cap=int(args.session_cap),
    )
    paths = write_report(report, Path(args.out))
    payload = {
        "run_id": report.run_id,
        "public_concurrency_cap": report.public_concurrency_cap,
        "knee_concurrency": report.knee_concurrency,
        "paths": {k: str(v) for k, v in paths.items()},
        "levels": [
            {
                "concurrency": lv.concurrency,
                "p50_ms": lv.p50_ms,
                "p95_ms": lv.p95_ms,
                "meets_nfr01_mock": lv.meets_nfr01_mock,
                "meets_nfr01_projected": lv.meets_nfr01_projected,
                "projected_p50_ms": lv.projected_p50_ms,
            }
            for lv in report.levels
        ],
        "cap_probe": {
            "third_blocked": report.cap_probe.third_blocked,
            "max_concurrent": report.cap_probe.max_concurrent,
        },
    }
    print(json.dumps(payload, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(asyncio.run(_async_main(args)))


if __name__ == "__main__":
    sys.exit(main())
