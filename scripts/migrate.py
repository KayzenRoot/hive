from __future__ import annotations

import subprocess
import sys
import time

import psycopg

from app.config import Settings

WAIT_ATTEMPTS = 60


def wait_for_database(settings: Settings) -> bool:
    for attempt in range(WAIT_ATTEMPTS):
        try:
            with (
                psycopg.connect(settings.postgres_dsn, connect_timeout=2) as connection,
                connection.cursor() as cursor,
            ):
                cursor.execute("SELECT 1")
            return True
        except psycopg.OperationalError as exc:
            if attempt == WAIT_ATTEMPTS - 1:
                print(f"PostgreSQL did not become available: {type(exc).__name__}", file=sys.stderr)
                return False
            time.sleep(1)
    return False


def main() -> int:
    settings = Settings()
    if not wait_for_database(settings):
        return 1
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
