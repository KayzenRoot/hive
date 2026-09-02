from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from .config import Settings
from .db import database_connection
from .registry import ProjectPathError, normalize_project_path
from .repository_indexer import (
    RepositoryIndexingError,
    _read_stable_file,
    _resolve_tracked_path,
)

logger = logging.getLogger(__name__)

CHUNKER_VERSION = "line-window-v1"
MAX_CHUNK_LINES = 80
MAX_CHUNK_CHARS = 6000
OVERLAP_LINES = 10
LONG_LINE_OVERLAP_CHARS = 256
MAX_QUERY_CHARS = 512
MAX_TOP_K = 20
MAX_SNIPPET_CHARS = 640
INDEX_ADVISORY_LOCK_KEY = 12006

_ALNUM_RE = re.compile(r"[^\W_]+", re.UNICODE)
_IDENTIFIER_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|\d+", re.UNICODE)
SOURCE_KINDS = {"REPOSITORY_FILE", "REPOSITORY_SYMBOL", "TASK"}


class CorpusRunStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    STALE = "STALE"
    BLOCKED = "BLOCKED"


class CorpusState(StrEnum):
    CURRENT = "CURRENT"
    SYNCING = "SYNCING"
    STALE = "STALE"
    BLOCKED = "BLOCKED"


class RetrievalSyncError(RuntimeError):
    """A deterministic corpus build failed without changing the current corpus."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class RetrievalProjectNotFoundError(LookupError):
    """The requested project does not exist."""


class RetrievalQueryError(ValueError):
    """The lexical query is invalid or outside the bounded contract."""


class LexicalRequest(BaseModel):
    query: str = Field(min_length=1, max_length=MAX_QUERY_CHARS)
    top_k: int = Field(default=5, ge=1, le=MAX_TOP_K)
    source_kind: str | None = None

    @field_validator("query")
    @classmethod
    def normalize_query_input(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be blank")
        return value

    @field_validator("source_kind")
    @classmethod
    def validate_source_kind(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if normalized not in SOURCE_KINDS:
            raise ValueError("source_kind must be REPOSITORY_FILE, REPOSITORY_SYMBOL, or TASK")
        return normalized


@dataclass(frozen=True)
class NormalizedQuery:
    original: str
    normalized: str
    tokens: tuple[str, ...]
    basename: str


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    content: str
    content_sha256: str
    start_line: int
    end_line: int
    start_char: int
    end_char: int


@dataclass(frozen=True)
class _Source:
    source_kind: str
    source_id: UUID
    repository_file_id: UUID | None
    repository_symbol_id: UUID | None
    task_id: UUID | None
    path: str | None
    source_title: str | None
    qualified_symbol: str | None
    source_content_sha256: str
    text: str
    file_path: Path | None = None
    base_line: int = 1
    base_char: int = 0


@dataclass(frozen=True)
class _SourceBundle:
    project_id: UUID
    repository_path: Path
    repository_index_run_id: UUID
    repository_head: str
    repository_inventory: tuple[str, ...]
    repository_file_hashes: tuple[tuple[str, str], ...]
    repository_sources: tuple[_Source, ...]
    task_sources: tuple[_Source, ...]
    repository_source_fingerprint: str
    task_source_fingerprint: str
    source_fingerprint: str
    skipped_binary_count: int
    skipped_decode_count: int


@dataclass(frozen=True)
class _DesiredReference:
    source: _Source
    chunk: Chunk
    reference_fingerprint: str
    metadata_text: str


class CorpusRunSummary(BaseModel):
    run_id: UUID
    project_id: UUID
    repository_index_run_id: UUID | None
    repository_source_fingerprint: str | None
    task_source_fingerprint: str | None
    source_fingerprint: str | None
    status: CorpusRunStatus
    started_at: datetime
    completed_at: datetime | None
    repository_source_count: int
    task_source_count: int
    chunk_count: int
    reference_count: int
    repository_reference_count: int
    task_reference_count: int
    new_chunk_count: int
    reused_chunk_count: int
    new_reference_count: int
    reused_reference_count: int
    removed_reference_count: int
    current_reference_count: int
    skipped_binary_count: int
    skipped_decode_count: int
    error: str | None


class CorpusStatusResponse(BaseModel):
    project_id: UUID
    state: CorpusState
    last_successful_sync: datetime | None
    latest_run: CorpusRunSummary | None
    chunk_count: int
    reference_count: int
    repository_reference_count: int
    task_reference_count: int


class LexicalCandidate(BaseModel):
    project_id: UUID
    reference_id: UUID
    chunk_id: UUID
    corpus_run_id: UUID
    source_kind: str
    lexical_score: float
    snippet: str
    path: str | None
    title: str | None
    qualified_symbol: str | None
    repository_file_id: UUID | None
    repository_symbol_id: UUID | None
    task_id: UUID | None
    source_content_sha256: str
    chunk_content_sha256: str
    chunker_version: str
    start_line: int
    end_line: int
    start_char: int
    end_char: int


class LexicalResponse(BaseModel):
    project_id: UUID
    query: str
    normalized_query: str
    top_k: int
    results: list[LexicalCandidate]


_RUN_COLUMNS = """
    run_id, project_id, repository_index_run_id,
    repository_source_fingerprint, task_source_fingerprint, source_fingerprint,
    status, started_at, completed_at, repository_source_count, task_source_count,
    chunk_count, reference_count, repository_reference_count, task_reference_count,
    new_chunk_count, reused_chunk_count, new_reference_count, reused_reference_count,
    removed_reference_count, current_reference_count, skipped_binary_count,
    skipped_decode_count, error
"""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _fingerprint(values: list[str]) -> str:
    digest = hashlib.sha256()
    for value in values:
        encoded = value.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def _identifier_tokens(value: str) -> list[str]:
    tokens: list[str] = []
    for raw in _ALNUM_RE.findall(value):
        pieces = _IDENTIFIER_RE.findall(raw)
        tokens.extend(piece.casefold() for piece in pieces or [raw])
    return [token for token in tokens if token]


def lexical_search_text(value: str) -> str:
    """Add identifier aliases so snake/camel/dotted queries match source text."""
    return value + "\n" + " ".join(_identifier_tokens(value))


def normalize_lexical_query(value: str) -> NormalizedQuery:
    original = value.strip()
    if not original:
        raise RetrievalQueryError("query must not be blank")
    if len(original) > MAX_QUERY_CHARS:
        raise RetrievalQueryError("query exceeds the maximum length")
    tokens: list[str] = []
    seen: set[str] = set()
    for token in _identifier_tokens(original):
        if token not in seen:
            seen.add(token)
            tokens.append(token)
    if not tokens:
        raise RetrievalQueryError("query must contain searchable characters")
    basename = re.split(r"[\\/]", original)[-1].casefold()
    return NormalizedQuery(original, " ".join(tokens), tuple(tokens), basename)


def chunk_text(text: str) -> list[Chunk]:
    """Create stable bounded line windows with exact Python character ranges."""
    if not text:
        return []
    lines = text.splitlines(keepends=True)
    if not lines:
        lines = [text]
    offsets: list[int] = []
    offset = 0
    for line in lines:
        offsets.append(offset)
        offset += len(line)

    chunks: list[Chunk] = []
    ordinal = 0
    start = 0
    while start < len(lines):
        line = lines[start]
        if len(line) > MAX_CHUNK_CHARS:
            segment_start = 0
            while segment_start < len(line):
                segment_end = min(segment_start + MAX_CHUNK_CHARS, len(line))
                content = line[segment_start:segment_end]
                chunks.append(
                    Chunk(
                        ordinal,
                        content,
                        _sha256(content.encode("utf-8")),
                        start + 1,
                        start + 1,
                        offsets[start] + segment_start,
                        offsets[start] + segment_end,
                    )
                )
                ordinal += 1
                if segment_end == len(line):
                    break
                segment_start = max(segment_start + 1, segment_end - LONG_LINE_OVERLAP_CHARS)
            start += 1
            continue

        end = start
        char_count = 0
        while end < len(lines) and end - start < MAX_CHUNK_LINES:
            next_length = len(lines[end])
            if end > start and char_count + next_length > MAX_CHUNK_CHARS:
                break
            char_count += next_length
            end += 1
        if end == start:
            end = start + 1
        start_char = offsets[start]
        end_char = offsets[end - 1] + len(lines[end - 1])
        content = text[start_char:end_char]
        chunks.append(
            Chunk(
                ordinal,
                content,
                _sha256(content.encode("utf-8")),
                start + 1,
                end,
                start_char,
                end_char,
            )
        )
        ordinal += 1
        if end >= len(lines):
            break
        start = max(start + 1, end - OVERLAP_LINES)
    return chunks


def _reference_fingerprint(source: _Source, chunk: Chunk) -> str:
    return _fingerprint(
        [
            CHUNKER_VERSION,
            source.source_kind,
            str(source.source_id),
            str(source.repository_file_id or ""),
            str(source.repository_symbol_id or ""),
            str(source.task_id or ""),
            source.path or "",
            source.source_title or "",
            source.qualified_symbol or "",
            source.source_content_sha256,
            str(chunk.ordinal),
            str(chunk.start_line),
            str(chunk.end_line),
            str(chunk.start_char),
            str(chunk.end_char),
            str(source.base_line),
            str(source.base_char),
            chunk.content_sha256,
        ]
    )


def _absolute_chunk_ranges(source: _Source, chunk: Chunk) -> tuple[int, int, int, int]:
    return (
        source.base_line + chunk.start_line - 1,
        source.base_line + chunk.end_line - 1,
        source.base_char + chunk.start_char,
        source.base_char + chunk.end_char,
    )


def _metadata_text(source: _Source) -> str:
    raw = " ".join(
        value for value in (source.path, source.source_title, source.qualified_symbol) if value
    )
    return lexical_search_text(raw)


def _run_from_row(row: tuple[Any, ...]) -> CorpusRunSummary:
    return CorpusRunSummary(
        run_id=cast(UUID, row[0]),
        project_id=cast(UUID, row[1]),
        repository_index_run_id=cast(UUID | None, row[2]),
        repository_source_fingerprint=cast(str | None, row[3]),
        task_source_fingerprint=cast(str | None, row[4]),
        source_fingerprint=cast(str | None, row[5]),
        status=CorpusRunStatus(str(row[6])),
        started_at=cast(datetime, row[7]),
        completed_at=cast(datetime | None, row[8]),
        repository_source_count=int(row[9]),
        task_source_count=int(row[10]),
        chunk_count=int(row[11]),
        reference_count=int(row[12]),
        repository_reference_count=int(row[13]),
        task_reference_count=int(row[14]),
        new_chunk_count=int(row[15]),
        reused_chunk_count=int(row[16]),
        new_reference_count=int(row[17]),
        reused_reference_count=int(row[18]),
        removed_reference_count=int(row[19]),
        current_reference_count=int(row[20]),
        skipped_binary_count=int(row[21]),
        skipped_decode_count=int(row[22]),
        error=cast(str | None, row[23]),
    )


def _get_run(settings: Settings, run_id: UUID) -> CorpusRunSummary:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {_RUN_COLUMNS} FROM retrieval_corpus_runs WHERE run_id = %s", (run_id,)
        )
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError("retrieval corpus run disappeared")
    return _run_from_row(row)


def _create_run(
    settings: Settings,
    run_id: UUID,
    project_id: UUID,
    repository_index_run_id: UUID | None,
) -> None:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO retrieval_corpus_runs (run_id, project_id, repository_index_run_id, status)
            VALUES (%s, %s, %s, 'RUNNING')
            """,
            (run_id, project_id, repository_index_run_id),
        )


def _update_failed_run(
    settings: Settings,
    run_id: UUID,
    status: CorpusRunStatus,
    error: str,
    bundle: _SourceBundle | None,
) -> CorpusRunSummary:
    values = (
        status.value,
        bundle.repository_source_fingerprint if bundle else None,
        bundle.task_source_fingerprint if bundle else None,
        bundle.source_fingerprint if bundle else None,
        len(bundle.repository_sources) if bundle else 0,
        len(bundle.task_sources) if bundle else 0,
        bundle.skipped_binary_count if bundle else 0,
        bundle.skipped_decode_count if bundle else 0,
        error[:256],
        run_id,
    )
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE retrieval_corpus_runs
            SET status = %s, completed_at = CURRENT_TIMESTAMP,
                repository_source_fingerprint = %s, task_source_fingerprint = %s,
                source_fingerprint = %s, repository_source_count = %s,
                task_source_count = %s, skipped_binary_count = %s,
                skipped_decode_count = %s, error = %s
            WHERE run_id = %s
            """,
            values,
        )
    return _get_run(settings, run_id)


def _project_path_and_index_run(
    settings: Settings, project_id: UUID
) -> tuple[Path, UUID, str, set[str]]:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT relative_path FROM projects WHERE project_id = %s", (project_id,))
        project_row = cursor.fetchone()
        if project_row is None:
            raise RetrievalProjectNotFoundError(str(project_id))
        cursor.execute(
            """
            SELECT run_id, repository_head_sha
            FROM repository_index_runs
            WHERE project_id = %s AND status = 'COMPLETED'
            ORDER BY completed_at DESC NULLS LAST, run_id DESC
            LIMIT 1
            """,
            (project_id,),
        )
        index_row = cursor.fetchone()
        if index_row is None or index_row[1] is None:
            raise RetrievalSyncError("repository_index_not_available")
        cursor.execute(
            """
            SELECT path
            FROM repository_files
            WHERE project_id = %s AND is_current
            ORDER BY path
            """,
            (project_id,),
        )
        indexed_paths = {str(row[0]) for row in cursor.fetchall()}
    try:
        _, project_path = normalize_project_path(cast(str, project_row[0]), settings)
    except ProjectPathError as exc:
        raise RetrievalSyncError("project_path_invalid") from exc
    return project_path, cast(UUID, index_row[0]), str(index_row[1]), indexed_paths


def _git_output(project_path: Path, arguments: list[str]) -> bytes:
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        result = subprocess.run(
            ["git", "-c", f"safe.directory={project_path}", "-C", str(project_path), *arguments],
            capture_output=True,
            check=False,
            env=environment,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RetrievalSyncError("repository_inventory_unavailable") from exc
    if result.returncode != 0:
        raise RetrievalSyncError("repository_inventory_unavailable")
    return result.stdout


def _load_repository_sources(
    settings: Settings, project_id: UUID
) -> tuple[
    Path,
    UUID,
    tuple[_Source, ...],
    int,
    int,
    str,
    str,
    tuple[str, ...],
    tuple[tuple[str, str], ...],
]:
    project_path, index_run_id, indexed_head, indexed_paths = _project_path_and_index_run(
        settings, project_id
    )
    try:
        current_head = _git_output(project_path, ["rev-parse", "--verify", "HEAD^{commit}"])
        if current_head.decode("ascii").strip().lower() != indexed_head.lower():
            raise RetrievalSyncError("repository_index_stale")
        inventory = _git_output(project_path, ["ls-files", "--cached", "-z", "--"])
        actual_paths = {raw.decode("utf-8") for raw in inventory.split(b"\0") if raw}
    except UnicodeDecodeError as exc:
        raise RetrievalSyncError("repository_inventory_unavailable") from exc
    if actual_paths != indexed_paths:
        raise RetrievalSyncError("repository_index_stale")

    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT file_id, path, content_sha256, file_type
            FROM repository_files
            WHERE project_id = %s AND is_current
            ORDER BY path
            """,
            (project_id,),
        )
        file_rows = cursor.fetchall()
        cursor.execute(
            """
            SELECT symbol_id, file_id, name, qualified_name, line_start, line_end
            FROM repository_symbols
            WHERE project_id = %s
            ORDER BY file_id, line_start, line_end, qualified_name, symbol_id
            """,
            (project_id,),
        )
        symbol_rows = cursor.fetchall()

    symbols_by_file: dict[UUID, list[tuple[Any, ...]]] = {}
    for row in symbol_rows:
        symbols_by_file.setdefault(cast(UUID, row[1]), []).append(row)
    sources: list[_Source] = []
    skipped_binary = 0
    skipped_decode = 0
    for file_id_raw, path_raw, content_hash_raw, file_type_raw in file_rows:
        file_id = cast(UUID, file_id_raw)
        path = str(path_raw)
        if str(file_type_raw) == "binary":
            skipped_binary += 1
            continue
        try:
            resolved = _resolve_tracked_path(project_path, path)
            source_bytes, _ = _read_stable_file(resolved, settings)
        except (ProjectPathError, RepositoryIndexingError) as exc:
            raise RetrievalSyncError("repository_source_unavailable") from exc
        if _sha256(source_bytes) != str(content_hash_raw):
            raise RetrievalSyncError("repository_source_stale")
        try:
            text = source_bytes.decode("utf-8")
        except UnicodeDecodeError:
            skipped_decode += 1
            continue
        file_source = _Source(
            "REPOSITORY_FILE",
            file_id,
            file_id,
            None,
            None,
            path,
            None,
            None,
            str(content_hash_raw),
            text,
            resolved,
        )
        sources.append(file_source)
        for (
            symbol_id_raw,
            _,
            name_raw,
            qualified_raw,
            line_start_raw,
            line_end_raw,
        ) in symbols_by_file.get(file_id, []):
            symbol_id = cast(UUID, symbol_id_raw)
            lines = text.splitlines(keepends=True)
            line_start = max(1, int(line_start_raw))
            line_end = max(line_start, int(line_end_raw))
            if not lines or line_start > len(lines):
                continue
            source_start = sum(len(line) for line in lines[: line_start - 1])
            source_end = sum(len(line) for line in lines[: min(line_end, len(lines))])
            sources.append(
                _Source(
                    "REPOSITORY_SYMBOL",
                    symbol_id,
                    file_id,
                    symbol_id,
                    None,
                    path,
                    None,
                    str(qualified_raw),
                    str(content_hash_raw),
                    text[source_start:source_end],
                    resolved,
                    line_start,
                    source_start,
                )
            )
            _ = name_raw
    fingerprint_values = [
        f"{source.source_kind}|{source.source_id}|{source.path}|{source.source_content_sha256}"
        for source in sources
    ]
    repository_file_hashes = tuple(
        sorted(
            (str(path_raw), str(content_hash_raw)) for _, path_raw, content_hash_raw, _ in file_rows
        )
    )
    return (
        project_path,
        index_run_id,
        tuple(sources),
        skipped_binary,
        skipped_decode,
        _fingerprint(fingerprint_values),
        indexed_head,
        tuple(sorted(indexed_paths)),
        repository_file_hashes,
    )


def _load_task_sources(settings: Settings, project_id: UUID) -> tuple[tuple[_Source, ...], str]:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT t.task_id, t.title, t.original_filename, t.extraction_version,
                   e.text_content
            FROM tasks AS t
            JOIN task_extractions AS e ON e.extraction_id = t.extraction_id
            WHERE t.project_id = %s AND t.intake_status = 'READY'
              AND e.status = 'READY' AND e.text_content IS NOT NULL
            ORDER BY t.task_id
            """,
            (project_id,),
        )
        rows = cursor.fetchall()
    sources: list[_Source] = []
    fingerprint_values: list[str] = []
    for task_id_raw, title_raw, filename_raw, extraction_version_raw, text_raw in rows:
        task_id = cast(UUID, task_id_raw)
        text = str(text_raw)
        if not text:
            continue
        source_hash = _sha256(text.encode("utf-8"))
        title = str(title_raw) if title_raw else str(filename_raw) if filename_raw else None
        source = _Source(
            "TASK",
            task_id,
            None,
            None,
            task_id,
            None,
            title,
            None,
            source_hash,
            text,
        )
        sources.append(source)
        fingerprint_values.append(f"{task_id}|{source_hash}|{extraction_version_raw}|{title or ''}")
    return tuple(sources), _fingerprint(fingerprint_values)


def _load_source_bundle(settings: Settings, project_id: UUID) -> _SourceBundle:
    (
        repository_path,
        index_run_id,
        repository_sources,
        skipped_binary,
        skipped_decode,
        repository_fingerprint,
        repository_head,
        repository_inventory,
        repository_file_hashes,
    ) = _load_repository_sources(settings, project_id)
    task_sources, task_fingerprint = _load_task_sources(settings, project_id)
    source_fingerprint = _fingerprint([repository_fingerprint, task_fingerprint, str(index_run_id)])
    return _SourceBundle(
        project_id,
        repository_path,
        index_run_id,
        repository_head,
        repository_inventory,
        repository_file_hashes,
        repository_sources,
        task_sources,
        repository_fingerprint,
        task_fingerprint,
        source_fingerprint,
        skipped_binary,
        skipped_decode,
    )


def _revalidate_bundle(settings: Settings, bundle: _SourceBundle) -> None:
    try:
        current_head = (
            _git_output(bundle.repository_path, ["rev-parse", "--verify", "HEAD^{commit}"])
            .decode("ascii")
            .strip()
            .lower()
        )
        inventory_bytes = _git_output(bundle.repository_path, ["ls-files", "--cached", "-z", "--"])
        current_inventory = tuple(
            sorted(raw.decode("utf-8") for raw in inventory_bytes.split(b"\0") if raw)
        )
    except (RetrievalSyncError, UnicodeDecodeError) as exc:
        raise RetrievalSyncError("repository_source_stale") from exc
    if current_head != bundle.repository_head.lower():
        raise RetrievalSyncError("repository_source_stale")
    if current_inventory != bundle.repository_inventory:
        raise RetrievalSyncError("repository_source_stale")

    for path, expected_hash in bundle.repository_file_hashes:
        try:
            resolved = _resolve_tracked_path(bundle.repository_path, path)
            source_bytes, _ = _read_stable_file(resolved, settings)
        except (ProjectPathError, RepositoryIndexingError) as exc:
            raise RetrievalSyncError("repository_source_stale") from exc
        if _sha256(source_bytes) != expected_hash:
            raise RetrievalSyncError("repository_source_stale")


def _desired_references(bundle: _SourceBundle) -> tuple[dict[str, Chunk], list[_DesiredReference]]:
    chunks: dict[str, Chunk] = {}
    references: list[_DesiredReference] = []
    for source in (*bundle.repository_sources, *bundle.task_sources):
        for chunk in chunk_text(source.text):
            chunks.setdefault(chunk.content_sha256, chunk)
            references.append(
                _DesiredReference(
                    source, chunk, _reference_fingerprint(source, chunk), _metadata_text(source)
                )
            )
    references.sort(key=lambda item: item.reference_fingerprint)
    return chunks, references


def _promote(
    settings: Settings,
    bundle: _SourceBundle,
    run_id: UUID,
    chunks: dict[str, Chunk],
    references: list[_DesiredReference],
) -> None:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(%s, hashtext(%s))",
            (INDEX_ADVISORY_LOCK_KEY, str(bundle.project_id)),
        )
        _revalidate_bundle(settings, bundle)
        cursor.execute(
            """
            SELECT run_id
            FROM repository_index_runs
            WHERE project_id = %s AND status = 'COMPLETED'
            ORDER BY completed_at DESC NULLS LAST, run_id DESC
            LIMIT 1
            """,
            (bundle.project_id,),
        )
        index_row = cursor.fetchone()
        if index_row is None or cast(UUID, index_row[0]) != bundle.repository_index_run_id:
            raise RetrievalSyncError("repository_index_changed_during_sync")

        chunk_ids: dict[str, UUID] = {}
        new_chunks = 0
        reused_chunks = 0
        for chunk_hash in sorted(chunks):
            chunk = chunks[chunk_hash]
            cursor.execute(
                """
                INSERT INTO retrieval_chunks (
                    chunk_id, project_id, content_sha256, chunker_version, content,
                    char_count, line_count, search_vector
                )
                SELECT %s, %s, %s, %s, %s, %s, %s,
                       to_tsvector('simple', %s)
                ON CONFLICT (project_id, chunker_version, content_sha256) DO NOTHING
                RETURNING chunk_id
                """,
                (
                    uuid4(),
                    bundle.project_id,
                    chunk.content_sha256,
                    CHUNKER_VERSION,
                    chunk.content,
                    len(chunk.content),
                    chunk.end_line - chunk.start_line + 1,
                    lexical_search_text(chunk.content),
                ),
            )
            inserted = cursor.fetchone()
            if inserted:
                chunk_ids[chunk_hash] = cast(UUID, inserted[0])
                new_chunks += 1
            else:
                cursor.execute(
                    """
                    SELECT chunk_id
                    FROM retrieval_chunks
                    WHERE project_id = %s AND chunker_version = %s AND content_sha256 = %s
                    """,
                    (bundle.project_id, CHUNKER_VERSION, chunk.content_sha256),
                )
                existing = cursor.fetchone()
                if existing is None:
                    raise RuntimeError("retrieval chunk disappeared after conflict")
                chunk_ids[chunk_hash] = cast(UUID, existing[0])
                reused_chunks += 1

        cursor.execute(
            """
            SELECT reference_id, reference_fingerprint
            FROM retrieval_references
            WHERE project_id = %s
            """,
            (bundle.project_id,),
        )
        reference_ids = {str(row[1]): cast(UUID, row[0]) for row in cursor.fetchall()}
        desired_fingerprints: set[str] = set()
        new_references = 0
        reused_references = 0
        repository_reference_count = 0
        task_reference_count = 0
        for desired in references:
            desired_fingerprints.add(desired.reference_fingerprint)
            source = desired.source
            chunk_id = chunk_ids[desired.chunk.content_sha256]
            start_line, end_line, start_char, end_char = _absolute_chunk_ranges(
                source, desired.chunk
            )
            if source.source_kind == "TASK":
                task_reference_count += 1
            else:
                repository_reference_count += 1
            existing_id = reference_ids.get(desired.reference_fingerprint)
            if existing_id is None:
                cursor.execute(
                    """
                    INSERT INTO retrieval_references (
                        reference_id, project_id, chunk_id, corpus_run_id, source_kind,
                        repository_file_id, repository_symbol_id, task_id, path,
                        source_title, qualified_symbol, source_content_sha256,
                        start_line, end_line, start_char, end_char, chunk_ordinal,
                        reference_fingerprint, is_current, metadata_vector
                    )
                    SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                           %s, %s, %s, %s, %s, %s, TRUE,
                           to_tsvector('simple', %s)
                    """,
                    (
                        uuid4(),
                        bundle.project_id,
                        chunk_id,
                        run_id,
                        source.source_kind,
                        source.repository_file_id,
                        source.repository_symbol_id,
                        source.task_id,
                        source.path,
                        source.source_title,
                        source.qualified_symbol,
                        source.source_content_sha256,
                        start_line,
                        end_line,
                        start_char,
                        end_char,
                        desired.chunk.ordinal,
                        desired.reference_fingerprint,
                        desired.metadata_text,
                    ),
                )
                new_references += 1
            else:
                cursor.execute(
                    """
                    UPDATE retrieval_references
                    SET chunk_id = %s, corpus_run_id = %s, is_current = TRUE,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE project_id = %s AND reference_id = %s
                    """,
                    (chunk_id, run_id, bundle.project_id, existing_id),
                )
                reused_references += 1

        removed_references = 0
        cursor.execute(
            """
            SELECT reference_id, reference_fingerprint
            FROM retrieval_references
            WHERE project_id = %s AND is_current
            """,
            (bundle.project_id,),
        )
        for reference_id_raw, fingerprint_raw in cursor.fetchall():
            if str(fingerprint_raw) not in desired_fingerprints:
                cursor.execute(
                    """
                    UPDATE retrieval_references
                    SET is_current = FALSE, corpus_run_id = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE project_id = %s AND reference_id = %s
                    """,
                    (run_id, bundle.project_id, reference_id_raw),
                )
                removed_references += 1

        cursor.execute(
            """
            UPDATE retrieval_corpus_runs
            SET status = 'COMPLETED', completed_at = CURRENT_TIMESTAMP,
                repository_index_run_id = %s,
                repository_source_fingerprint = %s, task_source_fingerprint = %s,
                source_fingerprint = %s, repository_source_count = %s,
                task_source_count = %s, chunk_count = %s, reference_count = %s,
                repository_reference_count = %s, task_reference_count = %s,
                new_chunk_count = %s, reused_chunk_count = %s,
                new_reference_count = %s, reused_reference_count = %s,
                removed_reference_count = %s, current_reference_count = %s,
                skipped_binary_count = %s, skipped_decode_count = %s, error = NULL
            WHERE run_id = %s
            """,
            (
                bundle.repository_index_run_id,
                bundle.repository_source_fingerprint,
                bundle.task_source_fingerprint,
                bundle.source_fingerprint,
                len(bundle.repository_sources),
                len(bundle.task_sources),
                len(chunks),
                len(references),
                repository_reference_count,
                task_reference_count,
                new_chunks,
                reused_chunks,
                new_references,
                reused_references,
                removed_references,
                len(references),
                bundle.skipped_binary_count,
                bundle.skipped_decode_count,
                run_id,
            ),
        )


def _has_successful_sync(settings: Settings, project_id: UUID) -> bool:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1 FROM retrieval_corpus_runs
            WHERE project_id = %s AND status = 'COMPLETED'
            LIMIT 1
            """,
            (project_id,),
        )
        return cursor.fetchone() is not None


def _project_exists(settings: Settings, project_id: UUID) -> bool:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM projects WHERE project_id = %s", (project_id,))
        return cursor.fetchone() is not None


def sync_corpus(settings: Settings, project_id: UUID) -> CorpusRunSummary:
    settings.validate_repository_limits()
    if not _project_exists(settings, project_id):
        raise RetrievalProjectNotFoundError(str(project_id))
    run_id = uuid4()
    bundle: _SourceBundle | None = None
    try:
        # The first lookup both validates the project and records the exact
        # repository index generation used by this build.
        try:
            _, index_run_id, _, _ = _project_path_and_index_run(settings, project_id)
        except RetrievalSyncError:
            index_run_id = None
        _create_run(settings, run_id, project_id, index_run_id)
        bundle = _load_source_bundle(settings, project_id)
        chunks, references = _desired_references(bundle)
        _promote(settings, bundle, run_id, chunks, references)
    except RetrievalProjectNotFoundError:
        raise
    except RetrievalSyncError as exc:
        if not _run_exists(settings, run_id):
            raise
        state = (
            CorpusRunStatus.STALE
            if _has_successful_sync(settings, project_id)
            else CorpusRunStatus.BLOCKED
        )
        return _update_failed_run(settings, run_id, state, exc.code, bundle)
    except (OSError, RuntimeError, psycopg.Error) as exc:
        if not _run_exists(settings, run_id):
            raise
        state = (
            CorpusRunStatus.FAILED
            if not _has_successful_sync(settings, project_id)
            else CorpusRunStatus.STALE
        )
        return _update_failed_run(
            settings, run_id, state, f"database_error_{type(exc).__name__}", bundle
        )
    return _get_run(settings, run_id)


def _run_exists(settings: Settings, run_id: UUID) -> bool:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM retrieval_corpus_runs WHERE run_id = %s", (run_id,))
        return cursor.fetchone() is not None


def corpus_status(settings: Settings, project_id: UUID) -> CorpusStatusResponse:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM projects WHERE project_id = %s", (project_id,))
        if cursor.fetchone() is None:
            raise RetrievalProjectNotFoundError(str(project_id))
        cursor.execute(
            f"""
            SELECT {_RUN_COLUMNS}
            FROM retrieval_corpus_runs
            WHERE project_id = %s
            ORDER BY started_at DESC, run_id DESC
            LIMIT 1
            """,
            (project_id,),
        )
        latest_row = cursor.fetchone()
        cursor.execute(
            """
            SELECT count(DISTINCT r.chunk_id), count(*),
                   count(*) FILTER (WHERE r.source_kind <> 'TASK'),
                   count(*) FILTER (WHERE r.source_kind = 'TASK')
            FROM retrieval_references AS r
            WHERE r.project_id = %s AND r.is_current
            """,
            (project_id,),
        )
        counts = cursor.fetchone() or (0, 0, 0, 0)
        cursor.execute(
            """
            SELECT completed_at
            FROM retrieval_corpus_runs
            WHERE project_id = %s AND status = 'COMPLETED'
            ORDER BY completed_at DESC, run_id DESC
            LIMIT 1
            """,
            (project_id,),
        )
        successful_row = cursor.fetchone()
    latest = _run_from_row(latest_row) if latest_row else None
    if latest and latest.status == CorpusRunStatus.RUNNING:
        state = CorpusState.SYNCING
    elif latest and latest.status == CorpusRunStatus.COMPLETED:
        state = CorpusState.CURRENT
    elif successful_row:
        state = CorpusState.STALE
    else:
        state = CorpusState.BLOCKED
    return CorpusStatusResponse(
        project_id=project_id,
        state=state,
        last_successful_sync=cast(datetime | None, successful_row[0]) if successful_row else None,
        latest_run=latest,
        chunk_count=int(counts[0]),
        reference_count=int(counts[1]),
        repository_reference_count=int(counts[2]),
        task_reference_count=int(counts[3]),
    )


def _snippet(content: str, query: NormalizedQuery) -> str:
    folded = content.casefold()
    positions = [folded.find(token) for token in query.tokens if folded.find(token) >= 0]
    center = min(positions) if positions else 0
    if len(content) <= MAX_SNIPPET_CHARS:
        return content
    start = max(0, center - MAX_SNIPPET_CHARS // 3)
    end = min(len(content), start + MAX_SNIPPET_CHARS)
    if end - start < MAX_SNIPPET_CHARS:
        start = max(0, end - MAX_SNIPPET_CHARS)
    prefix = "..." if start else ""
    suffix = "..." if end < len(content) else ""
    return prefix + content[start:end] + suffix


def lexical_search(
    settings: Settings, project_id: UUID, request: LexicalRequest
) -> LexicalResponse:
    query = normalize_lexical_query(request.query)
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM projects WHERE project_id = %s", (project_id,))
        if cursor.fetchone() is None:
            raise RetrievalProjectNotFoundError(str(project_id))
        cursor.execute(
            """
            WITH q AS (
                SELECT plainto_tsquery('simple', %s) AS ts_query,
                       lower(%s) AS raw_query,
                       lower(%s) AS basename
            ), scored AS (
                SELECT r.project_id, r.reference_id, r.chunk_id, r.corpus_run_id,
                       r.source_kind, c.content, r.path, r.source_title,
                       r.qualified_symbol, r.repository_file_id, r.repository_symbol_id,
                       r.task_id, r.source_content_sha256, c.content_sha256,
                       c.chunker_version, r.start_line, r.end_line, r.start_char,
                       r.end_char,
                       ts_rank_cd(c.search_vector, q.ts_query)
                   + 1.5 * ts_rank_cd(r.metadata_vector, q.ts_query)
                   + CASE WHEN lower(coalesce(r.qualified_symbol, '')) = q.raw_query
                         THEN 4.0 ELSE 0.0 END
                   + CASE WHEN lower(coalesce(r.path, '')) = q.raw_query
                         THEN 3.0 ELSE 0.0 END
                   + CASE WHEN lower(regexp_replace(coalesce(r.path, ''), '^.*/', '')) = q.basename
                         THEN 2.0 ELSE 0.0 END
                   + CASE WHEN lower(coalesce(r.source_title, '')) = q.raw_query
                         THEN 1.5 ELSE 0.0 END
                   + CASE WHEN lower(coalesce(r.qualified_symbol, '')) LIKE q.raw_query || '.%%'
                         THEN 1.0 ELSE 0.0 END
                       AS lexical_score
                FROM retrieval_references AS r
                JOIN retrieval_chunks AS c
                  ON c.project_id = r.project_id AND c.chunk_id = r.chunk_id
                CROSS JOIN q
                WHERE r.project_id = %s AND r.is_current
                  AND (%s::text IS NULL OR r.source_kind = %s)
                  AND (
                      c.search_vector @@ q.ts_query
                      OR r.metadata_vector @@ q.ts_query
                      OR lower(coalesce(r.path, '')) = q.raw_query
                      OR lower(coalesce(r.source_title, '')) = q.raw_query
                      OR lower(coalesce(r.qualified_symbol, '')) = q.raw_query
                  )
            ), ranked AS (
                SELECT scored.*,
                       row_number() OVER (
                           PARTITION BY source_kind,
                             CASE WHEN source_kind = 'TASK' THEN chunk_id ELSE reference_id END
                           ORDER BY lexical_score DESC, task_id NULLS LAST, reference_id
                       ) AS candidate_rank
                FROM scored
            )
            SELECT project_id, reference_id, chunk_id, corpus_run_id,
                   source_kind, content, path, source_title,
                   qualified_symbol, repository_file_id, repository_symbol_id,
                   task_id, source_content_sha256, content_sha256,
                   chunker_version, start_line, end_line, start_char,
                   end_char, lexical_score
            FROM ranked
            WHERE candidate_rank = 1
            ORDER BY lexical_score DESC,
                     source_kind,
                     lower(coalesce(path, '')),
                     lower(coalesce(qualified_symbol, '')),
                     start_line,
                     reference_id
            LIMIT %s
            """,
            (
                query.normalized,
                query.original,
                query.basename,
                project_id,
                request.source_kind,
                request.source_kind,
                request.top_k,
            ),
        )
        rows = cursor.fetchall()
    results = [
        LexicalCandidate(
            project_id=cast(UUID, row[0]),
            reference_id=cast(UUID, row[1]),
            chunk_id=cast(UUID, row[2]),
            corpus_run_id=cast(UUID, row[3]),
            source_kind=str(row[4]),
            lexical_score=float(row[19]),
            snippet=_snippet(str(row[5]), query),
            path=cast(str | None, row[6]),
            title=cast(str | None, row[7]),
            qualified_symbol=cast(str | None, row[8]),
            repository_file_id=cast(UUID | None, row[9]),
            repository_symbol_id=cast(UUID | None, row[10]),
            task_id=cast(UUID | None, row[11]),
            source_content_sha256=str(row[12]),
            chunk_content_sha256=str(row[13]),
            chunker_version=str(row[14]),
            start_line=int(row[15]),
            end_line=int(row[16]),
            start_char=int(row[17]),
            end_char=int(row[18]),
        )
        for row in rows
    ]
    return LexicalResponse(
        project_id=project_id,
        query=query.original,
        normalized_query=query.normalized,
        top_k=request.top_k,
        results=results,
    )


router = APIRouter(tags=["retrieval"])


def _settings() -> Settings:
    from .config import get_settings

    return get_settings()


@router.post(
    "/api/v1/projects/{project_id}/retrieval/corpus/sync",
    response_model=CorpusRunSummary,
)
def sync_retrieval_corpus(project_id: UUID) -> CorpusRunSummary:
    try:
        return sync_corpus(_settings(), project_id)
    except RetrievalProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    except psycopg.Error as exc:
        raise HTTPException(
            status_code=503, detail="retrieval corpus database unavailable"
        ) from exc


@router.get(
    "/api/v1/projects/{project_id}/retrieval/corpus",
    response_model=CorpusStatusResponse,
)
def get_retrieval_corpus(project_id: UUID) -> CorpusStatusResponse:
    try:
        return corpus_status(_settings(), project_id)
    except RetrievalProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    except psycopg.Error as exc:
        raise HTTPException(
            status_code=503, detail="retrieval corpus database unavailable"
        ) from exc


@router.post(
    "/api/v1/projects/{project_id}/retrieval/lexical",
    response_model=LexicalResponse,
)
def query_retrieval_lexical(project_id: UUID, request: LexicalRequest) -> LexicalResponse:
    try:
        return lexical_search(_settings(), project_id, request)
    except RetrievalProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    except RetrievalQueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except psycopg.Error as exc:
        logger.exception("lexical retrieval database query failed")
        raise HTTPException(
            status_code=503, detail="retrieval corpus database unavailable"
        ) from exc
