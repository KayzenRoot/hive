from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app import main
from app.health import HealthResponse, ServiceCheck


def _healthy_response() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version="0.0.1-bootstrap",
        environment="test",
        timestamp=datetime.now(UTC),
        data_root="/tmp/hive",
        checks={
            "postgres": ServiceCheck(status="ok", details={"pgvector": True}),
            "redis": ServiceCheck(status="ok", details={"canonical": False}),
            "storage": ServiceCheck(status="ok", details={"writable": True}),
        },
    )


def test_health_endpoint_returns_real_check_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "collect_health", lambda settings: _healthy_response())

    response = TestClient(main.app).get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["postgres"]["details"]["pgvector"] is True
    assert body["checks"]["redis"]["details"]["canonical"] is False


def test_health_endpoint_returns_service_unavailable_when_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    degraded = _healthy_response().model_copy(
        update={
            "status": "degraded",
            "checks": {
                **_healthy_response().checks,
                "postgres": ServiceCheck(status="degraded", details={"pgvector": False}),
            },
        }
    )
    monkeypatch.setattr(main, "collect_health", lambda settings: degraded)

    response = TestClient(main.app).get("/api/v1/status")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
