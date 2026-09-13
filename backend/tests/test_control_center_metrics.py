"""Focused contract tests for WO-021 Control Center metrics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app import control_center_metrics, main
from app.control_center_storage_metrics import StorageObservation
from app.telemetry import EVENT_ENVELOPE_VERSION, EventEnvelope, EventPage

PROJECT_A = UUID("00000000-0000-0000-0000-0000000000a1")
PROJECT_B = UUID("00000000-0000-0000-0000-0000000000b1")
RUN_A = UUID("00000000-0000-0000-0000-000000000011")
NOW = datetime(2026, 9, 13, 11, 0, tzinfo=UTC)


def event(
    event_type: str,
    *,
    project_id: UUID = PROJECT_A,
    run_id: UUID | None = RUN_A,
    ordering_id: int = 1,
    payload: dict[str, object] | None = None,
    provenance: dict[str, object] | None = None,
    occurred_at: datetime | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid4(),
        envelope_version=EVENT_ENVELOPE_VERSION,
        event_type=event_type,
        project_id=project_id,
        task_id=None,
        run_id=run_id,
        ordering_id=ordering_id,
        occurred_at=occurred_at or NOW,
        payload=payload or {"component": "fixture"},
        provenance=provenance or {"producer": "test", "deterministic": True},
        cursor=str(ordering_id),
    )


def wire(
    monkeypatch: pytest.MonkeyPatch,
    *,
    events: dict[UUID, list[EventEnvelope]],
    storage: dict[UUID, StorageObservation] | None = None,
    global_storage: StorageObservation | None = None,
    projects: list[UUID] | None = None,
) -> None:
    known = projects or list(events)
    monkeypatch.setattr(
        control_center_metrics,
        "get_settings",
        lambda: SimpleNamespace(),
    )
    monkeypatch.setattr(
        control_center_metrics,
        "get_project",
        lambda _settings, project_id: (
            SimpleNamespace(project_id=project_id) if project_id in known else None
        ),
    )
    monkeypatch.setattr(
        control_center_metrics,
        "list_projects",
        lambda _settings: [SimpleNamespace(project_id=project_id) for project_id in known],
    )

    def recent(
        _settings: object,
        project_id: UUID,
        *,
        limit: int = 100,
    ) -> EventPage:
        source = events.get(project_id, [])
        selected = source[-limit:]
        return EventPage(
            events=selected,
            next_cursor=(selected[-1].cursor if len(source) > limit and selected else None),
            has_more=len(source) > limit,
            limit=limit,
        )

    monkeypatch.setattr(
        control_center_metrics,
        "list_recent_events",
        recent,
    )
    storage_map = storage or {}
    empty_storage = StorageObservation(
        logical_task_bytes=0,
        physical_referenced_bytes=0,
        task_count=0,
        referenced_blob_count=0,
    )
    monkeypatch.setattr(
        control_center_metrics,
        "observe_project_storage",
        lambda _settings, project_id: storage_map.get(project_id, empty_storage),
    )
    monkeypatch.setattr(
        control_center_metrics,
        "observe_global_storage",
        lambda _settings: global_storage or empty_storage,
    )


def client() -> TestClient:
    return TestClient(main.app)


def test_project_metrics_preserve_provenance_and_real_cache_truth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = [
        event(
            "executor.started",
            ordering_id=1,
            occurred_at=NOW - timedelta(seconds=4),
            payload={
                "input_tokens": 100,
                "cached_tokens": 20,
                "estimated": True,
            },
        ),
        event(
            "run.completed",
            ordering_id=2,
            occurred_at=NOW - timedelta(seconds=3),
            payload={
                "input_tokens": 90,
                "cached_tokens": 30,
                "output_tokens": 15,
                "usage_reconciled": True,
            },
        ),
        event(
            "context.built",
            ordering_id=3,
            occurred_at=NOW - timedelta(seconds=2),
            payload={
                "estimated_tokens_before": 1000,
                "estimated_tokens_after": 600,
            },
        ),
        event(
            "cache.hit",
            ordering_id=4,
            occurred_at=NOW - timedelta(seconds=1),
        ),
        event("cache.miss", ordering_id=5),
    ]
    wire(
        monkeypatch,
        events={PROJECT_A: events},
        storage={
            PROJECT_A: StorageObservation(
                logical_task_bytes=1000,
                physical_referenced_bytes=600,
                task_count=2,
                referenced_blob_count=1,
            )
        },
    )

    response = client().get(
        "/api/v1/control-center/metrics",
        params={"project_id": str(PROJECT_A)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "PROJECT"
    assert body["canonical_store"] == "postgres"
    assert body["hot_store_canonical"] is False
    assert body["token"]["input_tokens"] == {
        "value": 90.0,
        "provenance": "EXACT",
        "source": "telemetry-window:input_tokens",
    }
    assert body["token"]["fresh_tokens"]["value"] == 60.0
    assert body["token"]["fresh_tokens"]["provenance"] == "EXACT"
    assert body["context"]["reduction_tokens"]["value"] == 400.0
    assert body["context"]["reduction_tokens"]["provenance"] == "ESTIMATED"
    assert body["cache"]["hits"]["value"] == 1.0
    assert body["cache"]["misses"]["value"] == 1.0
    assert body["cache"]["hit_rate"]["value"] == 0.5
    assert body["storage"]["logical_task_bytes"]["value"] == 1000.0
    assert body["storage"]["physical_referenced_bytes"]["value"] == 600.0
    assert body["storage"]["saved_bytes"]["value"] == 400.0
    assert body["cost_provenance"] == "UNAVAILABLE"


def test_missing_metrics_are_unavailable_not_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire(monkeypatch, events={PROJECT_A: [event("tool.called")]})

    body = (
        client()
        .get(
            "/api/v1/control-center/metrics",
            params={"project_id": str(PROJECT_A)},
        )
        .json()
    )

    assert body["token"]["input_tokens"]["value"] is None
    assert body["token"]["input_tokens"]["provenance"] == "UNAVAILABLE"
    assert body["cache"]["hits"]["value"] is None
    assert body["cache"]["hit_rate"]["value"] is None
    assert body["context"]["reduction_ratio"]["value"] is None
    assert body["storage"]["logical_task_bytes"]["value"] == 0.0
    assert body["storage"]["savings_ratio"]["value"] is None


def test_unlabelled_observed_token_value_is_unknown_not_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire(
        monkeypatch,
        events={
            PROJECT_A: [
                event(
                    "executor.started",
                    payload={"input_tokens": 33},
                )
            ]
        },
    )

    body = (
        client()
        .get(
            "/api/v1/control-center/metrics",
            params={"project_id": str(PROJECT_A)},
        )
        .json()
    )

    assert body["token"]["input_tokens"]["value"] == 33.0
    assert body["token"]["input_tokens"]["provenance"] == "UNKNOWN"


def test_history_is_bounded_and_unknown_project_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = [
        event(
            "executor.started",
            ordering_id=index + 1,
            run_id=UUID(int=index + 1),
            payload={"token_count": index + 1, "estimated": True},
        )
        for index in range(20)
    ]
    wire(monkeypatch, events={PROJECT_A: source})

    response = client().get(
        "/api/v1/control-center/metrics",
        params={
            "project_id": str(PROJECT_A),
            "history_points": 7,
        },
    )
    assert response.status_code == 200
    assert len(response.json()["history"]) <= 7
    assert response.json()["history_max_points"] == 7

    missing = client().get(
        "/api/v1/control-center/metrics",
        params={"project_id": str(UUID(int=999))},
    )
    assert missing.status_code == 404


def test_global_metrics_compose_project_truth_without_double_counting_shared_cas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = {
        PROJECT_A: [
            event(
                "cache.hit",
                project_id=PROJECT_A,
                payload={"input_tokens": 10, "estimated": True},
            )
        ],
        PROJECT_B: [
            event(
                "cache.miss",
                project_id=PROJECT_B,
                run_id=UUID(int=22),
                payload={"input_tokens": 20, "estimated": True},
            )
        ],
    }
    wire(
        monkeypatch,
        events=events,
        projects=[PROJECT_A, PROJECT_B],
        storage={
            PROJECT_A: StorageObservation(100, 60, 1, 1),
            PROJECT_B: StorageObservation(200, 60, 2, 1),
        },
        global_storage=StorageObservation(300, 60, 3, 1),
    )

    first = client().get("/api/v1/control-center/metrics/global").json()
    second = client().get("/api/v1/control-center/metrics/global").json()

    assert first["scope"] == "GLOBAL"
    assert first["project_count"] == 2
    assert first["token"]["input_tokens"]["value"] == 30.0
    assert first["token"]["input_tokens"]["provenance"] == "ESTIMATED"
    assert first["cache"]["hits"]["value"] == 1.0
    assert first["cache"]["misses"]["value"] == 1.0
    assert first["cache"]["hit_rate"]["value"] == 0.5
    assert first["storage"]["logical_task_bytes"]["value"] == 300.0
    assert first["storage"]["physical_referenced_bytes"]["value"] == 60.0
    assert first["storage"]["task_count"]["value"] == 3.0
    assert first["storage"]["referenced_blob_count"]["value"] == 1.0

    def comparable(body: dict[str, object]) -> dict[str, object]:
        return {key: value for key, value in body.items() if key != "generated_at"}

    assert comparable(first) == comparable(second)
