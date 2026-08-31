from datetime import UTC, datetime
from typing import Any

import psycopg
import redis
from pydantic import BaseModel, Field

from .config import Settings


class ServiceCheck(BaseModel):
    status: str
    details: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    timestamp: datetime
    data_root: str
    checks: dict[str, ServiceCheck]


def _unavailable(exc: Exception) -> ServiceCheck:
    return ServiceCheck(
        status="degraded",
        details={"reason": f"connection failed ({type(exc).__name__})"},
    )


def check_postgres(settings: Settings) -> ServiceCheck:
    try:
        with (
            psycopg.connect(settings.postgres_dsn, connect_timeout=2) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
            row = cursor.fetchone()
            vector_available = bool(row and row[0])
        return ServiceCheck(
            status="ok" if vector_available else "degraded",
            details={"pgvector": vector_available},
        )
    except Exception as exc:
        return _unavailable(exc)


def check_redis(settings: Settings) -> ServiceCheck:
    client = redis.Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=2,
        socket_timeout=2,
        decode_responses=True,
    )
    try:
        client.ping()
        return ServiceCheck(status="ok", details={"canonical": False})
    except Exception as exc:
        return _unavailable(exc)
    finally:
        client.close()  # type: ignore[no-untyped-call]


def check_storage(settings: Settings) -> ServiceCheck:
    try:
        root = settings.ensure_data_root()
        return ServiceCheck(
            status="ok",
            details={"configured": True, "writable": True, "canonical_data_root": str(root)},
        )
    except OSError as exc:
        return ServiceCheck(
            status="degraded",
            details={"configured": True, "writable": False, "reason": type(exc).__name__},
        )


def collect_health(settings: Settings) -> HealthResponse:
    checks = {
        "postgres": check_postgres(settings),
        "redis": check_redis(settings),
        "storage": check_storage(settings),
    }
    overall = "ok" if all(check.status == "ok" for check in checks.values()) else "degraded"
    return HealthResponse(
        status=overall,
        version=settings.version,
        environment=settings.environment,
        timestamp=datetime.now(UTC),
        data_root=str(settings.resolved_data_root),
        checks=checks,
    )
