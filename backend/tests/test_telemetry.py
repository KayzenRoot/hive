from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app import telemetry
from app.config import Settings

PROJECT_ID = UUID("00000000-0000-0000-0000-000000000901")
TASK_ID = UUID("00000000-0000-0000-0000-000000000902")
RUN_ID = UUID("00000000-0000-0000-0000-000000000903")


def envelope(**overrides: object) -> telemetry.EventEnvelope:
    data: dict[str, object] = {
        "event_id": uuid4(),
        "envelope_version": telemetry.EVENT_ENVELOPE_VERSION,
        "event_type": "executor.started",
        "project_id": PROJECT_ID,
        "task_id": TASK_ID,
        "run_id": RUN_ID,
        "ordering_id": 1,
        "occurred_at": datetime.now(UTC),
        "payload": {"adapter": "fixture"},
        "provenance": {"producer": "test", "deterministic": True},
        "cursor": "1",
    }
    data.update(overrides)
    return telemetry.EventEnvelope.model_validate(data)


class FakeCursor:
    def __init__(self) -> None:
        self.events: dict[str, tuple[object, ...]] = {}
        self.next_ordering = 1
        self.rows: list[tuple[object, ...]] = []
        self.last_params: tuple[object, ...] | None = None

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.last_params = params
        if query.startswith("SELECT 1 FROM tasks"):
            self.rows = [(1,)] if params[1] == TASK_ID else []
            return
        if query.startswith("INSERT INTO telemetry_events"):
            emission_key = str(params[-1])
            if emission_key in self.events:
                self.rows = []
                return
            ordering = self.next_ordering
            self.next_ordering += 1
            payload = getattr(params[6], "obj", params[6])
            provenance = getattr(params[7], "obj", params[7])
            row = (
                params[0],
                params[1],
                params[2],
                params[3],
                params[4],
                params[5],
                ordering,
                datetime.now(UTC),
                payload,
                provenance,
            )
            self.events[emission_key] = row
            self.rows = [row]
            return
        if "WHERE project_id = %s AND emission_key = %s" in query:
            self.rows = [self.events[str(params[1])]]
            return
        if "ORDER BY ordering_id ASC" in query:
            after_value = params[1] if len(params) > 2 else 0
            after = int(cast(str | int, after_value))
            limit = int(cast(str | int, params[-1]))
            rows = [row for row in self.events.values() if cast(int, row[6]) > after]
            self.rows = sorted(rows, key=lambda row: cast(int, row[6]))[:limit]
            return
        raise AssertionError(f"unexpected SQL: {query}")

    def fetchone(self) -> tuple[object, ...] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return self._cursor


def test_envelope_requires_version_and_canonical_event_type() -> None:
    with pytest.raises(ValidationError):
        envelope(envelope_version="telemetry-event-bus-v0")
    with pytest.raises(ValidationError):
        envelope(event_type="invented.event")


def test_payload_and_cursor_bounds_reject_secrets_paths_and_invalid_values() -> None:
    with pytest.raises(telemetry.TelemetryValidationError):
        telemetry.sanitize_payload({"password": "do-not-store"})
    with pytest.raises(telemetry.TelemetryValidationError):
        telemetry.sanitize_payload({"path": "C:\\Users\\csn19\\secret.txt"})
    with pytest.raises(telemetry.TelemetryValidationError):
        telemetry.sanitize_payload({"blob": "x" * telemetry.EVENT_PAYLOAD_MAX_BYTES})
    with pytest.raises(telemetry.TelemetryValidationError):
        telemetry.validate_cursor("not-a-cursor")
    with pytest.raises(telemetry.TelemetryValidationError):
        telemetry.validate_cursor("9" * (telemetry.EVENT_CURSOR_MAX_BYTES + 1))


def test_emit_event_enforces_task_project_and_suppresses_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = FakeCursor()
    monkeypatch.setattr(telemetry, "database_connection", lambda _settings: FakeConnection(cursor))
    settings = Settings()
    first = telemetry.emit_event(
        settings,
        PROJECT_ID,
        "executor.started",
        {"adapter": "fixture"},
        task_id=TASK_ID,
        run_id=RUN_ID,
        emission_key="same-emission",
    )
    second = telemetry.emit_event(
        settings,
        PROJECT_ID,
        "executor.started",
        {"adapter": "fixture"},
        task_id=TASK_ID,
        run_id=RUN_ID,
        emission_key="same-emission",
    )
    assert first.event_id == second.event_id
    assert first.ordering_id == second.ordering_id == 1
    assert len(cursor.events) == 1

    with pytest.raises(telemetry.TelemetryValidationError, match="does not belong"):
        telemetry.emit_event(
            settings,
            PROJECT_ID,
            "run.failed",
            {"status": "failed"},
            task_id=UUID("00000000-0000-0000-0000-000000000999"),
            run_id=RUN_ID,
            emission_key="foreign-task",
        )


def test_project_scoped_ordered_pagination_and_sse(monkeypatch: pytest.MonkeyPatch) -> None:
    events = [
        envelope(ordering_id=1, cursor="1"),
        envelope(ordering_id=2, cursor="2", event_type="run.completed"),
    ]
    calls: list[tuple[UUID, str | None, int]] = []

    def fake_list(
        _settings: Settings, project_id: UUID, *, after: str | None, limit: int
    ) -> telemetry.EventPage:
        calls.append((project_id, after, limit))
        selected = [event for event in events if after is None or event.ordering_id > int(after)]
        return telemetry.EventPage(
            events=selected[:limit],
            next_cursor=None,
            has_more=False,
            limit=limit,
        )

    monkeypatch.setattr(telemetry, "list_events", fake_list)
    page = telemetry.list_events  # keep the public seam referenced by the test
    assert callable(page)
    stream = "".join(
        telemetry.stream_events(Settings(), PROJECT_ID, after="1", max_events=1, timeout_seconds=1)
    )
    assert "id: 2" in stream
    assert "event: run.completed" in stream
    assert calls == [(PROJECT_ID, "1", 1)]


def test_event_page_is_project_scoped_by_query(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = FakeCursor()
    monkeypatch.setattr(telemetry, "database_connection", lambda _settings: FakeConnection(cursor))
    telemetry.list_events(Settings(), PROJECT_ID, limit=1)
    assert cursor.last_params is not None
    assert PROJECT_ID in cursor.last_params
