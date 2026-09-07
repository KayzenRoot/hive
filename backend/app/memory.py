from __future__ import annotations

import hashlib
import re
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .config import Settings
from .db import database_connection
from .registry import ProjectPathError, normalize_project_path
from .repository_indexer import (
    RepositoryIndexingError,
    _git_head,
    _git_inventory_fingerprint,
    _read_stable_file,
    _resolve_tracked_path,
)
from .repository_indexer import (
    _run_git as _run_repository_git,
)

MAX_CONTENT_BYTES = 64 * 1024
MAX_TAGS = 32
MAX_TAG_BYTES = 128
SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40,64}$")
SECRET_PATTERN = re.compile(
    r"(?i)(?:api[_ -]?key|access[_ -]?token|authorization\s*[:=]|password\s*[:=]|"
    r"secret\s*[:=]|bearer\s+[A-Za-z0-9._-]{12,})"
)
DECISIONS_LEDGER_PATH = "docs/project-brain/16-DECISIONS-LEDGER.md"
DECISION_ID_PATTERN = r"[A-Za-z][A-Za-z0-9]*(?:[-_.][A-Za-z0-9]+){0,15}"
APPROVED_DECISION_REFERENCE_PATTERN = re.compile(
    rf"^(?:{re.escape(DECISIONS_LEDGER_PATH)}#)?({DECISION_ID_PATTERN})$"
)
DECISION_HEADING_PATTERN = re.compile(
    rf"(?m)^##[ \t]+(?P<decision_id>{DECISION_ID_PATTERN})"
    rf"(?:[ \t]+(?:—|-[ \t])[^\r\n]*)?[ \t]*\r?$"
)
DECISION_STATUS_PATTERN = re.compile(
    r"(?im)^[ \t]*\*{0,2}Status\*{0,2}:\*{0,2}[ \t]*"
    r"(?P<status>Accepted|Approved)\b"
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


def _project_source_root(
    cursor: Any, settings: Settings, project_id: UUID
) -> tuple[str, str | None, Path]:
    cursor.execute(
        "SELECT relative_path, git_head_sha FROM projects WHERE project_id = %s",
        (project_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise MemoryProjectNotFoundError("project not found")
    try:
        identity, project_path = normalize_project_path(row["relative_path"], settings)
    except ProjectPathError as exc:
        raise MemoryError("project source path is not safely resolvable") from exc
    return identity, row["git_head_sha"], project_path


def _normalized_source_reference(reference: str) -> str:
    value = reference.strip()
    if (
        not value
        or "\x00" in value
        or "\\" in value
        or value.startswith("/")
        or re.match(r"^[A-Za-z]:", value)
    ):
        raise MemoryError("trusted source reference must be a safe project-relative path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise MemoryError("trusted source reference contains an unsafe path component")
    return "/".join(parts)


def _decode_git_sha(value: bytes, message: str) -> str:
    try:
        decoded = value.decode("ascii").strip().lower()
    except UnicodeDecodeError as exc:
        raise MemoryError(message) from exc
    if re.fullmatch(r"[0-9a-f]{40}", decoded) is None:
        raise MemoryError(message)
    return decoded


def _git_blob_sha(source: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(source)).encode("ascii") + b"\0" + source,
        usedforsecurity=False,
    ).hexdigest()


def _resolve_trusted_source(
    cursor: Any, settings: Settings, project_id: UUID, reference: str
) -> tuple[dict[str, Any], bytes]:
    project_identity, expected_head, project_path = _project_source_root(
        cursor, settings, project_id
    )
    normalized = _normalized_source_reference(reference)
    try:
        candidate = _resolve_tracked_path(project_path, normalized)
    except ProjectPathError as exc:
        raise MemoryError("trusted source is not safely contained by the project") from exc
    if not expected_head or SHA_PATTERN.fullmatch(expected_head) is None:
        raise MemoryError("registered project HEAD is unavailable for trusted source")
    try:
        inventory_before = _git_inventory_fingerprint(project_path)
        head = _git_head(project_path)
        if expected_head.lower() != head:
            raise MemoryError("registered project HEAD is stale for the trusted source")
        tracked = _run_repository_git(
            project_path,
            ["ls-files", "--error-unmatch", "--", normalized],
            allow_nonzero=True,
        )
        try:
            tracked_path = tracked.stdout.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise MemoryError("trusted source path identity is invalid") from exc
        if tracked.returncode != 0 or tracked_path != normalized:
            raise MemoryError("trusted source is not a tracked project file")
        dirty = _run_repository_git(
            project_path,
            ["diff", "--quiet", head, "--", normalized],
            allow_nonzero=True,
        )
        if dirty.returncode != 0:
            raise MemoryError("trusted source has uncommitted changes")
        filesystem_before, stamp_before = _read_stable_file(candidate, settings)
        blob_result = _run_repository_git(
            project_path,
            ["rev-parse", "--verify", f"{head}:{normalized}"],
            allow_nonzero=True,
        )
        if blob_result.returncode != 0:
            raise MemoryError("trusted source is not present in the verified Git HEAD")
        blob = _decode_git_sha(blob_result.stdout, "trusted source Git blob identity is invalid")
        object_type = _run_repository_git(
            project_path, ["cat-file", "-t", blob], allow_nonzero=True
        )
        if object_type.returncode != 0 or object_type.stdout.strip() != b"blob":
            raise MemoryError("trusted source Git object is not a blob")
        immutable_source = _run_repository_git(project_path, ["cat-file", "blob", blob]).stdout
        if len(immutable_source) > settings.repository_max_file_bytes:
            raise MemoryError("trusted source exceeds the repository file size limit")
        if _git_blob_sha(immutable_source) != blob:
            raise MemoryError("trusted source bytes do not match the recorded Git blob")
        if filesystem_before != immutable_source:
            raise MemoryError("trusted source changed before immutable qualification")
        filesystem_after, stamp_after = _read_stable_file(candidate, settings)
        inventory_after = _git_inventory_fingerprint(project_path)
        head_after = _git_head(project_path)
        if (
            stamp_before != stamp_after
            or filesystem_after != immutable_source
            or inventory_before != inventory_after
            or head_after != head
        ):
            raise MemoryError("trusted source mutated during qualification")
        content_sha256 = hashlib.sha256(immutable_source).hexdigest()
    except (OSError, RepositoryIndexingError, RuntimeError, TimeoutError) as exc:
        raise MemoryError("trusted source could not be verified deterministically") from exc
    return (
        {
            "resolver": "trusted-project-source-v1",
            "project_relative_path": project_identity,
            "reference": normalized,
            "source_commit": head,
            "git_blob_sha": blob,
            "source_sha256": content_sha256,
            "byte_binding": "immutable-git-blob-v1",
        },
        immutable_source,
    )


def _approved_adr_id(reference: str) -> str:
    match = APPROVED_DECISION_REFERENCE_PATTERN.fullmatch(reference.strip())
    if match is None:
        raise MemoryError("approved decision reference has an unsupported or ambiguous identifier")
    return match.group(1)


def _approved_decision_status(source: bytes, decision_id: str) -> str:
    try:
        ledger = source.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MemoryError("canonical decisions ledger is not valid UTF-8") from exc
    headings = list(DECISION_HEADING_PATTERN.finditer(ledger))
    matches = [heading for heading in headings if heading.group("decision_id") == decision_id]
    if len(matches) != 1:
        raise MemoryError("approved decision is missing or ambiguous in the decisions ledger")
    heading = matches[0]
    next_heading = next(
        (candidate for candidate in headings if candidate.start() > heading.start()),
        None,
    )
    section = ledger[heading.end() : next_heading.start() if next_heading else None]
    status_match = DECISION_STATUS_PATTERN.search(section)
    if status_match is None:
        raise MemoryError("approved decision does not have Status: Accepted or Status: Approved")
    return status_match.group("status").capitalize()


def _resolve_promotion_basis(
    cursor: Any, settings: Settings, project_id: UUID, basis: PromotionBasis
) -> dict[str, Any]:
    if basis.project_id is not None and basis.project_id != project_id:
        raise MemoryProjectConflictError("promotion basis belongs to another project")
    if SECRET_PATTERN.search(basis.reference):
        raise MemoryError("promotion basis must not contain credentials or secret material")
    if basis.kind is PromotionBasisKind.VALIDATED_EVIDENCE:
        raise MemoryError(
            "VALIDATED_EVIDENCE promotion is unsupported until a trusted deterministic seam exists"
        )
    if basis.kind is PromotionBasisKind.TRUSTED_SOURCE:
        verified, _ = _resolve_trusted_source(cursor, settings, project_id, basis.reference)
        return {
            "kind": basis.kind.value,
            "reference": verified["reference"],
            "project_id": str(project_id),
            "verified": verified,
        }
    decision_id = _approved_adr_id(basis.reference)
    verified_source, immutable_source = _resolve_trusted_source(
        cursor, settings, project_id, DECISIONS_LEDGER_PATH
    )
    decision_status = _approved_decision_status(immutable_source, decision_id)
    return {
        "kind": basis.kind.value,
        "reference": decision_id,
        "project_id": str(project_id),
        "verified": {
            "resolver": "accepted-decisions-ledger-adr-v1",
            "decision_id": decision_id,
            "status": decision_status,
            "decisions_source": verified_source,
        },
    }


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
    with (
        database_connection(settings) as connection,
        connection.cursor(row_factory=dict_row) as cursor,
    ):
        current = _fetch_memory(cursor, project_id, memory_id, lock=True)
        if MemoryStatus(current["status"]) is not MemoryStatus.CONFIRMED:
            raise MemoryError("only CONFIRMED memory may be promoted to CANONICAL")
        basis_payload = _resolve_promotion_basis(cursor, settings, project_id, basis)
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
