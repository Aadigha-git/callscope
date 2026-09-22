"""CLI: ``python -m callscope.devtools.experiment_cli e1|hotwords``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def cmd_hotwords(args: argparse.Namespace) -> int:
    from callscope.experiments.hotwords import build_hotword_list, write_hotwords_file

    words = write_hotwords_file(Path(args.out), max_words=args.max_words)
    print(json.dumps({"n": len(words), "path": args.out, "sample": words[:8]}, indent=2))
    if args.print:
        for w in build_hotword_list(max_words=args.max_words):
            print(w)
    return 0


def cmd_e1(args: argparse.Namespace) -> int:
    from callscope.experiments.e1 import run_e1

    result = run_e1(
        out_dir=Path(args.out),
        seed=int(args.seed),
        max_hotwords=args.max_words,
        log_mlflow=not bool(args.no_mlflow),
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("decision") in {"adopt", "reject"} else 1


def cmd_e3(args: argparse.Namespace) -> int:
    from callscope.experiments.e3 import run_e3

    result = run_e3(out_dir=Path(args.out), log_mlflow=not bool(args.no_mlflow))
    print(json.dumps(result, indent=2))
    return 0 if result.get("decision") in {"adopt", "reject"} else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="callscope-experiment")
    sub = p.add_subparsers(dest="cmd", required=True)

    hw = sub.add_parser("hotwords", help="Write domain hotword list (no test leakage)")
    hw.add_argument("--out", default="eval/hotwords.txt")
    hw.add_argument("--max-words", type=int, default=None)
    hw.add_argument("--print", action="store_true")
    hw.set_defaults(func=cmd_hotwords)

    e1 = sub.add_parser("e1", help="Run E1 hotword entity experiment")
    e1.add_argument("--out", default="artifacts/experiments/e1")
    e1.add_argument("--seed", type=int, default=42)
    e1.add_argument("--max-words", type=int, default=64)
    e1.add_argument("--no-mlflow", action="store_true")
    e1.set_defaults(func=cmd_e1)

    e3 = sub.add_parser("e3", help="Run E3 endpointing/VAD grid experiment")
    e3.add_argument("--out", default="artifacts/experiments/e3")
    e3.add_argument("--no-mlflow", action="store_true")
    e3.set_defaults(func=cmd_e3)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
