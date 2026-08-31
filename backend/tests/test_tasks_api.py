from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app import main, tasks_api
from app.cas import CASStore, StoredBlob
from app.config import Settings
from app.task_intake import TaskNotFoundError, TaskResponse

PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")
TASK_ID = UUID("00000000-0000-0000-0000-000000000002")


def task_response(filename: str | None = "prompt.txt") -> TaskResponse:
    now = datetime.now(UTC)
    return TaskResponse(
        task_id=TASK_ID,
        project_id=PROJECT_ID,
        title="Prompt",
        source_type="TXT",
        intake_status="READY",
        original_blob_sha256="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        original_filename=filename,
        media_type="text/plain",
        logical_size=5,
        compressed_size=20,
        extracted_text_available=True,
        extraction_method="hive-text-normalizer",
        extraction_version="1",
        extraction_error=None,
        page_count=None,
        created_at=now,
        updated_at=now,
    )


def test_wrong_project_task_is_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(_settings: Settings, _project_id: UUID, _task_id: UUID) -> TaskResponse:
        raise TaskNotFoundError("task not found")

    monkeypatch.setattr(tasks_api, "get_task", missing)
    response = TestClient(main.app).get(f"/api/v1/projects/{PROJECT_ID}/tasks/{TASK_ID}")

    assert response.status_code == 404
    assert response.json() == {"detail": "task not found"}


def test_artifact_is_verified_and_filename_header_is_sanitized(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = Settings(data_root=tmp_path)
    original = tmp_path / "original.txt"
    original.write_bytes(b"exact")
    stored = CASStore(settings).put(original)
    record = task_response("nested\\evil\r\nname.txt")
    record = record.model_copy(update={"original_blob_sha256": stored.sha256})
    blob = StoredBlob(
        sha256=stored.sha256,
        logical_size=stored.logical_size,
        physical_size=stored.physical_size,
        codec="zstd",
        codec_config=stored.codec_config,
        path=stored.path,
    )
    monkeypatch.setattr(tasks_api, "get_settings_for_router", lambda: settings)
    monkeypatch.setattr(tasks_api, "task_blob", lambda *_args: (record, blob))

    response = TestClient(main.app).get(f"/api/v1/projects/{PROJECT_ID}/tasks/{TASK_ID}/artifact")

    assert response.status_code == 200
    assert response.content == b"exact"
    assert "\r" not in response.headers["content-disposition"]
    assert "\n" not in response.headers["content-disposition"]
    assert "\\" not in response.headers["content-disposition"]


def test_text_endpoint_accepts_structured_input_without_db_in_unit_test(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = Settings(data_root=tmp_path)
    expected = task_response()
    monkeypatch.setattr(tasks_api, "get_settings_for_router", lambda: settings)
    monkeypatch.setattr(tasks_api, "create_task", lambda *_args: expected)

    response = TestClient(main.app).post(
        f"/api/v1/projects/{PROJECT_ID}/tasks/text",
        json={"title": "Prompt", "text": "hello\r\nworld", "format": "text"},
    )

    assert response.status_code == 201
    assert response.json()["task_id"] == str(TASK_ID)


def test_upload_rejects_unsupported_file_before_task_creation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = Settings(data_root=tmp_path)
    monkeypatch.setattr(tasks_api, "get_settings_for_router", lambda: settings)
    create_called = False

    def fail_if_called(*_args: object) -> TaskResponse:
        nonlocal create_called
        create_called = True
        raise AssertionError("invalid upload must not create a task")

    monkeypatch.setattr(tasks_api, "create_task", fail_if_called)
    response = TestClient(main.app).post(
        f"/api/v1/projects/{PROJECT_ID}/tasks/upload",
        files={"file": ("payload.bin", b"not accepted", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert not create_called
