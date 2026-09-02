from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg

from .config import Settings

CURRENT_SCHEMA_REVISION = "0005_semantic_retrieval"


@contextmanager
def database_connection(settings: Settings) -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(settings.postgres_dsn, connect_timeout=3) as connection:
        yield connection


def ensure_schema_current(settings: Settings) -> None:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version_num FROM alembic_version")
        row = cursor.fetchone()
    if row is None or row[0] != CURRENT_SCHEMA_REVISION:
        actual = row[0] if row else "missing"
        raise RuntimeError(
            f"HIVE database schema is not at {CURRENT_SCHEMA_REVISION}; "
            f"current revision is {actual}"
        )
