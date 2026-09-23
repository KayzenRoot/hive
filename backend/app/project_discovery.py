"""Bounded, safe discovery and indexing of immediate child Git projects."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import psycopg

from .config import Settings
from .registry import (
    InspectionResult,
    ProjectConflictError,
    ProjectCreateRequest,
    ProjectPathError,
    ProjectResponse,
    inspect_project,
    inspect_registered_project,
    list_projects,
    normalize_project_path,
    register_project,
)
from .repository_indexer import IndexRunStatus, index_project, latest_index_run
from .retrieval import CorpusRunStatus, CorpusState, corpus_status, sync_corpus
from .telemetry import emit_event

logger = logging.getLogger(__name__)
MAX_SCAN_SECONDS = 30.0
_scan_lock = threading.Lock()


@dataclass(frozen=True)
class ProjectCandidate:
    relative_path: str
    path: Path
    inspection: InspectionResult


@dataclass(frozen=True)
class DiscoverySummary:
    status: str
    scanned_entries: int
    valid_repositories: int
    discovered: int
    refreshed: int
    indexed: int
    offline: int
    skipped: int
    duration_seconds: float


def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction()) if callable(is_junction) else False


def scan_immediate_git_repositories(settings: Settings) -> tuple[list[ProjectCandidate], int]:
    """Scan only bounded, real immediate child directories beneath the configured root."""

    root = settings.resolved_projects_root
    if not root.is_dir():
        return [], 0
    try:
        with os.scandir(root) as entries:
            bounded_entries = sorted(entries, key=lambda entry: entry.name.casefold())[
                : settings.auto_discovery_max_projects
            ]
    except OSError:
        return [], 0

    started = time.monotonic()
    candidates: list[ProjectCandidate] = []
    seen_paths: list[Path] = []
    scanned_entries = 0
    for entry in bounded_entries:
        if time.monotonic() - started >= MAX_SCAN_SECONDS:
            break
        scanned_entries += 1
        candidate_path = Path(entry.path)
        try:
            if _is_link(candidate_path) or not entry.is_dir(follow_symlinks=False):
                continue
            relative_path, resolved_path = normalize_project_path(entry.name, settings)
            resolved_path.relative_to(root)
            if not resolved_path.is_dir() or _is_link(resolved_path):
                continue
            if any(os.path.samefile(resolved_path, prior) for prior in seen_paths):
                continue
            inspection = inspect_project(resolved_path)
        except (OSError, RuntimeError, ValueError, ProjectPathError):
            continue
        if (
            not inspection.repository_accessible
            or inspection.git_head_sha is None
            or inspection.state.value != "READY"
        ):
            continue
        seen_paths.append(resolved_path)
        candidates.append(ProjectCandidate(relative_path, resolved_path, inspection))
    return candidates, scanned_entries


def _emit_discovered(settings: Settings, project: ProjectResponse) -> None:
    if project.git_head_sha is None:
        return
    try:
        emit_event(
            settings,
            project.project_id,
            "project.discovered",
            {
                "relative_path": project.relative_path,
                "git_head_sha": project.git_head_sha,
                "state": project.state.value,
            },
            provenance={"producer": "project_auto_discovery", "deterministic": True},
            emission_key=f"project-discovered:{project.git_head_sha}",
        )
    except (psycopg.Error, ValueError, RuntimeError) as exc:
        logger.warning("project discovery telemetry unavailable (%s)", type(exc).__name__)


def _ensure_indexed(settings: Settings, project: ProjectResponse) -> bool:
    latest_index = latest_index_run(settings, project.project_id)
    needs_index = (
        latest_index is None
        or latest_index.status is not IndexRunStatus.COMPLETED
        or latest_index.repository_head_sha != project.git_head_sha
    )
    if needs_index:
        index_result = index_project(settings, project.project_id)
        if index_result.status is not IndexRunStatus.COMPLETED:
            return False
    corpus = corpus_status(settings, project.project_id)
    needs_corpus_sync = (
        corpus.latest_run is None
        or corpus.latest_run.status is not CorpusRunStatus.COMPLETED
        or corpus.state is not CorpusState.CURRENT
        or needs_index
    )
    if needs_corpus_sync:
        corpus_result = sync_corpus(settings, project.project_id)
        return corpus_result.status is CorpusRunStatus.COMPLETED
    return True


def discover_projects_once(settings: Settings) -> DiscoverySummary:
    """Discover, refresh and index a bounded set; never deletes registry or user data."""

    started = time.monotonic()
    if not settings.auto_discovery_enabled:
        return DiscoverySummary("DISABLED", 0, 0, 0, 0, 0, 0, 0, 0.0)
    if not _scan_lock.acquire(blocking=False):
        return DiscoverySummary("ALREADY_RUNNING", 0, 0, 0, 0, 0, 0, 0, 0.0)

    discovered = refreshed = indexed = offline = skipped = 0
    try:
        candidates, scanned_entries = scan_immediate_git_repositories(settings)
        try:
            existing_projects = list_projects(settings)
        except psycopg.Error as exc:
            logger.warning("project discovery registry unavailable (%s)", type(exc).__name__)
            return DiscoverySummary(
                "UNAVAILABLE",
                scanned_entries,
                len(candidates),
                0,
                0,
                0,
                0,
                len(candidates),
                round(time.monotonic() - started, 3),
            )

        existing_by_path = {project.relative_path: project for project in existing_projects}
        candidate_paths = {candidate.relative_path for candidate in candidates}
        processed: set[str] = set()
        for candidate in candidates:
            if len(processed) >= settings.auto_discovery_max_projects:
                skipped += 1
                continue
            processed.add(candidate.relative_path)
            existing = existing_by_path.get(candidate.relative_path)
            was_discovered = existing is None
            try:
                project = (
                    register_project(
                        settings,
                        ProjectCreateRequest(
                            name=candidate.path.name,
                            relative_path=candidate.relative_path,
                        ),
                    )
                    if existing is None
                    else inspect_registered_project(settings, existing.project_id)
                )
            except ProjectConflictError:
                skipped += 1
                continue
            except (psycopg.Error, ProjectPathError, RuntimeError) as exc:
                logger.warning("project discovery skipped a candidate (%s)", type(exc).__name__)
                skipped += 1
                continue
            if project is None or not project.repository_accessible:
                skipped += 1
                continue
            if was_discovered:
                discovered += 1
                _emit_discovered(settings, project)
            else:
                refreshed += 1
                if existing is not None and existing.git_head_sha != project.git_head_sha:
                    _emit_discovered(settings, project)
            try:
                if _ensure_indexed(settings, project):
                    indexed += 1
            except (psycopg.Error, RuntimeError, ValueError) as exc:
                logger.warning("automatic project indexing failed (%s)", type(exc).__name__)

        for existing in existing_projects[: settings.auto_discovery_max_projects]:
            relative_path = existing.relative_path
            if "/" in relative_path or relative_path in candidate_paths:
                continue
            try:
                _identity, path = normalize_project_path(relative_path, settings)
                path_is_present = path.exists() and not _is_link(path)
            except (OSError, RuntimeError, ValueError, ProjectPathError):
                path_is_present = False
            inspected = inspect_registered_project(settings, existing.project_id)
            if inspected is not None and inspected.state.value == "OFFLINE":
                offline += 1
            elif not path_is_present and inspected is not None:
                skipped += 1
        return DiscoverySummary(
            "PASS",
            scanned_entries,
            len(candidates),
            discovered,
            refreshed,
            indexed,
            offline,
            skipped,
            round(time.monotonic() - started, 3),
        )
    finally:
        _scan_lock.release()


async def run_project_discovery(settings: Settings) -> None:
    """Run startup discovery and bounded periodic refresh until application shutdown."""

    while True:
        try:
            summary = await asyncio.to_thread(discover_projects_once, settings)
            logger.info(
                "project discovery %s: candidates=%s discovered=%s indexed=%s offline=%s "
                "skipped=%s duration=%.3fs",
                summary.status,
                summary.valid_repositories,
                summary.discovered,
                summary.indexed,
                summary.offline,
                summary.skipped,
                summary.duration_seconds,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("project discovery cycle failed (%s)", type(exc).__name__)
        await asyncio.sleep(settings.auto_discovery_interval_seconds)
