from pathlib import Path

import pytest

from callscope.devtools import backlog

pytestmark = pytest.mark.unit


def test_real_backlog_is_valid() -> None:
    assert backlog.validate(backlog.load_tasks()) == []


def test_every_design_milestone_has_tasks() -> None:
    ms = {t["milestone"] for t in backlog.load_tasks()}
    assert ms == set(backlog.MILESTONES)


def test_render_contains_tasks_and_progress() -> None:
    md = backlog.render_markdown(backlog.load_tasks())
    assert "## Progress" in md
    assert "T-M0-01" in md


def test_validate_catches_problems() -> None:
    bad = [{"id": "X", "status": "nope", "milestone": "M9", "dependencies": ["T-M0-99"]}]
    errs = backlog.validate(bad)
    assert any("invalid status" in e for e in errs)
    assert any("unknown milestone" in e for e in errs)
    assert any("unknown dependency" in e for e in errs)


def test_set_field_rewrites_only_target_block() -> None:
    text = (
        "tasks:\n- id: T-M0-01\n  status: ready\n  issue: null\n"
        "- id: T-M0-02\n  status: ready\n  issue: null\n"
    )
    out = backlog.set_field(text, "T-M0-02", "status", "done")
    assert out.count("status: done") == 1
    assert "- id: T-M0-01\n  status: ready" in out
    out = backlog.set_field(out, "T-M0-01", "issue", 12)
    assert "issue: 12" in out
    with pytest.raises(KeyError):
        backlog.set_field(out, "T-M9-99", "status", "done")
    with pytest.raises(KeyError):
        backlog.set_field(out, "T-M0-01", "nonexistent", "x")


def test_rewrite_roundtrip(tmp_path: Path) -> None:
    f = tmp_path / "tasks.yaml"
    f.write_text("tasks:\n- id: T-M0-01\n  status: ready\n", encoding="utf-8")
    backlog._rewrite("T-M0-01", "status", "in_progress", path=f)
    assert "in_progress" in f.read_text(encoding="utf-8")


def test_report_and_issue_body() -> None:
    tasks = backlog.load_tasks()
    tasks[0]["status"] = "done"
    rep = backlog.report_markdown(tasks[:2], "Report: test", {tasks[0]["id"]: "abc123"})
    assert "abc123" in rep and "Not delivered" in rep
    body = backlog.issue_body(tasks[1])
    assert "Acceptance criteria" in body and "- [ ]" in body


def test_dropped_excluded_from_progress_and_hours() -> None:
    tasks = backlog.load_tasks()
    md = backlog.render_markdown(tasks)
    assert "dropped" in md.lower() or "T-M6-04" in md
    assert backlog.validate(tasks) == []
    extra = {
        "id": "T-M6-99",
        "title": "x",
        "milestone": "M6",
        "type": "feature",
        "requirements": ["FR-01"],
        "description": "x",
        "technical_approach": "x",
        "dependencies": ["T-M6-04"],
        "acceptance_criteria": ["x"],
        "owner": "BAG",
        "estimate_h": 1,
        "priority": "P0",
        "status": "backlog",
    }
    errs = backlog.validate([*tasks, extra])
    assert any("dropped task T-M6-04" in e for e in errs)


def test_report_excludes_dropped_from_active_count() -> None:
    tasks = backlog.load_tasks()
    rep = backlog.report_markdown(tasks, "Report: test")
    assert "dropped" in rep.lower()
    assert "T-M6-04" in rep


def test_cli_validate_and_render(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backlog, "BACKLOG_MD", tmp_path / "BACKLOG.md")
    assert backlog.main(["validate"]) == 0
    assert backlog.main(["render"]) == 0
    assert (tmp_path / "BACKLOG.md").exists()
