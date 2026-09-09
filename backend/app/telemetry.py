"""Project-scoped durable Telemetry/Event Bus primitives.

PostgreSQL is the canonical event store.  The module deliberately has no
provider, model, or Redis dependency: a reconnecting SSE client can rebuild
its view from the durable ordered history alone.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import Settings
from .db import database_connection
from .registry import get_project

EVENT_ENVELOPE_VERSION = "telemetry-event-bus-v1"
EVENT_PAYLOAD_MAX_BYTES = 64 * 1024
EVENT_CURSOR_MAX_BYTES = 128
EVENT_PAGE_MAX_SIZE = 100
EVENT_STREAM_MAX_EVENTS = 100
EVENT_STREAM_MAX_SECONDS = 30.0
EVENT_STREAM_POLL_SECONDS = 0.20
EVENT_STREAM_HEARTBEAT_SECONDS = 5.0

CANONICAL_EVENT_TYPES = (
    "project.discovered",
    "project.indexing",
    "task.ingested",
    "context.started",
    "context.retrieved",
    "context.built",
    "cache.hit",
    "cache.miss",
    "executor.started",
    "tool.called",
    "file.changed",
    "test.started",
    "test.finished",
    "validation.failed",
    "validation.passed",
    "memory.staged",
    "memory.promoted",
    "run.completed",
    "run.failed",
)

_CANONICAL_EVENT_SET = frozenset(CANONICAL_EVENT_TYPES)
_SECRET_KEY = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|refresh[_-]?token|authorization|password|secret)"
)
_SECRET_VALUE = re.compile(
    r"(?ix)(?:gh[pousr]_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]+|WO\d+_[A-Z0-9_-]*SECRET[A-Z0-9_-]*)"
)
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]|^\\\\")
_CURSOR = re.compile(r"^[1-9][0-9]*$")
_MAX_DEPTH = 6
_MAX_STRING_CHARS = 1_024
_MAX_COLLECTION_ITEMS = 100


class TelemetryValidationError(ValueError):
    """Input cannot be accepted into the canonical event stream."""


def _validate_safe_string(value: str, *, field_name: str) -> str:
    if not value or len(value) > _MAX_STRING_CHARS or any(ord(char) < 32 for char in value):
        raise TelemetryValidationError(f"{field_name} is outside its bound")
    if _SECRET_VALUE.search(value) or value.startswith("/") or _WINDOWS_ABSOLUTE.match(value):
        raise TelemetryValidationError(f"{field_name} contains forbidden secret or path data")
    return value


def _sanitize_value(value: object, *, depth: int = 0) -> object:
    if depth > _MAX_DEPTH:
        raise TelemetryValidationError("event payload nesting exceeds its bound")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if abs(value) > 2**53:
            raise TelemetryValidationError("event integer exceeds its bound")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TelemetryValidationError("event number must be finite")
        return value
    if isinstance(value, str):
        return _validate_safe_string(value, field_name="event value")
    if isinstance(value, Mapping):
        if len(value) > _MAX_COLLECTION_ITEMS:
            raise TelemetryValidationError("event object exceeds its item bound")
        sanitized: dict[str, object] = {}
        for raw_key, raw_value in value.items():
            if not isinstance(raw_key, str) or not raw_key or len(raw_key) > 128:
                raise TelemetryValidationError("event object key is outside its bound")
            if _SECRET_KEY.search(raw_key):
                raise TelemetryValidationError("event object contains a forbidden secret key")
            sanitized[raw_key] = _sanitize_value(raw_value, depth=depth + 1)
        return sanitized
    if isinstance(value, list | tuple):
        if len(value) > _MAX_COLLECTION_ITEMS:
            raise TelemetryValidationError("event list exceeds its item bound")
        return [_sanitize_value(item, depth=depth + 1) for item in value]
    raise TelemetryValidationError("event payload contains an unsupported value")


def sanitize_payload(value: Mapping[str, object]) -> dict[str, object]:
    sanitized = _sanitize_value(value)
    if not isinstance(sanitized, dict):
        raise TelemetryValidationError("event payload must be an object")
    encoded = json.dumps(sanitized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > EVENT_PAYLOAD_MAX_BYTES:
        raise TelemetryValidationError("event payload exceeds its byte bound")
    return cast(dict[str, object], sanitized)


def validate_cursor(value: str | None) -> int | None:
    if value is None:
        return None
    if len(value.encode("ascii", "ignore")) != len(value.encode("utf-8")):
        raise TelemetryValidationError("event cursor must be ASCII")
    if len(value.encode("utf-8")) > EVENT_CURSOR_MAX_BYTES or not _CURSOR.fullmatch(value):
        raise TelemetryValidationError("event cursor is invalid or exceeds its bound")
    return int(value)


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    envelope_version: str = Field(min_length=1, max_length=64)
    event_type: str = Field(min_length=1, max_length=64)
    project_id: UUID
    task_id: UUID | None = None
    run_id: UUID | None = None
    ordering_id: int = Field(gt=0)
    occurred_at: datetime
    payload: dict[str, object]
    provenance: dict[str, object]
    cursor: str

    @field_validator("envelope_version")
    @classmethod
    def require_version(cls, value: str) -> str:
        if value != EVENT_ENVELOPE_VERSION:
            raise ValueError("unsupported event envelope version")
        return value

    @field_validator("event_type")
    @classmethod
    def require_canonical_type(cls, value: str) -> str:
        if value not in _CANONICAL_EVENT_SET:
            raise ValueError("event type is not in the canonical vocabulary")
        return value

    @field_validator("payload", "provenance")
    @classmethod
    def require_sanitized_objects(cls, value: dict[str, object]) -> dict[str, object]:
        return sanitize_payload(value)

    @field_validator("occurred_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @field_validator("cursor")
    @classmethod
    def require_cursor(cls, value: str) -> str:
        validate_cursor(value)
        return value


class EventPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    events: list[EventEnvelope]
    next_cursor: str | None
    has_more: bool
    limit: int = Field(ge=1, le=EVENT_PAGE_MAX_SIZE)


def _event_from_row(row: tuple[Any, ...]) -> EventEnvelope:
    occurred_at = row[7]
    if not isinstance(occurred_at, datetime):
        raise RuntimeError("telemetry event timestamp is invalid")
    return EventEnvelope(
        event_id=row[0],
        envelope_version=row[1],
        event_type=row[2],
        project_id=row[3],
        task_id=row[4],
        run_id=row[5],
        ordering_id=row[6],
        occurred_at=occurred_at,
        payload=row[8],
        provenance=row[9],
        cursor=str(row[6]),
    )


_EVENT_COLUMNS = """
    event_id, envelope_version, event_type, project_id, task_id, run_id,
    ordering_id, occurred_at, payload, provenance
"""


def _fetch_by_emission_key(
    cursor: psycopg.Cursor[Any], project_id: UUID, emission_key: str
) -> EventEnvelope:
    cursor.execute(
        f"SELECT {_EVENT_COLUMNS} FROM telemetry_events "
        "WHERE project_id = %s AND emission_key = %s",
        (project_id, emission_key),
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("telemetry idempotency record disappeared")
    return _event_from_row(row)


def emit_event(
    settings: Settings,
    project_id: UUID,
    event_type: str,
    payload: Mapping[str, object],
    *,
    task_id: UUID | None = None,
    run_id: UUID | None = None,
    provenance: Mapping[str, object] | None = None,
    emission_key: str,
) -> EventEnvelope:
    if event_type not in _CANONICAL_EVENT_SET:
        raise TelemetryValidationError("event type is not in the canonical vocabulary")
    if not emission_key or len(emission_key) > 256 or any(ord(char) < 32 for char in emission_key):
        raise TelemetryValidationError("event emission key is outside its bound")
    clean_payload = sanitize_payload(payload)
    clean_provenance = sanitize_payload(provenance or {"producer": "hive", "deterministic": True})
    event_id = uuid4()
    with database_connection(settings) as connection, connection.cursor() as cursor:
        if task_id is not None:
            cursor.execute(
                "SELECT 1 FROM tasks WHERE project_id = %s AND task_id = %s",
                (project_id, task_id),
            )
            if cursor.fetchone() is None:
                raise TelemetryValidationError("task does not belong to project")
        cursor.execute(
            f"INSERT INTO telemetry_events "
            "(event_id, envelope_version, event_type, project_id, task_id, run_id, "
            "payload, provenance, emission_key) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (project_id, emission_key) DO NOTHING "
            f"RETURNING {_EVENT_COLUMNS}",
            (
                event_id,
                EVENT_ENVELOPE_VERSION,
                event_type,
                project_id,
                task_id,
                run_id,
                Jsonb(clean_payload),
                Jsonb(clean_provenance),
                emission_key,
            ),
        )
        row = cursor.fetchone()
        if row is None:
            return _fetch_by_emission_key(cursor, project_id, emission_key)
        return _event_from_row(row)


def list_events(
    settings: Settings,
    project_id: UUID,
    *,
    after: str | None = None,
    limit: int = EVENT_PAGE_MAX_SIZE,
) -> EventPage:
    if not 1 <= limit <= EVENT_PAGE_MAX_SIZE:
        raise TelemetryValidationError("event page size is outside its bound")
    after_id = validate_cursor(after)
    with database_connection(settings) as connection, connection.cursor() as cursor:
        if after_id is None:
            cursor.execute(
                f"SELECT {_EVENT_COLUMNS} FROM telemetry_events "
                "WHERE project_id = %s ORDER BY ordering_id ASC, event_id ASC LIMIT %s",
                (project_id, limit + 1),
            )
        else:
            cursor.execute(
                f"SELECT {_EVENT_COLUMNS} FROM telemetry_events "
                "WHERE project_id = %s AND ordering_id > %s "
                "ORDER BY ordering_id ASC, event_id ASC LIMIT %s",
                (project_id, after_id, limit + 1),
            )
        rows = cursor.fetchall()
    has_more = len(rows) > limit
    envelopes = [_event_from_row(row) for row in rows[:limit]]
    return EventPage(
        events=envelopes,
        next_cursor=envelopes[-1].cursor if has_more and envelopes else None,
        has_more=has_more,
        limit=limit,
    )


def _sse_event(event: EventEnvelope) -> str:
    payload = event.model_dump(mode="json")
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"id: {event.cursor}\nevent: {event.event_type}\ndata: {serialized}\n\n"


def stream_events(
    settings: Settings,
    project_id: UUID,
    *,
    after: str | None = None,
    max_events: int = EVENT_STREAM_MAX_EVENTS,
    timeout_seconds: float = EVENT_STREAM_MAX_SECONDS,
) -> Iterator[str]:
    if not 1 <= max_events <= EVENT_STREAM_MAX_EVENTS:
        raise TelemetryValidationError("event stream batch is outside its bound")
    if not 0 < timeout_seconds <= EVENT_STREAM_MAX_SECONDS:
        raise TelemetryValidationError("event stream timeout is outside its bound")
    validate_cursor(after)
    cursor = after
    deadline = time.monotonic() + timeout_seconds
    last_heartbeat = time.monotonic()
    sent = 0
    while sent < max_events and time.monotonic() < deadline:
        page = list_events(
            settings,
            project_id,
            after=cursor,
            limit=min(EVENT_PAGE_MAX_SIZE, max_events - sent),
        )
        if page.events:
            for event in page.events:
                yield _sse_event(event)
                cursor = event.cursor
                sent += 1
            continue
        now = time.monotonic()
        if now - last_heartbeat >= EVENT_STREAM_HEARTBEAT_SECONDS:
            yield ": heartbeat\n\n"
            last_heartbeat = now
        time.sleep(min(EVENT_STREAM_POLL_SECONDS, max(0.0, deadline - now)))


router = APIRouter(tags=["telemetry"])


def _project_exists(settings: Settings, project_id: UUID) -> bool:
    return get_project(settings, project_id) is not None


@router.get("/api/v1/projects/{project_id}/events", response_model=EventPage)
def get_project_events(
    project_id: UUID,
    after: str | None = Query(default=None, max_length=EVENT_CURSOR_MAX_BYTES),
    limit: int = Query(default=EVENT_PAGE_MAX_SIZE, ge=1, le=EVENT_PAGE_MAX_SIZE),
) -> EventPage:
    try:
        settings = _router_settings()
        if not _project_exists(settings, project_id):
            raise HTTPException(status_code=404, detail="project not found")
        return list_events(settings, project_id, after=after, limit=limit)
    except TelemetryValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="telemetry database unavailable") from exc


@router.get("/api/v1/projects/{project_id}/events/stream")
def stream_project_events(
    project_id: UUID,
    after: str | None = Query(default=None, max_length=EVENT_CURSOR_MAX_BYTES),
    max_events: int = Query(default=EVENT_STREAM_MAX_EVENTS, ge=1, le=EVENT_STREAM_MAX_EVENTS),
    timeout_seconds: float = Query(
        default=EVENT_STREAM_MAX_SECONDS, gt=0, le=EVENT_STREAM_MAX_SECONDS
    ),
) -> StreamingResponse:
    try:
        settings = _router_settings()
        if not _project_exists(settings, project_id):
            raise HTTPException(status_code=404, detail="project not found")
        validate_cursor(after)
    except TelemetryValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="telemetry database unavailable") from exc
    return StreamingResponse(
        stream_events(
            settings,
            project_id,
            after=after,
            max_events=max_events,
            timeout_seconds=timeout_seconds,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _router_settings() -> Settings:
    from .config import get_settings

    return get_settings()


__all__ = [
    "CANONICAL_EVENT_TYPES",
    "EVENT_CURSOR_MAX_BYTES",
    "EVENT_ENVELOPE_VERSION",
    "EVENT_PAGE_MAX_SIZE",
    "EVENT_PAYLOAD_MAX_BYTES",
    "EventEnvelope",
    "EventPage",
    "TelemetryValidationError",
    "emit_event",
    "list_events",
    "router",
    "sanitize_payload",
    "stream_events",
    "validate_cursor",
]
