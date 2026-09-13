"""WO-021 truthful bounded Control Center metrics surfaces."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

import psycopg
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from .config import get_settings
from .registry import get_project, list_projects
from .task_intake import storage_stats
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


router = APIRouter(tags=["control-center"])
