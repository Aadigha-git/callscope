"""PR artifact gate: code changes must ship with the matching project artifacts."""

from __future__ import annotations

import os
import subprocess
import sys

CODE_PREFIXES = ("callscope/", "apps/", "servers/", "plugins/")
SKIP_TOKEN = "[skip-artifacts]"  # noqa: S105 - not a secret


def evaluate(changed: list[str], title: str = "") -> list[str]:
    """Return human-readable violations (empty list means the gate passes)."""
    if SKIP_TOKEN in title:
        return []
    problems: list[str] = []
    touched = set(changed)
    if any(f.startswith(CODE_PREFIXES) for f in changed):
        for needed in ("docs/CHANGELOG.md", "backlog/tasks.yaml"):
            if needed not in touched:
                problems.append(f"code changed but {needed} was not updated")
    if any(f.startswith("apps/api/") for f in changed) and "docs/api/openapi.yaml" not in touched:
        problems.append("API code changed but docs/api/openapi.yaml was not updated")
    if any(f.startswith("migrations/") for f in changed) and "db/schema.sql" not in touched:
        problems.append("migrations changed but db/schema.sql was not updated")
    return problems


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - needs a git checkout
    base = (argv or sys.argv[1:] or ["origin/main"])[0]
    res = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    problems = evaluate(res.stdout.split(), os.environ.get("PR_TITLE", ""))
    for prob in problems:
        print("ARTIFACT GATE:", prob)
    if problems:
        print(f"Fix the above, or add {SKIP_TOKEN} to the PR title for chores/docs-only work.")
    return 1 if problems else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
