import pytest

from callscope.devtools.check_artifacts import evaluate

pytestmark = pytest.mark.unit


def test_code_without_artifacts_fails() -> None:
    assert len(evaluate(["callscope/x.py"])) == 2


def test_code_with_artifacts_passes() -> None:
    files = ["callscope/x.py", "docs/CHANGELOG.md", "backlog/tasks.yaml"]
    assert evaluate(files) == []


def test_api_change_requires_openapi() -> None:
    files = ["apps/api/main.py", "docs/CHANGELOG.md", "backlog/tasks.yaml"]
    assert evaluate(files) == ["API code changed but docs/api/openapi.yaml was not updated"]


def test_migration_requires_schema() -> None:
    assert any("schema.sql" in p for p in evaluate(["migrations/001.py"]))


def test_skip_token_and_docs_only() -> None:
    assert evaluate(["callscope/x.py"], "chore: tidy [skip-artifacts]") == []
    assert evaluate(["README.md"]) == []
