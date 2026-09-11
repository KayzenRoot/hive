"""Bounded, project-scoped operational core of the HIVE Control Center.

The module composes the durable Project Registry, the canonical telemetry
event bus and the existing health collectors into the eight canonical
operational surfaces of the control-center-core-v1 evidence contract.  It is
read-only: it never writes canonical state, never fabricates metrics and never
resolves project identity from free-form input.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

import psycopg
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from .config import Settings, get_settings
from .db import observed_schema_revision
from .health import collect_health
from .registry import ProjectResponse, ProjectState, get_project, list_projects
from .telemetry import (
    EVENT_PAGE_MAX_SIZE,
    EventEnvelope,
    RunAggregate,
    TelemetryValidationError,
    list_recent_events,
    list_run_events,
    sanitize_payload,
    summarize_runs,
)

CONTROL_CENTER_MAX_PROJECTS = 200
CONTROL_CENTER_PROJECT_LANGUAGE_LIMIT = 8
CONTROL_CENTER_RUN_LIMIT_DEFAULT = 20
CONTROL_CENTER_RUN_LIMIT_MAX = 50
CONTROL_CENTER_EVENT_LIMIT_DEFAULT = 50
CONTROL_CENTER_EVENT_WINDOW_MAX = EVENT_PAGE_MAX_SIZE
CONTROL_CENTER_RUN_TIMELINE_DEFAULT = 100
CONTROL_CENTER_WARNING_LIMIT_DEFAULT = 25
CONTROL_CENTER_WARNING_LIMIT_MAX = 50
CONTROL_CENTER_SUMMARY_MAX_CHARS = 200
CONTROL_CENTER_ERROR_TEXT_MAX_CHARS = 160
CONTROL_CENTER_ERROR_EVENT_TYPES = ("run.failed", "validation.failed")
CONTROL_CENTER_TEST_EVENT_TYPES = (
    "test.started",
    "test.finished",
    "validation.passed",
    "validation.failed",
)
CONTROL_CENTER_CHECK_DETAIL_KEYS: dict[str, tuple[str, ...]] = {
    "postgres": ("pgvector",),
    "redis": ("canonical",),
    "storage": ("configured", "writable"),
}
CONTROL_CENTER_UNAVAILABLE_METRICS = (
    "exact_live_token_usage",
    "exact_provider_cost",
    "cache_hit_rate",
    "context_signal_ratio",
)


class ProjectHeadline(BaseModel):
    """Bounded registry identity without any host filesystem path."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: UUID
    name: str
    relative_path: str
    state: ProjectState
    git_branch: str | None = None
    git_head_sha: str | None = None
    short_head: str | None = None
    detached_head: bool
    repository_accessible: bool
    working_tree_clean: bool | None = None
    language_stack: list[str]
    inspection_error: str | None = None
    last_inspected_at: datetime
    updated_at: datetime


class FleetStateCounts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    offline: int = Field(ge=0)
    stale: int = Field(ge=0)
    indexing: int = Field(ge=0)
    ready: int = Field(ge=0)
    active: int = Field(ge=0)
    degraded: int = Field(ge=0)
    blocked: int = Field(ge=0)


class FleetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    generated_at: datetime
    project_count: int = Field(ge=0)
    state_counts: FleetStateCounts
    projects: list[ProjectHeadline]
    truncated: bool
    max_projects: int = Field(ge=1)


class RunStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    OBSERVED = "OBSERVED"


class RunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    status: RunStatus
    stage: str
    last_event_type: str
    last_event_at: datetime
    first_event_at: datetime
    event_count: int = Field(ge=1)


class EventWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scanned_events: int = Field(ge=0)
    max_events: int = Field(ge=1)
    truncated: bool


class RunsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    generated_at: datetime
    project_id: UUID
    active: list[RunSummary]
    recent: list[RunSummary]
    truncated: bool
    window: EventWindow


class RunDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    generated_at: datetime
    project_id: UUID
    run: RunSummary
    task_id: UUID | None = None
    executor_identity: str | None = None
    timeline: list[EventEnvelope]
    timeline_truncated: bool
    max_timeline_events: int = Field(ge=1)


class TestStatusValue(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    RUNNING = "RUNNING"
    UNRECORDED = "UNRECORDED"


class TestRunStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    status: TestStatusValue
    test_started: int = Field(ge=0)
    test_finished: int = Field(ge=0)
    validation_passed: int = Field(ge=0)
    validation_failed: int = Field(ge=0)
    last_event_type: str
    last_event_at: datetime


class TestStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    generated_at: datetime
    project_id: UUID
    window: EventWindow
    runs: list[TestRunStatus]
    runs_without_test_telemetry_in_window: int = Field(ge=0)
    last_validation_event_at: datetime | None = None


class WarningSeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class WarningItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    severity: WarningSeverity
    kind: str
    project_id: UUID
    run_id: UUID | None = None
    event_id: UUID | None = None
    occurred_at: datetime | None = None
    summary: str


class ErrorsWarningsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    generated_at: datetime
    project_id: UUID
    window: EventWindow
    errors: list[WarningItem]
    warnings: list[WarningItem]
    truncated: bool


class ControlCenterCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str
    details: dict[str, bool]
    reason: str | None = None


class ControlCenterHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    generated_at: datetime
    status: str
    version: str
    environment: str
    migration_head: str
    canonical_store: str
    hot_store: str
    hot_store_canonical: bool
    checks: dict[str, ControlCenterCheck]
    unavailable_metrics: list[str]


class ProjectDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    generated_at: datetime
    project: ProjectHeadline
    active_run_count: int = Field(ge=0)
    recent_runs: list[RunSummary]
    recent_runs_truncated: bool
    recent_events: list[EventEnvelope]
    window: EventWindow
    tests: TestStatusResponse
    errors: ErrorsWarningsResponse


@dataclass
class _TestAccumulator:
    test_started: int = 0
    test_finished: int = 0
    validation_passed: int = 0
    validation_failed: int = 0
    finished_failed: int = 0
    finished_passed: int = 0
    last_event: EventEnvelope | None = None
    event_types: set[str] = field(default_factory=set)


def _now() -> datetime:
    return datetime.now(UTC)


def _router_settings() -> Settings:
    return get_settings()


def _database_unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail="control center database unavailable")


def _safe_text(value: str | None, *, max_chars: int) -> str | None:
    if value is None:
        return None
    candidate = value[:max_chars]
    if not candidate:
        return None
    try:
        sanitized = sanitize_payload({"value": candidate})
    except TelemetryValidationError:
        return "unavailable"
    sanitized_value = sanitized["value"]
    return sanitized_value if isinstance(sanitized_value, str) else "unavailable"


def _headline(project: ProjectResponse) -> ProjectHeadline:
    head = project.git_head_sha
    return ProjectHeadline(
        project_id=project.project_id,
        name=project.name,
        relative_path=project.relative_path,
        state=project.state,
        git_branch=project.git_branch,
        git_head_sha=head,
        short_head=head[:7] if head else None,
        detached_head=project.detached_head,
        repository_accessible=project.repository_accessible,
        working_tree_clean=project.working_tree_clean,
        language_stack=list(project.language_stack[:CONTROL_CENTER_PROJECT_LANGUAGE_LIMIT]),
        inspection_error=_safe_text(
            project.inspection_error, max_chars=CONTROL_CENTER_ERROR_TEXT_MAX_CHARS
        ),
        last_inspected_at=project.last_inspected_at,
        updated_at=project.updated_at,
    )


def _state_counts(projects: list[ProjectResponse]) -> FleetStateCounts:
    counts: dict[ProjectState, int] = dict.fromkeys(ProjectState, 0)
    for project in projects:
        counts[project.state] += 1
    return FleetStateCounts(
        offline=counts[ProjectState.OFFLINE],
        stale=counts[ProjectState.STALE],
        indexing=counts[ProjectState.INDEXING],
        ready=counts[ProjectState.READY],
        active=counts[ProjectState.ACTIVE],
        degraded=counts[ProjectState.DEGRADED],
        blocked=counts[ProjectState.BLOCKED],
    )


def _run_status(aggregate: RunAggregate) -> RunStatus:
    if aggregate.terminal_event_type == "run.completed":
        return RunStatus.COMPLETED
    if aggregate.terminal_event_type == "run.failed":
        return RunStatus.FAILED
    if aggregate.executor_started:
        return RunStatus.ACTIVE
    return RunStatus.OBSERVED


def _run_summary(aggregate: RunAggregate) -> RunSummary:
    return RunSummary(
        run_id=aggregate.run_id,
        status=_run_status(aggregate),
        stage=aggregate.last_event_type,
        last_event_type=aggregate.last_event_type,
        last_event_at=aggregate.last_occurred_at,
        first_event_at=aggregate.first_occurred_at,
        event_count=aggregate.event_count,
    )


def _recent_events(
    settings: Settings, project_id: UUID, *, limit: int
) -> tuple[list[EventEnvelope], bool]:
    page = list_recent_events(settings, project_id, limit=limit)
    return page.events, page.has_more


def _run_aggregates(
    settings: Settings, project_id: UUID, *, limit: int
) -> tuple[list[RunAggregate], bool]:
    requested = min(limit + 1, CONTROL_CENTER_RUN_LIMIT_MAX + 1)
    aggregates = summarize_runs(settings, project_id, limit=requested)
    return aggregates[:limit], len(aggregates) > limit


def _window(events: list[EventEnvelope], max_events: int, truncated: bool) -> EventWindow:
    return EventWindow(
        scanned_events=len(events),
        max_events=max_events,
        truncated=truncated,
    )


def _finished_outcome(event: EventEnvelope) -> bool | None:
    for key in ("passed", "success"):
        value = event.payload.get(key)
        if isinstance(value, bool):
            return value
    return None


def _test_status(
    project_id: UUID,
    events: list[EventEnvelope],
    aggregates: list[RunAggregate],
    *,
    max_events: int,
    truncated: bool,
) -> TestStatusResponse:
    accumulators: dict[UUID, _TestAccumulator] = {}
    last_validation_event_at: datetime | None = None
    for event in events:
        if event.run_id is None or event.event_type not in CONTROL_CENTER_TEST_EVENT_TYPES:
            continue
        accumulator = accumulators.setdefault(event.run_id, _TestAccumulator())
        accumulator.event_types.add(event.event_type)
        if event.event_type == "test.started":
            accumulator.test_started += 1
        elif event.event_type == "test.finished":
            accumulator.test_finished += 1
            outcome = _finished_outcome(event)
            if outcome is True:
                accumulator.finished_passed += 1
            elif outcome is False:
                accumulator.finished_failed += 1
        elif event.event_type == "validation.passed":
            accumulator.validation_passed += 1
        else:
            accumulator.validation_failed += 1
        accumulator.last_event = event
        if event.event_type in ("validation.passed", "validation.failed"):
            last_validation_event_at = event.occurred_at

    runs: list[TestRunStatus] = []
    for run_id, accumulator in accumulators.items():
        if accumulator.last_event is None:
            continue
        if accumulator.validation_failed or accumulator.finished_failed:
            status = TestStatusValue.FAILED
        elif accumulator.validation_passed or accumulator.finished_passed:
            status = TestStatusValue.PASSED
        elif accumulator.test_started > accumulator.test_finished:
            status = TestStatusValue.RUNNING
        else:
            status = TestStatusValue.UNRECORDED
        runs.append(
            TestRunStatus(
                run_id=run_id,
                status=status,
                test_started=accumulator.test_started,
                test_finished=accumulator.test_finished,
                validation_passed=accumulator.validation_passed,
                validation_failed=accumulator.validation_failed,
                last_event_type=accumulator.last_event.event_type,
                last_event_at=accumulator.last_event.occurred_at,
            )
        )
    runs.sort(key=lambda item: (item.last_event_at, str(item.run_id)), reverse=True)
    runs_in_window = {run.run_id for run in runs}
    without_telemetry = sum(1 for aggregate in aggregates if aggregate.run_id not in runs_in_window)
    return TestStatusResponse(
        generated_at=_now(),
        project_id=project_id,
        window=_window(events, max_events, truncated),
        runs=runs,
        runs_without_test_telemetry_in_window=without_telemetry,
        last_validation_event_at=last_validation_event_at,
    )


def _event_summary(event: EventEnvelope) -> str:
    summary = event.event_type
    for key in ("message", "error_type", "status"):
        value = event.payload.get(key)
        if isinstance(value, str) and value:
            summary = f"{event.event_type}: {value}"
            break
    return summary[:CONTROL_CENTER_SUMMARY_MAX_CHARS]


def _warning_items(
    project: ProjectHeadline,
    health: ControlCenterHealthResponse,
    events: list[EventEnvelope],
    *,
    limit: int,
) -> tuple[list[WarningItem], list[WarningItem], bool]:
    ordered_errors = sorted(
        (event for event in events if event.event_type in CONTROL_CENTER_ERROR_EVENT_TYPES),
        key=lambda event: (event.ordering_id, str(event.event_id)),
        reverse=True,
    )
    errors = [
        WarningItem(
            severity=WarningSeverity.ERROR,
            kind=event.event_type,
            project_id=event.project_id,
            run_id=event.run_id,
            event_id=event.event_id,
            occurred_at=event.occurred_at,
            summary=_event_summary(event),
        )
        for event in ordered_errors
    ]
    truncated = len(errors) > limit
    warnings: list[WarningItem] = []
    if project.state in (ProjectState.DEGRADED, ProjectState.BLOCKED):
        detail = project.inspection_error or "no deterministic source explains the state"
        warnings.append(
            WarningItem(
                severity=WarningSeverity.WARNING,
                kind=f"project.state.{project.state.value.lower()}",
                project_id=project.project_id,
                summary=f"project registry state is {project.state.value}: {detail}"[
                    :CONTROL_CENTER_SUMMARY_MAX_CHARS
                ],
            )
        )
    for name, check in sorted(health.checks.items()):
        if check.status != "ok":
            reason = check.reason or "service degraded"
            warnings.append(
                WarningItem(
                    severity=WarningSeverity.WARNING,
                    kind=f"health.{name}",
                    project_id=project.project_id,
                    summary=f"{name} status is {check.status}: {reason}"[
                        :CONTROL_CENTER_SUMMARY_MAX_CHARS
                    ],
                )
            )
    truncated = truncated or len(warnings) > limit
    return errors[:limit], warnings[:limit], truncated


def _errors_warnings(
    project: ProjectHeadline,
    health: ControlCenterHealthResponse,
    events: list[EventEnvelope],
    *,
    max_events: int,
    window_truncated: bool,
    limit: int,
) -> ErrorsWarningsResponse:
    errors, warnings, truncated = _warning_items(project, health, events, limit=limit)
    return ErrorsWarningsResponse(
        generated_at=_now(),
        project_id=project.project_id,
        window=_window(events, max_events, window_truncated),
        errors=errors,
        warnings=warnings,
        truncated=truncated,
    )


def _health(settings: Settings) -> ControlCenterHealthResponse:
    report = collect_health(settings)
    checks: dict[str, ControlCenterCheck] = {}
    for name, check in sorted(report.checks.items()):
        details: dict[str, bool] = {}
        for key in CONTROL_CENTER_CHECK_DETAIL_KEYS.get(name, ()):
            detail_value = check.details.get(key)
            if isinstance(detail_value, bool):
                details[key] = detail_value
        raw_reason = check.details.get("reason")
        reason = (
            _safe_text(raw_reason, max_chars=CONTROL_CENTER_ERROR_TEXT_MAX_CHARS)
            if isinstance(raw_reason, str)
            else None
        )
        checks[name] = ControlCenterCheck(status=check.status, details=details, reason=reason)
    try:
        migration_head = observed_schema_revision(settings)
    except psycopg.Error:
        migration_head = None
    return ControlCenterHealthResponse(
        generated_at=_now(),
        status=report.status if migration_head is not None else "degraded",
        version=report.version,
        environment=report.environment,
        migration_head=migration_head or "unavailable",
        canonical_store="postgres",
        hot_store="redis",
        hot_store_canonical=False,
        checks=checks,
        unavailable_metrics=list(CONTROL_CENTER_UNAVAILABLE_METRICS),
    )


router = APIRouter(tags=["control-center"])


@router.get("/api/v1/control-center/fleet", response_model=FleetResponse)
def control_center_fleet() -> FleetResponse:
    settings = _router_settings()
    try:
        projects = list_projects(settings)
    except psycopg.Error as exc:
        raise _database_unavailable() from exc
    truncated = len(projects) > CONTROL_CENTER_MAX_PROJECTS
    bounded = projects[:CONTROL_CENTER_MAX_PROJECTS]
    return FleetResponse(
        generated_at=_now(),
        project_count=len(bounded),
        state_counts=_state_counts(bounded),
        projects=[_headline(project) for project in bounded],
        truncated=truncated,
        max_projects=CONTROL_CENTER_MAX_PROJECTS,
    )


@router.get("/api/v1/control-center/health", response_model=ControlCenterHealthResponse)
def control_center_health(response: Response) -> ControlCenterHealthResponse:
    settings = _router_settings()
    result = _health(settings)
    if result.status != "ok":
        response.status_code = 503
    return result


def _require_project(settings: Settings, project_id: UUID) -> ProjectResponse:
    project = get_project(settings, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return project


@router.get(
    "/api/v1/control-center/projects/{project_id}",
    response_model=ProjectDetailResponse,
)
def control_center_project_detail(
    project_id: UUID,
    runs: int = Query(
        default=CONTROL_CENTER_RUN_LIMIT_DEFAULT, ge=1, le=CONTROL_CENTER_RUN_LIMIT_MAX
    ),
    events: int = Query(
        default=CONTROL_CENTER_EVENT_LIMIT_DEFAULT, ge=1, le=CONTROL_CENTER_EVENT_WINDOW_MAX
    ),
    warnings: int = Query(
        default=CONTROL_CENTER_WARNING_LIMIT_DEFAULT,
        ge=1,
        le=CONTROL_CENTER_WARNING_LIMIT_MAX,
    ),
) -> ProjectDetailResponse:
    settings = _router_settings()
    try:
        project = _require_project(settings, project_id)
        aggregates, runs_truncated = _run_aggregates(settings, project_id, limit=runs)
        window_events, window_truncated = _recent_events(settings, project_id, limit=events)
    except psycopg.Error as exc:
        raise _database_unavailable() from exc
    headline = _headline(project)
    health = _health(settings)
    summaries = [_run_summary(aggregate) for aggregate in aggregates]
    tests = _test_status(
        project_id,
        window_events,
        aggregates,
        max_events=events,
        truncated=window_truncated,
    )
    errors = _errors_warnings(
        headline,
        health,
        window_events,
        max_events=events,
        window_truncated=window_truncated,
        limit=warnings,
    )
    return ProjectDetailResponse(
        generated_at=_now(),
        project=headline,
        active_run_count=sum(1 for summary in summaries if summary.status is RunStatus.ACTIVE),
        recent_runs=summaries,
        recent_runs_truncated=runs_truncated,
        recent_events=window_events,
        window=_window(window_events, events, window_truncated),
        tests=tests,
        errors=errors,
    )


@router.get(
    "/api/v1/control-center/projects/{project_id}/runs",
    response_model=RunsResponse,
)
def control_center_runs(
    project_id: UUID,
    limit: int = Query(
        default=CONTROL_CENTER_RUN_LIMIT_DEFAULT, ge=1, le=CONTROL_CENTER_RUN_LIMIT_MAX
    ),
) -> RunsResponse:
    settings = _router_settings()
    try:
        _require_project(settings, project_id)
        aggregates, truncated = _run_aggregates(settings, project_id, limit=limit)
    except psycopg.Error as exc:
        raise _database_unavailable() from exc
    summaries = [_run_summary(aggregate) for aggregate in aggregates]
    return RunsResponse(
        generated_at=_now(),
        project_id=project_id,
        active=[summary for summary in summaries if summary.status is RunStatus.ACTIVE],
        recent=[summary for summary in summaries if summary.status is not RunStatus.ACTIVE],
        truncated=truncated,
        window=EventWindow(scanned_events=len(summaries), max_events=limit, truncated=truncated),
    )


@router.get(
    "/api/v1/control-center/projects/{project_id}/runs/{run_id}",
    response_model=RunDetailResponse,
)
def control_center_run_detail(
    project_id: UUID,
    run_id: UUID,
    events: int = Query(default=CONTROL_CENTER_RUN_TIMELINE_DEFAULT, ge=1, le=EVENT_PAGE_MAX_SIZE),
) -> RunDetailResponse:
    settings = _router_settings()
    try:
        _require_project(settings, project_id)
        aggregates = summarize_runs(settings, project_id, run_id=run_id, limit=1)
        if not aggregates:
            raise HTTPException(status_code=404, detail="run not found for project")
        page = list_run_events(settings, project_id, run_id, limit=events)
    except psycopg.Error as exc:
        raise _database_unavailable() from exc
    if not page.events:
        raise HTTPException(status_code=404, detail="run not found for project")
    task_id = next(
        (event.task_id for event in page.events if event.task_id is not None),
        None,
    )
    executor_identity: str | None = None
    for event in page.events:
        if event.event_type != "executor.started":
            continue
        adapter = event.payload.get("adapter")
        if isinstance(adapter, str) and adapter:
            executor_identity = adapter[:CONTROL_CENTER_SUMMARY_MAX_CHARS]
            break
    return RunDetailResponse(
        generated_at=_now(),
        project_id=project_id,
        run=_run_summary(aggregates[0]),
        task_id=task_id,
        executor_identity=executor_identity,
        timeline=page.events,
        timeline_truncated=page.has_more,
        max_timeline_events=events,
    )


@router.get(
    "/api/v1/control-center/projects/{project_id}/tests",
    response_model=TestStatusResponse,
)
def control_center_tests(
    project_id: UUID,
    events: int = Query(
        default=CONTROL_CENTER_EVENT_LIMIT_DEFAULT, ge=1, le=CONTROL_CENTER_EVENT_WINDOW_MAX
    ),
    runs: int = Query(
        default=CONTROL_CENTER_RUN_LIMIT_DEFAULT, ge=1, le=CONTROL_CENTER_RUN_LIMIT_MAX
    ),
) -> TestStatusResponse:
    settings = _router_settings()
    try:
        _require_project(settings, project_id)
        aggregates, _ = _run_aggregates(settings, project_id, limit=runs)
        window_events, window_truncated = _recent_events(settings, project_id, limit=events)
    except psycopg.Error as exc:
        raise _database_unavailable() from exc
    return _test_status(
        project_id,
        window_events,
        aggregates,
        max_events=events,
        truncated=window_truncated,
    )


@router.get(
    "/api/v1/control-center/projects/{project_id}/errors",
    response_model=ErrorsWarningsResponse,
)
def control_center_errors(
    project_id: UUID,
    events: int = Query(
        default=CONTROL_CENTER_EVENT_LIMIT_DEFAULT, ge=1, le=CONTROL_CENTER_EVENT_WINDOW_MAX
    ),
    limit: int = Query(
        default=CONTROL_CENTER_WARNING_LIMIT_DEFAULT,
        ge=1,
        le=CONTROL_CENTER_WARNING_LIMIT_MAX,
    ),
) -> ErrorsWarningsResponse:
    settings = _router_settings()
    try:
        project = _require_project(settings, project_id)
        window_events, window_truncated = _recent_events(settings, project_id, limit=events)
    except psycopg.Error as exc:
        raise _database_unavailable() from exc
    return _errors_warnings(
        _headline(project),
        _health(settings),
        window_events,
        max_events=events,
        window_truncated=window_truncated,
        limit=limit,
    )
