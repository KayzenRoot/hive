"""Bounded full Control Center read model for WO-022.

This module is intentionally read-only.  It composes the existing canonical
Project Registry, repository index, telemetry event bus, retrieval corpus,
memory lifecycle and storage observations into one project-scoped view.  A
missing observation remains UNKNOWN or UNAVAILABLE; it is never changed into
zero merely to make a chart or alert look complete.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
from collections import Counter
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import cast
from uuid import UUID

import psycopg
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from .config import Settings, get_settings
from .control_center import ProjectHeadline, _headline
from .control_center_metrics import (
    MetricProvenance,
    _number,
    _provenance,
)
from .control_center_storage_metrics import observe_project_storage
from .db import database_connection, observed_schema_revision
from .health import collect_health
from .memory import MemoryStatus, list_memories
from .registry import ProjectResponse, ProjectState, get_project
from .repository_indexer import IndexRunStatus, latest_index_run
from .retrieval import CorpusRunStatus, corpus_status
from .semantic_retrieval import semantic_status
from .telemetry import EVENT_PAGE_MAX_SIZE, EventEnvelope, list_recent_events, summarize_runs

FULL_EVIDENCE_VERSION = "control-center-full-v1"
FULL_HISTORY_MAX_POINTS = 100
FULL_TEXT_MAX_CHARS = 256
FULL_LIST_MAX = 100
FULL_CHART_MAX_POINTS = 100
FULL_COMMIT_MAX = 20
FULL_DOCUMENTS = (
    "docs/project-brain/13-CHECKPOINT.md",
    "docs/project-brain/03-SCOPE.md",
    "docs/project-brain/15-DEFINITION-OF-DONE.md",
)
PROJECT_CAPABILITIES = (
    "project-intelligence",
    "checkpoint-scope-dod",
    "index-health",
    "latest-commits",
    "run-history",
    "decisions-memory",
    "modules-symbols",
    "dependency-graph",
    "quality-history",
    "retrieval-quality",
)
CHART_IDS = (
    "tokens-over-time",
    "cached-vs-fresh-tokens",
    "token-savings",
    "cost-over-time",
    "cache-hit-rate",
    "context-reduction",
    "context-signal-ratio",
    "physical-vs-logical-storage",
    "compression-dedup-savings",
    "project-activity",
    "test-pass-failure-rate",
    "retrieval-latency",
    "service-latency-errors",
)
ALERT_IDS = (
    "disk-low",
    "redis-unavailable",
    "postgres-unavailable",
    "project-stale",
    "index-inconsistent",
    "retrieval-degradation",
    "cache-hit-collapse",
    "token-spike",
    "unexpected-cost-spike",
    "failed-test-build",
    "executor-disconnected",
    "checkpoint-mismatch",
)
HEALTH_IDS = (
    "platform-resource-health",
    "container-status",
    "local-model-health-conditional",
)


class FullStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    CLEAR = "CLEAR"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class FullValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: float | int | str | bool | None
    provenance: MetricProvenance
    source: str


class Capability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    status: FullStatus
    summary: str
    provenance: MetricProvenance
    details: dict[str, object] = Field(default_factory=dict)


class DocumentObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    status: FullStatus
    byte_count: int | None = Field(default=None, ge=0)
    source: str


class CommitObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sha: str
    short_sha: str
    occurred_at: datetime | None
    subject: str
    source: str


class ChartPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observed_at: datetime | None
    value: float | int | None
    provenance: MetricProvenance
    source: str
    series: str | None = None


class Chart(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    status: FullStatus
    points: list[ChartPoint]
    max_points: int = Field(ge=1, le=FULL_HISTORY_MAX_POINTS)
    truncated: bool


class Alert(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    status: FullStatus
    severity: str
    summary: str
    provenance: MetricProvenance
    source: str


class HealthSurface(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    status: FullStatus
    summary: str
    provenance: MetricProvenance
    details: dict[str, object] = Field(default_factory=dict)


class ControlCenterFullResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    control_center_full_version: str
    generated_at: datetime
    project_id: UUID
    project: ProjectHeadline
    capabilities: list[Capability]
    charts: list[Chart]
    alerts: list[Alert]
    health: list[HealthSurface]
    canonical_store: str
    hot_store: str
    hot_store_canonical: bool
    history_max_points: int = Field(ge=1, le=FULL_HISTORY_MAX_POINTS)
    project_scoped: bool
    full_v01_complete_claimed: bool


def _now() -> datetime:
    return datetime.now(UTC)


def _text(value: object, limit: int = FULL_TEXT_MAX_CHARS) -> str:
    if not isinstance(value, str) or not value:
        return "UNAVAILABLE"
    clean = value[:limit]
    try:
        from .telemetry import sanitize_payload

        sanitized = sanitize_payload({"value": clean}).get("value")
    except Exception:
        return "UNAVAILABLE"
    return sanitized if isinstance(sanitized, str) else "UNAVAILABLE"


def _details(values: dict[str, object]) -> dict[str, object]:
    """Keep API details bounded and run them through the canonical sanitizer."""

    from .telemetry import sanitize_payload

    try:
        return sanitize_payload(values)
    except Exception:
        return {"state": "UNAVAILABLE", "reason": "detail_sanitization_failed"}


def _value(
    value: float | int | str | bool | None,
    provenance: MetricProvenance,
    source: str,
) -> FullValue:
    return FullValue(value=value, provenance=provenance, source=source)


def _project_path(settings: Settings, project: ProjectResponse) -> Path | None:
    try:
        from .registry import normalize_project_path

        _, path = normalize_project_path(project.relative_path, settings)
        return path
    except (AttributeError, OSError, RuntimeError, ValueError):
        return None


def _document_observations(
    settings: Settings, project: ProjectResponse
) -> list[DocumentObservation]:
    root = _project_path(settings, project)
    observations: list[DocumentObservation] = []
    for relative in FULL_DOCUMENTS:
        path = root / Path(*relative.split("/")) if root is not None else None
        try:
            size = path.stat().st_size if path is not None and path.is_file() else None
        except OSError:
            size = None
        observations.append(
            DocumentObservation(
                path=relative,
                status=FullStatus.AVAILABLE if size is not None else FullStatus.UNAVAILABLE,
                byte_count=size,
                source="project-git-working-tree:canonical-governance-documents",
            )
        )
    return observations


def _git_commits(settings: Settings, project: ProjectResponse) -> list[CommitObservation]:
    root = _project_path(settings, project)
    if root is None or not root.is_dir():
        return []
    command = [
        "git",
        "-c",
        f"safe.directory={root}",
        "-C",
        str(root),
        "log",
        f"-n{FULL_COMMIT_MAX}",
        "--date=iso-strict",
        "--format=%H%x1f%aI%x1f%s",
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            check=False,
            timeout=5,
            text=True,
            encoding="utf-8",
            errors="strict",
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return []
    if result.returncode != 0:
        return []
    commits: list[CommitObservation] = []
    for line in result.stdout.splitlines()[:FULL_COMMIT_MAX]:
        fields = line.split("\x1f", 2)
        if len(fields) != 3 or len(fields[0]) != 40:
            continue
        try:
            occurred = datetime.fromisoformat(fields[1]).astimezone(UTC)
        except ValueError:
            occurred = None
        commits.append(
            CommitObservation(
                sha=fields[0].lower(),
                short_sha=fields[0][:7].lower(),
                occurred_at=occurred,
                subject=_text(fields[2]),
                source="git:project-repository",
            )
        )
    return commits


def _index_details(
    settings: Settings, project: ProjectResponse
) -> tuple[FullStatus, dict[str, object]]:
    run = latest_index_run(settings, project.project_id)
    if run is None:
        return FullStatus.UNAVAILABLE, {"reason": "no_index_run_recorded"}
    head_matches = bool(
        run.repository_head_sha
        and project.git_head_sha
        and run.repository_head_sha.lower() == project.git_head_sha.lower()
    )
    status = FullStatus.AVAILABLE
    if run.status is not IndexRunStatus.COMPLETED or not head_matches:
        status = FullStatus.DEGRADED
    return status, _details(
        {
            "run_id": str(run.run_id),
            "status": run.status.value,
            "repository_head_sha": run.repository_head_sha or "UNAVAILABLE",
            "current_project_head": project.git_head_sha or "UNAVAILABLE",
            "head_matches": head_matches,
            "discovered_file_count": run.discovered_file_count,
            "indexed_file_count": run.indexed_file_count,
            "parsed_file_count": run.parsed_file_count,
            "symbol_count": run.symbol_count,
            "error": _text(run.error) if run.error else None,
        }
    )


def _repository_inventory(
    settings: Settings, project_id: UUID
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT language, count(*)
            FROM repository_files
            WHERE project_id = %s AND is_current
            GROUP BY language
            ORDER BY count(*) DESC, language NULLS LAST
            LIMIT 32
            """,
            (project_id,),
        )
        language_counts = [
            {"language": row[0] or "UNAVAILABLE", "file_count": int(row[1])}
            for row in cursor.fetchall()
        ]
        cursor.execute(
            """
            SELECT path, language, file_type, file_size, parse_status
            FROM repository_files
            WHERE project_id = %s AND is_current
            ORDER BY path
            LIMIT %s
            """,
            (project_id, FULL_LIST_MAX),
        )
        modules = [
            {
                "path": str(row[0]),
                "language": row[1] or "UNAVAILABLE",
                "file_type": str(row[2]),
                "file_size": int(row[3]),
                "parse_status": str(row[4]),
            }
            for row in cursor.fetchall()
        ]
        cursor.execute(
            """
            SELECT f.path, s.qualified_name, s.kind, s.line_start, s.line_end
            FROM repository_symbols AS s
            JOIN repository_files AS f
              ON f.project_id = s.project_id AND f.file_id = s.file_id
            WHERE s.project_id = %s AND f.is_current
            ORDER BY f.path, s.line_start, s.qualified_name
            LIMIT %s
            """,
            (project_id, FULL_LIST_MAX),
        )
        symbols = [
            {
                "path": str(row[0]),
                "qualified_name": str(row[1]),
                "kind": str(row[2]),
                "line_start": int(row[3]),
                "line_end": int(row[4]),
            }
            for row in cursor.fetchall()
        ]
    return {"language_counts": language_counts, "module_count": len(modules)}, modules, symbols


def _dependency_summary(
    settings: Settings, project: ProjectResponse, modules: list[dict[str, object]]
) -> dict[str, object]:
    root = _project_path(settings, project)
    imports: Counter[str] = Counter()
    scanned = 0
    if root is not None:
        for entry in modules:
            if entry.get("language") != "python" or not isinstance(entry.get("path"), str):
                continue
            relative = cast(str, entry["path"])
            if ".." in relative.split("/") or "\\" in relative:
                continue
            candidate = root.joinpath(*relative.split("/"))
            try:
                source = candidate.read_bytes()
                if len(source) > 100_000:
                    continue
                tree = ast.parse(source.decode("utf-8"), filename=relative)
            except (OSError, UnicodeError, SyntaxError):
                continue
            scanned += 1
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for item in node.names:
                        imports[item.name.split(".", 1)[0]] += 1
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports[node.module.split(".", 1)[0]] += 1
    dependencies = [
        {"name": name, "observations": count} for name, count in imports.most_common(FULL_LIST_MAX)
    ]
    return _details(
        {
            "scanned_python_modules": scanned,
            "dependency_count": len(dependencies),
            "dependencies": dependencies,
            "source": "repository-index-files:bounded-python-imports",
        }
    )


def _memory_details(settings: Settings, project_id: UUID) -> tuple[FullStatus, dict[str, object]]:
    records = list_memories(settings, project_id, None, FULL_LIST_MAX)
    items = []
    for record in records:
        items.append(
            {
                "memory_id": str(record.memory_id),
                "type": record.type.value,
                "status": record.status.value,
                "content": _text(record.content),
                "source": _text(record.source),
                "source_commit": record.source_commit,
                "confidence": record.confidence,
                "importance": record.importance,
                "updated_at": record.updated_at.isoformat(),
            }
        )
    return FullStatus.AVAILABLE, _details(
        {
            "record_count": len(items),
            "canonical_count": sum(
                item["status"] == MemoryStatus.CANONICAL.value for item in items
            ),
            "staged_count": sum(
                item["status"] in {"OBSERVATION", "INFERRED", "PROPOSED", "CONFIRMED"}
                for item in items
            ),
            "records": items,
            "source": "postgres:memory_records",
        }
    )


def _retrieval_details(
    settings: Settings, project_id: UUID
) -> tuple[FullStatus, dict[str, object]]:
    corpus = corpus_status(settings, project_id)
    try:
        semantic = semantic_status(settings, project_id)
        semantic_payload: dict[str, object] = {
            "state": semantic.state.value,
            "enabled": semantic.enabled,
            "configured": semantic.configured,
            "total_current_chunks": semantic.total_current_chunks,
            "embedded_chunk_count": semantic.embedded_chunk_count,
            "missing_chunk_count": semantic.missing_chunk_count,
            "last_error": _text(semantic.last_error) if semantic.last_error else None,
        }
    except (psycopg.Error, RuntimeError):
        semantic_payload = {"state": FullStatus.UNAVAILABLE.value}
    status = FullStatus.AVAILABLE
    if corpus.state in {"STALE", "BLOCKED"} or (
        corpus.latest_run is not None and corpus.latest_run.status is CorpusRunStatus.FAILED
    ):
        status = FullStatus.DEGRADED
    return status, _details(
        {
            "corpus_state": corpus.state.value,
            "chunk_count": corpus.chunk_count,
            "reference_count": corpus.reference_count,
            "repository_reference_count": corpus.repository_reference_count,
            "task_reference_count": corpus.task_reference_count,
            "last_successful_sync": corpus.last_successful_sync.isoformat()
            if corpus.last_successful_sync
            else None,
            "semantic": semantic_payload,
            "source": "postgres:retrieval_corpus_and_semantic_status",
        }
    )


def _capability(
    capability_id: str,
    status: FullStatus,
    summary: str,
    provenance: MetricProvenance,
    details: dict[str, object],
) -> Capability:
    return Capability(
        id=capability_id,
        status=status,
        summary=summary,
        provenance=provenance,
        details=details,
    )


def _provenance_from_payload(event: EventEnvelope, key: str) -> MetricProvenance:
    return _provenance(event, key)


def _events_for_project(settings: Settings, project_id: UUID) -> tuple[list[EventEnvelope], bool]:
    page = list_recent_events(settings, project_id, limit=EVENT_PAGE_MAX_SIZE)
    return page.events, page.has_more


def _chart(
    chart_id: str,
    points: list[ChartPoint],
    truncated: bool = False,
    *,
    max_points: int = FULL_CHART_MAX_POINTS,
) -> Chart:
    bounded = points[-max_points:]
    return Chart(
        id=chart_id,
        status=FullStatus.AVAILABLE if bounded else FullStatus.UNAVAILABLE,
        points=bounded,
        max_points=max_points,
        truncated=truncated or len(points) > len(bounded),
    )


def _charts(
    settings: Settings,
    project: ProjectResponse,
    events: list[EventEnvelope],
    events_truncated: bool,
    history_points: int,
) -> list[Chart]:
    token_points: list[ChartPoint] = []
    cached_fresh: list[ChartPoint] = []
    savings: list[ChartPoint] = []
    context_reduction: list[ChartPoint] = []
    context_ratio: list[ChartPoint] = []
    cache_rates: list[ChartPoint] = []
    activity: list[ChartPoint] = []
    retrieval_latency: list[ChartPoint] = []
    service_latency: list[ChartPoint] = []
    cache_hits = 0
    cache_total = 0
    activity_counts: Counter[str] = Counter()
    for event in events:
        activity_counts[event.event_type] += 1
        for key in ("input_tokens", "output_tokens", "token_count", "token_budget"):
            numeric = _number(event.payload.get(key))
            if numeric is not None and numeric >= 0:
                token_points.append(
                    ChartPoint(
                        observed_at=event.occurred_at,
                        value=numeric,
                        provenance=_provenance_from_payload(event, key),
                        source=f"postgres:telemetry_events.payload.{key}",
                        series=key,
                    )
                )
        cached = _number(event.payload.get("cached_tokens"))
        fresh = _number(event.payload.get("fresh_tokens"))
        input_tokens = _number(event.payload.get("input_tokens"))
        if fresh is None and input_tokens is not None and cached is not None:
            fresh = max(input_tokens - cached, 0)
        if cached is not None and cached >= 0:
            cached_fresh.append(
                ChartPoint(
                    observed_at=event.occurred_at,
                    value=cached,
                    provenance=_provenance_from_payload(event, "cached_tokens"),
                    source="postgres:telemetry_events.payload.cached_tokens",
                    series="cached",
                )
            )
        if fresh is not None and fresh >= 0:
            cached_fresh.append(
                ChartPoint(
                    observed_at=event.occurred_at,
                    value=fresh,
                    provenance=_provenance_from_payload(event, "fresh_tokens"),
                    source="derived:input_tokens-minus-cached_tokens",
                    series="fresh",
                )
            )
        token_savings = _number(event.payload.get("token_savings"))
        if token_savings is None and input_tokens is not None and cached is not None:
            token_savings = cached
        if token_savings is not None and token_savings >= 0:
            savings.append(
                ChartPoint(
                    observed_at=event.occurred_at,
                    value=token_savings,
                    provenance=_provenance_from_payload(event, "token_savings"),
                    source="postgres:telemetry_events.payload.token_savings-or-cached_tokens",
                    series="token-savings",
                )
            )
        before = _number(event.payload.get("estimated_tokens_before"))
        after = _number(event.payload.get("estimated_tokens_after"))
        if before is not None and after is not None and before >= 0 and after >= 0:
            reduction = before - after
            provenance = MetricProvenance.ESTIMATED
            context_reduction.append(
                ChartPoint(
                    observed_at=event.occurred_at,
                    value=reduction,
                    provenance=provenance,
                    source="derived:context-before-minus-after",
                    series="reduction_tokens",
                )
            )
            if before > 0:
                context_ratio.append(
                    ChartPoint(
                        observed_at=event.occurred_at,
                        value=reduction / before,
                        provenance=provenance,
                        source="derived:context-reduction-ratio",
                        series="reduction_ratio",
                    )
                )
        if event.event_type == "cache.hit":
            cache_hits += 1
            cache_total += 1
        elif event.event_type == "cache.miss":
            cache_total += 1
        if event.event_type in {"cache.hit", "cache.miss"} and cache_total:
            cache_rates.append(
                ChartPoint(
                    observed_at=event.occurred_at,
                    value=cache_hits / cache_total,
                    provenance=MetricProvenance.EXACT,
                    source="derived:canonical-cache-events",
                    series="hit_rate",
                )
            )
        latency = _number(event.payload.get("latency_ms"))
        if latency is not None and latency >= 0:
            target = retrieval_latency if "retriev" in event.event_type else service_latency
            target.append(
                ChartPoint(
                    observed_at=event.occurred_at,
                    value=latency,
                    provenance=_provenance_from_payload(event, "latency_ms"),
                    source="postgres:telemetry_events.payload.latency_ms",
                    series="latency_ms",
                )
            )
    activity = [
        ChartPoint(
            observed_at=None,
            value=count,
            provenance=MetricProvenance.EXACT,
            source="postgres:telemetry_events",
            series=event_type,
        )
        for event_type, count in sorted(activity_counts.items())
    ]
    storage = observe_project_storage(settings, project.project_id)
    storage_points = [
        ChartPoint(
            observed_at=None,
            value=storage.logical_task_bytes,
            provenance=MetricProvenance.EXACT,
            source="postgres:tasks.logical_size",
            series="logical",
        ),
        ChartPoint(
            observed_at=None,
            value=storage.physical_referenced_bytes,
            provenance=MetricProvenance.EXACT,
            source="postgres:cas_blobs.physical_size",
            series="physical",
        ),
    ]
    savings_points = [
        ChartPoint(
            observed_at=None,
            value=max(storage.logical_task_bytes - storage.physical_referenced_bytes, 0),
            provenance=MetricProvenance.EXACT,
            source="derived:logical-physical-storage",
            series="storage-savings",
        )
    ]
    return [
        _chart("tokens-over-time", token_points, events_truncated, max_points=history_points),
        _chart("cached-vs-fresh-tokens", cached_fresh, events_truncated, max_points=history_points),
        _chart("token-savings", savings, events_truncated, max_points=history_points),
        Chart(
            id="cost-over-time",
            status=FullStatus.UNAVAILABLE,
            points=[],
            max_points=FULL_CHART_MAX_POINTS,
            truncated=False,
        ),
        _chart("cache-hit-rate", cache_rates, events_truncated, max_points=history_points),
        _chart("context-reduction", context_reduction, events_truncated, max_points=history_points),
        _chart("context-signal-ratio", context_ratio, events_truncated, max_points=history_points),
        _chart("physical-vs-logical-storage", storage_points, max_points=history_points),
        _chart("compression-dedup-savings", savings_points, max_points=history_points),
        _chart("project-activity", activity, events_truncated, max_points=history_points),
        _chart(
            "test-pass-failure-rate",
            _quality_points(events),
            events_truncated,
            max_points=history_points,
        ),
        _chart("retrieval-latency", retrieval_latency, events_truncated, max_points=history_points),
        _chart(
            "service-latency-errors", service_latency, events_truncated, max_points=history_points
        ),
    ]


def _quality_points(events: list[EventEnvelope]) -> list[ChartPoint]:
    passed = 0
    failed = 0
    points: list[ChartPoint] = []
    for event in events:
        if event.event_type in {"validation.passed", "test.finished"} and (
            event.event_type == "validation.passed" or event.payload.get("passed") is True
        ):
            passed += 1
        elif event.event_type in {"validation.failed", "run.failed"} or (
            event.event_type == "test.finished" and event.payload.get("passed") is False
        ):
            failed += 1
        if passed + failed:
            points.append(
                ChartPoint(
                    observed_at=event.occurred_at,
                    value=passed / (passed + failed),
                    provenance=MetricProvenance.EXACT,
                    source="derived:canonical-test-validation-events",
                    series="pass_rate",
                )
            )
    return points


def _alert(
    alert_id: str,
    status: FullStatus,
    summary: str,
    provenance: MetricProvenance,
    source: str,
    severity: str = "WARNING",
) -> Alert:
    return Alert(
        id=alert_id,
        status=status,
        severity=severity,
        summary=_text(summary),
        provenance=provenance,
        source=source,
    )


def _alerts(
    settings: Settings,
    project: ProjectResponse,
    events: list[EventEnvelope],
    index_status: FullStatus,
    retrieval_status: FullStatus,
    health: list[HealthSurface],
) -> list[Alert]:
    container = next((surface for surface in health if surface.id == "container-status"), None)
    raw_checks = container.details.get("checks") if container else None
    service_checks = raw_checks if isinstance(raw_checks, dict) else {}

    def service_alert_status(service: str) -> FullStatus:
        check = service_checks.get(service)
        if not isinstance(check, str):
            return FullStatus.UNKNOWN
        return FullStatus.CLEAR if check == "ok" else FullStatus.ACTIVE

    redis_status = service_alert_status("redis")
    postgres_status = service_alert_status("postgres")
    disk = next((surface for surface in health if surface.id == "platform-resource-health"), None)
    disk_free_ratio = disk.details.get("free_ratio") if disk else None
    disk_alert = (
        FullStatus.ACTIVE
        if isinstance(disk_free_ratio, int | float) and disk_free_ratio < 0.10
        else FullStatus.CLEAR
        if isinstance(disk_free_ratio, int | float)
        else FullStatus.UNAVAILABLE
    )
    cache_total = sum(event.event_type in {"cache.hit", "cache.miss"} for event in events)
    cache_hits = sum(event.event_type == "cache.hit" for event in events)
    cache_alert = (
        FullStatus.ACTIVE
        if cache_total >= 5 and cache_hits / cache_total < 0.20
        else FullStatus.CLEAR
        if cache_total >= 5
        else FullStatus.UNKNOWN
    )
    token_values = [
        value
        for event in events
        for key in ("input_tokens", "output_tokens", "token_count")
        for value in [_number(event.payload.get(key))]
        if value is not None and value >= 0
    ]
    token_spike = (
        FullStatus.ACTIVE
        if len(token_values) >= 3
        and token_values[-1] > (sum(token_values[:-1]) / len(token_values[:-1])) * 2
        else FullStatus.CLEAR
        if len(token_values) >= 3
        else FullStatus.UNKNOWN
    )
    test_events = [
        event
        for event in events
        if event.event_type in {"validation.passed", "validation.failed", "test.finished"}
    ]
    failed_tests = any(
        event.event_type == "validation.failed"
        or event.event_type == "test.finished"
        and event.payload.get("passed") is False
        for event in test_events
    )
    passed_tests = any(
        event.event_type == "validation.passed"
        or event.event_type == "test.finished"
        and event.payload.get("passed") is True
        for event in test_events
    )
    if failed_tests:
        test_status = FullStatus.ACTIVE
    elif passed_tests:
        test_status = FullStatus.CLEAR
    else:
        test_status = FullStatus.UNKNOWN
    executor_events = [event for event in events if event.event_type == "executor.started"]
    executor_status = FullStatus.CLEAR if not executor_events else FullStatus.AVAILABLE
    checkpoint = _document_observations(settings, project)[0]
    checkpoint_status = FullStatus.UNKNOWN
    checkpoint_source = "canonical-checkpoint-head-comparison"
    root = _project_path(settings, project)
    if checkpoint.status is FullStatus.AVAILABLE and root is not None:
        try:
            checkpoint_file = root / Path(*checkpoint.path.split("/"))
            content = checkpoint_file.read_text(encoding="utf-8")[:200_000]
            checkpoint_status = (
                FullStatus.CLEAR
                if project.git_head_sha and project.git_head_sha.lower() in content.lower()
                else FullStatus.UNKNOWN
            )
        except (OSError, UnicodeError):
            checkpoint_status = FullStatus.UNAVAILABLE
    return [
        _alert(
            "disk-low",
            disk_alert,
            "disk free space is below the deterministic threshold"
            if disk_alert is FullStatus.ACTIVE
            else "disk free space is above the deterministic threshold"
            if disk_alert is FullStatus.CLEAR
            else "disk free space is unavailable",
            MetricProvenance.EXACT
            if disk_alert is not FullStatus.UNAVAILABLE
            else MetricProvenance.UNAVAILABLE,
            "platform-resource-health",
        ),
        _alert(
            "redis-unavailable",
            redis_status,
            "Redis health check is degraded"
            if redis_status is FullStatus.ACTIVE
            else "Redis health check is clear"
            if redis_status is FullStatus.CLEAR
            else "Redis health check is unavailable",
            MetricProvenance.EXACT
            if redis_status is not FullStatus.UNKNOWN
            else MetricProvenance.UNAVAILABLE,
            "health:redis",
        ),
        _alert(
            "postgres-unavailable",
            postgres_status,
            "PostgreSQL health check requires attention"
            if postgres_status is FullStatus.ACTIVE
            else "PostgreSQL health check is clear"
            if postgres_status is FullStatus.CLEAR
            else "PostgreSQL health check is unavailable",
            MetricProvenance.EXACT
            if postgres_status is not FullStatus.UNKNOWN
            else MetricProvenance.UNAVAILABLE,
            "health:postgres",
        ),
        _alert(
            "project-stale",
            FullStatus.ACTIVE if project.state is ProjectState.STALE else FullStatus.CLEAR,
            "project registry marks this project STALE"
            if project.state is ProjectState.STALE
            else "project registry is not STALE",
            MetricProvenance.EXACT,
            "postgres:projects.state",
        ),
        _alert(
            "index-inconsistent",
            FullStatus.ACTIVE
            if index_status is FullStatus.DEGRADED
            else FullStatus.CLEAR
            if index_status is FullStatus.AVAILABLE
            else FullStatus.UNKNOWN,
            "repository index is inconsistent with the registered HEAD"
            if index_status is FullStatus.DEGRADED
            else "repository index matches the registered HEAD"
            if index_status is FullStatus.AVAILABLE
            else "repository index has no qualifying observation",
            MetricProvenance.EXACT,
            "postgres:repository_index_runs",
        ),
        _alert(
            "retrieval-degradation",
            FullStatus.ACTIVE
            if retrieval_status is FullStatus.DEGRADED
            else FullStatus.CLEAR
            if retrieval_status is FullStatus.AVAILABLE
            else FullStatus.UNKNOWN,
            "retrieval corpus is stale or blocked"
            if retrieval_status is FullStatus.DEGRADED
            else "retrieval corpus is current"
            if retrieval_status is FullStatus.AVAILABLE
            else "retrieval quality is unknown",
            MetricProvenance.EXACT,
            "postgres:retrieval_corpus_runs",
        ),
        _alert(
            "cache-hit-collapse",
            cache_alert,
            "cache hit rate is below 20%"
            if cache_alert is FullStatus.ACTIVE
            else "cache hit rate is not collapsed"
            if cache_alert is FullStatus.CLEAR
            else "fewer than five cache decisions are available",
            MetricProvenance.EXACT
            if cache_alert is not FullStatus.UNKNOWN
            else MetricProvenance.UNAVAILABLE,
            "derived:canonical-cache-events",
        ),
        _alert(
            "token-spike",
            token_spike,
            "latest observed token value is above twice the bounded baseline"
            if token_spike is FullStatus.ACTIVE
            else "no token spike observed"
            if token_spike is FullStatus.CLEAR
            else "insufficient token history for a spike comparison",
            MetricProvenance.EXACT
            if token_spike is not FullStatus.UNKNOWN
            else MetricProvenance.UNAVAILABLE,
            "derived:bounded-token-history",
        ),
        _alert(
            "unexpected-cost-spike",
            FullStatus.UNAVAILABLE,
            "provider cost telemetry is not configured",
            MetricProvenance.UNAVAILABLE,
            "cost-provenance:UNAVAILABLE",
        ),
        _alert(
            "failed-test-build",
            test_status,
            "a validation or test event failed"
            if test_status is FullStatus.ACTIVE
            else "latest observed validation/test outcome passed"
            if test_status is FullStatus.CLEAR
            else "no test/build outcome is recorded",
            MetricProvenance.EXACT
            if test_status is not FullStatus.UNKNOWN
            else MetricProvenance.UNAVAILABLE,
            "postgres:telemetry_events",
        ),
        _alert(
            "executor-disconnected",
            executor_status,
            "executor telemetry is observed"
            if executor_events
            else "no executor disconnect signal is recorded",
            MetricProvenance.EXACT,
            "postgres:telemetry_events.executor.started",
        ),
        _alert(
            "checkpoint-mismatch",
            FullStatus.ACTIVE if checkpoint_status is FullStatus.ACTIVE else checkpoint_status,
            "checkpoint does not contain the registered project HEAD"
            if checkpoint_status is FullStatus.ACTIVE
            else "checkpoint/head mismatch is not positively established"
            if checkpoint_status is FullStatus.UNKNOWN
            else "checkpoint/head observation is unavailable"
            if checkpoint_status is FullStatus.UNAVAILABLE
            else "checkpoint contains the registered project HEAD",
            MetricProvenance.EXACT
            if checkpoint_status is not FullStatus.UNKNOWN
            else MetricProvenance.UNAVAILABLE,
            checkpoint_source,
        ),
    ]


def _health_surfaces(settings: Settings) -> list[HealthSurface]:
    report = collect_health(settings)
    try:
        migration = observed_schema_revision(settings)
    except psycopg.Error:
        migration = None
    resource_details: dict[str, object] = {"migration_head": migration or "UNAVAILABLE"}
    try:
        root = (
            settings.resolved_data_root
            if settings.resolved_data_root.exists()
            else settings.resolved_data_root.parent
        )
        usage = shutil.disk_usage(root)
        resource_details.update(
            {
                "total_bytes": usage.total,
                "free_bytes": usage.free,
                "free_ratio": usage.free / usage.total if usage.total else None,
                "source": "filesystem:disk_usage",
            }
        )
        resource_status = FullStatus.AVAILABLE
        resource_provenance = MetricProvenance.EXACT
    except OSError:
        resource_status = FullStatus.UNAVAILABLE
        resource_provenance = MetricProvenance.UNAVAILABLE
    checks = {name: value.status for name, value in report.checks.items()}
    container_status = FullStatus.AVAILABLE if checks else FullStatus.UNAVAILABLE
    if any(value != "ok" for value in checks.values()):
        container_status = FullStatus.DEGRADED
    model_configured = bool(settings.embedding_enabled or settings.rerank_enabled)
    model_status = FullStatus.AVAILABLE if model_configured else FullStatus.NOT_CONFIGURED
    return [
        HealthSurface(
            id="platform-resource-health",
            status=resource_status,
            summary="filesystem resources are observed without exposing host paths"
            if resource_status is FullStatus.AVAILABLE
            else "filesystem resource health is unavailable",
            provenance=resource_provenance,
            details=_details(resource_details),
        ),
        HealthSurface(
            id="container-status",
            status=container_status,
            summary="configured service health checks are available"
            if container_status is FullStatus.AVAILABLE
            else "one or more configured service health checks are degraded"
            if container_status is FullStatus.DEGRADED
            else "service health checks are unavailable",
            provenance=MetricProvenance.EXACT if checks else MetricProvenance.UNAVAILABLE,
            details=_details(
                {
                    "checks": checks,
                    "canonical_store": "postgres",
                    "hot_store": "redis",
                    "hot_store_canonical": False,
                }
            ),
        ),
        HealthSurface(
            id="local-model-health-conditional",
            status=model_status,
            summary=(
                "local model integration is configured; provider reachability is not probed "
                "by deterministic evidence"
                if model_configured
                else "local model integration is not configured"
            ),
            provenance=MetricProvenance.EXACT,
            details=_details(
                {
                    "embedding_enabled": settings.embedding_enabled,
                    "rerank_enabled": settings.rerank_enabled,
                    "provider_calls": 0,
                }
            ),
        ),
    ]


def build_full_control_center(
    settings: Settings,
    project_id: UUID,
    history_points: int = FULL_HISTORY_MAX_POINTS,
) -> ControlCenterFullResponse:
    if not 1 <= history_points <= FULL_HISTORY_MAX_POINTS:
        raise ValueError("full Control Center history bound is outside its limit")
    project = get_project(settings, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    events, event_truncated = _events_for_project(settings, project_id)
    index_status, index_details = _index_details(settings, project)
    _, modules, symbols = _repository_inventory(settings, project_id)
    retrieval_status, retrieval_details = _retrieval_details(settings, project_id)
    documents = _document_observations(settings, project)
    commits = _git_commits(settings, project)
    runs = summarize_runs(settings, project_id, limit=FULL_LIST_MAX)
    try:
        memory_status, memory_details = _memory_details(settings, project_id)
    except (psycopg.Error, RuntimeError):
        memory_status, memory_details = (
            FullStatus.UNAVAILABLE,
            {"reason": "memory_observation_unavailable"},
        )
    health = _health_surfaces(settings)
    capabilities = [
        _capability(
            "project-intelligence",
            FullStatus.AVAILABLE,
            "registry identity and project state are visible",
            MetricProvenance.EXACT,
            _details(
                {
                    "branch": project.git_branch or "UNAVAILABLE",
                    "head": project.git_head_sha or "UNAVAILABLE",
                    "relative_path": project.relative_path,
                    "state": project.state.value,
                }
            ),
        ),
        _capability(
            "checkpoint-scope-dod",
            FullStatus.AVAILABLE
            if all(item.status is FullStatus.AVAILABLE for item in documents)
            else FullStatus.UNAVAILABLE,
            (
                "canonical checkpoint, scope and Definition of Done documents are observed "
                "by project-relative identity"
            ),
            MetricProvenance.EXACT,
            _details({"documents": [item.model_dump(mode="json") for item in documents]}),
        ),
        _capability(
            "index-health",
            index_status,
            "repository index status is compared with the registered HEAD",
            MetricProvenance.EXACT,
            index_details,
        ),
        _capability(
            "latest-commits",
            FullStatus.AVAILABLE if commits else FullStatus.UNAVAILABLE,
            "bounded Git commit history is visible",
            MetricProvenance.EXACT if commits else MetricProvenance.UNAVAILABLE,
            _details(
                {
                    "commits": [item.model_dump(mode="json") for item in commits],
                    "max_commits": FULL_COMMIT_MAX,
                }
            ),
        ),
        _capability(
            "run-history",
            FullStatus.AVAILABLE if runs else FullStatus.UNAVAILABLE,
            "durable telemetry run aggregates are visible",
            MetricProvenance.EXACT if runs else MetricProvenance.UNAVAILABLE,
            _details(
                {"run_count": len(runs), "runs": [item.model_dump(mode="json") for item in runs]}
            ),
        ),
        _capability(
            "decisions-memory",
            memory_status,
            "canonical and staged memory records are visible with provenance",
            MetricProvenance.EXACT
            if memory_status is FullStatus.AVAILABLE
            else MetricProvenance.UNAVAILABLE,
            memory_details,
        ),
        _capability(
            "modules-symbols",
            FullStatus.AVAILABLE if modules else FullStatus.UNAVAILABLE,
            "bounded repository modules and indexed symbols are visible",
            MetricProvenance.EXACT if modules else MetricProvenance.UNAVAILABLE,
            _details(
                {
                    "modules": modules,
                    "symbols": symbols,
                    "module_count": len(modules),
                    "symbol_count": len(symbols),
                }
            ),
        ),
        _capability(
            "dependency-graph",
            FullStatus.AVAILABLE,
            "bounded Python import observations are derived from indexed project files",
            MetricProvenance.EXACT,
            _dependency_summary(settings, project, modules),
        ),
        _capability(
            "quality-history",
            FullStatus.AVAILABLE if _quality_points(events) else FullStatus.UNAVAILABLE,
            "test and validation history is derived from canonical telemetry",
            MetricProvenance.EXACT if _quality_points(events) else MetricProvenance.UNAVAILABLE,
            _details(
                {
                    "observed_events": sum(
                        event.event_type
                        in {
                            "test.started",
                            "test.finished",
                            "validation.passed",
                            "validation.failed",
                        }
                        for event in events
                    )
                }
            ),
        ),
        _capability(
            "retrieval-quality",
            retrieval_status,
            "retrieval corpus and conditional semantic status are visible",
            MetricProvenance.EXACT,
            retrieval_details,
        ),
    ]
    charts = _charts(settings, project, events, event_truncated, history_points)
    return ControlCenterFullResponse(
        control_center_full_version=FULL_EVIDENCE_VERSION,
        generated_at=_now(),
        project_id=project_id,
        project=_headline(project),
        capabilities=capabilities,
        charts=charts,
        alerts=_alerts(settings, project, events, index_status, retrieval_status, health),
        health=health,
        canonical_store="postgres",
        hot_store="redis",
        hot_store_canonical=False,
        history_max_points=history_points,
        project_scoped=True,
        full_v01_complete_claimed=False,
    )


router = APIRouter(tags=["control-center"])


@router.get(
    "/api/v1/control-center/projects/{project_id}/full",
    response_model=ControlCenterFullResponse,
)
def control_center_full(
    project_id: UUID,
    history_points: int = Query(default=FULL_HISTORY_MAX_POINTS, ge=1, le=FULL_HISTORY_MAX_POINTS),
) -> ControlCenterFullResponse:
    try:
        return build_full_control_center(get_settings(), project_id, history_points)
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(
            status_code=503, detail="full control center database unavailable"
        ) from exc
