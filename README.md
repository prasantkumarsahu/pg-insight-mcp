# pg-insight-mcp

A read-only PostgreSQL server for the [Model Context Protocol](https://modelcontextprotocol.io).
It lets any MCP client (Claude Desktop, VS Code, Cursor, custom agents) explore a database schema, run
analytical queries and inspect execution plans, without any chance of changing data.

## Features

- **Schema discovery**: schemas, tables, views, columns, constraints, indexes and incoming foreign keys
- **Safe querying**: every statement runs inside a `READ ONLY` transaction with a statement timeout
- **Query guard**: SQL is checked before it reaches the database. Only one statement is allowed, writes and DDL are
  rejected, `EXPLAIN ANALYZE` and dangerous functions such as `pg_sleep`, `pg_read_file`, `dblink` and
  `set_config` are blocked, and `SELECT ... INTO` is refused
- **Row caps**: results are limited to a configurable row count and flagged as `truncated` when more rows exist
- **Plans without execution**: `explain_query` returns the JSON plan plus a readable summary tree
- **Schema allow-list**: restrict the server to selected schemas; system schemas are never exposed
- Structured tool output, an MCP resource with the full schema overview, and a prompt for guided analysis

## Tools

| Tool | Description |
|---|---|
| `list_schemas` | User schemas with table and view counts |
| `list_tables` | Tables and views in a schema with estimated rows and size |
| `describe_table` | Columns, types, defaults, constraints, indexes, referencing tables |
| `sample_rows` | First N rows of a table |
| `run_query` | Run a read-only SQL statement |
| `explain_query` | Execution plan without running the query |

Resource: `schema://overview`. Prompt: `analyse(question)`.

## Quick start

Requires Python 3.11+ and Docker (for the sample database).

```bash
docker compose up -d
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

On Windows the virtual environment's tools are in `.venv\Scripts\` instead of `.venv/bin/`.

The sample `shop` database (200 customers, 12 products, 1,500 orders) is created and seeded automatically on
port `5434`.

Run the server over stdio:

```bash
DATABASE_URL=postgresql://shop:shop@localhost:5434/shop pg-insight-mcp
```

PowerShell:

```powershell
$env:DATABASE_URL = "postgresql://shop:shop@localhost:5434/shop"
.venv\Scripts\pg-insight-mcp
```

Or over HTTP:

```bash
pg-insight-mcp --transport streamable-http
```

Try it interactively with the MCP Inspector:

```bash
DATABASE_URL=postgresql://shop:shop@localhost:5434/shop npx @modelcontextprotocol/inspector .venv/bin/pg-insight-mcp
```

Click **Connect**, open the **Tools** tab and try:

| Tool | Input | Expected |
|---|---|---|
| `list_tables` | `schema: public` | customers, products, orders, order_items |
| `describe_table` | `table: orders` | columns, primary and foreign keys, indexes |
| `run_query` | `SELECT status, count(*) FROM orders GROUP BY status` | order counts per status |
| `run_query` | `DELETE FROM orders` | rejected: only read-only queries are allowed |
| `explain_query` | `SELECT * FROM orders WHERE customer_id = 7` | plan using the customer index |

### Claude Desktop

Add the server to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "pg-insight": {
      "command": "/path/to/pg-insight-mcp/.venv/bin/pg-insight-mcp",
      "env": {
        "DATABASE_URL": "postgresql://shop:shop@localhost:5434/shop"
      }
    }
  }
}
```

On Windows the file is `%APPDATA%\Claude\claude_desktop_config.json` and the command is
`C:\\path\\to\\pg-insight-mcp\\.venv\\Scripts\\pg-insight-mcp.exe`. Restart Claude Desktop after editing it.

Then ask questions such as *"Which product category brought in the most revenue last quarter?"*.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | required | PostgreSQL connection string |
| `PG_INSIGHT_MAX_ROWS` | `200` | Maximum rows returned per query |
| `PG_INSIGHT_STATEMENT_TIMEOUT_MS` | `5000` | Per-statement timeout |
| `PG_INSIGHT_ALLOWED_SCHEMAS` | all | Comma-separated schema allow-list |

For production databases, also connect with a dedicated role that only has `SELECT` privileges. The server's
checks are a second layer of defence, not a replacement for database permissions.

## Project layout

```
src/pg_insight/
  config.py     settings from environment variables
  guard.py      SQL validation
  database.py   catalog queries and read-only execution
  server.py     MCP tools, resource and prompt
seed/           sample schema and data
tests/          guard unit tests and end-to-end MCP tests
```

## Tests

```bash
docker compose up -d
pytest
ruff check src tests
```

The end-to-end tests connect an in-memory MCP client to the server and run against the sample database. They are
skipped when the database is not reachable.

Stop the sample database with `docker compose down`.

## License

MIT
