#!/usr/bin/env python3
"""Thin wrapper: ``python scripts/purge.py --dry-run|--apply``."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from callscope.devtools.retention_cli import main

if __name__ == "__main__":
    # Map legacy flags onto the subcommand form.
    argv = list(sys.argv[1:])
    if argv and argv[0] not in {"purge", "delete-call"}:
        argv = ["purge", *argv]
    raise SystemExit(main(argv))
