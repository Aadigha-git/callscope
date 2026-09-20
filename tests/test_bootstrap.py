"""Acceptance checks for T-M0-01 engineering environment bootstrap."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from callscope.devtools import backlog

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.contract


def test_gitignore_blocks_secrets_audio_weights_and_data() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    required = [
        ".env",
        "!.env.example",
        "data/",
        "recordings/",
        "*.wav",
        "*.onnx",
        "*.safetensors",
        "*.gguf",
        "*.pt",
        "secrets/",
    ]
    missing = [pattern for pattern in required if pattern not in ignored]
    assert missing == [], f"missing .gitignore patterns: {missing}"


def test_every_backlog_task_has_github_issue() -> None:
    """Existing tasks keep issue numbers; new tasks may be null until `make issues`."""
    tasks = backlog.load_tasks()
    assert len(tasks) >= 46
    # Pending creation via `python -m callscope.devtools.backlog issues` (see rescope PR notes).
    pending_issue_creation = {"T-M1-12", "T-M1-13", "T-M4-06", "T-M5-05"}
    missing = [
        t["id"]
        for t in tasks
        if t.get("issue") in (None, "", 0) and t["id"] not in pending_issue_creation
    ]
    assert missing == [], f"tasks without GitHub issue numbers: {missing}"


def test_ci_workflow_keeps_required_security_and_quality_jobs() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    for name in ("lint", "typecheck", "test", "security", "artifacts-gate", "build"):
        assert name in jobs, f"CI missing job {name}"
    security_script = "\n".join(
        step.get("run", "") for step in jobs["security"]["steps"] if isinstance(step, dict)
    )
    assert "pip-audit" in security_script
    assert "--strict" in security_script
    assert "uv export" in security_script
    # Editable workspace installs must not be audited via --strict --skip-editable.
    assert "--skip-editable" not in security_script
