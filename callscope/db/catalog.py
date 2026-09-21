"""Canonical Postgres catalog fingerprint for schema drift checks."""

from __future__ import annotations

import json
from typing import Any

import psycopg


def catalog_fingerprint(conn: psycopg.Connection[Any]) -> str:
    """Return a stable JSON snapshot of cs/biz enums, tables, columns, and indexes."""
    enums = conn.execute(
        """
        SELECT n.nspname AS schema, t.typname AS enum_name,
               array_agg(e.enumlabel ORDER BY e.enumsortorder) AS labels
        FROM pg_type t
        JOIN pg_enum e ON t.oid = e.enumtypid
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname IN ('cs', 'biz')
        GROUP BY n.nspname, t.typname
        ORDER BY 1, 2
        """
    ).fetchall()

    columns = conn.execute(
        """
        SELECT table_schema, table_name, column_name, data_type, udt_name,
               is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema IN ('cs', 'biz')
        ORDER BY 1, 2, ordinal_position
        """
    ).fetchall()

    indexes = conn.execute(
        """
        SELECT schemaname, tablename, indexname, indexdef
        FROM pg_indexes
        WHERE schemaname IN ('cs', 'biz')
        ORDER BY 1, 2, 3
        """
    ).fetchall()

    constraints = conn.execute(
        """
        SELECT n.nspname, c.relname, con.conname, con.contype, pg_get_constraintdef(con.oid)
        FROM pg_constraint con
        JOIN pg_class c ON c.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname IN ('cs', 'biz')
        ORDER BY 1, 2, 3
        """
    ).fetchall()

    payload = {
        "enums": [list(r) for r in enums],
        "columns": [list(r) for r in columns],
        "indexes": [list(r) for r in indexes],
        "constraints": [list(r) for r in constraints],
    }
    return json.dumps(payload, default=str, sort_keys=True)
