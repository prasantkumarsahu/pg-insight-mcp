import datetime as dt
import decimal
import time
import uuid
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from .config import Settings
from .guard import validate_read_only

SYSTEM_SCHEMAS = ("pg_catalog", "information_schema", "pg_toast")


class AccessDenied(PermissionError):
    pass


def to_json_value(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, decimal.Decimal):
        return float(value) if value % 1 else int(value)
    if isinstance(value, dt.datetime | dt.date | dt.time):
        return value.isoformat()
    if isinstance(value, dt.timedelta):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bytes | bytearray | memoryview):
        return f"<{len(bytes(value))} bytes>"
    if isinstance(value, list | tuple):
        return [to_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: to_json_value(item) for key, item in value.items()}
    return str(value)


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings

    @contextmanager
    def _read_only(self):
        with psycopg.connect(self.settings.database_url, autocommit=False, row_factory=dict_row) as conn:
            conn.read_only = True
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SET LOCAL statement_timeout = {}").format(sql.Literal(self.settings.statement_timeout_ms))
                )
                yield cur
            conn.rollback()

    def _check_schema(self, schema: str) -> None:
        if schema in SYSTEM_SCHEMAS:
            raise AccessDenied(f"Schema '{schema}' is a system schema")
        if self.settings.allowed_schemas and schema not in self.settings.allowed_schemas:
            raise AccessDenied(f"Schema '{schema}' is not in the allowed list: {list(self.settings.allowed_schemas)}")

    def _visible(self, schema: str) -> bool:
        return not self.settings.allowed_schemas or schema in self.settings.allowed_schemas

    def list_schemas(self) -> list[dict]:
        with self._read_only() as cur:
            cur.execute(
                """
                SELECT n.nspname AS schema,
                       count(c.oid) FILTER (WHERE c.relkind IN ('r', 'p')) AS tables,
                       count(c.oid) FILTER (WHERE c.relkind IN ('v', 'm')) AS views
                FROM pg_namespace n
                LEFT JOIN pg_class c ON c.relnamespace = n.oid
                WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
                  AND n.nspname NOT LIKE 'pg_temp_%' AND n.nspname NOT LIKE 'pg_toast_temp_%'
                GROUP BY n.nspname
                ORDER BY n.nspname
                """
            )
            return [row for row in cur.fetchall() if self._visible(row["schema"])]

    def list_tables(self, schema: str) -> list[dict]:
        self._check_schema(schema)
        with self._read_only() as cur:
            cur.execute(
                """
                SELECT c.relname AS name,
                       CASE c.relkind WHEN 'r' THEN 'table' WHEN 'p' THEN 'table'
                                      WHEN 'v' THEN 'view' WHEN 'm' THEN 'materialized view' END AS type,
                       greatest(c.reltuples, 0)::bigint AS estimated_rows,
                       pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
                       obj_description(c.oid, 'pg_class') AS description
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = %s AND c.relkind IN ('r', 'p', 'v', 'm')
                ORDER BY c.relname
                """,
                (schema,),
            )
            return cur.fetchall()

    def describe_table(self, schema: str, table: str) -> dict:
        self._check_schema(schema)
        with self._read_only() as cur:
            cur.execute(
                """
                SELECT c.oid, obj_description(c.oid, 'pg_class') AS description,
                       greatest(c.reltuples, 0)::bigint AS estimated_rows
                FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = %s AND c.relname = %s AND c.relkind IN ('r', 'p', 'v', 'm')
                """,
                (schema, table),
            )
            relation = cur.fetchone()
            if relation is None:
                raise LookupError(f"Table '{schema}.{table}' does not exist")
            oid = relation["oid"]

            cur.execute(
                """
                SELECT a.attname AS name,
                       format_type(a.atttypid, a.atttypmod) AS type,
                       NOT a.attnotnull AS nullable,
                       pg_get_expr(d.adbin, d.adrelid) AS default,
                       col_description(a.attrelid, a.attnum) AS description
                FROM pg_attribute a
                LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
                WHERE a.attrelid = %s AND a.attnum > 0 AND NOT a.attisdropped
                ORDER BY a.attnum
                """,
                (oid,),
            )
            columns = cur.fetchall()

            cur.execute(
                """
                SELECT con.conname AS name,
                       CASE con.contype WHEN 'p' THEN 'primary key' WHEN 'f' THEN 'foreign key'
                                        WHEN 'u' THEN 'unique' WHEN 'c' THEN 'check' END AS type,
                       pg_get_constraintdef(con.oid) AS definition
                FROM pg_constraint con
                WHERE con.conrelid = %s
                ORDER BY con.contype, con.conname
                """,
                (oid,),
            )
            constraints = cur.fetchall()

            cur.execute(
                """
                SELECT i.relname AS name, pg_get_indexdef(i.oid) AS definition
                FROM pg_index x JOIN pg_class i ON i.oid = x.indexrelid
                WHERE x.indrelid = %s
                ORDER BY i.relname
                """,
                (oid,),
            )
            indexes = cur.fetchall()

            cur.execute(
                """
                SELECT conrelid::regclass::text AS from_table, pg_get_constraintdef(oid) AS definition
                FROM pg_constraint
                WHERE confrelid = %s AND contype = 'f'
                """,
                (oid,),
            )
            referenced_by = cur.fetchall()

        return {
            "schema": schema,
            "table": table,
            "description": relation["description"],
            "estimated_rows": relation["estimated_rows"],
            "columns": columns,
            "constraints": constraints,
            "indexes": indexes,
            "referenced_by": referenced_by,
        }

    def sample_rows(self, schema: str, table: str, limit: int) -> dict:
        self._check_schema(schema)
        limit = max(1, min(limit, self.settings.max_rows))
        query = sql.SQL("SELECT * FROM {} LIMIT {}").format(sql.Identifier(schema, table), sql.Literal(limit))
        with self._read_only() as cur:
            try:
                cur.execute(query)
            except psycopg.errors.UndefinedTable as ex:
                raise LookupError(f"Table '{schema}.{table}' does not exist") from ex
            return self._result(cur, limit, 0.0)

    def run_query(self, query: str, max_rows: int | None = None) -> dict:
        statement = validate_read_only(query)
        limit = max(1, min(max_rows or self.settings.max_rows, self.settings.max_rows))
        with self._read_only() as cur:
            started = time.perf_counter()
            cur.execute(statement)
            elapsed = (time.perf_counter() - started) * 1000
            return self._result(cur, limit, elapsed)

    def explain(self, query: str) -> dict:
        statement = validate_read_only(query)
        if statement.lower().startswith("explain"):
            statement = statement[len("explain") :].strip()
        with self._read_only() as cur:
            cur.execute(sql.SQL("EXPLAIN (FORMAT JSON) ") + sql.SQL(statement))
            plan = cur.fetchone()["QUERY PLAN"][0]["Plan"]
        return {"plan": plan, "summary": _summarise_plan(plan)}

    def _result(self, cur: psycopg.Cursor, limit: int, elapsed_ms: float) -> dict:
        if cur.description is None:
            return {"columns": [], "rows": [], "row_count": 0, "truncated": False}
        columns = [column.name for column in cur.description]
        rows = cur.fetchmany(limit + 1)
        truncated = len(rows) > limit
        rows = rows[:limit]
        return {
            "columns": columns,
            "rows": [{key: to_json_value(value) for key, value in row.items()} for row in rows],
            "row_count": len(rows),
            "truncated": truncated,
            "elapsed_ms": round(elapsed_ms, 2),
        }


def _summarise_plan(plan: dict, depth: int = 0) -> list[str]:
    relation = f" on {plan['Relation Name']}" if "Relation Name" in plan else ""
    index = f" using {plan['Index Name']}" if "Index Name" in plan else ""
    line = f"{'  ' * depth}{plan['Node Type']}{relation}{index} (cost={plan['Total Cost']}, rows={plan['Plan Rows']})"
    lines = [line]
    for child in plan.get("Plans", []):
        lines.extend(_summarise_plan(child, depth + 1))
    return lines
