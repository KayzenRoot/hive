from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from .cas import CHUNK_SIZE, CASIntegrityError, CASStore
from .config import Settings
from .task_intake import (
    ExtractionNotReadyError,
    IntakeValidationError,
    ProjectNotFoundError,
    StorageResponse,
    TaskNotFoundError,
    TaskResponse,
    TaskTextRequest,
    TaskTextResponse,
    create_task,
    get_task,
    get_task_text,
    list_tasks,
    project_exists,
    sanitize_filename,
    storage_stats,
    task_blob,
    validate_structured_source,
    validate_upload_source,
)

router = APIRouter(tags=["tasks"])


def _temporary_root(settings: Settings) -> Path:
    root = settings.ensure_data_root() / "tmp" / "intake"
    root.mkdir(parents=True, exist_ok=True)
    return root


async def _save_upload(settings: Settings, upload: UploadFile) -> Path:
    target: Path | None = None
    total = 0
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix="upload-", suffix=".part", dir=_temporary_root(settings), delete=False
        ) as handle:
            target = Path(handle.name)
            while chunk := await upload.read(CHUNK_SIZE):
                total += len(chunk)
                if total > settings.task_max_upload_bytes:
                    raise IntakeValidationError("upload exceeds the configured size limit")
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        return target
    except Exception:
        if target is not None:
            target.unlink(missing_ok=True)
        raise


def _save_text(settings: Settings, request: TaskTextRequest) -> Path:
    raw = request.text.encode("utf-8")
    if len(raw) > settings.task_max_structured_text_bytes:
        raise IntakeValidationError("structured text exceeds the configured size limit")
    with tempfile.NamedTemporaryFile(
        mode="wb", prefix="text-", suffix=".part", dir=_temporary_root(settings), delete=False
    ) as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
        return Path(handle.name)


def _validation_error(exc: IntakeValidationError) -> HTTPException:
    status = 413 if "limit" in str(exc) or "size" in str(exc) else 400
    return HTTPException(status_code=status, detail=str(exc))


@router.post(
    "/api/v1/projects/{project_id}/tasks/upload",
    response_model=TaskResponse,
    status_code=201,
)
async def upload_task(
    project_id: UUID,
    file: Annotated[UploadFile, File(...)],
    title: Annotated[str | None, Form()] = None,
) -> TaskResponse:
    settings = get_settings_for_router()
    temporary: Path | None = None
    try:
        temporary = await _save_upload(settings, file)
        source = validate_upload_source(temporary, file.filename, settings)
        normalized_title = title.strip() if title and title.strip() else None
        return create_task(settings, project_id, temporary, source, normalized_title)
    except IntakeValidationError as exc:
        raise _validation_error(exc) from exc
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="task intake database unavailable") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        await file.close()


@router.post(
    "/api/v1/projects/{project_id}/tasks/text",
    response_model=TaskResponse,
    status_code=201,
)
def create_text_task(project_id: UUID, request: TaskTextRequest) -> TaskResponse:
    settings = get_settings_for_router()
    temporary: Path | None = None
    try:
        temporary = _save_text(settings, request)
        source = validate_structured_source(temporary, request, settings)
        return create_task(settings, project_id, temporary, source, request.title)
    except IntakeValidationError as exc:
        raise _validation_error(exc) from exc
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="task intake database unavailable") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@router.get("/api/v1/projects/{project_id}/tasks", response_model=list[TaskResponse])
def get_tasks(
    project_id: UUID, limit: int = Query(default=100, ge=1, le=200)
) -> list[TaskResponse]:
    try:
        settings = get_settings_for_router()
        if not project_exists(settings, project_id):
            raise HTTPException(status_code=404, detail="project not found")
        return list_tasks(settings, project_id, limit)
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="task intake database unavailable") from exc


@router.get("/api/v1/projects/{project_id}/tasks/{task_id}", response_model=TaskResponse)
def get_task_detail(project_id: UUID, task_id: UUID) -> TaskResponse:
    try:
        return get_task(get_settings_for_router(), project_id, task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="task intake database unavailable") from exc


@router.get("/api/v1/projects/{project_id}/tasks/{task_id}/artifact")
def download_task_artifact(project_id: UUID, task_id: UUID) -> StreamingResponse:
    settings = get_settings_for_router()
    try:
        task, blob = task_blob(settings, project_id, task_id)
        handle = CASStore(settings).open_verified(blob.sha256, task.logical_size)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CASIntegrityError as exc:
        raise HTTPException(
            status_code=500, detail="stored artifact integrity verification failed"
        ) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="task intake database unavailable") from exc
    filename = sanitize_filename(task.original_filename)
    ascii_filename = filename.encode("ascii", "ignore").decode("ascii") or "artifact"
    return StreamingResponse(
        CASStore(settings).iter_file(handle),
        media_type=task.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{ascii_filename}"',
            "X-HIVE-Original-SHA256": task.original_blob_sha256,
        },
    )


@router.get("/api/v1/projects/{project_id}/tasks/{task_id}/text", response_model=TaskTextResponse)
def get_task_extracted_text(project_id: UUID, task_id: UUID) -> TaskTextResponse:
    try:
        return get_task_text(get_settings_for_router(), project_id, task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExtractionNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="task intake database unavailable") from exc


@router.get("/api/v1/storage", response_model=StorageResponse)
def get_storage_stats() -> StorageResponse:
    try:
        return storage_stats(get_settings_for_router())
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="storage database unavailable") from exc


def get_settings_for_router() -> Settings:
    # Kept as a small seam for API tests without creating a second application
    # configuration object or making the router depend on main.py.
    from .config import get_settings

    return get_settings()
