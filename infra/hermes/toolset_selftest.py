#!/usr/bin/env python3
"""Fail closed if Hermes platform_toolsets.api_server is not the CallScope allowlist.

Usage:
  python infra/hermes/toolset_selftest.py --config infra/hermes/config.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
DEFAULT_ALLOWLIST = ROOT / "toolset_allowlist.txt"


def load_allowlist(path: Path) -> frozenset[str]:
    lines = [
        ln.strip()
        for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    return frozenset(lines)


def effective_toolsets(config: dict[str, object]) -> list[str]:
    pt = config.get("platform_toolsets")
    if not isinstance(pt, dict):
        return []
    raw = pt.get("api_server")
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    return [str(raw)]


def check(config_path: Path, allowlist_path: Path) -> list[str]:
    allowed = load_allowlist(allowlist_path)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return ["config is not a mapping"]
    effective = effective_toolsets(data)
    problems: list[str] = []
    if not effective:
        problems.append("platform_toolsets.api_server is empty (would inherit unsafe defaults)")
    for name in effective:
        if name not in allowed:
            problems.append(f"disallowed toolset on api_server: {name!r}")
    for name in allowed:
        if name not in effective:
            problems.append(f"required toolset missing from api_server: {name!r}")
    # Explicit denylist of known-dangerous built-ins seen in spikes.
    denied = {"hermes-api-server", "terminal", "browser", "web", "file"}
    for name in effective:
        if name in denied:
            problems.append(f"explicitly denied toolset: {name!r}")
    return problems


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    p.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    args = p.parse_args(argv)
    problems = check(args.config, args.allowlist)
    if problems:
        for prob in problems:
            print(f"FAIL: {prob}", file=sys.stderr)
        return 1
    print("OK: platform_toolsets.api_server matches CallScope allowlist")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
