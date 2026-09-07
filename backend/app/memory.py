from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .config import Settings
from .db import database_connection

MAX_CONTENT_BYTES = 64 * 1024
MAX_TAGS = 32
MAX_TAG_BYTES = 128
SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40,64}$")
SECRET_PATTERN = re.compile(
    r"(?i)(?:api[_ -]?key|access[_ -]?token|authorization\s*[:=]|password\s*[:=]|"
    r"secret\s*[:=]|bearer\s+[A-Za-z0-9._-]{12,})"
)


class MemoryType(StrEnum):
    WORKING = "WORKING"
    SESSION = "SESSION"
    PROJECT = "PROJECT"
    SEMANTIC = "SEMANTIC"
    EPISODIC = "EPISODIC"
    DECISION = "DECISION"
    FAILURE = "FAILURE"
    PROCEDURAL = "PROCEDURAL"


class MemoryStatus(StrEnum):
    OBSERVATION = "OBSERVATION"
    INFERRED = "INFERRED"
    PROPOSED = "PROPOSED"
    CONFIRMED = "CONFIRMED"
    CANONICAL = "CANONICAL"
    DEPRECATED = "DEPRECATED"


class MemoryOrigin(StrEnum):
    USER = "USER"
    SYSTEM = "SYSTEM"
    MODEL = "MODEL"
    EXECUTOR = "EXECUTOR"
    RETRIEVAL = "RETRIEVAL"
    IMPORT = "IMPORT"


class PromotionBasisKind(StrEnum):
    TRUSTED_SOURCE = "TRUSTED_SOURCE"
    VALIDATED_EVIDENCE = "VALIDATED_EVIDENCE"
    APPROVED_ADR = "APPROVED_ADR"


class MemoryError(ValueError):
    pass


class MemoryNotFoundError(MemoryError):
    pass


class MemoryProjectNotFoundError(MemoryError):
    pass


class MemoryProjectConflictError(MemoryError):
    pass


class PromotionBasis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: PromotionBasisKind
    reference: str = Field(min_length=1, max_length=256)
    project_id: UUID | None = None

    @field_validator("reference")
    @classmethod
    def non_blank_reference(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("promotion reference must not be blank")
        return value


class MemoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: MemoryType
    content: str = Field(min_length=1, max_length=MAX_CONTENT_BYTES)
    source: str = Field(min_length=1, max_length=256)
    source_version: str | None = Field(default=None, max_length=128)
    source_commit: str | None = Field(default=None, max_length=64)
    confidence: float | None = Field(default=None, ge=0, le=1)
    importance: int = Field(default=0, ge=0, le=100)
    authority: str = Field(min_length=1, max_length=128)
    tags: list[str] = Field(default_factory=list, max_length=MAX_TAGS)
    status: MemoryStatus = MemoryStatus.PROPOSED
    origin: MemoryOrigin = MemoryOrigin.USER

    @field_validator("content", "source", "authority", "source_version", "source_commit")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("source_commit")
    @classmethod
    def valid_source_commit(cls, value: str | None) -> str | None:
        if value is not None and SHA_PATTERN.fullmatch(value) is None:
            raise ValueError("source_commit must be a 40-64 character hexadecimal SHA")
        return value.lower() if value else value

    @field_validator("tags")
    @classmethod
    def bounded_tags(cls, value: list[str]) -> list[str]:
        normalized = [tag.strip() for tag in value]
        if any(not tag for tag in normalized):
            raise ValueError("tags must not contain blank values")
        if any(len(tag.encode("utf-8")) > MAX_TAG_BYTES for tag in normalized):
            raise ValueError("tag exceeds the configured size limit")
        return normalized

    @model_validator(mode="after")
    def reject_direct_canonical(self) -> MemoryCreateRequest:
        if self.status is MemoryStatus.CANONICAL:
            raise ValueError("CANONICAL status requires the qualified promotion endpoint")
        if self.status is MemoryStatus.DEPRECATED:
            raise ValueError("DEPRECATED status requires a lifecycle transition")
        if SECRET_PATTERN.search(self.content) or SECRET_PATTERN.search(self.source):
            raise ValueError("memory content must not contain credentials or secret material")
        return self


class MemoryTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: MemoryStatus

    @model_validator(mode="after")
    def reject_canonical_transition(self) -> MemoryTransitionRequest:
        if self.status is MemoryStatus.CANONICAL:
            raise ValueError("CANONICAL status requires the qualified promotion endpoint")
        return self


class MemorySupersedeRequest(MemoryCreateRequest):
    pass


class MemoryHistoryEntry(BaseModel):
    history_id: UUID
    memory_id: UUID
    project_id: UUID
    version: int
    type: MemoryType
    status: MemoryStatus
    content: str
    source: str
    source_version: str | None
    source_commit: str | None
    confidence: float | None
    importance: int
    authority: str
    tags: list[str]
    origin: MemoryOrigin
    promotion_basis: dict[str, Any] | None
    supersedes_memory_id: UUID | None
    changed_reason: str
    recorded_at: datetime


class MemoryResponse(BaseModel):
    memory_id: UUID
    project_id: UUID
    type: MemoryType
    status: MemoryStatus
    content: str
    source: str
    source_version: str | None
    source_commit: str | None
    confidence: float | None
    importance: int
    authority: str
    tags: list[str]
    origin: MemoryOrigin
    promotion_basis: dict[str, Any] | None
    supersedes_memory_id: UUID | None
    superseded_by_memory_id: UUID | None
    version: int
    created_at: datetime
    updated_at: datetime


class MemoryProvenanceResponse(BaseModel):
    memory: MemoryResponse
    history: list[MemoryHistoryEntry]


TRANSITIONS: dict[MemoryStatus, frozenset[MemoryStatus]] = {
    MemoryStatus.OBSERVATION: frozenset(
        {
            MemoryStatus.INFERRED,
            MemoryStatus.PROPOSED,
            MemoryStatus.CONFIRMED,
            MemoryStatus.DEPRECATED,
        }
    ),
    MemoryStatus.INFERRED: frozenset(
        {MemoryStatus.PROPOSED, MemoryStatus.CONFIRMED, MemoryStatus.DEPRECATED}
    ),
    MemoryStatus.PROPOSED: frozenset({MemoryStatus.CONFIRMED, MemoryStatus.DEPRECATED}),
    MemoryStatus.CONFIRMED: frozenset({MemoryStatus.DEPRECATED}),
    MemoryStatus.CANONICAL: frozenset({MemoryStatus.DEPRECATED}),
    MemoryStatus.DEPRECATED: frozenset(),
}


def validate_transition(current: MemoryStatus, target: MemoryStatus) -> None:
    if target not in TRANSITIONS[current]:
        raise MemoryError(f"invalid memory status transition {current} -> {target}")


def _scan_secret_values(request: MemoryCreateRequest) -> None:
    values = [request.content, request.source, request.source_version or "", request.authority]
    values.extend(request.tags)
    if any(SECRET_PATTERN.search(value) for value in values):
        raise MemoryError("memory content must not contain credentials or secret material")


def _project_guard(cursor: Any, project_id: UUID) -> None:
    cursor.execute("SELECT 1 FROM projects WHERE project_id = %s", (project_id,))
    if cursor.fetchone() is None:
        raise MemoryProjectNotFoundError("project not found")


def _row_with_superseded_by(cursor: Any, row: dict[str, Any]) -> dict[str, Any]:
    cursor.execute(
        """
        SELECT memory_id
        FROM memory_records
        WHERE project_id = %s AND supersedes_memory_id = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (row["project_id"], row["memory_id"]),
    )
    successor = cursor.fetchone()
    return {**row, "superseded_by_memory_id": successor["memory_id"] if successor else None}


def _insert_history(cursor: Any, row: dict[str, Any], reason: str) -> None:
    cursor.execute(
        """
        INSERT INTO memory_record_history (
            history_id, project_id, memory_id, version, memory_type, status, content,
            source, source_version, source_commit, confidence, importance, authority,
            tags, origin, promotion_basis, supersedes_memory_id, changed_reason
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            uuid4(),
            row["project_id"],
            row["memory_id"],
            row["version"],
            row["memory_type"],
            row["status"],
            row["content"],
            row["source"],
            row["source_version"],
            row["source_commit"],
            row["confidence"],
            row["importance"],
            row["authority"],
            Jsonb(row["tags"]),
            row["origin"],
            Jsonb(row["promotion_basis"]) if row["promotion_basis"] is not None else None,
            row["supersedes_memory_id"],
            reason,
        ),
    )


def _fetch_memory(
    cursor: Any, project_id: UUID, memory_id: UUID, *, lock: bool = False
) -> dict[str, Any]:
    cursor.execute(
        "SELECT * FROM memory_records WHERE project_id = %s AND memory_id = %s"
        + (" FOR UPDATE" if lock else ""),
        (project_id, memory_id),
    )
    row = cursor.fetchone()
    if row is None:
        raise MemoryNotFoundError("memory record not found")
    return cast(dict[str, Any], row)


def _response(cursor: Any, row: dict[str, Any]) -> MemoryResponse:
    return MemoryResponse.model_validate(
        _row_with_superseded_by(cursor, row) | {"type": row["memory_type"]}
    )


def create_memory(
    settings: Settings, project_id: UUID, request: MemoryCreateRequest
) -> MemoryResponse:
    _scan_secret_values(request)
    with (
        database_connection(settings) as connection,
        connection.cursor(row_factory=dict_row) as cursor,
    ):
        _project_guard(cursor, project_id)
        memory_id = uuid4()
        cursor.execute(
            """
            INSERT INTO memory_records (
                memory_id, project_id, memory_type, status, content, source, source_version,
                source_commit, confidence, importance, authority, tags, origin
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                memory_id,
                project_id,
                request.type.value,
                request.status.value,
                request.content,
                request.source,
                request.source_version,
                request.source_commit,
                request.confidence,
                request.importance,
                request.authority,
                Jsonb(request.tags),
                request.origin.value,
            ),
        )
        row = cursor.fetchone()
        assert row is not None
        _insert_history(cursor, row, "created")
        return _response(cursor, row)


def list_memories(
    settings: Settings, project_id: UUID, status: MemoryStatus | None, limit: int
) -> list[MemoryResponse]:
    with (
        database_connection(settings) as connection,
        connection.cursor(row_factory=dict_row) as cursor,
    ):
        _project_guard(cursor, project_id)
        if status is None:
            cursor.execute(
                "SELECT * FROM memory_records WHERE project_id = %s "
                "ORDER BY updated_at DESC LIMIT %s",
                (project_id, limit),
            )
        else:
            cursor.execute(
                "SELECT * FROM memory_records WHERE project_id = %s AND status = %s "
                "ORDER BY updated_at DESC LIMIT %s",
                (project_id, status.value, limit),
            )
        return [_response(cursor, row) for row in cursor.fetchall()]


def get_memory(settings: Settings, project_id: UUID, memory_id: UUID) -> MemoryResponse:
    with (
        database_connection(settings) as connection,
        connection.cursor(row_factory=dict_row) as cursor,
    ):
        return _response(cursor, _fetch_memory(cursor, project_id, memory_id))


def _update_status(
    cursor: Any, project_id: UUID, memory_id: UUID, target: MemoryStatus, reason: str
) -> dict[str, Any]:
    current = _fetch_memory(cursor, project_id, memory_id, lock=True)
    validate_transition(MemoryStatus(current["status"]), target)
    cursor.execute(
        "UPDATE memory_records SET status = %s, version = version + 1, updated_at = now() "
        "WHERE project_id = %s AND memory_id = %s RETURNING *",
        (target.value, project_id, memory_id),
    )
    row = cursor.fetchone()
    assert row is not None
    _insert_history(cursor, row, reason)
    return cast(dict[str, Any], row)


def transition_memory(
    settings: Settings, project_id: UUID, memory_id: UUID, request: MemoryTransitionRequest
) -> MemoryResponse:
    with (
        database_connection(settings) as connection,
        connection.cursor(row_factory=dict_row) as cursor,
    ):
        row = _update_status(cursor, project_id, memory_id, request.status, "status_transition")
        return _response(cursor, row)


def promote_memory(
    settings: Settings, project_id: UUID, memory_id: UUID, basis: PromotionBasis
) -> MemoryResponse:
    if basis.project_id is not None and basis.project_id != project_id:
        raise MemoryProjectConflictError("promotion basis belongs to another project")
    _scan_secret_values(
        MemoryCreateRequest(
            type=MemoryType.PROJECT,
            content=basis.reference,
            source="promotion-basis",
            authority="promotion",
        )
    )
    basis_payload = {
        "kind": basis.kind.value,
        "reference": basis.reference,
        "project_id": str(project_id),
    }
    with (
        database_connection(settings) as connection,
        connection.cursor(row_factory=dict_row) as cursor,
    ):
        current = _fetch_memory(cursor, project_id, memory_id, lock=True)
        if MemoryStatus(current["status"]) is not MemoryStatus.CONFIRMED:
            raise MemoryError("only CONFIRMED memory may be promoted to CANONICAL")
        cursor.execute(
            "UPDATE memory_records SET status = 'CANONICAL', promotion_basis = %s, "
            "version = version + 1, updated_at = now() WHERE project_id = %s AND memory_id = %s "
            "RETURNING *",
            (Jsonb(basis_payload), project_id, memory_id),
        )
        row = cursor.fetchone()
        assert row is not None
        _insert_history(cursor, row, "qualified_promotion")
        return _response(cursor, row)


def supersede_memory(
    settings: Settings, project_id: UUID, memory_id: UUID, request: MemorySupersedeRequest
) -> MemoryResponse:
    _scan_secret_values(request)
    with (
        database_connection(settings) as connection,
        connection.cursor(row_factory=dict_row) as cursor,
    ):
        old = _fetch_memory(cursor, project_id, memory_id, lock=True)
        if MemoryStatus(old["status"]) is MemoryStatus.DEPRECATED:
            raise MemoryError("deprecated memory cannot be superseded")
        new_id = uuid4()
        cursor.execute(
            """
            INSERT INTO memory_records (
                memory_id, project_id, memory_type, status, content, source, source_version,
                source_commit, confidence, importance, authority, tags, origin, supersedes_memory_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                new_id,
                project_id,
                request.type.value,
                request.status.value,
                request.content,
                request.source,
                request.source_version,
                request.source_commit,
                request.confidence,
                request.importance,
                request.authority,
                Jsonb(request.tags),
                request.origin.value,
                memory_id,
            ),
        )
        new_row = cursor.fetchone()
        assert new_row is not None
        _insert_history(cursor, new_row, "created_as_supersession")
        old_row = _update_status(
            cursor, project_id, memory_id, MemoryStatus.DEPRECATED, "superseded"
        )
        _ = old_row
        return _response(cursor, new_row)


def get_provenance(
    settings: Settings, project_id: UUID, memory_id: UUID
) -> MemoryProvenanceResponse:
    with (
        database_connection(settings) as connection,
        connection.cursor(row_factory=dict_row) as cursor,
    ):
        row = _fetch_memory(cursor, project_id, memory_id)
        cursor.execute(
            "SELECT * FROM memory_record_history WHERE project_id = %s AND memory_id = %s "
            "ORDER BY version ASC",
            (project_id, memory_id),
        )
        history = [
            MemoryHistoryEntry.model_validate({**item, "type": item["memory_type"]})
            for item in cursor.fetchall()
        ]
        return MemoryProvenanceResponse(memory=_response(cursor, row), history=history)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, MemoryNotFoundError | MemoryProjectNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, MemoryProjectConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, MemoryError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, psycopg.Error):
        return HTTPException(status_code=503, detail="memory database unavailable")
    return HTTPException(status_code=500, detail="memory operation failed")


router = APIRouter(tags=["memory"])


def _settings() -> Settings:
    from .config import get_settings

    return get_settings()


@router.post(
    "/api/v1/projects/{project_id}/memories", response_model=MemoryResponse, status_code=201
)
def create_memory_endpoint(project_id: UUID, request: MemoryCreateRequest) -> MemoryResponse:
    try:
        return create_memory(_settings(), project_id, request)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/api/v1/projects/{project_id}/memories", response_model=list[MemoryResponse])
def list_memory_endpoint(
    project_id: UUID,
    status: MemoryStatus | None = None,
    limit: int = Query(default=100, ge=1, le=200),
) -> list[MemoryResponse]:
    try:
        return list_memories(_settings(), project_id, status, limit)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/api/v1/projects/{project_id}/memories/{memory_id}", response_model=MemoryResponse)
def get_memory_endpoint(project_id: UUID, memory_id: UUID) -> MemoryResponse:
    try:
        return get_memory(_settings(), project_id, memory_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post(
    "/api/v1/projects/{project_id}/memories/{memory_id}/transition",
    response_model=MemoryResponse,
)
def transition_memory_endpoint(
    project_id: UUID, memory_id: UUID, request: MemoryTransitionRequest
) -> MemoryResponse:
    try:
        return transition_memory(_settings(), project_id, memory_id, request)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post(
    "/api/v1/projects/{project_id}/memories/{memory_id}/promote",
    response_model=MemoryResponse,
)
def promote_memory_endpoint(
    project_id: UUID, memory_id: UUID, basis: PromotionBasis
) -> MemoryResponse:
    try:
        return promote_memory(_settings(), project_id, memory_id, basis)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post(
    "/api/v1/projects/{project_id}/memories/{memory_id}/supersede",
    response_model=MemoryResponse,
    status_code=201,
)
def supersede_memory_endpoint(
    project_id: UUID, memory_id: UUID, request: MemorySupersedeRequest
) -> MemoryResponse:
    try:
        return supersede_memory(_settings(), project_id, memory_id, request)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get(
    "/api/v1/projects/{project_id}/memories/{memory_id}/provenance",
    response_model=MemoryProvenanceResponse,
)
def provenance_endpoint(project_id: UUID, memory_id: UUID) -> MemoryProvenanceResponse:
    try:
        return get_provenance(_settings(), project_id, memory_id)
    except Exception as exc:
        raise _http_error(exc) from exc
