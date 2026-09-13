"""Bounded full Control Center read model for WO-022.

This module is intentionally read-only.  It composes the existing canonical
Project Registry, repository index, telemetry event bus, retrieval corpus,
memory lifecycle and storage observations into one project-scoped view.  A
missing observation remains UNKNOWN or UNAVAILABLE; it is never changed into
zero merely to make a chart or alert look complete.
"""

from __future__ import annotations

import ast
import math
import os
import re
import shutil
import subprocess
from collections import Counter
from collections.abc import Sequence
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
FULL_CANONICAL_BLOB_MAX_BYTES = 200_000
FULL_CHART_MAX_POINTS = 100
FULL_COMMIT_MAX = 20
FULL_DOCUMENTS = (
    "docs/project-brain/13-CHECKPOINT.md",
    "docs/project-brain/03-SCOPE.md",
    "docs/project-brain/15-DEFINITION-OF-DONE.md",
)
DECISIONS_DOCUMENT = "docs/project-brain/16-DECISIONS-LEDGER.md"
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
    git_head_sha: str | None = None
    tracked: bool = False
    working_tree_clean: bool | None = None
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


def _git_command(root: Path, *arguments: str) -> str | None:
    command = [
        "git",
        "-c",
        f"safe.directory={root}",
        "-C",
        str(root),
        *arguments,
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
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _valid_git_head(value: str | None) -> bool:
    return value is not None and re.fullmatch(r"[0-9a-fA-F]{40,64}", value) is not None


def _document_observation(
    settings: Settings, project: ProjectResponse, relative: str
) -> DocumentObservation:
    root = _project_path(settings, project)
    repository_head = _git_command(root, "rev-parse", "--verify", "HEAD") if root else None
    registered_head = project.git_head_sha
    status = FullStatus.UNAVAILABLE
    size: int | None = None
    tracked = False
    working_tree_clean: bool | None = None
    source = "git:project-repository-unavailable"
    if root is not None:
        if not _valid_git_head(repository_head) or not _valid_git_head(registered_head):
            source = "git:HEAD-identity-unavailable"
        elif cast(str, repository_head).lower() != cast(str, registered_head).lower():
            source = "git:HEAD-does-not-match-registered-project"
        else:
            tracked = _git_command(root, "ls-files", "--error-unmatch", "--", relative) is not None
            if not tracked:
                source = "git:governance-document-not-tracked"
            else:
                dirty = _git_command(
                    root, "status", "--porcelain=v1", "--untracked-files=all", "--", relative
                )
                working_tree_clean = dirty == ""
                if not working_tree_clean:
                    source = "git:governance-document-working-tree-dirty"
                else:
                    blob_size = _git_command(
                        root, "cat-file", "-s", f"{repository_head}:{relative}"
                    )
                    try:
                        size = int(blob_size) if blob_size is not None else None
                    except ValueError:
                        size = None
                    if size is not None and size >= 0:
                        status = FullStatus.AVAILABLE
                        source = f"git:HEAD-blob:{relative}"
                    else:
                        source = "git:HEAD-blob-unavailable"
    return DocumentObservation(
        path=relative,
        status=status,
        byte_count=size,
        git_head_sha=repository_head if _valid_git_head(repository_head) else None,
        tracked=tracked,
        working_tree_clean=working_tree_clean,
        source=source,
    )


def _document_observations(
    settings: Settings, project: ProjectResponse
) -> list[DocumentObservation]:
    return [_document_observation(settings, project, relative) for relative in FULL_DOCUMENTS]


def _git_head_blob(
    settings: Settings,
    project: ProjectResponse,
    relative: str,
    observation: DocumentObservation | object,
) -> str | None:
    """Read bounded canonical bytes only after the exact Git identity checks."""

    status = getattr(observation, "status", None)
    status_value = getattr(status, "value", status)
    if status_value != FullStatus.AVAILABLE.value:
        return None
    if getattr(observation, "tracked", False) is not True:
        return None
    if getattr(observation, "working_tree_clean", None) is not True:
        return None
    observed_head = getattr(observation, "git_head_sha", None)
    registered_head = getattr(project, "git_head_sha", None)
    root = _project_path(settings, project)
    repository_head = _git_command(root, "rev-parse", "--verify", "HEAD") if root else None
    if (
        not _valid_git_head(repository_head)
        or not _valid_git_head(observed_head)
        or not _valid_git_head(registered_head)
        or cast(str, repository_head).lower() != cast(str, observed_head).lower()
        or cast(str, repository_head).lower() != cast(str, registered_head).lower()
    ):
        return None
    blob = _git_command(root, "cat-file", "blob", f"{repository_head}:{relative}") if root else None
    if blob is None:
        return None
    try:
        if len(blob.encode("utf-8")) > FULL_CANONICAL_BLOB_MAX_BYTES:
            return None
    except UnicodeError:
        return None
    return blob


def _markdown_section(text: str, heading: str) -> str | None:
    match = re.search(
        rf"^##[ \t]+{re.escape(heading)}[ \t]*\r?\n(?P<body>.*?)(?=^##[ \t]+|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    return match.group("body") if match else None


def _section_first_line(section: str | None) -> str | None:
    if section is None:
        return None
    for line in section.splitlines():
        value = line.strip()
        if value:
            return value
    return None


def _section_bullets(section: str | None) -> list[tuple[str, bool | None]]:
    if section is None:
        return []
    entries: list[tuple[str, bool | None]] = []
    for line in section.splitlines():
        match = re.match(r"^\s*-\s+(?:\[([ xX])\]\s+)?(\S.*)\s*$", line)
        if not match:
            continue
        checked = match.group(1)
        entries.append((match.group(2), None if checked is None else checked.lower() == "x"))
        if len(entries) >= FULL_LIST_MAX:
            break
    return entries


def _required_section_bullets(text: str, heading: str) -> list[tuple[str, bool | None]] | None:
    section = _markdown_section(text, heading)
    if section is None:
        return None
    entries = _section_bullets(section)
    return entries if entries else None


def _sanitized_texts(values: list[str]) -> list[str] | None:
    sanitized = [_text(value) for value in values]
    return sanitized if all(value != "UNAVAILABLE" for value in sanitized) else None


def _parse_checkpoint_document(blob: str) -> dict[str, object] | None:
    status = _section_first_line(_markdown_section(blob, "STATUS"))
    in_progress_entries = _required_section_bullets(blob, "IN PROGRESS")
    pending_entries = _required_section_bullets(blob, "PENDING")
    in_progress = (
        _sanitized_texts([value for value, _checked in in_progress_entries])
        if in_progress_entries is not None
        else None
    )
    pending_items = (
        _sanitized_texts([value for value, _checked in pending_entries])
        if pending_entries is not None
        else None
    )
    next_step = _section_first_line(_markdown_section(blob, "NEXT STEP"))
    if status is None or next_step is None or in_progress is None or pending_items is None:
        return None
    status_text = _text(status)
    next_step_text = _text(next_step)
    if status_text == "UNAVAILABLE" or next_step_text == "UNAVAILABLE":
        return None
    return {
        "current_status": status_text,
        "in_progress": in_progress,
        "pending": {
            "count": len(pending_items),
            "summary": _text(f"{len(pending_items)} pending item(s)"),
            "items": pending_items,
        },
        "next_step": next_step_text,
    }


def _parse_scope_document(blob: str) -> dict[str, object] | None:
    entries = _required_section_bullets(blob, "NECESSARY — V0.1")
    items = (
        _sanitized_texts([value for value, _checked in entries]) if entries is not None else None
    )
    if items is None:
        return None
    return {
        "summary": _text(f"NECESSARY — V0.1: {len(items)} required item(s)"),
        "required_items_count": len(items),
        "required_items": items,
    }


def _parse_definition_of_done(blob: str) -> dict[str, object] | None:
    section_headings = re.findall(r"^##[ \t]+(.+?)[ \t]*$", blob, flags=re.MULTILINE)
    entries: list[tuple[str, bool | None]] = []
    for heading in section_headings:
        entries.extend(_section_bullets(_markdown_section(blob, heading)))
        if len(entries) >= FULL_LIST_MAX:
            entries = entries[:FULL_LIST_MAX]
            break
    if not entries:
        return None
    item_payload = [{"text": _text(value), "completed": checked} for value, checked in entries]
    if any(item["text"] == "UNAVAILABLE" for item in item_payload):
        return None
    explicit_checklist = all(checked is not None for _value, checked in entries)
    if explicit_checklist:
        completed = sum(checked is True for _value, checked in entries)
        percentage = round((completed / len(entries)) * 100, 2)
        return {
            "status": FullStatus.AVAILABLE.value,
            "total_count": len(entries),
            "completed_count": completed,
            "percentage": percentage,
            "percentage_status": FullStatus.AVAILABLE.value,
            "checklist_grammar": "markdown-task-checkbox",
            "items": item_payload,
        }
    return {
        "status": FullStatus.UNAVAILABLE.value,
        "total_count": len(entries),
        "completed_count": None,
        "percentage": None,
        "percentage_status": FullStatus.UNAVAILABLE.value,
        "checklist_grammar": "unmarked-bullet-requirements",
        "items": item_payload,
        "reason": "explicit checklist/status grammar is absent; percentage is not inferred",
    }


def _document_payload(observation: DocumentObservation | object) -> dict[str, object]:
    model_dump = getattr(observation, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped
    return {
        "path": getattr(observation, "path", "UNAVAILABLE"),
        "status": getattr(getattr(observation, "status", None), "value", "UNAVAILABLE"),
        "byte_count": getattr(observation, "byte_count", None),
        "git_head_sha": getattr(observation, "git_head_sha", None),
        "tracked": getattr(observation, "tracked", False),
        "working_tree_clean": getattr(observation, "working_tree_clean", None),
        "source": getattr(observation, "source", "git:HEAD-identity-unavailable"),
    }


def _canonical_project_intelligence(
    settings: Settings,
    project: ProjectResponse,
    observations: Sequence[object],
) -> tuple[FullStatus, dict[str, object]]:
    by_path = {getattr(item, "path", None): item for item in observations}
    document_payload = [_document_payload(item) for item in observations]
    parsed: dict[str, dict[str, object]] = {}
    parsers = {
        FULL_DOCUMENTS[0]: _parse_checkpoint_document,
        FULL_DOCUMENTS[1]: _parse_scope_document,
        FULL_DOCUMENTS[2]: _parse_definition_of_done,
    }
    for relative, parser in parsers.items():
        observation = by_path.get(relative)
        blob = (
            _git_head_blob(settings, project, relative, observation)
            if observation is not None
            else None
        )
        parsed_document = parser(blob) if blob is not None else None
        if parsed_document is None:
            return FullStatus.UNAVAILABLE, _details(
                {
                    "status": FullStatus.UNAVAILABLE.value,
                    "provenance": MetricProvenance.UNAVAILABLE.value,
                    "reason": f"canonical Git HEAD blob parsing is unavailable for {relative}",
                    "documents": document_payload,
                    "source": "git:HEAD-blob:canonical-project-brain",
                }
            )
        parsed[relative] = {
            **parsed_document,
            "source": f"git:HEAD-blob:{relative}",
            "provenance": MetricProvenance.EXACT.value,
        }
    return FullStatus.AVAILABLE, _details(
        {
            "status": FullStatus.AVAILABLE.value,
            "provenance": MetricProvenance.EXACT.value,
            "documents": document_payload,
            "checkpoint": parsed[FULL_DOCUMENTS[0]],
            "scope": parsed[FULL_DOCUMENTS[1]],
            "definition_of_done": parsed[FULL_DOCUMENTS[2]],
            "source": "git:HEAD-blob:canonical-project-brain",
        }
    )


def _parse_decisions_ledger(blob: str) -> list[dict[str, object]] | None:
    headings = list(
        re.finditer(
            r"^##[ \t]+(HIVE-ADR-[0-9]+)[ \t]+[—-][ \t]+(.+?)[ \t]*$",
            blob,
            flags=re.MULTILINE,
        )
    )
    if not headings:
        return None
    decisions: list[dict[str, object]] = []
    for index, match in enumerate(headings[:FULL_LIST_MAX]):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(blob)
        section = blob[match.end() : end]
        status_match = re.search(r"^\*\*Status:\*\*[ \t]*(.+?)[ \t]*$", section, flags=re.MULTILINE)
        if status_match is None:
            return None
        identifier = _text(match.group(1))
        title = _text(match.group(2))
        decision_status = _text(status_match.group(1))
        if "UNAVAILABLE" in {identifier, title, decision_status}:
            return None
        decisions.append(
            {
                "id": identifier,
                "title": title,
                "status": decision_status,
                "source": f"git:HEAD-blob:{DECISIONS_DOCUMENT}",
                "provenance": MetricProvenance.EXACT.value,
            }
        )
    return decisions


def _decisions_details(
    settings: Settings, project: ProjectResponse
) -> tuple[FullStatus, dict[str, object]]:
    observation = _document_observation(settings, project, DECISIONS_DOCUMENT)
    blob = _git_head_blob(settings, project, DECISIONS_DOCUMENT, observation)
    decisions = _parse_decisions_ledger(blob) if blob is not None else None
    if decisions is None:
        return FullStatus.UNAVAILABLE, _details(
            {
                "status": FullStatus.UNAVAILABLE.value,
                "count": 0,
                "decisions": [],
                "reason": (
                    "canonical decisions ledger is missing, malformed, dirty or not HEAD-bound"
                ),
                "source": f"git:HEAD-blob:{DECISIONS_DOCUMENT}",
                "provenance": MetricProvenance.UNAVAILABLE.value,
            }
        )
    return FullStatus.AVAILABLE, _details(
        {
            "status": FullStatus.AVAILABLE.value,
            "count": len(decisions),
            "decisions": decisions,
            "source": f"git:HEAD-blob:{DECISIONS_DOCUMENT}",
            "provenance": MetricProvenance.EXACT.value,
        }
    )


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
) -> tuple[FullStatus, dict[str, object]]:
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
    languages = sorted(
        {
            str(entry["language"])
            for entry in modules
            if isinstance(entry.get("language"), str) and entry.get("language") != "python"
        }
    )
    python_modules = sum(entry.get("language") == "python" for entry in modules)
    if not modules:
        status = FullStatus.UNAVAILABLE
    elif languages:
        status = FullStatus.DEGRADED
    elif scanned == 0:
        status = FullStatus.UNKNOWN
    else:
        status = FullStatus.AVAILABLE
    return status, _details(
        {
            "scanned_python_modules": scanned,
            "python_module_count": python_modules,
            "dependency_count": len(dependencies),
            "dependencies": dependencies,
            "supported_languages": ["python"],
            "unsupported_languages": languages,
            "complete_graph": bool(python_modules) and not languages and scanned == python_modules,
            "limitations": [
                "only Python imports are analyzed",
                "non-Python imports are unavailable",
            ],
            "source": "repository-index-files:bounded-python-imports-only",
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
            "state": "AVAILABLE" if items else "NO_RECORDS",
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
        useful = _number(event.payload.get("useful_context_tokens"))
        total_sent = _number(event.payload.get("total_context_tokens_sent"))
        if (
            useful is not None
            and total_sent is not None
            and useful >= 0
            and total_sent > 0
            and useful <= total_sent
        ):
            context_ratio.append(
                ChartPoint(
                    observed_at=event.occurred_at,
                    value=useful / total_sent,
                    provenance=_provenance_from_payload(event, "useful_context_tokens"),
                    source="derived:useful-context-tokens-div-total-context-tokens-sent",
                    series="useful_context_ratio",
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


def _executor_connection_observation(
    events: list[EventEnvelope],
) -> tuple[FullStatus, str, MetricProvenance, str]:
    status = FullStatus.UNKNOWN
    source = "postgres:telemetry_events.executor-connection-evidence"
    summary = "no explicit executor heartbeat, connection, or disconnect evidence is recorded"
    for event in events:
        payload = event.payload
        connection_status = payload.get("connection_status")
        disconnected = (
            payload.get("executor_disconnected") is True
            or payload.get("disconnected") is True
            or isinstance(connection_status, str)
            and connection_status.lower() == "disconnected"
        )
        connected = (
            payload.get("executor_heartbeat") is True
            or payload.get("heartbeat") is True
            or isinstance(connection_status, str)
            and connection_status.lower() in {"connected", "heartbeat"}
        )
        if disconnected:
            status = FullStatus.ACTIVE
            summary = "explicit executor disconnect evidence is recorded"
        elif connected:
            status = FullStatus.CLEAR
            summary = "explicit executor heartbeat or connection evidence is recorded"
    provenance = (
        MetricProvenance.EXACT if status is not FullStatus.UNKNOWN else MetricProvenance.UNAVAILABLE
    )
    return status, summary, provenance, source


def _checkpoint_observation(
    settings: Settings,
    project: ProjectResponse,
    checkpoint: DocumentObservation,
) -> tuple[FullStatus, str, MetricProvenance, str]:
    root = _project_path(settings, project)
    repository_head = _git_command(root, "rev-parse", "--verify", "HEAD") if root else None
    registered_head = project.git_head_sha
    source = "git:HEAD-vs-postgres:projects.git_head_sha"
    if not _valid_git_head(repository_head) or not _valid_git_head(registered_head):
        return (
            FullStatus.UNAVAILABLE,
            "checkpoint/head comparison is unavailable because Git identity is incomplete",
            MetricProvenance.UNAVAILABLE,
            source,
        )
    if cast(str, repository_head).lower() != cast(str, registered_head).lower():
        return (
            FullStatus.ACTIVE,
            "registered project HEAD differs from the repository HEAD",
            MetricProvenance.EXACT,
            source,
        )
    if (
        checkpoint.status is not FullStatus.AVAILABLE
        or getattr(checkpoint, "tracked", False) is not True
        or getattr(checkpoint, "working_tree_clean", None) is not True
    ):
        return (
            FullStatus.UNAVAILABLE,
            "checkpoint mismatch is unavailable because canonical document identity is unproven",
            MetricProvenance.UNAVAILABLE,
            "git:canonical-checkpoint-document",
        )
    checkpoint_head = getattr(checkpoint, "git_head_sha", None)
    if (
        isinstance(checkpoint_head, str)
        and checkpoint_head.lower() != cast(str, repository_head).lower()
    ):
        return (
            FullStatus.ACTIVE,
            "checkpoint document observation is bound to a different repository HEAD",
            MetricProvenance.EXACT,
            "git:canonical-checkpoint-document-head",
        )
    return (
        FullStatus.CLEAR,
        "canonical checkpoint document is tracked and bound to the registered repository HEAD",
        MetricProvenance.EXACT,
        "git:canonical-checkpoint-document",
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
    executor_status, executor_summary, executor_provenance, executor_source = (
        _executor_connection_observation(events)
    )
    checkpoint = _document_observations(settings, project)[0]
    checkpoint_status, checkpoint_summary, checkpoint_provenance, checkpoint_source = (
        _checkpoint_observation(settings, project, checkpoint)
    )
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
            executor_summary,
            executor_provenance,
            executor_source,
        ),
        _alert(
            "checkpoint-mismatch",
            checkpoint_status,
            checkpoint_summary,
            checkpoint_provenance,
            checkpoint_source,
        ),
    ]


def _read_platform_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _health_surfaces(settings: Settings) -> list[HealthSurface]:
    report = collect_health(settings)
    try:
        migration = observed_schema_revision(settings)
    except psycopg.Error:
        migration = None
    resource_details: dict[str, object] = {"migration_head": migration or "UNAVAILABLE"}
    observations: dict[str, dict[str, object]] = {}

    def unavailable_observation(name: str, unit: str) -> dict[str, object]:
        return {
            "status": FullStatus.UNAVAILABLE.value,
            "value": None,
            "unit": unit,
            "provenance": MetricProvenance.UNAVAILABLE.value,
            "source": f"platform:{name}:unsupported-or-unavailable",
        }

    cpu_observation = unavailable_observation("cpu", "load_1m")
    try:
        load_average = float(_read_platform_text("/proc/loadavg").split()[0])
        if math.isfinite(load_average) and load_average >= 0:
            cpu_observation = {
                "status": FullStatus.AVAILABLE.value,
                "value": load_average,
                "unit": "load_1m",
                "provenance": MetricProvenance.EXACT.value,
                "source": "procfs:cpu-loadavg",
            }
    except (OSError, UnicodeError, IndexError, ValueError):
        pass
    observations["cpu"] = cpu_observation

    ram_observation = unavailable_observation("ram", "bytes")
    try:
        memory: dict[str, int] = {}
        for line in _read_platform_text("/proc/meminfo").splitlines():
            key, separator, raw_value = line.partition(":")
            if separator and key in {"MemTotal", "MemAvailable"}:
                parts = raw_value.strip().split()
                if parts and parts[0].isdigit():
                    memory[key] = int(parts[0]) * 1024
        total = memory.get("MemTotal")
        available = memory.get("MemAvailable")
        if total is not None and available is not None and total > 0 and 0 <= available <= total:
            ram_observation = {
                "status": FullStatus.AVAILABLE.value,
                "total_bytes": total,
                "available_bytes": available,
                "used_ratio": (total - available) / total,
                "unit": "bytes",
                "provenance": MetricProvenance.EXACT.value,
                "source": "procfs:memory-info",
            }
    except (OSError, UnicodeError, ValueError):
        pass
    observations["ram"] = ram_observation

    disk_observation = unavailable_observation("disk", "bytes")
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
                "source": "filesystem:disk-usage",
            }
        )
        disk_observation = {
            "status": FullStatus.AVAILABLE.value,
            "total_bytes": usage.total,
            "free_bytes": usage.free,
            "free_ratio": usage.free / usage.total if usage.total else None,
            "unit": "bytes",
            "provenance": MetricProvenance.EXACT.value,
            "source": "filesystem:disk-usage",
        }
    except OSError:
        pass
    observations["disk"] = disk_observation

    io_observation = unavailable_observation("io", "bytes")
    try:
        read_sectors = 0
        written_sectors = 0
        devices = 0
        for line in _read_platform_text("/proc/diskstats").splitlines():
            fields = line.split()
            if len(fields) < 10:
                continue
            try:
                read_sectors += int(fields[5])
                written_sectors += int(fields[9])
            except ValueError:
                continue
            devices += 1
        if devices:
            io_observation = {
                "status": FullStatus.AVAILABLE.value,
                "read_bytes_cumulative": read_sectors * 512,
                "write_bytes_cumulative": written_sectors * 512,
                "observed_devices": devices,
                "unit": "bytes",
                "provenance": MetricProvenance.EXACT.value,
                "source": "procfs:diskstats-cumulative",
            }
    except (OSError, UnicodeError):
        pass
    observations["io"] = io_observation
    resource_details["observations"] = observations
    statuses = [item["status"] for item in observations.values()]
    if all(status == FullStatus.AVAILABLE.value for status in statuses):
        resource_status = FullStatus.AVAILABLE
        resource_provenance = MetricProvenance.EXACT
    elif any(status == FullStatus.AVAILABLE.value for status in statuses):
        resource_status = FullStatus.DEGRADED
        resource_provenance = MetricProvenance.UNKNOWN
    else:
        resource_status = FullStatus.UNAVAILABLE
        resource_provenance = MetricProvenance.UNAVAILABLE
    checks = {name: value.status for name, value in report.checks.items()}
    container_status = FullStatus.AVAILABLE if checks else FullStatus.UNAVAILABLE
    if any(value != "ok" for value in checks.values()):
        container_status = FullStatus.DEGRADED
    model_configured = bool(
        getattr(settings, "embedding_enabled", False) or getattr(settings, "rerank_enabled", False)
    )
    model_status = FullStatus.UNKNOWN if model_configured else FullStatus.NOT_CONFIGURED
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
            provenance=MetricProvenance.UNKNOWN if model_configured else MetricProvenance.EXACT,
            details=_details(
                {
                    "embedding_enabled": getattr(settings, "embedding_enabled", False),
                    "rerank_enabled": getattr(settings, "rerank_enabled", False),
                    "reachability": "UNKNOWN" if model_configured else "NOT_CONFIGURED",
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
    dependency_status, dependency_details = _dependency_summary(settings, project, modules)
    documents = _document_observations(settings, project)
    checkpoint_scope_dod_status, checkpoint_scope_dod_details = _canonical_project_intelligence(
        settings, project, documents
    )
    checkpoint_scope_dod_provenance = (
        MetricProvenance.EXACT
        if checkpoint_scope_dod_status is FullStatus.AVAILABLE
        else MetricProvenance.UNAVAILABLE
    )
    commits = _git_commits(settings, project)
    runs = summarize_runs(settings, project_id, limit=FULL_LIST_MAX)
    try:
        memory_status, memory_details = _memory_details(settings, project_id)
    except (psycopg.Error, RuntimeError):
        memory_status, memory_details = (
            FullStatus.UNAVAILABLE,
            {"reason": "memory_observation_unavailable"},
        )
    canonical_decisions_status, canonical_decisions_details = _decisions_details(settings, project)
    if canonical_decisions_status is FullStatus.AVAILABLE and memory_status is FullStatus.AVAILABLE:
        decisions_memory_status = FullStatus.AVAILABLE
        decisions_memory_provenance = MetricProvenance.EXACT
    elif (
        canonical_decisions_status is FullStatus.AVAILABLE or memory_status is FullStatus.AVAILABLE
    ):
        decisions_memory_status = FullStatus.DEGRADED
        decisions_memory_provenance = MetricProvenance.UNKNOWN
    else:
        decisions_memory_status = FullStatus.UNAVAILABLE
        decisions_memory_provenance = MetricProvenance.UNAVAILABLE
    decisions_memory_details = _details(
        {
            "canonical_decisions": canonical_decisions_details,
            "memory": memory_details,
            "source": (
                "git:HEAD-blob:docs/project-brain/16-DECISIONS-LEDGER.md + postgres:memory_records"
            ),
            "provenance": decisions_memory_provenance.value,
        }
    )
    health = _health_surfaces(settings)
    quality_events = [
        {
            "event_type": event.event_type,
            "occurred_at": event.occurred_at.isoformat(),
            "passed": (
                event.payload.get("passed")
                if event.event_type == "test.finished"
                else event.event_type == "validation.passed"
            ),
            "source": "postgres:telemetry_events",
        }
        for event in events
        if event.event_type
        in {"test.started", "test.finished", "validation.passed", "validation.failed"}
    ][-FULL_LIST_MAX:]
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
            checkpoint_scope_dod_status,
            (
                "canonical checkpoint, scope and Definition of Done content is visible from "
                "the project-relative Git HEAD blobs"
            ),
            checkpoint_scope_dod_provenance,
            checkpoint_scope_dod_details,
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
            decisions_memory_status,
            "canonical decisions remain separate from durable memory records, each with provenance",
            decisions_memory_provenance,
            decisions_memory_details,
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
            dependency_status,
            "bounded Python import observations are derived from indexed project files; "
            "non-Python imports remain unavailable",
            MetricProvenance.EXACT
            if dependency_status is FullStatus.AVAILABLE
            else MetricProvenance.UNKNOWN
            if dependency_status is FullStatus.UNKNOWN
            else MetricProvenance.UNAVAILABLE,
            dependency_details,
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
                    ),
                    "events": quality_events,
                    "source": "postgres:telemetry_events",
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
