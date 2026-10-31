import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    max_rows: int = 200
    statement_timeout_ms: int = 5000
    allowed_schemas: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> "Settings":
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL is not set, e.g. postgresql://user:pass@localhost:5432/db")
        schemas = os.environ.get("PG_INSIGHT_ALLOWED_SCHEMAS", "")
        return cls(
            database_url=url,
            max_rows=int(os.environ.get("PG_INSIGHT_MAX_ROWS", "200")),
            statement_timeout_ms=int(os.environ.get("PG_INSIGHT_STATEMENT_TIMEOUT_MS", "5000")),
            allowed_schemas=tuple(s.strip() for s in schemas.split(",") if s.strip()),
        )
