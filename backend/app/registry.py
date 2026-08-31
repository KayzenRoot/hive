from __future__ import annotations

import ntpath
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, field_validator

from .config import Settings
from .db import database_connection

GIT_TIMEOUT_SECONDS = 5
SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40,64}$")
REGISTRY_ADVISORY_LOCK = (12002, 1)


class ProjectState(StrEnum):
    OFFLINE = "OFFLINE"
    STALE = "STALE"
    INDEXING = "INDEXING"
    READY = "READY"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    relative_path: str = Field(min_length=1, max_length=1024)

    @field_validator("name", "relative_path")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value


class ProjectResponse(BaseModel):
    project_id: UUID
    name: str
    relative_path: str
    git_branch: str | None
    git_head_sha: str | None
    detached_head: bool
    repository_accessible: bool
    working_tree_clean: bool | None
    language_stack: list[str]
    state: ProjectState
    inspection_error: str | None
    created_at: datetime
    updated_at: datetime
    last_inspected_at: datetime


class ProjectPathError(ValueError):
    """The requested path is not safely contained by HIVE_PROJECTS_ROOT."""

    def __init__(self, message: str, *, code: str = "invalid_project_path") -> None:
        super().__init__(message)
        self.code = code


class ProjectConflictError(RuntimeError):
    """A project with the same canonical relative path already exists."""


@dataclass(frozen=True)
class InspectionResult:
    git_branch: str | None
    git_head_sha: str | None
    detached_head: bool
    repository_accessible: bool
    working_tree_clean: bool | None
    language_stack: list[str]
    state: ProjectState
    inspection_error: str | None


def normalize_project_path(relative_path: str, settings: Settings) -> tuple[str, Path]:
    """Return the canonical relative identity and resolved path below the configured root."""
    value = relative_path.strip()
    if not value or "\x00" in value or "\\" in value:
        raise ProjectPathError("project path must be a non-empty POSIX-relative path")
    if (
        PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
        or bool(ntpath.splitdrive(value)[0])
    ):
        raise ProjectPathError("project path must be relative to HIVE_PROJECTS_ROOT")

    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ProjectPathError("project path contains an unsafe component")

    try:
        allowed_root = settings.resolved_projects_root
        resolved_path = (allowed_root / Path(*parts)).resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise ProjectPathError(
            "project path could not be resolved",
            code="path_resolution_failed",
        ) from exc
    try:
        resolved_path.relative_to(allowed_root)
    except ValueError as exc:
        raise ProjectPathError(
            "project path resolves outside HIVE_PROJECTS_ROOT",
            code="path_boundary_violation",
        ) from exc
    canonical_relative = resolved_path.relative_to(allowed_root).as_posix()
    if not canonical_relative or canonical_relative == ".":
        raise ProjectPathError(
            "project path must resolve to a directory below HIVE_PROJECTS_ROOT",
            code="path_boundary_violation",
        )
    return canonical_relative, resolved_path


def _failure_result(error: str, language_stack: list[str] | None = None) -> InspectionResult:
    return InspectionResult(
        git_branch=None,
        git_head_sha=None,
        detached_head=False,
        repository_accessible=False,
        working_tree_clean=None,
        language_stack=language_stack or [],
        state=ProjectState.DEGRADED,
        inspection_error=error,
    )


def _detect_languages(project_path: Path) -> list[str]:
    try:
        entries = sorted(project_path.iterdir(), key=lambda item: item.name.casefold())
    except OSError:
        return []

    names = {entry.name.casefold() for entry in entries}
    suffixes = {entry.suffix.casefold() for entry in entries if entry.is_file()}
    detected: set[str] = set()
    if (
        names & {"pyproject.toml", "requirements.txt", "setup.py", "poetry.lock"}
        or ".py" in suffixes
    ):
        detected.add("python")
    if "package.json" in names or names & {"package-lock.json", "yarn.lock", "pnpm-lock.yaml"}:
        detected.add("javascript")
    if "tsconfig.json" in names or suffixes & {".ts", ".tsx"}:
        detected.add("typescript")
    if "cargo.toml" in names or ".rs" in suffixes:
        detected.add("rust")
    if "go.mod" in names or ".go" in suffixes:
        detected.add("go")
    if names & {"pom.xml", "build.gradle", "build.gradle.kts"} or ".java" in suffixes:
        detected.add("java")
    if (
        any(name.endswith(".csproj") or name.endswith(".sln") for name in names)
        or ".cs" in suffixes
    ):
        detected.add("csharp")
    if "gemfile" in names or ".rb" in suffixes:
        detected.add("ruby")
    if "composer.json" in names or ".php" in suffixes:
        detected.add("php")
    if "dockerfile" in names or any(name.startswith("dockerfile.") for name in names):
        detected.add("docker")
    order = [
        "python",
        "typescript",
        "javascript",
        "rust",
        "go",
        "java",
        "csharp",
        "ruby",
        "php",
        "docker",
    ]
    return [language for language in order if language in detected]


def _run_git(
    project_path: Path, arguments: list[str], *, allow_nonzero: bool = False
) -> subprocess.CompletedProcess[str]:
    command = [
        "git",
        "-c",
        f"safe.directory={project_path}",
        "-C",
        str(project_path),
        *arguments,
    ]
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            check=False,
            cwd=None,
            env=environment,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git_unavailable") from exc
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError("git_timeout") from exc
    if result.returncode != 0 and not allow_nonzero:
        raise RuntimeError("git_command_failed")
    return result


def inspect_project(project_path: Path) -> InspectionResult:
    try:
        if not project_path.exists() or not project_path.is_dir():
            return InspectionResult(
                git_branch=None,
                git_head_sha=None,
                detached_head=False,
                repository_accessible=False,
                working_tree_clean=None,
                language_stack=[],
                state=ProjectState.OFFLINE,
                inspection_error="path_unavailable",
            )
    except OSError:
        return InspectionResult(
            git_branch=None,
            git_head_sha=None,
            detached_head=False,
            repository_accessible=False,
            working_tree_clean=None,
            language_stack=[],
            state=ProjectState.OFFLINE,
            inspection_error="path_unavailable",
        )

    language_stack = _detect_languages(project_path)
    try:
        inside_work_tree = _run_git(project_path, ["rev-parse", "--is-inside-work-tree"])
        if inside_work_tree.stdout.strip().lower() != "true":
            return _failure_result("not_a_git_repository", language_stack)

        head = _run_git(project_path, ["rev-parse", "--verify", "HEAD"]).stdout.strip()
        if not SHA_PATTERN.fullmatch(head):
            return _failure_result("git_head_unavailable", language_stack)

        branch_result = _run_git(
            project_path,
            ["symbolic-ref", "--quiet", "--short", "HEAD"],
            allow_nonzero=True,
        )
        if branch_result.returncode == 0:
            branch = branch_result.stdout.strip() or None
            detached_head = False
        elif branch_result.returncode == 1:
            branch = None
            detached_head = True
        else:
            return _failure_result("git_branch_unavailable", language_stack)

        status = _run_git(project_path, ["status", "--porcelain=v1", "--untracked-files=no"])
        return InspectionResult(
            git_branch=branch,
            git_head_sha=head.lower(),
            detached_head=detached_head,
            repository_accessible=True,
            working_tree_clean=status.stdout == "",
            language_stack=language_stack,
            state=ProjectState.READY,
            inspection_error=None,
        )
    except TimeoutError:
        return _failure_result("git_timeout", language_stack)
    except RuntimeError as exc:
        return _failure_result(str(exc), language_stack)


_PROJECT_COLUMNS = """
    project_id, name, relative_path, git_branch, git_head_sha, detached_head,
    repository_accessible, working_tree_clean, language_stack, state,
    inspection_error, created_at, updated_at, last_inspected_at
"""


def _project_from_row(row: tuple[Any, ...]) -> ProjectResponse:
    return ProjectResponse(
        project_id=row[0],
        name=row[1],
        relative_path=row[2],
        git_branch=row[3],
        git_head_sha=row[4],
        detached_head=row[5],
        repository_accessible=row[6],
        working_tree_clean=row[7],
        language_stack=list(row[8]),
        state=ProjectState(row[9]),
        inspection_error=row[10],
        created_at=row[11],
        updated_at=row[12],
        last_inspected_at=row[13],
    )


def _blocked_result(error: str) -> InspectionResult:
    return InspectionResult(
        git_branch=None,
        git_head_sha=None,
        detached_head=False,
        repository_accessible=False,
        working_tree_clean=None,
        language_stack=[],
        state=ProjectState.BLOCKED,
        inspection_error=error,
    )


def _acquire_registry_lock(cursor: psycopg.Cursor[Any]) -> None:
    cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", REGISTRY_ADVISORY_LOCK)


def _find_identity_conflict(
    cursor: psycopg.Cursor[Any],
    settings: Settings,
    candidate_identity: str,
    candidate_path: Path,
    *,
    excluded_project_id: UUID | None = None,
) -> UUID | None:
    cursor.execute("SELECT project_id, relative_path FROM projects")
    for raw_project_id, raw_relative_path in cursor.fetchall():
        project_id = cast(UUID, raw_project_id)
        relative_path = cast(str, raw_relative_path)
        if excluded_project_id is not None and project_id == excluded_project_id:
            continue
        if relative_path == candidate_identity:
            return project_id
        try:
            _, registered_path = normalize_project_path(relative_path, settings)
            if (
                candidate_path.exists()
                and registered_path.exists()
                and os.path.samefile(candidate_path, registered_path)
            ):
                return project_id
        except (OSError, ValueError, ProjectPathError):
            continue
    return None


def list_projects(settings: Settings) -> list[ProjectResponse]:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {_PROJECT_COLUMNS} FROM projects ORDER BY last_inspected_at DESC, project_id"
        )
        return [_project_from_row(row) for row in cursor.fetchall()]


def get_project(settings: Settings, project_id: UUID) -> ProjectResponse | None:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {_PROJECT_COLUMNS} FROM projects WHERE project_id = %s",
            (project_id,),
        )
        row = cursor.fetchone()
    return _project_from_row(row) if row else None


def register_project(settings: Settings, request: ProjectCreateRequest) -> ProjectResponse:
    identity, resolved_path = normalize_project_path(request.relative_path, settings)
    inspection = inspect_project(resolved_path)
    project_id = uuid4()
    try:
        with database_connection(settings) as connection, connection.cursor() as cursor:
            _acquire_registry_lock(cursor)
            if _find_identity_conflict(cursor, settings, identity, resolved_path) is not None:
                raise ProjectConflictError("project physical identity is already registered")
            cursor.execute(
                f"""
                INSERT INTO projects (
                    project_id, name, relative_path, git_branch, git_head_sha, detached_head,
                    repository_accessible, working_tree_clean, language_stack, state,
                    inspection_error, last_inspected_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s::hive_project_state, %s, CURRENT_TIMESTAMP
                )
                RETURNING {_PROJECT_COLUMNS}
                """,
                (
                    project_id,
                    request.name,
                    identity,
                    inspection.git_branch,
                    inspection.git_head_sha,
                    inspection.detached_head,
                    inspection.repository_accessible,
                    inspection.working_tree_clean,
                    Jsonb(inspection.language_stack),
                    inspection.state.value,
                    inspection.inspection_error,
                ),
            )
            row = cursor.fetchone()
    except psycopg.errors.UniqueViolation as exc:
        raise ProjectConflictError("project path is already registered") from exc
    if row is None:
        raise RuntimeError("project registration returned no record")
    return _project_from_row(row)


def inspect_registered_project(settings: Settings, project_id: UUID) -> ProjectResponse | None:
    existing = get_project(settings, project_id)
    if existing is None:
        return None

    try:
        canonical_identity, resolved_path = normalize_project_path(existing.relative_path, settings)
    except ProjectPathError as exc:
        inspection = _blocked_result(exc.code)
        canonical_identity = existing.relative_path

        with database_connection(settings) as connection, connection.cursor() as cursor:
            _update_inspection(cursor, project_id, canonical_identity, inspection)
            row = cursor.fetchone()
        return _project_from_row(row) if row else None

    with database_connection(settings) as connection, connection.cursor() as cursor:
        _acquire_registry_lock(cursor)
        if (
            _find_identity_conflict(
                cursor,
                settings,
                canonical_identity,
                resolved_path,
                excluded_project_id=project_id,
            )
            is not None
        ):
            inspection = _blocked_result("physical_identity_conflict")
            canonical_identity = existing.relative_path
        else:
            inspection = inspect_project(resolved_path)
        _update_inspection(cursor, project_id, canonical_identity, inspection)
        row = cursor.fetchone()
    return _project_from_row(row) if row else None


def _update_inspection(
    cursor: psycopg.Cursor[Any],
    project_id: UUID,
    canonical_identity: str,
    inspection: InspectionResult,
) -> None:
    cursor.execute(
        f"""
            UPDATE projects
            SET relative_path = %s,
                git_branch = %s,
                git_head_sha = %s,
                detached_head = %s,
                repository_accessible = %s,
                working_tree_clean = %s,
                language_stack = %s,
                state = %s::hive_project_state,
                inspection_error = %s,
                updated_at = CURRENT_TIMESTAMP,
                last_inspected_at = CURRENT_TIMESTAMP
            WHERE project_id = %s
            RETURNING {_PROJECT_COLUMNS}
            """,
        (
            canonical_identity,
            inspection.git_branch,
            inspection.git_head_sha,
            inspection.detached_head,
            inspection.repository_accessible,
            inspection.working_tree_clean,
            Jsonb(inspection.language_stack),
            inspection.state.value,
            inspection.inspection_error,
            project_id,
        ),
    )
