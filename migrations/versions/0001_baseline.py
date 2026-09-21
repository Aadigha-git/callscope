"""Baseline schema: apply db/schema.sql verbatim.

Revision ID: 0001
Revises:
Create Date: 2026-09-20
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA = _ROOT / "db" / "schema.sql"


def upgrade() -> None:
    sql = _SCHEMA.read_text(encoding="utf-8")
    # schema.sql is multi-statement; driver executes the full script.
    op.get_bind().exec_driver_sql(sql)


def downgrade() -> None:
    op.get_bind().exec_driver_sql("DROP SCHEMA IF EXISTS cs CASCADE")
    op.get_bind().exec_driver_sql("DROP SCHEMA IF EXISTS biz CASCADE")
