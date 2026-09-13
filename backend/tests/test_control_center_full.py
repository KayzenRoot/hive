from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app import control_center_full, main
from app.control_center_full import (
    ALERT_IDS,
    CHART_IDS,
    HEALTH_IDS,
    PROJECT_CAPABILITIES,
    FullStatus,
)
from app.control_center_metrics import MetricProvenance
from app.control_center_storage_metrics import StorageObservation
from app.registry import ProjectState
from app.telemetry import EVENT_ENVELOPE_VERSION, EventEnvelope

PROJECT_ID = UUID("00000000-0000-0000-0000-000000000022")
NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


def project() -> SimpleNamespace:
    return SimpleNamespace(
        project_id=PROJECT_ID,
        name="fixture",
        relative_path="fixture",
        git_branch="main",
        git_head_sha="a" * 40,
        detached_head=False,
        repository_accessible=True,
        working_tree_clean=True,
        language_stack=["python"],
        state=ProjectState.READY,
        inspection_error=None,
        created_at=NOW,
        updated_at=NOW,
        last_inspected_at=NOW,
    )


def event(event_type: str, ordering_id: int, payload: dict[str, object]) -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid4(),
        envelope_version=EVENT_ENVELOPE_VERSION,
        event_type=event_type,
        project_id=PROJECT_ID,
        task_id=None,
        run_id=uuid4(),
        ordering_id=ordering_id,
        occurred_at=NOW,
        payload=payload,
        provenance={"producer": "test", "deterministic": True},
        cursor=str(ordering_id),
    )


def wire(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(control_center_full, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(control_center_full, "get_project", lambda _settings, _id: project())
    monkeypatch.setattr(
        control_center_full,
        "_events_for_project",
        lambda _settings, _id: (
            [
                event("executor.started", 1, {"input_tokens": 10}),
                event("cache.hit", 2, {"layer": "retrieval"}),
                event("validation.passed", 3, {"passed": True}),
            ],
            False,
        ),
    )
    monkeypatch.setattr(
        control_center_full,
        "_index_details",
        lambda _settings, _project: (FullStatus.AVAILABLE, {"head_matches": True}),
    )
    monkeypatch.setattr(
        control_center_full,
        "_repository_inventory",
        lambda _settings, _id: ({}, [{"path": "app.py", "language": "python"}], []),
    )
    monkeypatch.setattr(
        control_center_full,
        "_retrieval_details",
        lambda _settings, _id: (FullStatus.AVAILABLE, {"corpus_state": "CURRENT"}),
    )
    monkeypatch.setattr(
        control_center_full,
        "_document_observations",
        lambda _settings, _project: [
            SimpleNamespace(
                path="docs/project-brain/13-CHECKPOINT.md",
                status=FullStatus.AVAILABLE,
                model_dump=lambda **_kwargs: {
                    "path": "docs/project-brain/13-CHECKPOINT.md",
                    "status": "AVAILABLE",
                    "byte_count": 10,
                    "source": "test",
                },
            ),
            SimpleNamespace(
                path="docs/project-brain/03-SCOPE.md",
                status=FullStatus.AVAILABLE,
                model_dump=lambda **_kwargs: {
                    "path": "docs/project-brain/03-SCOPE.md",
                    "status": "AVAILABLE",
                    "byte_count": 10,
                    "source": "test",
                },
            ),
            SimpleNamespace(
                path="docs/project-brain/15-DEFINITION-OF-DONE.md",
                status=FullStatus.AVAILABLE,
                model_dump=lambda **_kwargs: {
                    "path": "docs/project-brain/15-DEFINITION-OF-DONE.md",
                    "status": "AVAILABLE",
                    "byte_count": 10,
                    "source": "test",
                },
            ),
        ],
    )
    monkeypatch.setattr(control_center_full, "_git_commits", lambda _settings, _project: [])
    monkeypatch.setattr(control_center_full, "summarize_runs", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        control_center_full,
        "_memory_details",
        lambda _settings, _id: (FullStatus.AVAILABLE, {"record_count": 0}),
    )
    monkeypatch.setattr(
        control_center_full,
        "_health_surfaces",
        lambda _settings: [
            control_center_full.HealthSurface(
                id=health_id,
                status=FullStatus.AVAILABLE,
                summary="test",
                provenance=MetricProvenance.EXACT,
                details={"free_ratio": 0.5} if health_id == "platform-resource-health" else {},
            )
            for health_id in HEALTH_IDS
        ],
    )
    monkeypatch.setattr(
        control_center_full,
        "observe_project_storage",
        lambda _settings, _id: StorageObservation(100, 50, 1, 1),
    )


def test_full_contract_exposes_all_closed_surface_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    wire(monkeypatch)

    response = TestClient(main.app).get(
        "/api/v1/control-center/projects/00000000-0000-0000-0000-000000000022/full?history_points=7"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["control_center_full_version"] == "control-center-full-v1"
    assert {item["id"] for item in body["capabilities"]} == set(PROJECT_CAPABILITIES)
    assert {item["id"] for item in body["charts"]} == set(CHART_IDS)
    assert {item["id"] for item in body["alerts"]} == set(ALERT_IDS)
    assert {item["id"] for item in body["health"]} == set(HEALTH_IDS)
    assert body["canonical_store"] == "postgres"
    assert body["hot_store_canonical"] is False
    assert body["full_v01_complete_claimed"] is False
    assert body["history_max_points"] == 7
    assert {chart["max_points"] for chart in body["charts"]} == {7, 100}


def test_full_endpoint_keeps_missing_observations_truthful(monkeypatch: pytest.MonkeyPatch) -> None:
    wire(monkeypatch)

    def missing_document(path: str) -> SimpleNamespace:
        return SimpleNamespace(
            path=path,
            status=FullStatus.UNAVAILABLE,
            model_dump=lambda **_kwargs: {
                "path": path,
                "status": "UNAVAILABLE",
                "byte_count": None,
                "source": "test",
            },
        )

    monkeypatch.setattr(
        control_center_full,
        "_document_observations",
        lambda _settings, _project: [
            missing_document(path) for path in control_center_full.FULL_DOCUMENTS
        ],
    )

    response = TestClient(main.app).get(
        "/api/v1/control-center/projects/00000000-0000-0000-0000-000000000022/full"
    )

    assert response.status_code == 200
    checkpoint = next(
        item for item in response.json()["capabilities"] if item["id"] == "checkpoint-scope-dod"
    )
    assert checkpoint["status"] == "UNAVAILABLE"
    assert "0" not in checkpoint["summary"]
