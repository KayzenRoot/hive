from __future__ import annotations

import ast
import hashlib
import io
import ntpath
import os
import re
import stat
import subprocess
import tokenize
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .config import Settings
from .db import database_connection
from .registry import ProjectPathError, normalize_project_path

GIT_TIMEOUT_SECONDS = 5
SHA_PATTERN = re.compile(r"^[0-9a-f]{40,64}$")
INDEX_ADVISORY_LOCK_KEY = 12005


class IndexRunStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class IndexRunSummary(BaseModel):
    run_id: UUID
    project_id: UUID
    repository_head_sha: str | None
    git_branch: str | None
    status: IndexRunStatus
    started_at: datetime
    completed_at: datetime | None
    discovered_file_count: int
    indexed_file_count: int
    reused_file_count: int
    changed_file_count: int
    added_file_count: int
    removed_file_count: int
    unchanged_file_count: int
    parsed_file_count: int
    symbol_count: int
    error: str | None


class RepositoryProjectNotFoundError(LookupError):
    """The requested project does not exist."""


class RepositoryIndexingError(RuntimeError):
    """A deterministic repository indexing operation failed safely."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class SymbolRecord:
    name: str
    qualified_name: str
    kind: str
    line_start: int
    line_end: int
    parent_qualified_name: str | None


class _SymbolVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.symbols: list[SymbolRecord] = []
        self._parents: list[str] = []

    @property
    def parent(self) -> str | None:
        return self._parents[-1] if self._parents else None

    def _qualified_name(self, name: str) -> str:
        return f"{self.parent}.{name}" if self.parent else name

    def _line_end(self, node: ast.AST) -> int:
        value = getattr(node, "end_lineno", None)
        if isinstance(value, int):
            return value
        fallback = getattr(node, "lineno", 1)
        if isinstance(fallback, int):
            return fallback
        return 1

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified_name = self._qualified_name(node.name)
        self.symbols.append(
            SymbolRecord(
                name=node.name,
                qualified_name=qualified_name,
                kind="class",
                line_start=int(node.lineno),
                line_end=self._line_end(node),
                parent_qualified_name=self.parent,
            )
        )
        self._parents.append(qualified_name)
        for statement in node.body:
            self.visit(statement)
        self._parents.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node, "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node, "async_function")

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, kind: str) -> None:
        qualified_name = self._qualified_name(node.name)
        self.symbols.append(
            SymbolRecord(
                name=node.name,
                qualified_name=qualified_name,
                kind=kind,
                line_start=int(node.lineno),
                line_end=self._line_end(node),
                parent_qualified_name=self.parent,
            )
        )
        self._parents.append(qualified_name)
        for statement in node.body:
            self.visit(statement)
        self._parents.pop()


def parse_python_symbols(path: str, content: bytes) -> list[SymbolRecord]:
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(content).readline)
        source = content.decode(encoding)
        tree = ast.parse(source, filename=path, mode="exec")
    except (LookupError, SyntaxError, UnicodeError, ValueError) as exc:
        raise RepositoryIndexingError("python_syntax_error") from exc
    visitor = _SymbolVisitor()
    visitor.visit(tree)
    return visitor.symbols


_LANGUAGE_BY_SUFFIX: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".sql": "sql",
    ".sh": "shell",
    ".bash": "shell",
}
_DOCUMENTATION_SUFFIXES = {".md", ".markdown", ".rst", ".txt"}
_CONFIGURATION_SUFFIXES = {
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".conf",
    ".xml",
}


@dataclass(frozen=True)
class _FileStamp:
    device: int
    inode: int
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class _TrackedFile:
    path: str
    resolved_path: Path
    content_sha256: str
    file_size: int
    language: str | None
    file_type: str
    git_mode: str
    git_blob_sha: str | None
    git_status: str
    stamp: _FileStamp
    source: bytes


@dataclass(frozen=True)
class _RepositorySnapshot:
    project_path: Path
    repository_head_sha: str
    git_branch: str | None
    git_inventory_fingerprint: str
    files: tuple[_TrackedFile, ...]


def _run_git(
    project_path: Path,
    arguments: list[str],
    *,
    allow_nonzero: bool = False,
) -> subprocess.CompletedProcess[bytes]:
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
            timeout=GIT_TIMEOUT_SECONDS,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise RepositoryIndexingError("git_unavailable") from exc
    except subprocess.TimeoutExpired as exc:
        raise RepositoryIndexingError("git_timeout") from exc
    if result.returncode != 0 and not allow_nonzero:
        raise RepositoryIndexingError("git_command_failed")
    return result


def _decode_git_text(value: bytes, error_code: str) -> str:
    try:
        return value.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise RepositoryIndexingError(error_code) from exc


def _git_head(project_path: Path) -> str:
    try:
        result = _run_git(project_path, ["rev-parse", "--verify", "HEAD^{commit}"])
    except RepositoryIndexingError as exc:
        raise RepositoryIndexingError("git_head_unavailable") from exc
    head = _decode_git_text(result.stdout, "git_head_unavailable").lower()
    if not SHA_PATTERN.fullmatch(head):
        raise RepositoryIndexingError("git_head_unavailable")
    return head


def _git_branch(project_path: Path) -> str | None:
    try:
        result = _run_git(
            project_path,
            ["symbolic-ref", "--quiet", "--short", "HEAD"],
            allow_nonzero=True,
        )
    except RepositoryIndexingError as exc:
        raise RepositoryIndexingError("git_branch_unavailable") from exc
    if result.returncode == 0:
        return _decode_git_text(result.stdout, "git_branch_unavailable") or None
    if result.returncode == 1:
        return None
    raise RepositoryIndexingError("git_branch_unavailable")


def _git_status_inventory(project_path: Path) -> tuple[set[str], bytes]:
    try:
        result = _run_git(
            project_path,
            ["status", "--porcelain=v1", "--untracked-files=no", "-z", "--"],
        )
    except RepositoryIndexingError as exc:
        raise RepositoryIndexingError("git_status_unavailable") from exc
    paths: set[str] = set()
    for record in result.stdout.split(b"\0"):
        if not record:
            continue
        raw_path = record[3:] if len(record) >= 3 and record[2:3] == b" " else record
        try:
            paths.add(raw_path.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise RepositoryIndexingError("non_utf8_git_path") from exc
    return paths, result.stdout


def _inventory_fingerprint(listing: bytes, status: bytes) -> str:
    digest = hashlib.sha256()
    for value in (listing, status):
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)
    return digest.hexdigest()


def _git_inventory_fingerprint(project_path: Path) -> str:
    try:
        listing = _run_git(project_path, ["ls-files", "--cached", "--stage", "-z", "--"])
    except RepositoryIndexingError as exc:
        raise RepositoryIndexingError("git_inventory_unavailable") from exc
    _, status = _git_status_inventory(project_path)
    return _inventory_fingerprint(listing.stdout, status)


def _classify(path: str, source: bytes) -> tuple[str | None, str]:
    name = PurePosixPath(path).name.casefold()
    suffix = PurePosixPath(path).suffix.casefold()
    if b"\0" in source[:8192]:
        return None, "binary"
    language = _LANGUAGE_BY_SUFFIX.get(suffix)
    if name == "dockerfile" or name.startswith("dockerfile."):
        return "docker", "configuration"
    if language is not None:
        return language, "source"
    if suffix in _DOCUMENTATION_SUFFIXES:
        return None, "documentation"
    if suffix in _CONFIGURATION_SUFFIXES:
        return None, "configuration"
    return None, "text"


def _stamp(result: os.stat_result) -> _FileStamp:
    return _FileStamp(
        device=int(result.st_dev),
        inode=int(result.st_ino),
        size=int(result.st_size),
        mtime_ns=int(result.st_mtime_ns),
    )


def _read_stable_file(path: Path, settings: Settings) -> tuple[bytes, _FileStamp]:
    try:
        before = path.stat()
    except OSError as exc:
        raise RepositoryIndexingError("tracked_file_unavailable") from exc
    if not stat.S_ISREG(before.st_mode):
        raise RepositoryIndexingError("tracked_file_not_regular")
    if before.st_size > settings.repository_max_file_bytes:
        raise RepositoryIndexingError("repository_file_size_limit")
    try:
        with path.open("rb") as handle:
            source = handle.read(settings.repository_max_file_bytes + 1)
        after = path.stat()
    except OSError as exc:
        raise RepositoryIndexingError("tracked_file_unavailable") from exc
    if len(source) > settings.repository_max_file_bytes:
        raise RepositoryIndexingError("repository_file_size_limit")
    before_stamp = _stamp(before)
    after_stamp = _stamp(after)
    if before_stamp != after_stamp or len(source) != after_stamp.size:
        raise RepositoryIndexingError("source_mutated_during_index")
    return source, after_stamp


def _resolve_tracked_path(project_path: Path, path: str) -> Path:
    if (
        not path
        or "\\" in path
        or "\0" in path
        or path.startswith("/")
        or PureWindowsPath(path).is_absolute()
        or bool(ntpath.splitdrive(path)[0])
    ):
        raise ProjectPathError("tracked repository path contains an unsafe component")
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts) or ".git" in parts:
        raise ProjectPathError("tracked repository path contains an unsafe component")
    candidate = project_path.joinpath(*parts)
    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise ProjectPathError("tracked repository path could not be resolved") from exc
    try:
        resolved.relative_to(project_path)
    except ValueError as exc:
        raise ProjectPathError("tracked repository path resolves outside the project") from exc
    return resolved


def _collect_inventory(settings: Settings, project_path: Path) -> _RepositorySnapshot:
    try:
        project_root = project_path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise RepositoryIndexingError("path_unavailable") from exc
    if not project_root.is_dir():
        raise RepositoryIndexingError("path_unavailable")

    try:
        inside = _run_git(project_root, ["rev-parse", "--is-inside-work-tree"])
    except RepositoryIndexingError as exc:
        if exc.code == "git_command_failed":
            raise RepositoryIndexingError("not_a_git_repository") from exc
        raise
    if inside.stdout.strip().lower() != b"true":
        raise RepositoryIndexingError("not_a_git_repository")
    head = _git_head(project_root)
    branch = _git_branch(project_root)

    try:
        listing = _run_git(project_root, ["ls-files", "--cached", "--stage", "-z", "--"])
    except RepositoryIndexingError as exc:
        raise RepositoryIndexingError("git_inventory_unavailable") from exc
    records = [record for record in listing.stdout.split(b"\0") if record]
    if len(records) > settings.repository_max_files:
        raise RepositoryIndexingError("repository_file_count_limit")
    status_paths, status_inventory = _git_status_inventory(project_root)
    inventory_fingerprint = _inventory_fingerprint(listing.stdout, status_inventory)
    files: list[_TrackedFile] = []
    total_size = 0
    for record in records:
        try:
            metadata, raw_path = record.split(b"\t", 1)
            metadata_parts = metadata.split()
            if len(metadata_parts) != 3:
                raise ValueError("unexpected git ls-files --stage metadata")
            mode = metadata_parts[0].decode("ascii")
            blob_sha = metadata_parts[1].decode("ascii").lower()
            stage = metadata_parts[2].decode("ascii")
            path = raw_path.decode("utf-8")
        except (IndexError, UnicodeDecodeError, ValueError) as exc:
            raise RepositoryIndexingError("git_inventory_unavailable") from exc
        if stage != "0":
            raise RepositoryIndexingError("git_unmerged_entry")
        if mode == "160000":
            raise RepositoryIndexingError("tracked_submodule_unsupported")
        if not SHA_PATTERN.fullmatch(blob_sha):
            raise RepositoryIndexingError("git_inventory_unavailable")
        try:
            resolved_path = _resolve_tracked_path(project_root, path)
        except ProjectPathError as exc:
            raise RepositoryIndexingError("tracked_path_unsafe") from exc
        source, stamp = _read_stable_file(resolved_path, settings)
        total_size += len(source)
        if total_size > settings.repository_max_total_bytes:
            raise RepositoryIndexingError("repository_total_size_limit")
        content_sha256 = hashlib.sha256(source).hexdigest()
        language, file_type = _classify(path, source)
        files.append(
            _TrackedFile(
                path=path,
                resolved_path=resolved_path,
                content_sha256=content_sha256,
                file_size=len(source),
                language=language,
                file_type=file_type,
                git_mode=mode,
                git_blob_sha=blob_sha,
                git_status="MODIFIED" if path in status_paths else "CLEAN",
                stamp=stamp,
                source=source,
            )
        )
    files.sort(key=lambda item: item.path)
    return _RepositorySnapshot(project_root, head, branch, inventory_fingerprint, tuple(files))


def _assert_snapshot_stable(settings: Settings, snapshot: _RepositorySnapshot) -> None:
    for entry in snapshot.files:
        try:
            resolved = entry.resolved_path.resolve(strict=True)
            resolved.relative_to(snapshot.project_path)
        except (OSError, RuntimeError, ValueError) as exc:
            raise RepositoryIndexingError("source_mutated_during_index") from exc
        source, stamp = _read_stable_file(resolved, settings)
        if stamp != entry.stamp or hashlib.sha256(source).hexdigest() != entry.content_sha256:
            raise RepositoryIndexingError("source_mutated_during_index")
    if _git_inventory_fingerprint(snapshot.project_path) != snapshot.git_inventory_fingerprint:
        raise RepositoryIndexingError("git_inventory_changed_during_index")
    if _git_head(snapshot.project_path) != snapshot.repository_head_sha:
        raise RepositoryIndexingError("repository_changed_during_index")
    if _git_branch(snapshot.project_path) != snapshot.git_branch:
        raise RepositoryIndexingError("repository_changed_during_index")


def _run_columns() -> str:
    return """
        run_id, project_id, repository_head_sha, git_branch, status,
        started_at, completed_at, discovered_file_count, indexed_file_count,
        reused_file_count, changed_file_count, added_file_count, removed_file_count,
        unchanged_file_count, parsed_file_count, symbol_count, error
    """


def _run_from_row(row: tuple[Any, ...]) -> IndexRunSummary:
    return IndexRunSummary(
        run_id=cast(UUID, row[0]),
        project_id=cast(UUID, row[1]),
        repository_head_sha=cast(str | None, row[2]),
        git_branch=cast(str | None, row[3]),
        status=IndexRunStatus(str(row[4])),
        started_at=cast(datetime, row[5]),
        completed_at=cast(datetime | None, row[6]),
        discovered_file_count=int(row[7]),
        indexed_file_count=int(row[8]),
        reused_file_count=int(row[9]),
        changed_file_count=int(row[10]),
        added_file_count=int(row[11]),
        removed_file_count=int(row[12]),
        unchanged_file_count=int(row[13]),
        parsed_file_count=int(row[14]),
        symbol_count=int(row[15]),
        error=cast(str | None, row[16]),
    )


def _get_run(settings: Settings, run_id: UUID) -> IndexRunSummary:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {_run_columns()} FROM repository_index_runs WHERE run_id = %s", (run_id,)
        )
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError("repository index run disappeared")
    return _run_from_row(row)


def _create_run(
    settings: Settings,
    run_id: UUID,
    project_id: UUID,
    snapshot: _RepositorySnapshot | None,
) -> IndexRunSummary:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO repository_index_runs (
                run_id, project_id, repository_head_sha, git_branch, status
            ) VALUES (%s, %s, %s, %s, 'RUNNING')
            """,
            (
                run_id,
                project_id,
                snapshot.repository_head_sha if snapshot else None,
                snapshot.git_branch if snapshot else None,
            ),
        )
    return _get_run(settings, run_id)


def _mark_failed(
    settings: Settings,
    run_id: UUID,
    error: str,
    discovered_file_count: int,
) -> IndexRunSummary:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE repository_index_runs
            SET status = 'FAILED', completed_at = CURRENT_TIMESTAMP,
                discovered_file_count = %s, indexed_file_count = 0,
                reused_file_count = 0, changed_file_count = 0,
                added_file_count = 0, removed_file_count = 0,
                unchanged_file_count = 0, parsed_file_count = 0,
                symbol_count = (
                    SELECT count(*) FROM repository_symbols
                    WHERE project_id = repository_index_runs.project_id
                ),
                error = %s
            WHERE run_id = %s
            """,
            (discovered_file_count, error[:256], run_id),
        )
    return _get_run(settings, run_id)


def _project_path(settings: Settings, project_id: UUID) -> Path:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT relative_path FROM projects WHERE project_id = %s", (project_id,))
        row = cursor.fetchone()
    if row is None:
        raise RepositoryProjectNotFoundError(str(project_id))
    _, resolved_path = normalize_project_path(cast(str, row[0]), settings)
    return resolved_path


def _perform_reconcile(
    settings: Settings,
    project_id: UUID,
    run_id: UUID,
    snapshot: _RepositorySnapshot,
) -> None:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(%s, hashtext(%s))",
            (INDEX_ADVISORY_LOCK_KEY, str(project_id)),
        )
        cursor.execute(
            """
            SELECT file_id, path, content_sha256, file_size, language, file_type,
                   git_mode, git_blob_sha, git_status, is_current, parse_status
            FROM repository_files
            WHERE project_id = %s
            FOR UPDATE
            """,
            (project_id,),
        )
        rows = cursor.fetchall()
        existing: dict[str, tuple[Any, ...]] = {str(row[1]): row for row in rows}
        changed_paths: set[str] = set()
        added_count = 0
        changed_count = 0
        unchanged_count = 0
        for entry in snapshot.files:
            row = existing.get(entry.path)
            is_current = row is not None and bool(row[9])
            unchanged = (
                row is not None
                and is_current
                and str(row[2]) == entry.content_sha256
                and int(row[3]) == entry.file_size
            )
            if unchanged:
                unchanged_count += 1
            else:
                changed_paths.add(entry.path)
                if is_current:
                    changed_count += 1
                else:
                    added_count += 1

        removed_paths = {
            path
            for path, row in existing.items()
            if bool(row[9]) and path not in {item.path for item in snapshot.files}
        }
        parsed_by_path: dict[str, list[SymbolRecord]] = {}
        for entry in snapshot.files:
            if entry.path in changed_paths and entry.language == "python":
                parsed_by_path[entry.path] = parse_python_symbols(entry.path, entry.source)

        _assert_snapshot_stable(settings, snapshot)

        for path in sorted(removed_paths):
            row = existing[path]
            file_id = cast(UUID, row[0])
            cursor.execute("DELETE FROM repository_symbols WHERE file_id = %s", (file_id,))
            cursor.execute(
                """
                UPDATE repository_files
                SET is_current = FALSE, removed_in_run_id = %s, updated_at = CURRENT_TIMESTAMP
                WHERE file_id = %s
                """,
                (run_id, file_id),
            )

        for entry in snapshot.files:
            row = existing.get(entry.path)
            is_current = row is not None and bool(row[9])
            unchanged = (
                row is not None
                and is_current
                and str(row[2]) == entry.content_sha256
                and int(row[3]) == entry.file_size
            )
            parse_status = "PARSED" if entry.language == "python" else "NOT_APPLICABLE"
            if row is None:
                cursor.execute(
                    """
                    INSERT INTO repository_files (
                        file_id, project_id, path, content_sha256, file_size, language,
                        file_type, git_mode, git_blob_sha, git_status, is_current,
                        parse_status, first_seen_run_id, last_seen_run_id,
                        last_indexed_run_id
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE,
                        %s, %s, %s, %s
                    )
                    """,
                    (
                        uuid4(),
                        project_id,
                        entry.path,
                        entry.content_sha256,
                        entry.file_size,
                        entry.language,
                        entry.file_type,
                        entry.git_mode,
                        entry.git_blob_sha,
                        entry.git_status,
                        parse_status,
                        run_id,
                        run_id,
                        run_id,
                    ),
                )
                cursor.execute(
                    "SELECT file_id FROM repository_files WHERE project_id = %s AND path = %s",
                    (project_id, entry.path),
                )
                inserted_row = cursor.fetchone()
                if inserted_row is None:
                    raise RuntimeError("repository file insert returned no row")
                file_id = cast(UUID, inserted_row[0])
            else:
                file_id = cast(UUID, row[0])
                if not unchanged:
                    cursor.execute("DELETE FROM repository_symbols WHERE file_id = %s", (file_id,))
                update_sql = """
                    UPDATE repository_files
                    SET content_sha256 = %s, file_size = %s, language = %s,
                        file_type = %s, git_mode = %s, git_blob_sha = %s,
                        git_status = %s, is_current = TRUE, parse_status = %s,
                        parse_error = NULL, last_seen_run_id = %s,
                        removed_in_run_id = NULL, updated_at = CURRENT_TIMESTAMP
                """
                values: list[Any] = [
                    entry.content_sha256,
                    entry.file_size,
                    entry.language,
                    entry.file_type,
                    entry.git_mode,
                    entry.git_blob_sha,
                    entry.git_status,
                    parse_status,
                    run_id,
                ]
                if not unchanged:
                    update_sql += ", last_indexed_run_id = %s"
                    values.append(run_id)
                update_sql += " WHERE file_id = %s"
                values.append(file_id)
                cursor.execute(update_sql, tuple(values))

            if not unchanged:
                for symbol in parsed_by_path.get(entry.path, []):
                    cursor.execute(
                        """
                        INSERT INTO repository_symbols (
                            symbol_id, project_id, file_id, name, qualified_name, kind,
                            line_start, line_end, parent_qualified_name
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            uuid4(),
                            project_id,
                            file_id,
                            symbol.name,
                            symbol.qualified_name,
                            symbol.kind,
                            symbol.line_start,
                            symbol.line_end,
                            symbol.parent_qualified_name,
                        ),
                    )

        cursor.execute(
            "SELECT count(*) FROM repository_symbols WHERE project_id = %s",
            (project_id,),
        )
        symbol_row = cursor.fetchone()
        if symbol_row is None:
            raise RuntimeError("repository symbol count query returned no row")
        symbol_count = int(symbol_row[0])
        _assert_snapshot_stable(settings, snapshot)
        cursor.execute(
            """
            UPDATE repository_index_runs
            SET status = 'COMPLETED', completed_at = CURRENT_TIMESTAMP,
                discovered_file_count = %s, indexed_file_count = %s,
                reused_file_count = %s, changed_file_count = %s,
                added_file_count = %s, removed_file_count = %s,
                unchanged_file_count = %s, parsed_file_count = %s,
                symbol_count = %s, error = NULL
            WHERE run_id = %s
            """,
            (
                len(snapshot.files),
                len(changed_paths),
                unchanged_count,
                changed_count,
                added_count,
                len(removed_paths),
                unchanged_count,
                len(parsed_by_path),
                symbol_count,
                run_id,
            ),
        )


def index_project(settings: Settings, project_id: UUID) -> IndexRunSummary:
    settings.validate_repository_limits()
    project_path = _project_path(settings, project_id)
    run_id = uuid4()
    try:
        snapshot = _collect_inventory(settings, project_path)
    except RepositoryIndexingError as exc:
        _create_run(settings, run_id, project_id, None)
        return _mark_failed(settings, run_id, exc.code, 0)

    _create_run(settings, run_id, project_id, snapshot)
    try:
        _perform_reconcile(settings, project_id, run_id, snapshot)
    except RepositoryIndexingError as exc:
        return _mark_failed(settings, run_id, exc.code, len(snapshot.files))
    except psycopg.Error as exc:
        return _mark_failed(
            settings,
            run_id,
            f"database_error_{type(exc).__name__}",
            len(snapshot.files),
        )
    return _get_run(settings, run_id)


def latest_index_run(settings: Settings, project_id: UUID) -> IndexRunSummary | None:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT {_run_columns()}
            FROM repository_index_runs
            WHERE project_id = %s
            ORDER BY started_at DESC, run_id DESC
            LIMIT 1
            """,
            (project_id,),
        )
        row = cursor.fetchone()
    return _run_from_row(row) if row else None


router = APIRouter(tags=["repository-indexing"])


def _api_error(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503, detail=f"repository index database unavailable ({type(exc).__name__})"
    )


@router.post(
    "/api/v1/projects/{project_id}/index",
    response_model=IndexRunSummary,
)
def trigger_repository_index(project_id: UUID) -> IndexRunSummary:
    try:
        return index_project(_settings(), project_id)
    except RepositoryProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    except ProjectPathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise _api_error(exc) from exc


@router.get(
    "/api/v1/projects/{project_id}/index",
    response_model=IndexRunSummary,
)
@router.get(
    "/api/v1/projects/{project_id}/index/status",
    response_model=IndexRunSummary,
)
def get_repository_index_status(project_id: UUID) -> IndexRunSummary:
    try:
        result = latest_index_run(_settings(), project_id)
    except psycopg.Error as exc:
        raise _api_error(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="repository index run not found")
    return result


def _settings() -> Settings:
    from .config import get_settings

    return get_settings()
