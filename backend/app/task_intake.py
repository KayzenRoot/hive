from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

import pypdf
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, field_validator

from .cas import CASStore, StoredBlob
from .config import Settings
from .db import database_connection

MAX_TITLE_LENGTH = 200
MAX_FILENAME_LENGTH = 1024
NEWLINE_CONFIG = {"encoding": "utf-8-sig", "newline": "LF", "version": "1"}


class IntakeValidationError(ValueError):
    """The input is not an accepted bounded task artifact."""


class ProjectNotFoundError(LookupError):
    """The requested task project does not exist."""


class TaskNotFoundError(LookupError):
    """The requested task is not owned by the requested project."""


class ExtractionNotReadyError(RuntimeError):
    """The accepted original exists but usable text is unavailable."""


class TaskTextRequest(BaseModel):
    title: str | None = Field(default=None, max_length=MAX_TITLE_LENGTH)
    text: str = Field(min_length=1)
    format: Literal["text", "markdown"] = "text"

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class TaskResponse(BaseModel):
    task_id: UUID
    project_id: UUID
    title: str | None
    source_type: str
    intake_status: str
    original_blob_sha256: str
    original_filename: str | None
    media_type: str
    logical_size: int
    compressed_size: int
    extracted_text_available: bool
    extraction_method: str
    extraction_version: str
    extraction_error: str | None
    page_count: int | None
    created_at: Any
    updated_at: Any


class TaskTextResponse(BaseModel):
    task_id: UUID
    project_id: UUID
    text: str
    extraction_method: str
    extraction_version: str
    page_count: int | None


class StorageResponse(BaseModel):
    task_count: int
    referenced_logical_bytes: int
    unique_logical_bytes: int
    physical_cas_bytes: int
    unique_blob_count: int
    deduplication_delta_bytes: int
    compression_delta_bytes: int
    compression_ratio: float | None
    compression_savings_bytes: int | None
    compression_delta_label: str


@dataclass(frozen=True)
class ExtractionResult:
    extraction_kind: str
    extractor: str
    extractor_version: str
    config_sha256: str
    status: str
    text: str | None
    page_count: int | None
    error: str | None


@dataclass(frozen=True)
class ValidatedSource:
    source_type: str
    media_type: str
    original_filename: str | None
    extraction: ExtractionResult


@dataclass(frozen=True)
class _StoredExtraction:
    extraction_id: UUID
    status: str
    text: str | None
    extractor: str
    extractor_version: str
    error: str | None
    page_count: int | None


_TASK_COLUMNS = """
    t.task_id, t.project_id, t.title, t.source_type, t.intake_status,
    t.original_blob_sha256, t.original_filename, t.media_type, t.logical_size,
    c.physical_size, t.extraction_method, t.extraction_version,
    t.extraction_error, t.page_count, t.created_at, t.updated_at,
    (e.status = 'READY' AND e.text_content IS NOT NULL)
"""


def _config_sha256(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _decode_text(path: Path, *, max_bytes: int) -> str:
    raw = path.read_bytes()
    if len(raw) > max_bytes:
        raise IntakeValidationError("text input exceeds the configured size limit")
    if b"\x00" in raw:
        raise IntakeValidationError("binary payloads are not accepted as text")
    try:
        return _normalize_newlines(raw.decode("utf-8-sig"))
    except UnicodeDecodeError as exc:
        raise IntakeValidationError("text input must be valid UTF-8") from exc


def _text_extraction(text: str, *, source_type: str, max_bytes: int) -> ExtractionResult:
    encoded_size = len(text.encode("utf-8"))
    if encoded_size > max_bytes:
        raise IntakeValidationError("extracted text exceeds the configured size limit")
    config = {**NEWLINE_CONFIG, "max_bytes": max_bytes, "source_type": source_type}
    return ExtractionResult(
        extraction_kind="text",
        extractor="hive-text-normalizer",
        extractor_version="1",
        config_sha256=_config_sha256(config),
        status="READY",
        text=text,
        page_count=None,
        error=None,
    )


def _pdf_extraction(path: Path, settings: Settings) -> ExtractionResult:
    config = {
        "max_pages": settings.task_max_pdf_pages,
        "max_text_bytes": settings.task_max_extracted_text_bytes,
        "newline": "LF",
    }
    config_hash = _config_sha256(config)
    version = pypdf.__version__
    try:
        reader = pypdf.PdfReader(str(path), strict=False)
        page_count = len(reader.pages)
        if page_count > settings.task_max_pdf_pages:
            return ExtractionResult(
                "pdf_text",
                "pypdf",
                version,
                config_hash,
                "EXTRACTION_FAILED",
                None,
                page_count,
                "pdf_page_limit_exceeded",
            )
        pages: list[str] = []
        total_bytes = 0
        for page in reader.pages:
            page_text = _normalize_newlines(page.extract_text() or "")
            total_bytes += len(page_text.encode("utf-8"))
            if total_bytes > settings.task_max_extracted_text_bytes:
                return ExtractionResult(
                    "pdf_text",
                    "pypdf",
                    version,
                    config_hash,
                    "EXTRACTION_FAILED",
                    None,
                    page_count,
                    "extracted_text_limit_exceeded",
                )
            pages.append(page_text)
        text = "\n".join(pages)
        if not text.strip():
            return ExtractionResult(
                "pdf_text",
                "pypdf",
                version,
                config_hash,
                "EXTRACTION_FAILED",
                None,
                page_count,
                "no_extractable_text",
            )
        return ExtractionResult(
            "pdf_text",
            "pypdf",
            version,
            config_hash,
            "READY",
            text,
            page_count,
            None,
        )
    except Exception:
        return ExtractionResult(
            "pdf_text",
            "pypdf",
            version,
            config_hash,
            "EXTRACTION_FAILED",
            None,
            None,
            "pdf_parse_failed",
        )


def _stored_filename(filename: str | None) -> str | None:
    if filename is None:
        return None
    value = filename.replace("\x00", "").strip()
    return value[:MAX_FILENAME_LENGTH] or None


def sanitize_filename(filename: str | None) -> str:
    value = filename or "artifact"
    value = re.sub(r'[\x00-\x1f\x7f"\\/:]+', "_", value).strip(" .")
    return value[:180] or "artifact"


def validate_upload_source(path: Path, filename: str | None, settings: Settings) -> ValidatedSource:
    settings.validate_intake_limits()
    if path.stat().st_size > settings.task_max_upload_bytes:
        raise IntakeValidationError("upload exceeds the configured size limit")
    stored_name = _stored_filename(filename)
    suffix = Path(stored_name or "").suffix.lower()
    with path.open("rb") as handle:
        magic = handle.read(5)
    if suffix == ".pdf":
        if magic != b"%PDF-":
            raise IntakeValidationError("PDF upload does not have valid PDF magic bytes")
        extraction = _pdf_extraction(path, settings)
        if extraction.error in {"pdf_page_limit_exceeded", "extracted_text_limit_exceeded"}:
            raise IntakeValidationError(extraction.error)
        if extraction.error == "pdf_parse_failed":
            raise IntakeValidationError("PDF could not be parsed")
        return ValidatedSource("PDF", "application/pdf", stored_name, extraction)
    if suffix in {".md", ".markdown"}:
        if magic == b"%PDF-":
            raise IntakeValidationError("PDF content must use a .pdf filename")
        text = _decode_text(path, max_bytes=settings.task_max_extracted_text_bytes)
        return ValidatedSource(
            "MARKDOWN",
            "text/markdown",
            stored_name,
            _text_extraction(
                text, source_type="MARKDOWN", max_bytes=settings.task_max_extracted_text_bytes
            ),
        )
    if suffix == ".txt":
        if magic == b"%PDF-":
            raise IntakeValidationError("PDF content must use a .pdf filename")
        text = _decode_text(path, max_bytes=settings.task_max_extracted_text_bytes)
        return ValidatedSource(
            "TXT",
            "text/plain",
            stored_name,
            _text_extraction(
                text, source_type="TXT", max_bytes=settings.task_max_extracted_text_bytes
            ),
        )
    raise IntakeValidationError("only PDF, Markdown, and TXT uploads are accepted")


def validate_structured_source(
    path: Path, request: TaskTextRequest, settings: Settings
) -> ValidatedSource:
    settings.validate_intake_limits()
    text = _decode_text(path, max_bytes=settings.task_max_structured_text_bytes)
    source_type = "MARKDOWN" if request.format == "markdown" else "STRUCTURED_TEXT"
    media_type = "text/markdown" if request.format == "markdown" else "text/plain"
    return ValidatedSource(
        source_type,
        media_type,
        None,
        _text_extraction(
            text, source_type=source_type, max_bytes=settings.task_max_structured_text_bytes
        ),
    )


def _task_from_row(row: tuple[Any, ...]) -> TaskResponse:
    return TaskResponse(
        task_id=row[0],
        project_id=row[1],
        title=row[2],
        source_type=row[3],
        intake_status=row[4],
        original_blob_sha256=row[5],
        original_filename=row[6],
        media_type=row[7],
        logical_size=row[8],
        compressed_size=row[9],
        extraction_method=row[10],
        extraction_version=row[11],
        extraction_error=row[12],
        page_count=row[13],
        created_at=row[14],
        updated_at=row[15],
        extracted_text_available=row[16],
    )


def _extraction_from_row(row: tuple[Any, ...]) -> _StoredExtraction:
    return _StoredExtraction(
        extraction_id=row[0],
        status=row[1],
        text=row[2],
        extractor=row[3],
        extractor_version=row[4],
        error=row[5],
        page_count=row[6],
    )


def project_exists(settings: Settings, project_id: UUID) -> bool:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM projects WHERE project_id = %s", (project_id,))
        return cursor.fetchone() is not None


def create_task(
    settings: Settings,
    project_id: UUID,
    source_path: Path,
    source: ValidatedSource,
    title: str | None,
) -> TaskResponse:
    if not project_exists(settings, project_id):
        raise ProjectNotFoundError("project not found")
    blob = CASStore(settings).put(source_path)
    extraction = source.extraction
    task_id = uuid4()
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO cas_blobs (
                sha256, logical_size, physical_size, codec, codec_config, last_verified_at
            ) VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (sha256) DO UPDATE SET last_verified_at = CURRENT_TIMESTAMP
            """,
            (
                blob.sha256,
                blob.logical_size,
                blob.physical_size,
                blob.codec,
                Jsonb(blob.codec_config),
            ),
        )
        cursor.execute(
            """
            INSERT INTO task_extractions (
                extraction_id, source_sha256, extraction_kind, extractor,
                extractor_version, config_sha256, status, text_content,
                page_count, extraction_error
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (
                source_sha256, extraction_kind, extractor, extractor_version, config_sha256
            ) DO NOTHING
            """,
            (
                uuid4(),
                blob.sha256,
                extraction.extraction_kind,
                extraction.extractor,
                extraction.extractor_version,
                extraction.config_sha256,
                extraction.status,
                extraction.text,
                extraction.page_count,
                extraction.error,
            ),
        )
        cursor.execute(
            """
            SELECT extraction_id, status, text_content, extractor,
                   extractor_version, extraction_error, page_count
            FROM task_extractions
            WHERE source_sha256 = %s AND extraction_kind = %s
              AND extractor = %s AND extractor_version = %s AND config_sha256 = %s
            """,
            (
                blob.sha256,
                extraction.extraction_kind,
                extraction.extractor,
                extraction.extractor_version,
                extraction.config_sha256,
            ),
        )
        extraction_row = cursor.fetchone()
        if extraction_row is None:
            raise RuntimeError("task extraction cache row was not created")
        stored_extraction = _extraction_from_row(extraction_row)
        cursor.execute(
            """
            INSERT INTO tasks (
                task_id, project_id, title, source_type, intake_status,
                original_blob_sha256, original_filename, media_type, logical_size,
                extraction_id, extraction_method, extraction_version,
                extraction_error, page_count
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                task_id,
                project_id,
                title,
                source.source_type,
                stored_extraction.status,
                blob.sha256,
                source.original_filename,
                source.media_type,
                blob.logical_size,
                stored_extraction.extraction_id,
                stored_extraction.extractor,
                stored_extraction.extractor_version,
                stored_extraction.error,
                stored_extraction.page_count,
            ),
        )
        cursor.execute(
            f"""
            SELECT {_TASK_COLUMNS}
            FROM tasks AS t
            JOIN cas_blobs AS c ON c.sha256 = t.original_blob_sha256
            JOIN task_extractions AS e ON e.extraction_id = t.extraction_id
            WHERE t.task_id = %s
            """,
            (task_id,),
        )
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError("task creation returned no record")
    return _task_from_row(row)


def list_tasks(settings: Settings, project_id: UUID, limit: int = 100) -> list[TaskResponse]:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT {_TASK_COLUMNS}
            FROM tasks AS t
            JOIN cas_blobs AS c ON c.sha256 = t.original_blob_sha256
            JOIN task_extractions AS e ON e.extraction_id = t.extraction_id
            WHERE t.project_id = %s
            ORDER BY t.created_at DESC, t.task_id DESC
            LIMIT %s
            """,
            (project_id, limit),
        )
        return [_task_from_row(row) for row in cursor.fetchall()]


def get_task(settings: Settings, project_id: UUID, task_id: UUID) -> TaskResponse:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT {_TASK_COLUMNS}
            FROM tasks AS t
            JOIN cas_blobs AS c ON c.sha256 = t.original_blob_sha256
            JOIN task_extractions AS e ON e.extraction_id = t.extraction_id
            WHERE t.project_id = %s AND t.task_id = %s
            """,
            (project_id, task_id),
        )
        row = cursor.fetchone()
    if row is None:
        raise TaskNotFoundError("task not found")
    return _task_from_row(row)


def get_task_text(settings: Settings, project_id: UUID, task_id: UUID) -> TaskTextResponse:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT t.task_id, t.project_id, t.extraction_method,
                   t.extraction_version, t.page_count, e.status,
                   e.text_content, e.extraction_error
            FROM tasks AS t
            JOIN task_extractions AS e ON e.extraction_id = t.extraction_id
            WHERE t.project_id = %s AND t.task_id = %s
            """,
            (project_id, task_id),
        )
        row = cursor.fetchone()
    if row is None:
        raise TaskNotFoundError("task not found")
    if row[5] != "READY" or row[6] is None:
        raise ExtractionNotReadyError(row[7] or "extracted text is not available")
    return TaskTextResponse(
        task_id=row[0],
        project_id=row[1],
        text=row[6],
        extraction_method=row[2],
        extraction_version=row[3],
        page_count=row[4],
    )


def storage_stats(settings: Settings) -> StorageResponse:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*), COALESCE(sum(logical_size), 0)
            FROM tasks
            """
        )
        task_count, referenced_logical = cursor.fetchone() or (0, 0)
        cursor.execute(
            """
            SELECT count(c.sha256), COALESCE(sum(c.logical_size), 0),
                   COALESCE(sum(c.physical_size), 0)
            FROM cas_blobs AS c
            WHERE EXISTS (
                SELECT 1 FROM tasks AS t WHERE t.original_blob_sha256 = c.sha256
            )
            """
        )
        unique_count, unique_logical, physical = cursor.fetchone() or (0, 0, 0)
    dedup_delta = int(referenced_logical) - int(unique_logical)
    compression_delta = int(unique_logical) - int(physical)
    ratio = (int(physical) / int(unique_logical)) if unique_logical else None
    return StorageResponse(
        task_count=int(task_count),
        referenced_logical_bytes=int(referenced_logical),
        unique_logical_bytes=int(unique_logical),
        physical_cas_bytes=int(physical),
        unique_blob_count=int(unique_count),
        deduplication_delta_bytes=dedup_delta,
        compression_delta_bytes=compression_delta,
        compression_ratio=ratio,
        compression_savings_bytes=max(compression_delta, 0) if unique_logical else None,
        compression_delta_label=(
            "savings"
            if compression_delta > 0
            else "overhead"
            if compression_delta < 0
            else "neutral"
        ),
    )


def task_blob(
    settings: Settings, project_id: UUID, task_id: UUID
) -> tuple[TaskResponse, StoredBlob]:
    task = get_task(settings, project_id, task_id)
    store = CASStore(settings)
    path = store.blob_path(task.original_blob_sha256)
    return task, StoredBlob(
        sha256=task.original_blob_sha256,
        logical_size=task.logical_size,
        physical_size=task.compressed_size,
        codec="zstd",
        codec_config=store.codec_config,
        path=path,
    )
