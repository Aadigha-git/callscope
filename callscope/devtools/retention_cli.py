"""CLI: ``python -m callscope.devtools.retention_cli purge|delete-call``."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from callscope.retention import (
    DEFAULT_RETENTION_DAYS,
    RetentionCatalog,
    apply_purge,
    delete_call,
)


def _recordings_root() -> Path:
    return Path(os.environ.get("CALLSCOPE_RECORDINGS_DIR", "data/recordings")).expanduser()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CallScope recording retention")
    sub = parser.add_subparsers(dest="cmd", required=True)

    purge_p = sub.add_parser("purge", help="Delete eligible recordings past retention")
    purge_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Report only (default if no --apply)",
    )
    purge_p.add_argument("--apply", action="store_true", help="Actually delete")
    purge_p.add_argument(
        "--days",
        type=int,
        default=DEFAULT_RETENTION_DAYS,
        help=f"Retention days (default {DEFAULT_RETENTION_DAYS})",
    )
    purge_p.add_argument(
        "--audit-log",
        type=Path,
        default=None,
        help="Append JSONL audit lines (default: <recordings>/purge_audit.jsonl)",
    )

    del_p = sub.add_parser("delete-call", help="Delete one call by UUID")
    del_p.add_argument("call_id", type=UUID)
    del_p.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)
    root = _recordings_root()
    catalog = RetentionCatalog(root / "index.jsonl")
    catalog.load()

    if args.cmd == "purge":
        dry_run = not args.apply
        if args.dry_run:
            dry_run = True
        audit = args.audit_log or (root / "purge_audit.jsonl")
        results = apply_purge(
            catalog,
            dry_run=dry_run,
            retention_days=args.days,
            now=datetime.now(UTC),
            audit_log=audit,
        )
        mode = "dry-run" if dry_run else "apply"
        print(f"purge {mode}: {len(results)} eligible")
        for r in results:
            print(r)
        return 0

    if args.cmd == "delete-call":
        result = delete_call(catalog, args.call_id, dry_run=args.dry_run)
        print(result)
        return 0 if result.get("found") or args.dry_run else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
