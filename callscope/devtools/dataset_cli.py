"""CLI: ``python -m callscope.devtools.dataset_cli build``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

import yaml

from callscope.datasets.conditions import ALL_CONDITIONS, ConditionCode
from callscope.datasets.synth import DEFAULT_N_CALLS, DEFAULT_VOICES, build_dataset


def _load_spec(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"spec must be a mapping: {path}")
    return cast(dict[str, Any], data)


def cmd_build(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec)
    out = Path(args.out)
    spec = _load_spec(spec_path) if spec_path.exists() else {}
    n_raw = args.n if args.n is not None else spec.get("n_calls", DEFAULT_N_CALLS)
    seed_raw = args.seed if args.seed is not None else spec.get("seed", 42)
    n_calls = int(n_raw)
    seed = int(seed_raw)
    voices_raw = spec.get("voices", list(DEFAULT_VOICES))
    if not isinstance(voices_raw, list):
        raise SystemExit("voices must be a list")
    voices = tuple(str(v) for v in voices_raw)
    conds_raw = spec.get("conditions", list(ALL_CONDITIONS))
    if not isinstance(conds_raw, list):
        raise SystemExit("conditions must be a list")
    conditions = tuple(str(c) for c in conds_raw)
    for c in conditions:
        if c not in ALL_CONDITIONS:
            raise SystemExit(f"unknown condition {c}")
    manifest = build_dataset(
        out_dir=out,
        n_calls=n_calls,
        seed=seed,
        voices=voices,
        conditions=cast(tuple[ConditionCode, ...], conditions),
    )
    payload = {
        "n": manifest["n_calls"],
        "out": str(out),
        "note": manifest["ci_width_note"],
    }
    print(json.dumps(payload))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="callscope-dataset")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="Build synthetic dataset from scenarios")
    b.add_argument("--spec", default="eval/dataset_specs/v1.yaml")
    b.add_argument("--out", default="artifacts/datasets/v1")
    b.add_argument("--n", type=int, default=None)
    b.add_argument("--seed", type=int, default=None)
    b.set_defaults(func=cmd_build)
    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
