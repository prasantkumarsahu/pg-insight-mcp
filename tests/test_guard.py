import pytest

from pg_insight.guard import QueryRejected, validate_read_only


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "select * from orders where status = 'paid';",
        "WITH t AS (SELECT 1 AS x) SELECT x FROM t",
        "EXPLAIN SELECT * FROM orders",
        "SHOW server_version",
        "VALUES (1), (2)",
        "TABLE customers",
        "SELECT 'drop table x; delete' AS text",
        'SELECT "update" FROM t',
        "SELECT 1 -- delete everything",
        "SELECT $$insert into x$$",
        "SELECT created_at FROM orders",
    ],
)
def test_accepts_read_only_queries(sql):
    assert validate_read_only(sql)


@pytest.mark.parametrize(
    ("sql", "message"),
    [
        ("", "empty"),
        ("   ", "empty"),
        ("-- only a comment", "empty"),
        ("DELETE FROM orders", "read-only"),
        ("UPDATE orders SET status = 'paid'", "read-only"),
        ("SELECT 1; DROP TABLE orders", "single statement"),
        ("WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d", "forbidden keyword"),
        ("EXPLAIN ANALYZE SELECT * FROM orders", "EXPLAIN ANALYZE"),
        ("EXPLAIN (ANALYZE) DELETE FROM orders", "EXPLAIN ANALYZE"),
        ("SELECT pg_sleep(10)", "blocked function"),
        ("SELECT pg_read_file('/etc/passwd')", "blocked function"),
        ("SELECT set_config('statement_timeout', '0', false)", "blocked function"),
        ("SELECT * INTO backup FROM orders", "INTO"),
    ],
)
def test_rejects_unsafe_queries(sql, message):
    with pytest.raises(QueryRejected, match=message):
        validate_read_only(sql)


def test_strips_trailing_semicolon():
    assert validate_read_only("  SELECT 1;  ") == "SELECT 1"
