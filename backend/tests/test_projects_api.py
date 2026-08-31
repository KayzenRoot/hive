from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app import main
from app.registry import ProjectConflictError, ProjectResponse, ProjectState

PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")


def project_response() -> ProjectResponse:
    now = datetime.now(UTC)
    return ProjectResponse(
        project_id=PROJECT_ID,
        name="Sample",
        relative_path="sample",
        git_branch="main",
        git_head_sha="1234567890abcdef1234567890abcdef12345678",
        detached_head=False,
        repository_accessible=True,
        working_tree_clean=True,
        language_stack=["python"],
        state=ProjectState.READY,
        inspection_error=None,
        created_at=now,
        updated_at=now,
        last_inspected_at=now,
    )


def test_register_list_and_fetch_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    record = project_response()
    monkeypatch.setattr(main, "register_project", lambda settings, request: record)
    monkeypatch.setattr(main, "list_projects", lambda settings: [record])
    monkeypatch.setattr(main, "get_project", lambda settings, project_id: record)
    client = TestClient(main.app)

    created = client.post("/api/v1/projects", json={"name": "Sample", "relative_path": "sample"})
    listed = client.get("/api/v1/projects")
    fetched = client.get(f"/api/v1/projects/{PROJECT_ID}")

    assert created.status_code == 201
    assert created.json()["state"] == "READY"
    assert listed.status_code == 200
    assert listed.json()[0]["project_id"] == str(PROJECT_ID)
    assert fetched.status_code == 200
    assert fetched.json()["relative_path"] == "sample"


def test_duplicate_and_invalid_path_errors_are_stable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        main,
        "register_project",
        lambda settings, request: (_ for _ in ()).throw(
            ProjectConflictError("project path is already registered")
        ),
    )
    client = TestClient(main.app)

    duplicate = client.post("/api/v1/projects", json={"name": "Sample", "relative_path": "sample"})
    malformed = client.post("/api/v1/projects", json={"name": "", "relative_path": "sample"})

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "project path is already registered"
    assert malformed.status_code == 422


def test_missing_project_and_inspection_return_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "get_project", lambda settings, project_id: None)
    monkeypatch.setattr(main, "inspect_registered_project", lambda settings, project_id: None)
    client = TestClient(main.app)

    missing = client.get(f"/api/v1/projects/{PROJECT_ID}")
    missing_inspection = client.post(f"/api/v1/projects/{PROJECT_ID}/inspect")
    malformed_id = client.get("/api/v1/projects/not-a-uuid")

    assert missing.status_code == 404
    assert missing_inspection.status_code == 404
    assert malformed_id.status_code == 422


def test_inspection_updates_persisted_record(monkeypatch: pytest.MonkeyPatch) -> None:
    record = project_response()
    monkeypatch.setattr(main, "inspect_registered_project", lambda settings, project_id: record)
    client = TestClient(main.app)

    inspected = client.post(f"/api/v1/projects/{PROJECT_ID}/inspect")

    assert inspected.status_code == 200
    assert inspected.json()["git_head_sha"] == record.git_head_sha


def test_inspection_exposes_persisted_blocked_state(monkeypatch: pytest.MonkeyPatch) -> None:
    blocked = project_response().model_copy(
        update={
            "git_branch": None,
            "git_head_sha": None,
            "detached_head": False,
            "repository_accessible": False,
            "working_tree_clean": None,
            "language_stack": [],
            "state": ProjectState.BLOCKED,
            "inspection_error": "path_boundary_violation",
        }
    )
    monkeypatch.setattr(main, "inspect_registered_project", lambda settings, project_id: blocked)
    client = TestClient(main.app)

    inspected = client.post(f"/api/v1/projects/{PROJECT_ID}/inspect")

    assert inspected.status_code == 200
    assert inspected.json()["state"] == "BLOCKED"
    assert inspected.json()["git_head_sha"] is None
    assert inspected.json()["inspection_error"] == "path_boundary_violation"
