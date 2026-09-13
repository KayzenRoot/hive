"""WO-021 truthful bounded Control Center metrics surfaces."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

import psycopg
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from .config import Settings, get_settings
from .control_center_storage_metrics import StorageObservation, observe_project_storage
from .registry import get_project, list_projects
from .telemetry import EventEnvelope, list_recent_events

METRICS_EVIDENCE_VERSION = "control-center-metrics-v1"
METRICS_HISTORY_MAX_POINTS = 100
TOKEN_KEYS = (
    "input_tokens",
    "output_tokens",
    "cached_tokens",
    "fresh_tokens",
    "token_count",
    "token_budget",
    "token_savings",
)
CONTEXT_EVENTS = frozenset({"context.started", "context.retrieved", "context.built"})


class MetricProvenance(StrEnum):
    EXACT = "EXACT"
    ESTIMATED = "ESTIMATED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class MetricValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    value: float | int | None
    provenance: MetricProvenance
    source: str


class MetricsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    metrics_evidence_version: str
    generated_at: datetime
    scope: str
    project_id: UUID | None
    project_count: int = Field(ge=1)
    canonical_store: str
    hot_store: str
    hot_store_canonical: bool
    scanned_events: int = Field(ge=0)
    window_truncated: bool
    token: dict[str, MetricValue]
    context: dict[str, MetricValue]
    cache: dict[str, MetricValue]
    storage: dict[str, MetricValue]
    history: list[dict[str, object]]
    history_max_points: int = Field(ge=1, le=METRICS_HISTORY_MAX_POINTS)
    cost_provenance: MetricProvenance


def _now() -> datetime:
    return datetime.now(UTC)


def _missing(source: str) -> MetricValue:
    return MetricValue(value=None, provenance=MetricProvenance.UNAVAILABLE, source=source)


def _value(value: float | int, provenance: MetricProvenance, source: str) -> MetricValue:
    return MetricValue(value=value, provenance=provenance, source=source)


def _number(value: object) -> float | int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int | float) else None


def _provenance(event: EventEnvelope, key: str) -> MetricProvenance:
    candidates = (
        event.payload.get(f"{key}_provenance"),
        event.payload.get("metric_provenance"),
        event.payload.get("token_provenance"),
        event.payload.get("usage_provenance"),
        event.provenance.get(f"{key}_provenance"),
        event.provenance.get("metric_provenance"),
        event.provenance.get("usage_provenance"),
    )
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        normalized = candidate.upper()
        if normalized in MetricProvenance._value2member_map_:
            return MetricProvenance(normalized)
        if normalized in {"PROVIDER_FINAL", "RECONCILED", "FINAL"}:
            return MetricProvenance.EXACT
    if event.payload.get("provider_final_usage") is True or event.payload.get("usage_reconciled") is True:
        return MetricProvenance.EXACT
    if event.payload.get("estimated") is True or event.payload.get("tokens_estimated") is True:
        return MetricProvenance.ESTIMATED
    return MetricProvenance.UNKNOWN


def _aggregate(values: list[MetricValue], source: str) -> MetricValue:
    available = [item for item in values if item.value is not None]
    if not available:
        return _missing(source)
    total: float | int = sum(item.value for item in available if item.value is not None)
    provenances = {item.provenance for item in available}
    provenance = (
        MetricProvenance.UNKNOWN
        if MetricProvenance.UNKNOWN in provenances
        else MetricProvenance.ESTIMATED
        if MetricProvenance.ESTIMATED in provenances
        else MetricProvenance.EXACT
    )
    return _value(total, provenance, source)


def _token_metrics(events: list[EventEnvelope]) -> dict[str, MetricValue]:
    # One observation per run+metric. An explicit final/exact observation wins
    # over an earlier estimate; otherwise the newest same-quality value wins.
    selected: dict[tuple[str, str], tuple[float | int, MetricProvenance, datetime]] = {}
    rank = {MetricProvenance.EXACT: 3, MetricProvenance.ESTIMATED: 2, MetricProvenance.UNKNOWN: 1}
    for event in events:
        identity = str(event.run_id) if event.run_id is not None else f"event:{event.event_id}"
        for key in TOKEN_KEYS:
            numeric = _number(event.payload.get(key))
            if numeric is None or numeric < 0:
                continue
            candidate = (numeric, _provenance(event, key), event.occurred_at)
            current = selected.get((identity, key))
            if current is None or rank[candidate[1]] > rank[current[1]] or (
                rank[candidate[1]] == rank[current[1]] and candidate[2] >= current[2]
            ):
                selected[(identity, key)] = candidate

    identities = {identity for identity, _key in selected}
    for identity in identities:
        if (identity, "fresh_tokens") in selected:
            continue
        input_value = selected.get((identity, "input_tokens"))
        cached_value = selected.get((identity, "cached_tokens"))
        if input_value is None or cached_value is None:
            continue
        if MetricProvenance.UNKNOWN in {input_value[1], cached_value[1]}:
            continue
        provenance = (
            MetricProvenance.EXACT
            if input_value[1] == cached_value[1] == MetricProvenance.EXACT
            else MetricProvenance.ESTIMATED
        )
        selected[(identity, "fresh_tokens")] = (
            max(input_value[0] - cached_value[0], 0),
            provenance,
            max(input_value[2], cached_value[2]),
        )

    result: dict[str, MetricValue] = {}
    for key in TOKEN_KEYS:
        observations = [value for (_identity, metric_key), value in selected.items() if metric_key == key]
        result[key] = _aggregate(
            [_value(value[0], value[1], f"telemetry:{key}") for value in observations],
            f"telemetry-window:{key}",
        )
    return result


def _context_metrics(events: list[EventEnvelope]) -> dict[str, MetricValue]:
    measurements: list[tuple[float | int, float | int, MetricProvenance]] = []
    for event in events:
        if event.event_type not in CONTEXT_EVENTS:
            continue
        before = _number(event.payload.get("estimated_tokens_before"))
        after = _number(event.payload.get("estimated_tokens_after"))
        provenance = MetricProvenance.ESTIMATED
        if before is None or after is None:
            before = _number(event.payload.get("context_before_tokens"))
            after = _number(event.payload.get("context_after_tokens"))
            provenance = _provenance(event, "context_before_tokens")
        if before is not None and after is not None and before >= 0 and after >= 0:
            measurements.append((before, after, provenance))
    if not measurements:
        return {name: _missing("context-window") for name in ("before_tokens", "after_tokens", "reduction_tokens", "reduction_ratio")}
    before_total: float | int = sum(item[0] for item in measurements)
    after_total: float | int = sum(item[1] for item in measurements)
    provenances = {item[2] for item in measurements}
    provenance = (
        MetricProvenance.UNKNOWN
        if MetricProvenance.UNKNOWN in provenances
        else MetricProvenance.ESTIMATED
        if MetricProvenance.ESTIMATED in provenances
        else MetricProvenance.EXACT
    )
    reduction = before_total - after_total
    return {
        "before_tokens": _value(before_total, provenance, "context-window:before"),
        "after_tokens": _value(after_total, provenance, "context-window:after"),
        "reduction_tokens": _value(reduction, provenance, "derived:context-reduction"),
        "reduction_ratio": (
            _value(reduction / before_total, provenance, "derived:context-reduction-ratio")
            if before_total > 0
            else _missing("derived:context-reduction-ratio")
        ),
    }


def _cache_metrics(events: list[EventEnvelope]) -> dict[str, MetricValue]:
    hits = sum(event.event_type == "cache.hit" for event in events)
    misses = sum(event.event_type == "cache.miss" for event in events)
    total = hits + misses
    if total == 0:
        return {name: _missing("canonical-cache-events") for name in ("hits", "misses", "observed_decisions", "hit_rate")}
    return {
        "hits": _value(hits, MetricProvenance.EXACT, "canonical-cache-events"),
        "misses": _value(misses, MetricProvenance.EXACT, "canonical-cache-events"),
        "observed_decisions": _value(total, MetricProvenance.EXACT, "canonical-cache-events"),
        "hit_rate": _value(hits / total, MetricProvenance.EXACT, "canonical-cache-events"),
    }


def _storage_metrics(observation: StorageObservation) -> dict[str, MetricValue]:
    logical = observation.logical_task_bytes
    physical = observation.physical_referenced_bytes
    saved = logical - physical
    return {
        "logical_task_bytes": _value(logical, MetricProvenance.EXACT, "postgres:tasks.logical_size"),
        "physical_referenced_bytes": _value(physical, MetricProvenance.EXACT, "postgres:cas_blobs.physical_size"),
        "saved_bytes": _value(saved, MetricProvenance.EXACT, "derived:logical-physical"),
        "savings_ratio": (
            _value(saved / logical, MetricProvenance.EXACT, "derived:storage-savings-ratio")
            if logical > 0
            else _missing("derived:storage-savings-ratio")
        ),
        "task_count": _value(observation.task_count, MetricProvenance.EXACT, "postgres:tasks"),
        "referenced_blob_count": _value(observation.referenced_blob_count, MetricProvenance.EXACT, "postgres:tasks.original_blob_sha256"),
    }


def _history(events: list[EventEnvelope], limit: int) -> list[dict[str, object]]:
    points: list[dict[str, object]] = []
    for event in events:
        for key in TOKEN_KEYS:
            numeric = _number(event.payload.get(key))
            if numeric is not None and numeric >= 0:
                points.append({"family": "token", "name": key, "value": numeric, "provenance": _provenance(event, key).value, "observed_at": event.occurred_at.isoformat(), "event_type": event.event_type, "run_id": str(event.run_id) if event.run_id else None})
        if event.event_type in {"cache.hit", "cache.miss"}:
            points.append({"family": "cache", "name": "decision", "value": 1, "provenance": "EXACT", "observed_at": event.occurred_at.isoformat(), "event_type": event.event_type, "run_id": str(event.run_id) if event.run_id else None})
    return points[-limit:]


def _project_snapshot(settings: Settings, project_id: UUID, limit: int) -> MetricsResponse:
    if get_project(settings, project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    page = list_recent_events(settings, project_id, limit=limit)
    return MetricsResponse(
        metrics_evidence_version=METRICS_EVIDENCE_VERSION,
        generated_at=_now(),
        scope="PROJECT",
        project_id=project_id,
        project_count=1,
        canonical_store="postgres",
        hot_store="redis",
        hot_store_canonical=False,
        scanned_events=len(page.events),
        window_truncated=page.has_more,
        token=_token_metrics(page.events),
        context=_context_metrics(page.events),
        cache=_cache_metrics(page.events),
        storage=_storage_metrics(observe_project_storage(settings, project_id)),
        history=_history(page.events, limit),
        history_max_points=limit,
        cost_provenance=MetricProvenance.UNAVAILABLE,
    )


def _global_snapshot(settings: Settings, limit: int) -> MetricsResponse:
    projects = list_projects(settings)
    if not projects:
        raise HTTPException(status_code=404, detail="no registered projects")
    snapshots = [_project_snapshot(settings, project.project_id, limit) for project in projects]

    def family(names: tuple[str, ...], attr: str) -> dict[str, MetricValue]:
        return {
            name: _aggregate([getattr(snapshot, attr)[name] for snapshot in snapshots], f"global:{attr}:{name}")
            for name in names
        }

    token = family(TOKEN_KEYS, "token")
    context = family(("before_tokens", "after_tokens"), "context")
    before = context["before_tokens"]
    after = context["after_tokens"]
    if before.value is not None and after.value is not None:
        provenance = MetricProvenance.ESTIMATED if MetricProvenance.ESTIMATED in {before.provenance, after.provenance} else MetricProvenance.EXACT
        if MetricProvenance.UNKNOWN in {before.provenance, after.provenance}:
            provenance = MetricProvenance.UNKNOWN
        reduction = before.value - after.value
        context["reduction_tokens"] = _value(reduction, provenance, "global:context:reduction")
        context["reduction_ratio"] = _value(reduction / before.value, provenance, "global:context:ratio") if before.value > 0 else _missing("global:context:ratio")
    else:
        context["reduction_tokens"] = _missing("global:context:reduction")
        context["reduction_ratio"] = _missing("global:context:ratio")

    cache = family(("hits", "misses", "observed_decisions"), "cache")
    total = cache["observed_decisions"]
    hits = cache["hits"]
    cache["hit_rate"] = _value(hits.value / total.value, MetricProvenance.EXACT, "global:cache:hit-rate") if hits.value is not None and total.value is not None and total.value > 0 else _missing("global:cache:hit-rate")

    storage = family(("logical_task_bytes", "physical_referenced_bytes", "task_count", "referenced_blob_count"), "storage")
    logical = storage["logical_task_bytes"]
    physical = storage["physical_referenced_bytes"]
    if logical.value is not None and physical.value is not None:
        saved = logical.value - physical.value
        storage["saved_bytes"] = _value(saved, MetricProvenance.EXACT, "global:storage:saved")
        storage["savings_ratio"] = _value(saved / logical.value, MetricProvenance.EXACT, "global:storage:ratio") if logical.value > 0 else _missing("global:storage:ratio")
    else:
        storage["saved_bytes"] = _missing("global:storage:saved")
        storage["savings_ratio"] = _missing("global:storage:ratio")

    history = [point for snapshot in snapshots for point in snapshot.history][-limit:]
    return MetricsResponse(
        metrics_evidence_version=METRICS_EVIDENCE_VERSION,
        generated_at=_now(),
        scope="GLOBAL",
        project_id=None,
        project_count=len(projects),
        canonical_store="postgres",
        hot_store="redis",
        hot_store_canonical=False,
        scanned_events=sum(snapshot.scanned_events for snapshot in snapshots),
        window_truncated=any(snapshot.window_truncated for snapshot in snapshots),
        token=token,
        context=context,
        cache=cache,
        storage=storage,
        history=history,
        history_max_points=limit,
        cost_provenance=MetricProvenance.UNAVAILABLE,
    )


router = APIRouter(tags=["control-center"])


@router.get("/api/v1/control-center/metrics", response_model=MetricsResponse)
def control_center_metrics(project_id: UUID, history_points: int = Query(default=100, ge=1, le=100)) -> MetricsResponse:
    try:
        return _project_snapshot(get_settings(), project_id, history_points)
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="control center metrics database unavailable") from exc


@router.get("/api/v1/control-center/metrics/global", response_model=MetricsResponse)
def control_center_metrics_global(history_points: int = Query(default=100, ge=1, le=100)) -> MetricsResponse:
    try:
        return _global_snapshot(get_settings(), history_points)
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="control center metrics database unavailable") from exc
