"""CLI: ``python -m callscope.devtools.dataset_cli build|validate|publish|freeze``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

import yaml

from callscope.datasets.conditions import ALL_CONDITIONS, ConditionCode
from callscope.datasets.dq import run_dq
from callscope.datasets.manifest import (
    attach_splits_and_dq,
    load_manifest,
    write_manifest,
)
from callscope.datasets.registry import FileRegistry, RegistryError
from callscope.datasets.splits import assign_splits
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


def cmd_validate(args: argparse.Namespace) -> int:
    root = Path(args.dataset)
    man_path = root / "manifest.json"
    manifest = load_manifest(man_path)
    items = list(manifest.get("items") or [])
    plan = assign_splits(items, seed=int(args.seed), frozen_test=bool(args.freeze_test))
    dq = run_dq(plan.all_items(), audio_root=root)
    enriched = attach_splits_and_dq(
        manifest,
        items=plan.all_items(),
        dq_report=dq.to_dict(),
        held_voices=plan.held_voices,
        held_variants=plan.held_variants,
        frozen_test=plan.frozen_test,
    )
    write_manifest(man_path, enriched)
    print(
        json.dumps(
            {
                "dq_passed": enriched["dq_passed"],
                "manifest_sha256": enriched["manifest_sha256"],
                "splits": enriched["splits"],
                "n_findings": len(dq.findings),
            }
        )
    )
    return 0 if enriched["dq_passed"] else 1


def cmd_publish(args: argparse.Namespace) -> int:
    root = Path(args.dataset)
    man_path = root / "manifest.json"
    manifest = load_manifest(man_path)
    registry = FileRegistry(Path(args.registry) if args.registry else root.parent)
    try:
        entry = registry.publish(
            name=args.name,
            version=args.version,
            manifest_uri=str(man_path.resolve()),
            manifest=manifest,
            kind=args.kind,
        )
    except RegistryError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps({"ok": True, "entry": entry.to_dict()}))
    return 0


def cmd_freeze(args: argparse.Namespace) -> int:
    registry = FileRegistry(Path(args.registry))
    try:
        entry = registry.freeze(args.name, args.version)
    except RegistryError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps({"ok": True, "entry": entry.to_dict()}))
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

    v = sub.add_parser("validate", help="DQ checks + splits; write enriched manifest")
    v.add_argument("--dataset", required=True, help="Dataset directory with manifest.json")
    v.add_argument("--seed", type=int, default=42)
    v.add_argument("--freeze-test", action="store_true")
    v.set_defaults(func=cmd_validate)

    pub = sub.add_parser("publish", help="Register dataset if dq_passed")
    pub.add_argument("--dataset", required=True)
    pub.add_argument("--name", required=True)
    pub.add_argument("--version", required=True)
    pub.add_argument("--registry", default="artifacts/datasets")
    pub.add_argument("--kind", default="synthetic")
    pub.set_defaults(func=cmd_publish)

    fr = sub.add_parser("freeze", help="Freeze a published dataset version")
    fr.add_argument("--name", required=True)
    fr.add_argument("--version", required=True)
    fr.add_argument("--registry", default="artifacts/datasets")
    fr.set_defaults(func=cmd_freeze)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
