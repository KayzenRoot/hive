from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import psycopg
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
    for key in (
        "/secret.txt",
        r"C:\Users\csn19\secret.txt",
        r"\\server\share\secret.txt",
        "api_key",
        "api%5Fkey",
    ):
        with pytest.raises(telemetry.TelemetryValidationError):
            telemetry.sanitize_payload({key: "safe"})
    for value in (
        "/",
        "/secret.txt",
        "/secret.txt/",
        "message before /secret.txt",
        "message before /safe+name.txt",
        "message before /safe%20name.txt",
        "message before C:\\Users\\csn19\\secret.txt",
        r"message before \\server\share\secret.txt",
        "message before /home/csn19/secret.txt",
        "message Authorization: Bearer abc.def.ghi",
        "message api_key=embedded-secret",
        "message client_secret=embedded-secret",
        "message password: embedded-secret",
        "message token=embedded-secret",
        "message secret=embedded-secret",
        "message " + "AK" + "IA1234567890ABCDEF",
        "message WO018_TEST_SECRET_DO_NOT_LEAK_integration",
        "message Bearer x",
        "message https://user:pass@example.com/path",
        "message https://user%3Apass%40example.com/path",
        "message postgres://user:pass@host/db",
        "message redis://:secret@redis:6379/0",
        "%252Fsecret.txt",
        "message %252Fhome%252Fuser%252Fsecret.txt",
    ):
        with pytest.raises(telemetry.TelemetryValidationError):
            telemetry.sanitize_payload({"message": value})
    for value in (
        "https://example.com/path",
        "ordinary prose with a slash / between words",
    ):
        assert telemetry.sanitize_payload({"message": value}) == {"message": value}
    for value in (
        "https://example.com/path?api_key=embedded-secret",
        "https://example.com/path#client_secret=embedded-secret",
        "https://example.com/path?api%5Fkey=embedded-secret",
        "https://example.com/path?api%5Fkey%3Dembedded-secret",
        "Authorization/Bearer",
    ):
        with pytest.raises(telemetry.TelemetryValidationError):
            telemetry.sanitize_payload({"message": value})
    assert telemetry.sanitize_payload(
        {"path": "src/module.py", "message": "ordinary prose remains safe"}
    ) == {"path": "src/module.py", "message": "ordinary prose remains safe"}
    for key in (
        "OPENAI_API_KEY",
        "openai_api_key",
        "GITHUB_TOKEN",
        "AUTH_TOKEN",
        "ID_TOKEN",
        "SESSION_TOKEN",
        "AWS_SECRET_ACCESS_KEY",
        "SECRET_KEY",
        "PRIVATE_KEY",
        "CLIENT_SECRET",
        "ACCESS_TOKEN",
        "REFRESH_TOKEN",
        "PASSWORD",
        "AUTHORIZATION",
        "OPENAI%5FAPI%5FKEY",
    ):
        with pytest.raises(telemetry.TelemetryValidationError):
            telemetry.sanitize_payload({key: "safe"})
    for key in ("DATABASE_PASSWORD", "MY_API_KEY", "HIVE_OPENAI_API_KEY"):
        with pytest.raises(telemetry.TelemetryValidationError):
            telemetry.sanitize_payload({key: "safe"})
    for value in (
        "OPENAI_API_KEY=embedded-secret",
        "GITHUB_TOKEN: embedded-secret",
        "AUTH_TOKEN%3Dembedded-secret",
        "MY_API_KEY=foo",
        "database_password=foo",
        "AWS_ACCESS_TOKEN=foo",
        "HIVE_CLIENT_SECRET=foo",
        "MY_REFRESH_TOKEN=foo",
        "APP_AUTH_TOKEN=foo",
        "prefix MY_API_KEY%3Dfoo suffix",
        "file:///home/user/secret.txt",
        "file:///secret.txt",
        "file:/etc/passwd",
        "embedded file:///home/user/secret.txt",
        "/n",
        "prefix /n suffix",
        "/segredo-ç.txt",
        "/home/usuário/segredo.txt",
        "/🔒/secret.txt",
        "prefix /segredo-ç.txt suffix",
        "prefix /home/usuário/segredo.txt suffix",
    ):
        with pytest.raises(telemetry.TelemetryValidationError):
            telemetry.sanitize_payload({"message": value})
    with pytest.raises(telemetry.TelemetryValidationError):
        telemetry.sanitize_payload({"nested": {"message": "MY_API_KEY=foo"}})
    for metric_key, metric_value in (
        ("input_tokens", 12),
        ("output_tokens", 34),
        ("cached_tokens", 5),
        ("fresh_tokens", 6),
        ("token_count", 100),
        ("token_budget", 4096),
        ("token_savings", 128),
    ):
        assert telemetry.sanitize_payload({metric_key: metric_value}) == {metric_key: metric_value}
    assert telemetry.sanitize_payload(
        {"url": "https://example.com/documentação", "path": "src/module.py"}
    ) == {"url": "https://example.com/documentação", "path": "src/module.py"}
    with pytest.raises(telemetry.TelemetryValidationError):
        telemetry.sanitize_payload({"nested": {"GITHUB_TOKEN": "safe"}})
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

    with pytest.raises(telemetry.TelemetryValidationError, match="collision"):
        telemetry.emit_event(
            settings,
            PROJECT_ID,
            "run.completed",
            {"adapter": "fixture"},
            task_id=TASK_ID,
            run_id=RUN_ID,
            emission_key="same-emission",
        )

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


def test_immutable_content_comparison_preserves_nested_json_types() -> None:
    existing = envelope(
        payload={"nested": {"flag": True}, "items": [False, {"count": 1}]},
        provenance={"attempt": 1, "metadata": {"enabled": False}},
    )

    def same(payload: dict[str, object], provenance: dict[str, object]) -> bool:
        return telemetry._same_immutable_content(
            existing,
            existing.event_type,
            existing.task_id,
            existing.run_id,
            payload,
            provenance,
        )

    assert same(
        {"nested": {"flag": True}, "items": [False, {"count": 1}]},
        {"attempt": 1, "metadata": {"enabled": False}},
    )
    assert not same(
        {"nested": {"flag": 1}, "items": [False, {"count": 1}]},
        {"attempt": 1, "metadata": {"enabled": False}},
    )
    assert not same(
        {"nested": {"flag": True}, "items": [0, {"count": 1}]},
        {"attempt": 1, "metadata": {"enabled": False}},
    )
    assert not same(
        {"nested": {"flag": True}, "items": [False, {"count": 1}]},
        {"attempt": 1, "metadata": {"enabled": 0}},
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


def test_stream_ends_without_fabricating_data_when_database_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(
        _settings: Settings, _project_id: UUID, *, after: str | None, limit: int
    ) -> telemetry.EventPage:
        del after, limit
        raise psycopg.Error("database unavailable")

    monkeypatch.setattr(telemetry, "list_events", unavailable)
    assert (
        list(telemetry.stream_events(Settings(), PROJECT_ID, max_events=1, timeout_seconds=1)) == []
    )


def test_event_page_is_project_scoped_by_query(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = FakeCursor()
    monkeypatch.setattr(telemetry, "database_connection", lambda _settings: FakeConnection(cursor))
    telemetry.list_events(Settings(), PROJECT_ID, limit=1)
    assert cursor.last_params is not None
    assert PROJECT_ID in cursor.last_params
