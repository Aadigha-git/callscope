"""Prompt hash + skill loading for the receptionist skill (T-M2-04)."""

from __future__ import annotations

import hashlib
from importlib import resources
from pathlib import Path

SKILL_NAME = "callscope:receptionist"
SKILL_RESOURCE = "receptionist.md"

# Slim system text assembled with the skill for stack_versions.prompt_hash.
SYSTEM_PREAMBLE = (
    "You are the Lakeside Home Services voice receptionist. "
    "Follow the callscope:receptionist skill. Keep replies short and spoken."
)


def skill_text() -> str:
    """Load the versioned receptionist skill markdown."""
    try:
        ref = resources.files("hermes_callscope").joinpath("skills", SKILL_RESOURCE)
        return ref.read_text(encoding="utf-8")
    except (FileNotFoundError, TypeError, AttributeError):
        path = Path(__file__).resolve().parent / "skills" / SKILL_RESOURCE
        return path.read_text(encoding="utf-8")


def assembled_prompt(*, system_preamble: str = SYSTEM_PREAMBLE) -> str:
    return f"{system_preamble.strip()}\n\n{skill_text().strip()}\n"


def prompt_hash(*, system_preamble: str = SYSTEM_PREAMBLE) -> str:
    """SHA-256 hex of assembled skill + system text (recorded in stack_versions)."""
    payload = assembled_prompt(system_preamble=system_preamble).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
