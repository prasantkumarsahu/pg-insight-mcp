import argparse
from contextlib import contextmanager
from typing import Any

import psycopg
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import __version__
from .config import Settings
from .database import AccessDenied, Database
from .guard import QueryRejected

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)

INSTRUCTIONS = """
Read-only access to a PostgreSQL database.
Start with list_schemas and list_tables, use describe_table before writing a query,
and prefer explain_query for anything that may scan a large table.
Only SELECT, WITH, EXPLAIN, SHOW, VALUES and TABLE statements are accepted.
""".strip()


@contextmanager
def tool_errors():
    try:
        yield
    except (QueryRejected, AccessDenied, LookupError) as ex:
        raise ToolError(str(ex)) from ex
    except psycopg.errors.QueryCanceled as ex:
        raise ToolError("Query cancelled: statement timeout exceeded") from ex
    except psycopg.Error as ex:
        raise ToolError(f"PostgreSQL error: {ex.diag.message_primary or ex}") from ex


def build_server(db: Database) -> MCPServer:
    server = MCPServer(name="pg-insight", version=__version__, instructions=INSTRUCTIONS)

    @server.tool(
        title="List schemas",
        description="List user schemas with table and view counts.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def list_schemas() -> dict[str, Any]:
        with tool_errors():
            return {"schemas": db.list_schemas()}

    @server.tool(
        title="List tables",
        description="List tables and views in a schema with estimated row counts and sizes.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def list_tables(schema: str = "public") -> dict[str, Any]:
        with tool_errors():
            return {"schema": schema, "tables": db.list_tables(schema)}

    @server.tool(
        title="Describe table",
        description="Columns, constraints, indexes and incoming foreign keys of a table.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def describe_table(table: str, schema: str = "public") -> dict[str, Any]:
        with tool_errors():
            return db.describe_table(schema, table)

    @server.tool(
        title="Sample rows",
        description="Return the first rows of a table to see what the data looks like.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def sample_rows(table: str, schema: str = "public", limit: int = 10) -> dict[str, Any]:
        with tool_errors():
            return db.sample_rows(schema, table, limit)

    @server.tool(
        title="Run query",
        description="Run a single read-only SQL statement inside a read-only transaction. "
        "Results are capped and marked as truncated when more rows exist.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def run_query(sql: str, max_rows: int | None = None) -> dict[str, Any]:
        with tool_errors():
            return db.run_query(sql, max_rows)

    @server.tool(
        title="Explain query",
        description="Show the PostgreSQL execution plan for a read-only query without running it.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def explain_query(sql: str) -> dict[str, Any]:
        with tool_errors():
            return db.explain(sql)

    @server.resource(
        "schema://overview",
        name="schema-overview",
        title="Schema overview",
        description="Every visible table with its columns, as plain text.",
        mime_type="text/plain",
    )
    def schema_overview() -> str:
        lines = []
        for schema in db.list_schemas():
            for table in db.list_tables(schema["schema"]):
                detail = db.describe_table(schema["schema"], table["name"])
                columns = ", ".join(f"{c['name']} {c['type']}" for c in detail["columns"])
                lines.append(f"{schema['schema']}.{table['name']} (~{table['estimated_rows']} rows): {columns}")
        return "\n".join(lines) or "No tables found"

    @server.prompt(title="Analyse data", description="Guide an analysis of a business question against the database.")
    def analyse(question: str) -> str:
        return (
            f"Answer this question using the database: {question}\n\n"
            "1. Read the schema://overview resource or call list_tables to find relevant tables.\n"
            "2. Call describe_table on each table you plan to use and check the join keys.\n"
            "3. Call explain_query on your query if it touches large tables.\n"
            "4. Call run_query and answer with the numbers, showing the final SQL you used."
        )

    return server


def main() -> None:
    parser = argparse.ArgumentParser(prog="pg-insight-mcp")
    parser.add_argument("--transport", choices=["stdio", "sse", "streamable-http"], default="stdio")
    args = parser.parse_args()
    build_server(Database(Settings.from_env())).run(args.transport)


if __name__ == "__main__":
    main()
