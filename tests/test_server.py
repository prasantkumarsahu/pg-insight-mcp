import os

import psycopg
import pytest
from mcp import Client

from pg_insight.config import Settings
from pg_insight.database import Database
from pg_insight.server import build_server

DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://shop:shop@localhost:5434/shop")


def _database_available() -> bool:
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2):
            return True
    except psycopg.OperationalError:
        return False


pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(not _database_available(), reason="sample database is not running"),
]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def server():
    return build_server(Database(Settings(database_url=DATABASE_URL, max_rows=50, statement_timeout_ms=2000)))


async def call(server, tool, **arguments):
    async with Client(server) as client:
        return await client.call_tool(tool, arguments)


async def test_lists_read_only_tools(server):
    async with Client(server) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    assert set(tools) == {"list_schemas", "list_tables", "describe_table", "sample_rows", "run_query", "explain_query"}
    assert all(tool.annotations.read_only_hint for tool in tools.values())


async def test_lists_tables(server):
    result = await call(server, "list_tables", schema="public")
    names = {table["name"] for table in result.structured_content["tables"]}
    assert {"customers", "products", "orders", "order_items"} <= names


async def test_describes_table_with_foreign_keys(server):
    result = await call(server, "describe_table", table="orders")
    detail = result.structured_content
    assert "customer_id" in {column["name"] for column in detail["columns"]}
    assert any(c["type"] == "foreign key" for c in detail["constraints"])
    assert any(ref["from_table"] == "order_items" for ref in detail["referenced_by"])


async def test_runs_query_and_truncates(server):
    result = await call(server, "run_query", sql="SELECT id, status FROM orders ORDER BY id")
    data = result.structured_content
    assert data["row_count"] == 50
    assert data["truncated"] is True
    assert data["columns"] == ["id", "status"]


async def test_aggregates_revenue(server):
    result = await call(
        server,
        "run_query",
        sql="""
            SELECT p.category, round(sum(oi.quantity * oi.unit_price), 2) AS revenue
            FROM order_items oi JOIN products p ON p.id = oi.product_id
            GROUP BY p.category ORDER BY revenue DESC
        """,
    )
    rows = result.structured_content["rows"]
    assert rows
    assert isinstance(rows[0]["revenue"], int | float)


async def test_rejects_write_query(server):
    result = await call(server, "run_query", sql="DELETE FROM orders")
    assert result.is_error
    assert "read-only" in result.content[0].text


async def test_rejects_system_schema(server):
    result = await call(server, "list_tables", schema="pg_catalog")
    assert result.is_error


async def test_explains_without_running(server):
    result = await call(server, "explain_query", sql="SELECT * FROM orders WHERE customer_id = 7")
    summary = result.structured_content["summary"]
    assert any("orders" in line for line in summary)


async def test_statement_timeout(server):
    result = await call(server, "run_query", sql="SELECT count(*) FROM generate_series(1, 1000000000)")
    assert result.is_error
    assert "timeout" in result.content[0].text.lower()


async def test_schema_overview_resource(server):
    async with Client(server) as client:
        resource = await client.read_resource("schema://overview")
    text = resource.contents[0].text
    assert "public.orders" in text


async def test_allowed_schemas_filter():
    restricted = Database(Settings(database_url=DATABASE_URL, allowed_schemas=("analytics",)))
    assert restricted.list_schemas() == []
