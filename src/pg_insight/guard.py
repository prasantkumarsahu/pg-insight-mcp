import re

ALLOWED_FIRST_KEYWORDS = {"select", "with", "explain", "show", "values", "table"}

FORBIDDEN_KEYWORDS = {
    "insert",
    "update",
    "delete",
    "merge",
    "drop",
    "alter",
    "create",
    "truncate",
    "grant",
    "revoke",
    "copy",
    "call",
    "vacuum",
    "reindex",
}

FORBIDDEN_FUNCTIONS = {
    "pg_sleep",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_stat_file",
    "lo_import",
    "lo_export",
    "dblink",
    "dblink_exec",
    "pg_terminate_backend",
    "pg_cancel_backend",
    "set_config",
}

_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")
_DOLLAR_QUOTED = re.compile(r"\$((?:[A-Za-z_]\w*)?)\$.*?\$\1\$", re.DOTALL)
_QUOTED_IDENTIFIER = re.compile(r'"(?:[^"]|"")*"')
_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class QueryRejected(ValueError):
    pass


def _strip_literals_and_comments(sql: str) -> str:
    for pattern in (_BLOCK_COMMENT, _LINE_COMMENT, _DOLLAR_QUOTED, _STRING_LITERAL, _QUOTED_IDENTIFIER):
        sql = pattern.sub(" ", sql)
    return sql


def validate_read_only(sql: str) -> str:
    if not sql or not sql.strip():
        raise QueryRejected("Query is empty")

    cleaned = _strip_literals_and_comments(sql).strip().rstrip(";").strip()
    if not cleaned:
        raise QueryRejected("Query is empty")
    if ";" in cleaned:
        raise QueryRejected("Only a single statement is allowed")

    words = [word.lower() for word in _WORD.findall(cleaned)]
    if words[0] not in ALLOWED_FIRST_KEYWORDS:
        raise QueryRejected(f"Only read-only queries are allowed, got '{words[0].upper()}'")

    if words[0] == "explain" and "analyze" in words[:4]:
        raise QueryRejected("EXPLAIN ANALYZE executes the query; use the explain_query tool instead")

    forbidden = sorted(set(words) & FORBIDDEN_KEYWORDS)
    if forbidden:
        raise QueryRejected(f"Query contains forbidden keyword(s): {', '.join(k.upper() for k in forbidden)}")

    blocked = sorted(set(words) & FORBIDDEN_FUNCTIONS)
    if blocked:
        raise QueryRejected(f"Query calls blocked function(s): {', '.join(blocked)}")

    if re.search(r"\binto\b", cleaned, re.IGNORECASE) and words[0] in {"select", "with"}:
        raise QueryRejected("SELECT ... INTO creates a table and is not allowed")

    return sql.strip().rstrip(";").strip()
