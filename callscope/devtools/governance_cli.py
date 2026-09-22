"""CLI: ``python -m callscope.devtools.governance_cli backfill|list-models|list-stacks``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from callscope.eval.runner import resolve_git_sha
from callscope.governance.registry import ModelStackRegistry, backfill_m0_inventory


def _registry(root: str) -> ModelStackRegistry:
    return ModelStackRegistry(root=Path(root))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="callscope-governance")
    p.add_argument(
        "--registry",
        default="artifacts/registry",
        help="File-backed registry root",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    bf = sub.add_parser("backfill", help="Register M0 models + local-mac-dev stack")
    bf.add_argument("--git-sha", default=None)
    sub.add_parser("list-models", help="Print registered models as JSON")
    sub.add_parser("list-stacks", help="Print registered stacks as JSON")

    args = p.parse_args(argv)
    reg = _registry(args.registry)
    if args.cmd == "backfill":
        stack = backfill_m0_inventory(reg, git_sha=resolve_git_sha(explicit=args.git_sha))
        print(json.dumps({"stack_version_id": str(stack.stack_version_id), "label": stack.label}))
        return 0
    if args.cmd == "list-models":
        print(json.dumps([m.to_dict() for m in reg.list_models()], indent=2))
        return 0
    if args.cmd == "list-stacks":
        print(json.dumps([s.to_dict() for s in reg.list_stacks()], indent=2))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
