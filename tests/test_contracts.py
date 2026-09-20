"""Contract tests: the API spec and DB DDL must always be valid."""

import os
from pathlib import Path

import pglast
import pytest
import yaml
from openapi_spec_validator import validate

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.contract


def test_openapi_is_valid() -> None:
    spec = yaml.safe_load((ROOT / "docs/api/openapi.yaml").read_text(encoding="utf-8"))
    validate(spec)


def test_schema_sql_parses() -> None:
    assert pglast.parse_sql((ROOT / "db/schema.sql").read_text(encoding="utf-8"))


@pytest.mark.integration
@pytest.mark.skipif(not os.environ.get("CALLSCOPE_TEST_DATABASE_URL"), reason="no test database")
def test_schema_applies_to_real_postgres() -> None:
    import psycopg

    with psycopg.connect(os.environ["CALLSCOPE_TEST_DATABASE_URL"], autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS cs CASCADE; DROP SCHEMA IF EXISTS biz CASCADE;")
        conn.execute((ROOT / "db/schema.sql").read_text(encoding="utf-8"))
        row = conn.execute("SELECT count(*) FROM cs.root_cause_codes").fetchone()
        assert row is not None
        assert row[0] == 21
