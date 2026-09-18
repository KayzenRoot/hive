"""Contract tests for the WO-020 control-center operational core.

Every surface is exercised through the public HTTP contract with deterministic
in-memory doubles for the durable stores, so the suite never needs a live
PostgreSQL or Redis instance, never fabricates a metric and asserts the
fail-closed boundaries (404, 422 and 503) explicitly.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import control_center, main
from app.config import Settings
from app.health import HealthResponse, ServiceCheck
from app.registry import ProjectResponse, ProjectState
from app.telemetry import (
    EVENT_ENVELOPE_VERSION,
    EVENT_PAGE_MAX_SIZE,
    EventEnvelope,
    EventPage,
    RunAggregate,
)

PROJECT_A = UUID("00000000-0000-0000-0000-0000000000a1")
PROJECT_B = UUID("00000000-0000-0000-0000-0000000000b1")
PROJECT_UNKNOWN = UUID("00000000-0000-0000-0000-0000000000ff")
RUN_ACTIVE = UUID("00000000-0000-0000-0000-000000000011")
RUN_COMPLETED = UUID("00000000-0000-0000-0000-000000000012")
RUN_FAILED = UUID("00000000-0000-0000-0000-000000000013")
RUN_OBSERVED = UUID("00000000-0000-0000-0000-000000000014")
RUN_UNKNOWN = UUID("00000000-0000-0000-0000-0000000000fe")
TASK_ID = UUID("00000000-0000-0000-0000-0000000000c1")
MIGRATION_HEAD = "0007_telemetry_events"
HEAD_SHA = "abcdef1234567890abcdef1234567890abcdef12"
NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


def project(
    project_id: UUID = PROJECT_A,
    *,
    name: str = "Alpha",
    relative_path: str = "alpha",
    state: ProjectState = ProjectState.READY,
    git_head_sha: str | None = HEAD_SHA,
    inspection_error: str | None = None,
    language_stack: list[str] | None = None,
) -> ProjectResponse:
    return ProjectResponse(
        project_id=project_id,
        name=name,
        relative_path=relative_path,
        git_branch="main",
        git_head_sha=git_head_sha,
        detached_head=False,
        repository_accessible=True,
        working_tree_clean=True,
        language_stack=["python"] if language_stack is None else language_stack,
        state=state,
        inspection_error=inspection_error,
        created_at=NOW - timedelta(days=1),
        updated_at=NOW,
        last_inspected_at=NOW,
    )


def event(
    event_type: str,
    *,
    project_id: UUID = PROJECT_A,
    run_id: UUID | None = RUN_ACTIVE,
    ordering_id: int = 1,
    occurred_at: datetime | None = None,
    payload: dict[str, object] | None = None,
    task_id: UUID | None = TASK_ID,
    event_id: UUID | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid4() if event_id is None else event_id,
        envelope_version=EVENT_ENVELOPE_VERSION,
        event_type=event_type,
        project_id=project_id,
        task_id=task_id,
        run_id=run_id,
        ordering_id=ordering_id,
        occurred_at=NOW if occurred_at is None else occurred_at,
        payload={"component": "fixture"} if payload is None else payload,
        provenance={"producer": "test", "deterministic": True},
        cursor=str(ordering_id),
    )


def aggregate(
    run_id: UUID,
    *,
    event_count: int = 3,
    first_occurred_at: datetime | None = None,
    last_occurred_at: datetime | None = None,
    last_event_type: str = "executor.started",
    executor_started: bool = True,
    terminal_event_type: str | None = None,
) -> RunAggregate:
    return RunAggregate(
        run_id=run_id,
        event_count=event_count,
        first_occurred_at=NOW - timedelta(minutes=5)
        if first_occurred_at is None
        else first_occurred_at,
        last_occurred_at=NOW if last_occurred_at is None else last_occurred_at,
        last_event_type=last_event_type,
        executor_started=executor_started,
        terminal_event_type=terminal_event_type,
    )


def page(
    events: list[EventEnvelope],
    *,
    has_more: bool = False,
    limit: int = control_center.CONTROL_CENTER_EVENT_LIMIT_DEFAULT,
) -> EventPage:
    return EventPage(
        events=events,
        next_cursor=events[-1].cursor if has_more and events else None,
        has_more=has_more,
        limit=limit,
    )


def health_report(
    *,
    status: str = "ok",
    checks: dict[str, ServiceCheck] | None = None,
) -> HealthResponse:
    if checks is None:
        checks = {
            "postgres": ServiceCheck(status="ok", details={"pgvector": True}),
            "redis": ServiceCheck(status="ok", details={"canonical": False}),
            "storage": ServiceCheck(
                status="ok",
                details={
                    "configured": True,
                    "writable": True,
                    "canonical_data_root": "/var/lib/hive",
                },
            ),
        }
    return HealthResponse(
        status=status,
        version="1.0.0",
        environment="test",
        timestamp=NOW,
        data_root="/var/lib/hive",
        checks=checks,
    )


def wire(
    monkeypatch: pytest.MonkeyPatch,
    *,
    projects: list[ProjectResponse] | None = None,
    aggregates: dict[UUID, list[RunAggregate]] | None = None,
    events: dict[UUID, list[EventEnvelope]] | None = None,
    timelines: dict[tuple[UUID, UUID], list[EventEnvelope]] | None = None,
    health: HealthResponse | None = None,
    migration_head: str | None = MIGRATION_HEAD,
    database_error: str | None = None,
) -> list[tuple[str, UUID, int]]:
    """Install deterministic doubles for the durable stores behind the router."""

    registry = {item.project_id: item for item in projects or []}
    run_aggregates = aggregates or {}
    recent_events = events or {}
    run_timelines = timelines or {}
    calls: list[tuple[str, UUID, int]] = []

    def list_projects_double(_settings: Settings) -> list[ProjectResponse]:
        calls.append(("list_projects", PROJECT_A, 0))
        if database_error is not None:
            raise psycopg.Error(database_error)
        return list(registry.values())

    def get_project_double(_settings: Settings, project_id: UUID) -> ProjectResponse | None:
        calls.append(("get_project", project_id, 0))
        if database_error is not None:
            raise psycopg.Error(database_error)
        return registry.get(project_id)

    def summarize_runs_double(
        _settings: Settings,
        project_id: UUID,
        *,
        run_id: UUID | None = None,
        limit: int = 100,
    ) -> list[RunAggregate]:
        calls.append(("summarize_runs", project_id, limit))
        if database_error is not None:
            raise psycopg.Error(database_error)
        selected = list(run_aggregates.get(project_id, []))
        if run_id is not None:
            selected = [item for item in selected if item.run_id == run_id]
        return selected[:limit]

    def list_recent_events_double(
        _settings: Settings,
        project_id: UUID,
        *,
        limit: int = 100,
    ) -> EventPage:
        calls.append(("list_recent_events", project_id, limit))
        if database_error is not None:
            raise psycopg.Error(database_error)
        ordered = list(recent_events.get(project_id, []))
        window = ordered if limit >= len(ordered) else ordered[-limit:]
        return page(window, has_more=len(ordered) > limit, limit=limit)

    def list_run_events_double(
        _settings: Settings,
        project_id: UUID,
        run_id: UUID,
        *,
        after: str | None = None,
        limit: int = 100,
    ) -> EventPage:
        calls.append(("list_run_events", project_id, limit))
        if database_error is not None:
            raise psycopg.Error(database_error)
        ordered = [
            item
            for item in run_timelines.get((project_id, run_id), [])
            if item.project_id == project_id and item.run_id == run_id
        ]
        if after is not None:
            ordered = [item for item in ordered if item.ordering_id > int(after)]
        return page(ordered[:limit], has_more=len(ordered) > limit, limit=limit)

    def collect_health_double(_settings: Settings) -> HealthResponse:
        return health_report() if health is None else health

    def observed_schema_revision_double(_settings: Settings) -> str:
        if migration_head is None:
            raise psycopg.Error("schema head unavailable")
        return migration_head

    monkeypatch.setattr(control_center, "get_settings", lambda: Settings())
    monkeypatch.setattr(control_center, "list_projects", list_projects_double)
    monkeypatch.setattr(control_center, "get_project", get_project_double)
    monkeypatch.setattr(control_center, "summarize_runs", summarize_runs_double)
    monkeypatch.setattr(control_center, "list_recent_events", list_recent_events_double)
    monkeypatch.setattr(control_center, "list_run_events", list_run_events_double)
    monkeypatch.setattr(control_center, "collect_health", collect_health_double)
    monkeypatch.setattr(control_center, "observed_schema_revision", observed_schema_revision_double)
    return calls


def client() -> TestClient:
    return TestClient(main.app)


def test_fleet_reports_exact_state_counts_and_derives_short_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    states = (
        ProjectState.OFFLINE,
        ProjectState.STALE,
        ProjectState.INDEXING,
        ProjectState.READY,
        ProjectState.ACTIVE,
        ProjectState.DEGRADED,
        ProjectState.BLOCKED,
    )
    projects = [
        project(
            UUID(int=index + 1),
            name=f"Project {index}",
            relative_path=f"projects/p{index}",
            state=state,
            git_head_sha=HEAD_SHA if index % 2 == 0 else None,
        )
        for index, state in enumerate(states)
    ]
    wire(monkeypatch, projects=projects)

    response = client().get("/api/v1/control-center/fleet")

    assert response.status_code == 200
    body = response.json()
    assert body["project_count"] == len(states)
    assert body["state_counts"] == {
        "offline": 1,
        "stale": 1,
        "indexing": 1,
        "ready": 1,
        "active": 1,
        "degraded": 1,
        "blocked": 1,
    }
    assert body["truncated"] is False
    assert body["max_projects"] == control_center.CONTROL_CENTER_MAX_PROJECTS
    assert body["offset"] == 0
    assert body["limit"] == control_center.CONTROL_CENTER_MAX_PROJECTS
    assert body["has_more"] is False
    assert body["next_offset"] is None
    assert body["projects"][0]["project_id"] == str(UUID(int=1))
    assert body["projects"][0]["short_head"] == "abcdef1"
    assert body["projects"][0]["git_head_sha"] == HEAD_SHA
    assert body["projects"][1]["short_head"] is None
    assert body["projects"][1]["git_head_sha"] is None
    assert body["projects"][0]["relative_path"] == "projects/p0"
    assert "absolute_path" not in body["projects"][0]
    serialized = json.dumps(body)
    assert "C:\\" not in serialized
    assert "/Users/" not in serialized


def test_fleet_empty_registry_reports_zeroes_without_fabrication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire(monkeypatch, projects=[])

    response = client().get("/api/v1/control-center/fleet")

    assert response.status_code == 200
    body = response.json()
    assert body["project_count"] == 0
    assert set(body["state_counts"].values()) == {0}
    assert body["projects"] == []
    assert body["truncated"] is False
    assert body["has_more"] is False
    assert body["next_offset"] is None


def test_fleet_truncates_past_the_bounded_project_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    total = control_center.CONTROL_CENTER_MAX_PROJECTS + 1
    projects = [project(UUID(int=index + 1), relative_path=f"p{index}") for index in range(total)]
    wire(monkeypatch, projects=projects)

    response = client().get("/api/v1/control-center/fleet")

    assert response.status_code == 200
    body = response.json()
    assert body["project_count"] == total
    assert len(body["projects"]) == control_center.CONTROL_CENTER_MAX_PROJECTS
    assert body["truncated"] is True
    assert body["has_more"] is True
    assert body["next_offset"] == control_center.CONTROL_CENTER_MAX_PROJECTS
    assert body["state_counts"]["ready"] == total


def test_fleet_pagination_reaches_every_project_with_global_truth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    total = control_center.CONTROL_CENTER_MAX_PROJECTS + 1
    projects = [project(UUID(int=index + 1), relative_path=f"p{index}") for index in range(total)]
    projects[-1] = project(
        UUID(int=total), relative_path=f"p{total - 1}", state=ProjectState.BLOCKED
    )
    wire(monkeypatch, projects=projects)
    api = client()

    first = api.get("/api/v1/control-center/fleet").json()
    assert first["offset"] == 0
    assert first["limit"] == control_center.CONTROL_CENTER_MAX_PROJECTS
    assert first["project_count"] == total
    assert len(first["projects"]) == control_center.CONTROL_CENTER_MAX_PROJECTS
    assert first["truncated"] is True
    assert first["has_more"] is True
    assert first["next_offset"] == control_center.CONTROL_CENTER_MAX_PROJECTS
    assert first["state_counts"]["ready"] == total - 1
    assert first["state_counts"]["blocked"] == 1

    second = api.get(
        "/api/v1/control-center/fleet",
        params={
            "offset": first["next_offset"],
            "limit": control_center.CONTROL_CENTER_MAX_PROJECTS,
        },
    ).json()
    assert second["offset"] == control_center.CONTROL_CENTER_MAX_PROJECTS
    assert second["project_count"] == total
    assert [item["project_id"] for item in second["projects"]] == [str(UUID(int=total))]
    assert second["truncated"] is True
    assert second["has_more"] is False
    assert second["next_offset"] is None
    assert second["state_counts"] == first["state_counts"]

    first_ids = {item["project_id"] for item in first["projects"]}
    second_ids = {item["project_id"] for item in second["projects"]}
    assert first_ids.isdisjoint(second_ids)
    assert len(first_ids | second_ids) == total

    beyond = api.get("/api/v1/control-center/fleet", params={"offset": total + 50}).json()
    assert beyond["projects"] == []
    assert beyond["project_count"] == total
    assert beyond["truncated"] is True
    assert beyond["has_more"] is False
    assert beyond["next_offset"] is None


def test_fleet_paging_input_fails_closed_with_422(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire(monkeypatch, projects=[project()])
    api = client()
    route = "/api/v1/control-center/fleet"
    bound = control_center.CONTROL_CENTER_MAX_PROJECTS

    assert api.get(route, params={"offset": -1}).status_code == 422
    assert api.get(route, params={"limit": 0}).status_code == 422
    assert api.get(route, params={"limit": bound + 1}).status_code == 422
    assert api.get(route, params={"offset": "not-a-number"}).status_code == 422
    assert api.get(route, params={"limit": "not-a-number"}).status_code == 422
    assert api.get(route, params={"limit": 1}).status_code == 200


def test_runs_classify_active_terminal_and_observed_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aggregates = [
        aggregate(RUN_ACTIVE, last_event_type="executor.started"),
        aggregate(
            RUN_COMPLETED,
            last_event_type="run.completed",
            terminal_event_type="run.completed",
        ),
        aggregate(
            RUN_FAILED,
            last_event_type="run.failed",
            terminal_event_type="run.failed",
        ),
        aggregate(
            RUN_OBSERVED,
            last_event_type="project.discovered",
            executor_started=False,
        ),
    ]
    calls = wire(monkeypatch, projects=[project()], aggregates={PROJECT_A: aggregates})

    response = client().get(f"/api/v1/control-center/projects/{PROJECT_A}/runs")

    assert response.status_code == 200
    body = response.json()
    assert [item["run_id"] for item in body["active"]] == [str(RUN_ACTIVE)]
    assert body["active"][0]["status"] == "ACTIVE"
    assert body["active"][0]["stage"] == "executor.started"
    recent = {item["run_id"]: item["status"] for item in body["recent"]}
    assert recent == {
        str(RUN_COMPLETED): "COMPLETED",
        str(RUN_FAILED): "FAILED",
        str(RUN_OBSERVED): "OBSERVED",
    }
    assert body["window"]["scanned_events"] == len(aggregates)
    assert body["window"]["truncated"] is False
    assert calls[-1] == (
        "summarize_runs",
        PROJECT_A,
        control_center.CONTROL_CENTER_RUN_LIMIT_DEFAULT + 1,
    )


def test_run_listing_preserves_supplied_canonical_order_with_ties(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = UUID("00000000-0000-0000-0000-0000000000d2")
    second = UUID("00000000-0000-0000-0000-0000000000d1")
    aggregates = [
        aggregate(first, last_event_type="run.failed", terminal_event_type="run.failed"),
        aggregate(second, last_event_type="run.completed", terminal_event_type="run.completed"),
    ]
    wire(monkeypatch, projects=[project()], aggregates={PROJECT_A: aggregates})

    body = client().get(f"/api/v1/control-center/projects/{PROJECT_A}/runs").json()

    assert [item["run_id"] for item in body["recent"]] == [str(first), str(second)]


def test_test_surface_orders_runs_deterministically_on_tied_timestamps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_a = UUID("00000000-0000-0000-0000-0000000000d1")
    run_b = UUID("00000000-0000-0000-0000-0000000000d2")
    tied_events = [
        event(
            "test.finished",
            run_id=run_a,
            ordering_id=2,
            occurred_at=NOW,
            payload={"passed": True},
        ),
        event(
            "test.finished",
            run_id=run_b,
            ordering_id=3,
            occurred_at=NOW,
            payload={"passed": True},
        ),
    ]
    aggregates = {
        PROJECT_A: [
            aggregate(run_a, last_event_type="test.finished"),
            aggregate(run_b, last_event_type="test.finished"),
        ]
    }
    wire(monkeypatch, projects=[project()], aggregates=aggregates, events={PROJECT_A: tied_events})

    body = client().get(f"/api/v1/control-center/projects/{PROJECT_A}/tests").json()

    assert [item["run_id"] for item in body["runs"]] == [str(run_b), str(run_a)]


def test_projects_are_isolated_through_every_project_scoped_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_b = UUID("00000000-0000-0000-0000-0000000000b2")
    aggregates = {
        PROJECT_A: [aggregate(RUN_ACTIVE)],
        PROJECT_B: [
            aggregate(
                run_b,
                last_event_type="run.completed",
                terminal_event_type="run.completed",
            )
        ],
    }
    events = {
        PROJECT_A: [
            event("executor.started", project_id=PROJECT_A, run_id=RUN_ACTIVE, ordering_id=1)
        ],
        PROJECT_B: [event("run.completed", project_id=PROJECT_B, run_id=run_b, ordering_id=9)],
    }
    timelines = {
        (PROJECT_A, RUN_ACTIVE): [
            event("executor.started", project_id=PROJECT_A, run_id=RUN_ACTIVE, ordering_id=1)
        ]
    }
    wire(
        monkeypatch,
        projects=[
            project(PROJECT_A, name="Alpha", relative_path="alpha"),
            project(PROJECT_B, name="Beta", relative_path="beta"),
        ],
        aggregates=aggregates,
        events=events,
        timelines=timelines,
    )
    api = client()

    alpha_runs = api.get(f"/api/v1/control-center/projects/{PROJECT_A}/runs").json()
    beta_runs = api.get(f"/api/v1/control-center/projects/{PROJECT_B}/runs").json()

    assert [item["run_id"] for item in alpha_runs["active"]] == [str(RUN_ACTIVE)]
    assert alpha_runs["recent"] == []
    assert [item["run_id"] for item in beta_runs["recent"]] == [str(run_b)]
    assert beta_runs["active"] == []
    assert all(
        item["run_id"] != str(RUN_ACTIVE) for item in beta_runs["active"] + beta_runs["recent"]
    )

    alpha_detail = api.get(f"/api/v1/control-center/projects/{PROJECT_A}").json()
    assert [item["run_id"] for item in alpha_detail["recent_events"]] == [str(RUN_ACTIVE)]
    assert [item["run_id"] for item in alpha_detail["recent_runs"]] == [str(RUN_ACTIVE)]

    cross_project_run = api.get(f"/api/v1/control-center/projects/{PROJECT_A}/runs/{run_b}")
    assert cross_project_run.status_code == 404
    assert cross_project_run.json()["detail"] == "run not found for project"


def test_unknown_project_and_run_fail_closed_with_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire(monkeypatch, projects=[project()], aggregates={PROJECT_A: [aggregate(RUN_ACTIVE)]})
    api = client()

    for path in (
        f"/api/v1/control-center/projects/{PROJECT_UNKNOWN}",
        f"/api/v1/control-center/projects/{PROJECT_UNKNOWN}/runs",
        f"/api/v1/control-center/projects/{PROJECT_UNKNOWN}/tests",
        f"/api/v1/control-center/projects/{PROJECT_UNKNOWN}/errors",
    ):
        response = api.get(path)
        assert response.status_code == 404, path
        assert response.json()["detail"] == "project not found"

    missing_run = api.get(f"/api/v1/control-center/projects/{PROJECT_A}/runs/{RUN_UNKNOWN}")
    assert missing_run.status_code == 404
    assert missing_run.json()["detail"] == "run not found for project"

    assert api.get("/api/v1/control-center/projects/not-a-uuid").status_code == 422


def test_project_detail_composes_the_bounded_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = [
        event(
            "executor.started",
            ordering_id=1,
            occurred_at=NOW - timedelta(minutes=3),
            payload={"adapter": "codex/openai"},
        ),
        event("test.started", ordering_id=2, occurred_at=NOW - timedelta(minutes=2)),
        event(
            "test.finished",
            ordering_id=3,
            occurred_at=NOW - timedelta(minutes=1),
            payload={"passed": True},
        ),
    ]
    wire(
        monkeypatch,
        projects=[project()],
        aggregates={PROJECT_A: [aggregate(RUN_ACTIVE)]},
        events={PROJECT_A: events},
    )

    body = client().get(f"/api/v1/control-center/projects/{PROJECT_A}").json()

    assert body["project"]["name"] == "Alpha"
    assert body["active_run_count"] == 1
    assert [item["run_id"] for item in body["recent_runs"]] == [str(RUN_ACTIVE)]
    assert body["recent_runs_truncated"] is False
    assert [item["event_type"] for item in body["recent_events"]] == [
        "executor.started",
        "test.started",
        "test.finished",
    ]
    assert body["window"] == {
        "scanned_events": 3,
        "max_events": control_center.CONTROL_CENTER_EVENT_LIMIT_DEFAULT,
        "truncated": False,
    }
    assert body["tests"]["runs"][0]["status"] == "PASSED"
    assert body["errors"]["errors"] == []


def test_bounded_windows_report_truncation_and_reject_out_of_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aggregates = [
        aggregate(RUN_ACTIVE),
        aggregate(
            RUN_COMPLETED,
            last_event_type="run.completed",
            terminal_event_type="run.completed",
        ),
        aggregate(RUN_FAILED, last_event_type="run.failed", terminal_event_type="run.failed"),
    ]
    events = [
        event(
            "executor.started",
            ordering_id=index + 1,
            occurred_at=NOW - timedelta(minutes=10 - index),
        )
        for index in range(5)
    ]
    calls = wire(
        monkeypatch,
        projects=[project()],
        aggregates={PROJECT_A: aggregates},
        events={PROJECT_A: events},
    )
    api = client()

    runs_body = api.get(
        f"/api/v1/control-center/projects/{PROJECT_A}/runs", params={"limit": 1}
    ).json()
    assert len(runs_body["active"]) + len(runs_body["recent"]) == 1
    assert runs_body["truncated"] is True
    assert runs_body["window"] == {"scanned_events": 1, "max_events": 1, "truncated": True}

    max_limit_body = api.get(
        f"/api/v1/control-center/projects/{PROJECT_A}/runs",
        params={"limit": control_center.CONTROL_CENTER_RUN_LIMIT_MAX},
    ).json()
    assert max_limit_body["truncated"] is False
    assert calls[-1] == (
        "summarize_runs",
        PROJECT_A,
        control_center.CONTROL_CENTER_RUN_LIMIT_MAX + 1,
    )

    detail_body = api.get(
        f"/api/v1/control-center/projects/{PROJECT_A}",
        params={"runs": 1, "events": 2},
    ).json()
    assert len(detail_body["recent_runs"]) == 1
    assert detail_body["recent_runs_truncated"] is True
    assert len(detail_body["recent_events"]) == 2
    assert detail_body["window"] == {"scanned_events": 2, "max_events": 2, "truncated": True}

    assert (
        api.get(
            f"/api/v1/control-center/projects/{PROJECT_A}/runs", params={"limit": 0}
        ).status_code
        == 422
    )
    assert (
        api.get(
            f"/api/v1/control-center/projects/{PROJECT_A}/runs",
            params={"limit": control_center.CONTROL_CENTER_RUN_LIMIT_MAX + 1},
        ).status_code
        == 422
    )
    assert (
        api.get(
            f"/api/v1/control-center/projects/{PROJECT_A}",
            params={"events": control_center.CONTROL_CENTER_EVENT_WINDOW_MAX + 1},
        ).status_code
        == 422
    )


def test_run_detail_returns_bounded_timeline_and_executor_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    duplicate_ordering_event = UUID("00000000-0000-0000-0000-000000000077")
    timeline = [
        event(
            "executor.started",
            ordering_id=7,
            occurred_at=NOW - timedelta(minutes=2),
            payload={"adapter": "codex/openai/gpt-5"},
        ),
        event(
            "tool.called",
            ordering_id=7,
            occurred_at=NOW - timedelta(minutes=2),
            payload={"tool": "pytest"},
            event_id=duplicate_ordering_event,
        ),
        event(
            "run.completed",
            ordering_id=8,
            occurred_at=NOW,
            payload={"status": "completed"},
        ),
    ]
    wire(
        monkeypatch,
        projects=[project()],
        aggregates={
            PROJECT_A: [
                aggregate(
                    RUN_ACTIVE,
                    last_event_type="run.completed",
                    terminal_event_type="run.completed",
                )
            ]
        },
        timelines={(PROJECT_A, RUN_ACTIVE): timeline},
    )

    body = (
        client()
        .get(
            f"/api/v1/control-center/projects/{PROJECT_A}/runs/{RUN_ACTIVE}",
            params={"events": 2},
        )
        .json()
    )

    assert body["run"]["status"] == "COMPLETED"
    assert body["run"]["last_event_type"] == "run.completed"
    assert body["task_id"] == str(TASK_ID)
    assert body["executor_identity"] == "codex/openai/gpt-5"
    assert [item["ordering_id"] for item in body["timeline"]] == [7, 7]
    assert body["timeline"][1]["event_id"] == str(duplicate_ordering_event)
    assert body["timeline_truncated"] is True
    assert body["max_timeline_events"] == 2

    unbounded = client().get(
        f"/api/v1/control-center/projects/{PROJECT_A}/runs/{RUN_ACTIVE}",
        params={"events": EVENT_PAGE_MAX_SIZE + 1},
    )
    assert unbounded.status_code == 422


def test_database_failure_is_explicit_503_without_fabricated_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire(
        monkeypatch,
        projects=[project()],
        aggregates={PROJECT_A: [aggregate(RUN_ACTIVE)]},
        database_error="simulated connection refused",
    )
    api = client()

    for path in (
        "/api/v1/control-center/fleet",
        f"/api/v1/control-center/projects/{PROJECT_A}",
        f"/api/v1/control-center/projects/{PROJECT_A}/runs",
        f"/api/v1/control-center/projects/{PROJECT_A}/tests",
        f"/api/v1/control-center/projects/{PROJECT_A}/errors",
    ):
        response = api.get(path)
        assert response.status_code == 503, path
        assert response.json()["detail"] == "control center database unavailable"
        assert "simulated connection refused" not in response.text


def test_health_surface_reports_canonical_store_and_unavailable_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire(monkeypatch)

    response = client().get("/api/v1/control-center/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["migration_head"] == MIGRATION_HEAD
    assert body["canonical_store"] == "postgres"
    assert body["hot_store"] == "redis"
    assert body["hot_store_canonical"] is False
    assert body["unavailable_metrics"] == [
        "exact_live_token_usage",
        "exact_provider_cost",
        "cache_hit_rate",
        "context_signal_ratio",
    ]
    assert body["checks"]["storage"]["details"] == {"configured": True, "writable": True}
    assert "canonical_data_root" not in response.text
    assert "/var/lib/hive" not in response.text


def test_redis_loss_degrades_health_without_destroying_the_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    degraded = health_report(
        status="degraded",
        checks={
            "postgres": ServiceCheck(status="ok", details={"pgvector": True}),
            "redis": ServiceCheck(
                status="degraded",
                details={"reason": "connection failed (ConnectionError)"},
            ),
            "storage": ServiceCheck(
                status="ok",
                details={
                    "configured": True,
                    "writable": True,
                    "canonical_data_root": "/var/lib/hive",
                },
            ),
        },
    )
    wire(
        monkeypatch,
        projects=[project()],
        aggregates={PROJECT_A: [aggregate(RUN_ACTIVE)]},
        health=degraded,
    )
    api = client()

    health_response = api.get("/api/v1/control-center/health")

    assert health_response.status_code == 503
    body = health_response.json()
    assert body["status"] == "degraded"
    assert body["hot_store"] == "redis"
    assert body["hot_store_canonical"] is False
    assert body["checks"]["redis"]["status"] == "degraded"
    assert body["checks"]["postgres"]["status"] == "ok"
    assert body["migration_head"] == MIGRATION_HEAD

    snapshot = api.get(f"/api/v1/control-center/projects/{PROJECT_A}/runs")
    assert snapshot.status_code == 200
    assert [item["run_id"] for item in snapshot.json()["active"]] == [str(RUN_ACTIVE)]

    warnings = api.get(f"/api/v1/control-center/projects/{PROJECT_A}/errors").json()["warnings"]
    assert [item["kind"] for item in warnings] == ["health.redis"]


def test_health_marks_migration_head_unavailable_when_the_database_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire(monkeypatch, migration_head=None)

    response = client().get("/api/v1/control-center/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["migration_head"] == "unavailable"


def test_test_surface_classifies_outcomes_and_counts_runs_without_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_passed = UUID("00000000-0000-0000-0000-0000000000e1")
    run_failed = UUID("00000000-0000-0000-0000-0000000000e2")
    run_running = UUID("00000000-0000-0000-0000-0000000000e3")
    run_validation_failed = UUID("00000000-0000-0000-0000-0000000000e4")
    run_unrecorded = UUID("00000000-0000-0000-0000-0000000000e5")
    run_silent = UUID("00000000-0000-0000-0000-0000000000e6")
    events = [
        event(
            "test.started",
            run_id=run_passed,
            ordering_id=1,
            occurred_at=NOW - timedelta(minutes=9),
        ),
        event(
            "test.finished",
            run_id=run_passed,
            ordering_id=2,
            occurred_at=NOW - timedelta(minutes=8),
            payload={"passed": True},
        ),
        event(
            "test.finished",
            run_id=run_failed,
            ordering_id=3,
            occurred_at=NOW - timedelta(minutes=7),
            payload={"passed": False},
        ),
        event(
            "test.started",
            run_id=run_running,
            ordering_id=4,
            occurred_at=NOW - timedelta(minutes=6),
        ),
        event(
            "validation.failed",
            run_id=run_validation_failed,
            ordering_id=5,
            occurred_at=NOW - timedelta(minutes=5),
            payload={"status": "failed"},
        ),
        event(
            "test.started",
            run_id=run_unrecorded,
            ordering_id=6,
            occurred_at=NOW - timedelta(minutes=4),
        ),
        event(
            "test.finished",
            run_id=run_unrecorded,
            ordering_id=7,
            occurred_at=NOW - timedelta(minutes=3),
            payload={"detail": "no boolean outcome"},
        ),
    ]
    aggregates = {
        PROJECT_A: [
            aggregate(run_passed, last_event_type="test.finished"),
            aggregate(run_failed, last_event_type="test.finished"),
            aggregate(run_running, last_event_type="test.started"),
            aggregate(run_validation_failed, last_event_type="validation.failed"),
            aggregate(run_unrecorded, last_event_type="test.finished"),
            aggregate(run_silent, last_event_type="executor.started"),
        ]
    }
    wire(monkeypatch, projects=[project()], aggregates=aggregates, events={PROJECT_A: events})

    body = client().get(f"/api/v1/control-center/projects/{PROJECT_A}/tests").json()

    statuses = {item["run_id"]: item["status"] for item in body["runs"]}
    assert statuses[str(run_passed)] == "PASSED"
    assert statuses[str(run_failed)] == "FAILED"
    assert statuses[str(run_running)] == "RUNNING"
    assert statuses[str(run_validation_failed)] == "FAILED"
    assert statuses[str(run_unrecorded)] == "UNRECORDED"
    assert str(run_silent) not in statuses
    assert body["runs_without_test_telemetry_in_window"] == 1
    assert body["window"] == {
        "scanned_events": len(events),
        "max_events": control_center.CONTROL_CENTER_EVENT_LIMIT_DEFAULT,
        "truncated": False,
    }
    last_validation = datetime.fromisoformat(
        body["last_validation_event_at"].replace("Z", "+00:00")
    )
    assert last_validation == NOW - timedelta(minutes=5)


def test_errors_surface_lists_failures_and_degradation_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_failed = UUID("00000000-0000-0000-0000-0000000000f1")
    events = [
        event(
            "run.failed",
            run_id=run_failed,
            ordering_id=5,
            occurred_at=NOW - timedelta(minutes=2),
            payload={"message": "executor crashed"},
        ),
        event(
            "validation.failed",
            run_id=run_failed,
            ordering_id=6,
            occurred_at=NOW - timedelta(minutes=1),
            payload={"status": "failed"},
        ),
    ]
    degraded = health_report(
        status="degraded",
        checks={
            "postgres": ServiceCheck(status="ok", details={"pgvector": True}),
            "redis": ServiceCheck(status="ok", details={"canonical": False}),
            "storage": ServiceCheck(
                status="degraded",
                details={"configured": True, "writable": False, "reason": "OSError"},
            ),
        },
    )
    wire(
        monkeypatch,
        projects=[
            project(
                state=ProjectState.DEGRADED,
                inspection_error="repository is not accessible",
            )
        ],
        aggregates={
            PROJECT_A: [
                aggregate(
                    run_failed,
                    last_event_type="run.failed",
                    terminal_event_type="run.failed",
                )
            ]
        },
        events={PROJECT_A: events},
        health=degraded,
    )
    api = client()

    body = api.get(f"/api/v1/control-center/projects/{PROJECT_A}/errors").json()

    assert [item["kind"] for item in body["errors"]] == ["validation.failed", "run.failed"]
    assert [item["severity"] for item in body["errors"]] == ["ERROR", "ERROR"]
    assert body["errors"][0]["summary"] == "validation.failed: failed"
    assert body["errors"][1]["summary"] == "run.failed: executor crashed"
    assert [item["kind"] for item in body["warnings"]] == [
        "project.state.degraded",
        "health.storage",
    ]
    assert all(item["severity"] == "WARNING" for item in body["warnings"])
    assert body["truncated"] is False

    limited = api.get(
        f"/api/v1/control-center/projects/{PROJECT_A}/errors",
        params={"limit": 1},
    ).json()
    assert len(limited["errors"]) == 1
    assert limited["truncated"] is True


def test_surfaces_sanitize_hostile_project_text_and_never_leak_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire(
        monkeypatch,
        projects=[
            project(
                state=ProjectState.DEGRADED,
                inspection_error="C:\\Users\\csn19\\secret\\vault",
            )
        ],
    )

    response = client().get(f"/api/v1/control-center/projects/{PROJECT_A}")

    assert response.status_code == 200
    body = response.json()
    assert body["project"]["inspection_error"] == "unavailable"
    assert "secret" not in response.text
    assert "vault" not in response.text
    assert "Users" not in response.text


def test_headline_bounds_error_text_and_language_stack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire(
        monkeypatch,
        projects=[
            project(
                state=ProjectState.BLOCKED,
                inspection_error="e" * 400,
                language_stack=[f"lang{index}" for index in range(20)],
            )
        ],
    )

    body = client().get("/api/v1/control-center/fleet").json()
    headline = body["projects"][0]

    assert len(headline["inspection_error"]) == control_center.CONTROL_CENTER_ERROR_TEXT_MAX_CHARS
    assert len(headline["language_stack"]) == control_center.CONTROL_CENTER_PROJECT_LANGUAGE_LIMIT


def test_headline_model_rejects_extra_and_unbounded_fields() -> None:
    with pytest.raises(ValidationError):
        control_center.ProjectHeadline.model_validate(
            {
                "project_id": str(PROJECT_A),
                "name": "Alpha",
                "relative_path": "alpha",
                "state": "READY",
                "detached_head": False,
                "repository_accessible": True,
                "language_stack": ["python"],
                "last_inspected_at": NOW.isoformat(),
                "updated_at": NOW.isoformat(),
                "absolute_path": "/etc/hive",
            }
        )
    with pytest.raises(ValidationError):
        control_center.FleetStateCounts.model_validate(
            {
                "offline": 0,
                "stale": 0,
                "indexing": 0,
                "ready": 0,
                "active": 0,
                "degraded": 0,
                "blocked": 0,
                "unknown": 1,
            }
        )
