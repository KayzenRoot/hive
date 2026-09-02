"""Provider-independent pgvector semantic retrieval and deterministic hybrid fusion."""

from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .config import Settings
from .db import database_connection
from .retrieval import (
    MAX_TOP_K,
    LexicalCandidate,
    LexicalRequest,
    RetrievalProjectNotFoundError,
    RetrievalQueryError,
    lexical_search,
    normalize_lexical_query,
)

logger = logging.getLogger(__name__)

ADAPTER_KIND = "openai-compatible-http"
DISTANCE_METRIC = "cosine"
MAX_VECTOR_DIMENSIONS = 2000
MAX_PROVIDER_ERROR = 256


class SemanticRunStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    STALE = "STALE"
    BLOCKED = "BLOCKED"


class SemanticState(StrEnum):
    CURRENT = "CURRENT"
    SYNCING = "SYNCING"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    BLOCKED = "BLOCKED"


class SemanticError(RuntimeError):
    """Base class for bounded semantic retrieval errors."""

    def __init__(self, code: str) -> None:
        self.code = code[:MAX_PROVIDER_ERROR]
        super().__init__(self.code)


class SemanticConfigurationError(SemanticError):
    pass


class SemanticUnavailableError(SemanticError):
    pass


class SemanticNotCurrentError(SemanticError):
    pass


class EmbeddingProviderError(SemanticError):
    pass


class EmbeddingProfile(BaseModel):
    adapter_kind: str
    model: str
    model_revision: str | None
    dimensions: int
    distance_metric: str
    identity_fingerprint: str


class SemanticRunSummary(BaseModel):
    run_id: UUID
    project_id: UUID
    corpus_run_id: UUID
    profile_id: UUID
    status: SemanticRunStatus
    source_fingerprint: str
    started_at: datetime
    completed_at: datetime | None
    current_chunk_count: int
    newly_embedded_count: int
    reused_embedding_count: int
    failed_count: int
    provider_request_count: int
    error: str | None


class SemanticStatusResponse(BaseModel):
    project_id: UUID
    state: SemanticState
    enabled: bool
    configured: bool
    profile: EmbeddingProfile | None
    current_corpus_run_id: UUID | None
    latest_run: SemanticRunSummary | None
    total_current_chunks: int
    embedded_chunk_count: int
    missing_chunk_count: int
    last_error: str | None


class SemanticCandidate(BaseModel):
    project_id: UUID
    reference_id: UUID
    chunk_id: UUID
    corpus_run_id: UUID
    semantic_run_id: UUID
    source_kind: str
    semantic_score: float
    semantic_distance: float
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


class SemanticResponse(BaseModel):
    project_id: UUID
    query: str
    normalized_query: str
    top_k: int
    semantic_state: SemanticState
    results: list[SemanticCandidate]


class HybridRequest(LexicalRequest):
    strict_semantic: bool = False


class HybridCandidate(BaseModel):
    project_id: UUID
    reference_id: UUID
    chunk_id: UUID
    corpus_run_id: UUID
    source_kind: str
    hybrid_score: float
    lexical_score: float | None
    semantic_score: float | None
    semantic_distance: float | None
    lexical_rank: int | None
    semantic_rank: int | None
    lexical_contribution: float
    semantic_contribution: float
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


class HybridResponse(BaseModel):
    project_id: UUID
    query: str
    normalized_query: str
    top_k: int
    state: str
    semantic_state: SemanticState
    fallback_reason: str | None
    candidate_pool: int
    results: list[HybridCandidate]


@dataclass(frozen=True)
class _CorpusGeneration:
    run_id: UUID
    source_fingerprint: str
    chunk_count: int


class EmbeddingAdapter(Protocol):
    profile: EmbeddingProfile

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        """Return vectors in exactly the same order as ``texts``."""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _normalize_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"}:
        raise SemanticConfigurationError("embedding_base_url_invalid_scheme")
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise SemanticConfigurationError("embedding_base_url_contains_credentials")
    return normalized


def _profile_from_settings(settings: Settings) -> EmbeddingProfile:
    settings.validate_embedding_limits()
    if not settings.embedding_enabled:
        raise SemanticUnavailableError("semantic_unavailable")
    if not settings.embedding_base_url or not settings.embedding_model:
        raise SemanticConfigurationError("embedding_configuration_incomplete")
    if settings.embedding_dimensions is None:
        raise SemanticConfigurationError("embedding_dimensions_missing")
    base_url = _normalize_base_url(settings.embedding_base_url)
    identity_payload = {
        "adapter_kind": ADAPTER_KIND,
        "base_url": base_url,
        "dimensions": settings.embedding_dimensions,
        "distance_metric": DISTANCE_METRIC,
        "model": settings.embedding_model.strip(),
        "model_revision": (settings.embedding_model_revision or "").strip() or None,
    }
    identity = _sha256(
        json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return EmbeddingProfile(
        adapter_kind=ADAPTER_KIND,
        model=str(identity_payload["model"]),
        model_revision=cast(str | None, identity_payload["model_revision"]),
        dimensions=settings.embedding_dimensions,
        distance_metric=DISTANCE_METRIC,
        identity_fingerprint=identity,
    )


def _validate_vector(values: object, dimensions: int, max_dimensions: int) -> tuple[float, ...]:
    if not isinstance(values, list) or not 1 <= len(values) <= max_dimensions:
        raise EmbeddingProviderError("provider_vector_invalid")
    if len(values) != dimensions:
        raise EmbeddingProviderError("provider_dimension_mismatch")
    vector: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise EmbeddingProviderError("provider_vector_invalid")
        converted = float(value)
        if not math.isfinite(converted):
            raise EmbeddingProviderError("provider_vector_non_finite")
        vector.append(converted)
    return tuple(vector)


def _safe_provider_error(error: Exception) -> str:
    if isinstance(error, HTTPError):
        return f"provider_http_{error.code}"
    if isinstance(error, TimeoutError):
        return "provider_timeout"
    if isinstance(error, URLError):
        return "provider_unavailable"
    return "provider_request_failed"


class OpenAICompatibleEmbeddingAdapter:
    """Small HTTP transport adapter; provider identity stays in configuration."""

    def __init__(self, settings: Settings, profile: EmbeddingProfile) -> None:
        if not settings.embedding_base_url:
            raise SemanticConfigurationError("embedding_base_url_missing")
        self.settings = settings
        self.profile = profile
        self.url = _normalize_base_url(settings.embedding_base_url) + "/embeddings"

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        if not texts:
            return []
        if len(texts) > self.settings.embedding_batch_size:
            raise EmbeddingProviderError("embedding_batch_too_large")
        if any(not isinstance(text, str) or not text for text in texts):
            raise EmbeddingProviderError("embedding_input_invalid")
        if any(len(text) > self.settings.embedding_max_input_chars for text in texts):
            raise EmbeddingProviderError("embedding_input_too_large")
        payload = json.dumps(
            {"input": texts, "model": self.profile.model},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.settings.embedding_api_key is not None:
            secret = self.settings.embedding_api_key.get_secret_value()
            headers["Authorization"] = f"Bearer {secret}"
        request = Request(self.url, data=payload, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self.settings.embedding_timeout_seconds) as response:
                response_body = response.read(2_000_000)
        except (HTTPError, OSError, TimeoutError, URLError) as exc:
            raise EmbeddingProviderError(_safe_provider_error(exc)) from exc
        try:
            decoded = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EmbeddingProviderError("provider_malformed_response") from exc
        if not isinstance(decoded, dict):
            raise EmbeddingProviderError("provider_malformed_response")
        model = decoded.get("model")
        if model is not None and model != self.profile.model:
            raise EmbeddingProviderError("provider_model_mismatch")
        data = decoded.get("data")
        if not isinstance(data, list) or len(data) != len(texts):
            raise EmbeddingProviderError("provider_response_count_mismatch")
        indexed: dict[int, tuple[float, ...]] = {}
        for item in data:
            if not isinstance(item, dict):
                raise EmbeddingProviderError("provider_malformed_response")
            index = item.get("index")
            if isinstance(index, bool) or not isinstance(index, int) or index in indexed:
                raise EmbeddingProviderError("provider_response_index_invalid")
            if index < 0 or index >= len(texts):
                raise EmbeddingProviderError("provider_response_index_invalid")
            indexed[index] = _validate_vector(
                item.get("embedding"),
                self.profile.dimensions,
                self.settings.embedding_max_dimensions,
            )
        if set(indexed) != set(range(len(texts))):
            raise EmbeddingProviderError("provider_response_index_invalid")
        return [indexed[index] for index in range(len(texts))]


def build_embedding_adapter(settings: Settings) -> EmbeddingAdapter | None:
    try:
        settings.validate_embedding_limits()
        if not settings.embedding_enabled:
            return None
        profile = _profile_from_settings(settings)
    except SemanticError:
        raise
    except ValueError as exc:
        raise SemanticConfigurationError("embedding_configuration_invalid") from exc
    return OpenAICompatibleEmbeddingAdapter(settings, profile)


def vector_literal(vector: tuple[float, ...]) -> str:
    return "[" + ",".join(format(value, ".17g") for value in vector) + "]"


def _embedding_fingerprint(
    profile: EmbeddingProfile, content_hash: str, vector: tuple[float, ...]
) -> str:
    payload = f"{profile.identity_fingerprint}|{content_hash}|{vector_literal(vector)}"
    return _sha256(payload.encode("utf-8"))


def _run_from_row(row: tuple[Any, ...]) -> SemanticRunSummary:
    return SemanticRunSummary(
        run_id=cast(UUID, row[0]),
        project_id=cast(UUID, row[1]),
        corpus_run_id=cast(UUID, row[2]),
        profile_id=cast(UUID, row[3]),
        status=SemanticRunStatus(str(row[4])),
        source_fingerprint=str(row[5]),
        started_at=cast(datetime, row[6]),
        completed_at=cast(datetime | None, row[7]),
        current_chunk_count=int(row[8]),
        newly_embedded_count=int(row[9]),
        reused_embedding_count=int(row[10]),
        failed_count=int(row[11]),
        provider_request_count=int(row[12]),
        error=cast(str | None, row[13]),
    )


_RUN_COLUMNS = """
    run_id, project_id, corpus_run_id, profile_id, status, source_fingerprint,
    started_at, completed_at, current_chunk_count, newly_embedded_count,
    reused_embedding_count, failed_count, provider_request_count, error
"""


def _get_run(settings: Settings, run_id: UUID) -> SemanticRunSummary:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {_RUN_COLUMNS} FROM retrieval_embedding_runs WHERE run_id = %s", (run_id,)
        )
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError("semantic run disappeared")
    return _run_from_row(row)


def _project_exists(settings: Settings, project_id: UUID) -> bool:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM projects WHERE project_id = %s", (project_id,))
        return cursor.fetchone() is not None


def _current_corpus(settings: Settings, project_id: UUID) -> _CorpusGeneration:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM projects WHERE project_id = %s", (project_id,))
        if cursor.fetchone() is None:
            raise RetrievalProjectNotFoundError(str(project_id))
        cursor.execute(
            """
            SELECT run_id, status, source_fingerprint, chunk_count
            FROM retrieval_corpus_runs
            WHERE project_id = %s
            ORDER BY started_at DESC, run_id DESC
            LIMIT 1
            """,
            (project_id,),
        )
        row = cursor.fetchone()
    if row is None or str(row[1]) != "COMPLETED" or not row[2]:
        raise SemanticNotCurrentError("lexical_corpus_not_current")
    return _CorpusGeneration(cast(UUID, row[0]), str(row[2]), int(row[3]))


def _latest_corpus(settings: Settings, project_id: UUID) -> _CorpusGeneration | None:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT run_id, status, source_fingerprint, chunk_count
            FROM retrieval_corpus_runs
            WHERE project_id = %s
            ORDER BY started_at DESC, run_id DESC
            LIMIT 1
            """,
            (project_id,),
        )
        row = cursor.fetchone()
    if row is None or str(row[1]) != "COMPLETED" or not row[2]:
        return None
    return _CorpusGeneration(cast(UUID, row[0]), str(row[2]), int(row[3]))


def _ensure_profile(settings: Settings, profile: EmbeddingProfile) -> UUID:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO embedding_profiles (
                profile_id, adapter_kind, model, model_revision, dimensions,
                distance_metric, identity_fingerprint
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (identity_fingerprint) DO UPDATE
            SET updated_at = CURRENT_TIMESTAMP
            RETURNING profile_id
            """,
            (
                uuid4(),
                profile.adapter_kind,
                profile.model,
                profile.model_revision,
                profile.dimensions,
                profile.distance_metric,
                profile.identity_fingerprint,
            ),
        )
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError("embedding profile was not returned")
    return cast(UUID, row[0])


def _profile_id(settings: Settings, profile: EmbeddingProfile) -> UUID | None:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT profile_id FROM embedding_profiles WHERE identity_fingerprint = %s",
            (profile.identity_fingerprint,),
        )
        row = cursor.fetchone()
    return cast(UUID, row[0]) if row else None


def _create_run(
    settings: Settings,
    run_id: UUID,
    project_id: UUID,
    corpus: _CorpusGeneration,
    profile_id: UUID,
) -> None:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO retrieval_embedding_runs (
                run_id, project_id, corpus_run_id, profile_id, status, source_fingerprint
            ) VALUES (%s, %s, %s, %s, 'RUNNING', %s)
            """,
            (run_id, project_id, corpus.run_id, profile_id, corpus.source_fingerprint),
        )


def _update_run(
    settings: Settings,
    run_id: UUID,
    *,
    status: SemanticRunStatus,
    current_count: int,
    new_count: int,
    reused_count: int,
    failed_count: int,
    requests: int,
    error: str | None,
) -> None:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE retrieval_embedding_runs
                SET status = %s, completed_at = CASE
                    WHEN %s <> 'RUNNING' THEN CURRENT_TIMESTAMP
                    ELSE completed_at
                END,
                current_chunk_count = %s, newly_embedded_count = %s,
                reused_embedding_count = %s, failed_count = %s,
                provider_request_count = %s, error = %s
            WHERE run_id = %s
            """,
            (
                status.value,
                status.value,
                current_count,
                new_count,
                reused_count,
                failed_count,
                requests,
                error[:MAX_PROVIDER_ERROR] if error else None,
                run_id,
            ),
        )


def _current_chunks(
    settings: Settings, project_id: UUID, corpus_run_id: UUID
) -> list[tuple[UUID, str, str]]:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT c.chunk_id, c.content, c.content_sha256
            FROM retrieval_references AS r
            JOIN retrieval_chunks AS c
              ON c.project_id = r.project_id AND c.chunk_id = r.chunk_id
            WHERE r.project_id = %s AND r.corpus_run_id = %s AND r.is_current
            ORDER BY c.chunk_id
            """,
            (project_id, corpus_run_id),
        )
        return [(cast(UUID, row[0]), str(row[1]), str(row[2])) for row in cursor.fetchall()]


def _compatible_embedding_ids(
    settings: Settings,
    project_id: UUID,
    profile_id: UUID,
    chunks: list[tuple[UUID, str, str]],
) -> set[UUID]:
    if not chunks:
        return set()
    chunk_ids = [chunk[0] for chunk in chunks]
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT chunk_id, source_chunk_content_sha256
            FROM retrieval_chunk_embeddings
            WHERE project_id = %s AND profile_id = %s
              AND dimensions = (SELECT dimensions FROM embedding_profiles WHERE profile_id = %s)
              AND chunk_id = ANY(%s)
            """,
            (project_id, profile_id, profile_id, chunk_ids),
        )
        expected_hashes = {chunk_id: content_hash for chunk_id, _, content_hash in chunks}
        return {
            cast(UUID, row[0])
            for row in cursor.fetchall()
            if expected_hashes.get(cast(UUID, row[0])) == str(row[1])
        }


def _persist_batch(
    settings: Settings,
    project_id: UUID,
    profile: EmbeddingProfile,
    profile_id: UUID,
    batch: list[tuple[UUID, str, str]],
    vectors: list[tuple[float, ...]],
) -> int:
    inserted_count = 0
    with database_connection(settings) as connection, connection.cursor() as cursor:
        for (chunk_id, _, content_hash), vector in zip(batch, vectors, strict=True):
            cursor.execute(
                """
                INSERT INTO retrieval_chunk_embeddings (
                    embedding_id, project_id, chunk_id, profile_id, embedding,
                    dimensions, source_chunk_content_sha256, embedding_fingerprint
                ) VALUES (%s, %s, %s, %s, %s::vector, %s, %s, %s)
                ON CONFLICT (project_id, chunk_id, profile_id) DO NOTHING
                """,
                (
                    uuid4(),
                    project_id,
                    chunk_id,
                    profile_id,
                    vector_literal(vector),
                    profile.dimensions,
                    content_hash,
                    _embedding_fingerprint(profile, content_hash, vector),
                ),
            )
            inserted_count += cursor.rowcount
    return inserted_count


def sync_semantic(settings: Settings, project_id: UUID) -> SemanticRunSummary:
    adapter = build_embedding_adapter(settings)
    if adapter is None:
        raise SemanticUnavailableError("semantic_unavailable")
    profile = adapter.profile
    corpus = _current_corpus(settings, project_id)
    profile_id = _ensure_profile(settings, profile)
    run_id = uuid4()
    _create_run(settings, run_id, project_id, corpus, profile_id)
    chunks = _current_chunks(settings, project_id, corpus.run_id)
    compatible = _compatible_embedding_ids(settings, project_id, profile_id, chunks)
    missing = [chunk for chunk in chunks if chunk[0] not in compatible]
    new_count = 0
    reused_count = len(compatible)
    provider_requests = 0
    try:
        for start in range(0, len(missing), settings.embedding_batch_size):
            batch = missing[start : start + settings.embedding_batch_size]
            vectors = adapter.embed([chunk[1] for chunk in batch])
            provider_requests += 1
            new_count += _persist_batch(settings, project_id, profile, profile_id, batch, vectors)
            _update_run(
                settings,
                run_id,
                status=SemanticRunStatus.RUNNING,
                current_count=len(compatible) + new_count,
                new_count=new_count,
                reused_count=reused_count,
                failed_count=0,
                requests=provider_requests,
                error=None,
            )
        actual_compatible = _compatible_embedding_ids(settings, project_id, profile_id, chunks)
        if len(actual_compatible) != len(chunks):
            raise EmbeddingProviderError("semantic_generation_incomplete")
        _update_run(
            settings,
            run_id,
            status=SemanticRunStatus.COMPLETED,
            current_count=len(chunks),
            new_count=new_count,
            reused_count=reused_count,
            failed_count=0,
            requests=provider_requests,
            error=None,
        )
    except SemanticError as exc:
        _update_run(
            settings,
            run_id,
            status=SemanticRunStatus.FAILED,
            current_count=len(compatible) + new_count,
            new_count=new_count,
            reused_count=reused_count,
            failed_count=1,
            requests=provider_requests,
            error=exc.code,
        )
    except (OSError, psycopg.Error, RuntimeError) as exc:
        _update_run(
            settings,
            run_id,
            status=SemanticRunStatus.FAILED,
            current_count=len(compatible) + new_count,
            new_count=new_count,
            reused_count=reused_count,
            failed_count=1,
            requests=provider_requests,
            error=f"semantic_sync_{type(exc).__name__}",
        )
    return _get_run(settings, run_id)


def _latest_semantic_run(settings: Settings, project_id: UUID) -> SemanticRunSummary | None:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT {_RUN_COLUMNS}
            FROM retrieval_embedding_runs
            WHERE project_id = %s
            ORDER BY started_at DESC, run_id DESC
            LIMIT 1
            """,
            (project_id,),
        )
        row = cursor.fetchone()
    return _run_from_row(row) if row else None


def _current_semantic_run(
    settings: Settings,
    project_id: UUID,
    corpus: _CorpusGeneration,
    profile_id: UUID,
) -> SemanticRunSummary | None:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT {_RUN_COLUMNS}
            FROM retrieval_embedding_runs
            WHERE project_id = %s AND corpus_run_id = %s AND profile_id = %s
              AND status = 'COMPLETED'
            ORDER BY completed_at DESC NULLS LAST, run_id DESC
            LIMIT 1
            """,
            (project_id, corpus.run_id, profile_id),
        )
        row = cursor.fetchone()
    if row is None:
        return None
    result = _run_from_row(row)
    return result if result.current_chunk_count >= corpus.chunk_count else None


def semantic_status(settings: Settings, project_id: UUID) -> SemanticStatusResponse:
    if not _project_exists(settings, project_id):
        raise RetrievalProjectNotFoundError(str(project_id))
    latest_run = _latest_semantic_run(settings, project_id)
    if not settings.embedding_enabled:
        return SemanticStatusResponse(
            project_id=project_id,
            state=SemanticState.UNAVAILABLE,
            enabled=False,
            configured=False,
            profile=None,
            current_corpus_run_id=None,
            latest_run=latest_run,
            total_current_chunks=0,
            embedded_chunk_count=0,
            missing_chunk_count=0,
            last_error=latest_run.error if latest_run else None,
        )
    try:
        profile = _profile_from_settings(settings)
    except SemanticError as exc:
        return SemanticStatusResponse(
            project_id=project_id,
            state=SemanticState.UNAVAILABLE,
            enabled=True,
            configured=False,
            profile=None,
            current_corpus_run_id=None,
            latest_run=latest_run,
            total_current_chunks=0,
            embedded_chunk_count=0,
            missing_chunk_count=0,
            last_error=exc.code,
        )
    corpus = _latest_corpus(settings, project_id)
    if corpus is None:
        return SemanticStatusResponse(
            project_id=project_id,
            state=SemanticState.BLOCKED,
            enabled=True,
            configured=True,
            profile=profile,
            current_corpus_run_id=None,
            latest_run=latest_run,
            total_current_chunks=0,
            embedded_chunk_count=0,
            missing_chunk_count=0,
            last_error=latest_run.error if latest_run else "lexical_corpus_not_current",
        )
    profile_id = _profile_id(settings, profile)
    current_run = (
        _current_semantic_run(settings, project_id, corpus, profile_id) if profile_id else None
    )
    embedded = 0
    if profile_id:
        with database_connection(settings) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(DISTINCT c.chunk_id), count(DISTINCT e.chunk_id)
                FROM retrieval_references AS r
                JOIN retrieval_chunks AS c
                  ON c.project_id = r.project_id AND c.chunk_id = r.chunk_id
                LEFT JOIN retrieval_chunk_embeddings AS e
                  ON e.project_id = c.project_id AND e.chunk_id = c.chunk_id
                 AND e.profile_id = %s AND e.source_chunk_content_sha256 = c.content_sha256
                WHERE r.project_id = %s AND r.corpus_run_id = %s AND r.is_current
                """,
                (profile_id, project_id, corpus.run_id),
            )
            counts = cursor.fetchone() or (0, 0)
        embedded = int(counts[1])
        total = int(counts[0])
    else:
        total = corpus.chunk_count
    state = SemanticState.CURRENT if current_run else SemanticState.STALE
    if latest_run and latest_run.status == SemanticRunStatus.RUNNING:
        state = SemanticState.SYNCING
    return SemanticStatusResponse(
        project_id=project_id,
        state=state,
        enabled=True,
        configured=True,
        profile=profile,
        current_corpus_run_id=corpus.run_id,
        latest_run=latest_run,
        total_current_chunks=total,
        embedded_chunk_count=embedded,
        missing_chunk_count=max(0, total - embedded),
        last_error=(
            latest_run.error
            if latest_run and latest_run.status != SemanticRunStatus.COMPLETED
            else None
        ),
    )


def _semantic_rows(
    settings: Settings,
    project_id: UUID,
    request: LexicalRequest,
    adapter: EmbeddingAdapter,
    corpus: _CorpusGeneration,
    semantic_run: SemanticRunSummary,
) -> list[SemanticCandidate]:
    query = normalize_lexical_query(request.query)
    vectors = adapter.embed([query.original])
    if len(vectors) != 1:
        raise EmbeddingProviderError("provider_response_count_mismatch")
    vector = vector_literal(vectors[0])
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            WITH scored AS (
                SELECT r.project_id, r.reference_id, r.chunk_id, r.corpus_run_id,
                       r.source_kind, sr.run_id AS semantic_run_id,
                       c.content, r.path, r.source_title, r.qualified_symbol,
                       r.repository_file_id, r.repository_symbol_id, r.task_id,
                       r.source_content_sha256, c.content_sha256, c.chunker_version,
                       r.start_line, r.end_line, r.start_char, r.end_char,
                       e.embedding <=> %s::vector AS semantic_distance
                FROM retrieval_references AS r
                JOIN retrieval_chunks AS c
                  ON c.project_id = r.project_id AND c.chunk_id = r.chunk_id
                JOIN retrieval_chunk_embeddings AS e
                  ON e.project_id = c.project_id AND e.chunk_id = c.chunk_id
                 AND e.profile_id = %s AND e.dimensions = %s
                 AND e.source_chunk_content_sha256 = c.content_sha256
                JOIN retrieval_embedding_runs AS sr
                  ON sr.project_id = r.project_id AND sr.run_id = %s
                 AND sr.status = 'COMPLETED'
                WHERE r.project_id = %s AND r.corpus_run_id = %s AND r.is_current
                  AND (%s::text IS NULL OR r.source_kind = %s)
            ), ranked AS (
                SELECT scored.*,
                       row_number() OVER (
                           PARTITION BY source_kind,
                             CASE WHEN source_kind = 'TASK' THEN chunk_id ELSE reference_id END
                           ORDER BY semantic_distance ASC, task_id NULLS LAST, reference_id
                       ) AS candidate_rank
                FROM scored
            )
            SELECT project_id, reference_id, chunk_id, corpus_run_id, semantic_run_id,
                   source_kind, content, path, source_title, qualified_symbol,
                   repository_file_id, repository_symbol_id, task_id,
                   source_content_sha256, content_sha256, chunker_version,
                   start_line, end_line, start_char, end_char, semantic_distance
            FROM ranked
            WHERE candidate_rank = 1
            ORDER BY semantic_distance ASC, source_kind,
                     lower(coalesce(path, '')),
                     lower(coalesce(qualified_symbol, '')),
                     start_line, reference_id
            LIMIT %s
            """,
            (
                vector,
                semantic_run.profile_id,
                adapter.profile.dimensions,
                semantic_run.run_id,
                project_id,
                corpus.run_id,
                request.source_kind,
                request.source_kind,
                request.top_k,
            ),
        )
        rows = cursor.fetchall()
    from .retrieval import _snippet

    return [
        SemanticCandidate(
            project_id=cast(UUID, row[0]),
            reference_id=cast(UUID, row[1]),
            chunk_id=cast(UUID, row[2]),
            corpus_run_id=cast(UUID, row[3]),
            semantic_run_id=cast(UUID, row[4]),
            source_kind=str(row[5]),
            semantic_score=1.0 / (1.0 + float(row[20])),
            semantic_distance=float(row[20]),
            snippet=_snippet(str(row[6]), query),
            path=cast(str | None, row[7]),
            title=cast(str | None, row[8]),
            qualified_symbol=cast(str | None, row[9]),
            repository_file_id=cast(UUID | None, row[10]),
            repository_symbol_id=cast(UUID | None, row[11]),
            task_id=cast(UUID | None, row[12]),
            source_content_sha256=str(row[13]),
            chunk_content_sha256=str(row[14]),
            chunker_version=str(row[15]),
            start_line=int(row[16]),
            end_line=int(row[17]),
            start_char=int(row[18]),
            end_char=int(row[19]),
        )
        for row in rows
    ]


def semantic_search(
    settings: Settings, project_id: UUID, request: LexicalRequest
) -> SemanticResponse:
    query = normalize_lexical_query(request.query)
    adapter = build_embedding_adapter(settings)
    if adapter is None:
        raise SemanticUnavailableError("semantic_unavailable")
    corpus = _current_corpus(settings, project_id)
    profile_id = _profile_id(settings, adapter.profile)
    if profile_id is None:
        raise SemanticNotCurrentError("semantic_needs_sync")
    semantic_run = _current_semantic_run(settings, project_id, corpus, profile_id)
    if semantic_run is None:
        raise SemanticNotCurrentError("semantic_needs_sync")
    results = _semantic_rows(settings, project_id, request, adapter, corpus, semantic_run)
    return SemanticResponse(
        project_id=project_id,
        query=query.original,
        normalized_query=query.normalized,
        top_k=request.top_k,
        semantic_state=SemanticState.CURRENT,
        results=results,
    )


def _fallback_state(error: SemanticError) -> tuple[SemanticState, str]:
    if isinstance(error, SemanticNotCurrentError):
        return SemanticState.STALE, "LEXICAL_FALLBACK_SEMANTIC_STALE"
    if isinstance(error, SemanticUnavailableError | SemanticConfigurationError):
        return SemanticState.UNAVAILABLE, "LEXICAL_FALLBACK_SEMANTIC_UNAVAILABLE"
    return SemanticState.UNAVAILABLE, "LEXICAL_FALLBACK_PROVIDER_ERROR"


def hybrid_search(settings: Settings, project_id: UUID, request: HybridRequest) -> HybridResponse:
    query = normalize_lexical_query(request.query)
    candidate_pool = min(settings.embedding_candidate_pool, MAX_TOP_K)
    lexical_request = LexicalRequest(
        query=request.query, top_k=candidate_pool, source_kind=request.source_kind
    )
    lexical = lexical_search(settings, project_id, lexical_request)
    semantic: SemanticResponse | None = None
    fallback_reason: str | None = None
    semantic_state = SemanticState.UNAVAILABLE
    try:
        semantic = semantic_search(
            settings,
            project_id,
            LexicalRequest(
                query=request.query,
                top_k=candidate_pool,
                source_kind=request.source_kind,
            ),
        )
        semantic_state = semantic.semantic_state
    except SemanticError as exc:
        semantic_state, fallback_reason = _fallback_state(exc)
        if request.strict_semantic:
            raise

    if semantic is None:
        results = [
            _hybrid_candidate(
                lexical_item=item,
                lexical_rank=index + 1,
                semantic_item=None,
                semantic_rank=None,
                settings=settings,
            )
            for index, item in enumerate(lexical.results[: request.top_k])
        ]
        return HybridResponse(
            project_id=project_id,
            query=query.original,
            normalized_query=query.normalized,
            top_k=request.top_k,
            state=fallback_reason or "LEXICAL_FALLBACK_SEMANTIC_UNAVAILABLE",
            semantic_state=semantic_state,
            fallback_reason=fallback_reason,
            candidate_pool=candidate_pool,
            results=results,
        )

    lexical_by_id = {
        item.reference_id: (index + 1, item) for index, item in enumerate(lexical.results)
    }
    semantic_by_id = {
        item.reference_id: (index + 1, item) for index, item in enumerate(semantic.results)
    }
    candidate_ids = set(lexical_by_id) | set(semantic_by_id)
    fused: list[HybridCandidate] = []
    for reference_id in candidate_ids:
        lexical_entry = lexical_by_id.get(reference_id)
        semantic_entry = semantic_by_id.get(reference_id)
        lexical_rank = lexical_entry[0] if lexical_entry else None
        semantic_rank = semantic_entry[0] if semantic_entry else None
        fused.append(
            _hybrid_candidate(
                lexical_item=lexical_entry[1] if lexical_entry else None,
                lexical_rank=lexical_rank,
                semantic_item=semantic_entry[1] if semantic_entry else None,
                semantic_rank=semantic_rank,
                settings=settings,
            )
        )
    fused.sort(
        key=lambda item: (
            -item.hybrid_score,
            item.source_kind,
            (item.path or "").casefold(),
            (item.qualified_symbol or "").casefold(),
            item.start_line,
            str(item.reference_id),
        )
    )
    return HybridResponse(
        project_id=project_id,
        query=query.original,
        normalized_query=query.normalized,
        top_k=request.top_k,
        state="HYBRID",
        semantic_state=semantic_state,
        fallback_reason=None,
        candidate_pool=candidate_pool,
        results=fused[: request.top_k],
    )


def _hybrid_candidate(
    *,
    lexical_item: LexicalCandidate | None,
    lexical_rank: int | None,
    semantic_item: SemanticCandidate | None,
    semantic_rank: int | None,
    settings: Settings,
) -> HybridCandidate:
    source = semantic_item or lexical_item
    if source is None:
        raise RuntimeError("hybrid candidate has no source")
    lexical_contribution = (
        settings.embedding_lexical_weight / (settings.embedding_rrf_k + lexical_rank)
        if lexical_rank is not None
        else 0.0
    )
    semantic_contribution = (
        settings.embedding_semantic_weight / (settings.embedding_rrf_k + semantic_rank)
        if semantic_rank is not None
        else 0.0
    )
    return HybridCandidate(
        project_id=source.project_id,
        reference_id=source.reference_id,
        chunk_id=source.chunk_id,
        corpus_run_id=source.corpus_run_id,
        source_kind=source.source_kind,
        hybrid_score=lexical_contribution + semantic_contribution,
        lexical_score=lexical_item.lexical_score if lexical_item else None,
        semantic_score=semantic_item.semantic_score if semantic_item else None,
        semantic_distance=semantic_item.semantic_distance if semantic_item else None,
        lexical_rank=lexical_rank,
        semantic_rank=semantic_rank,
        lexical_contribution=lexical_contribution,
        semantic_contribution=semantic_contribution,
        snippet=source.snippet,
        path=source.path,
        title=source.title,
        qualified_symbol=source.qualified_symbol,
        repository_file_id=source.repository_file_id,
        repository_symbol_id=source.repository_symbol_id,
        task_id=source.task_id,
        source_content_sha256=source.source_content_sha256,
        chunk_content_sha256=source.chunk_content_sha256,
        chunker_version=source.chunker_version,
        start_line=source.start_line,
        end_line=source.end_line,
        start_char=source.start_char,
        end_char=source.end_char,
    )


router = APIRouter(tags=["semantic-retrieval"])


def _settings() -> Settings:
    from .config import get_settings

    return get_settings()


@router.post(
    "/api/v1/projects/{project_id}/retrieval/semantic/sync",
    response_model=SemanticRunSummary,
)
def sync_retrieval_semantic(project_id: UUID) -> SemanticRunSummary:
    try:
        return sync_semantic(_settings(), project_id)
    except RetrievalProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    except SemanticUnavailableError as exc:
        raise HTTPException(status_code=503, detail=exc.code) from exc
    except SemanticNotCurrentError as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc
    except (SemanticConfigurationError, psycopg.Error) as exc:
        raise HTTPException(status_code=503, detail="semantic retrieval unavailable") from exc


@router.get(
    "/api/v1/projects/{project_id}/retrieval/semantic",
    response_model=SemanticStatusResponse,
)
def get_retrieval_semantic_status(project_id: UUID) -> SemanticStatusResponse:
    try:
        return semantic_status(_settings(), project_id)
    except RetrievalProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    except psycopg.Error as exc:
        raise HTTPException(
            status_code=503, detail="semantic retrieval database unavailable"
        ) from exc


@router.post(
    "/api/v1/projects/{project_id}/retrieval/semantic",
    response_model=SemanticResponse,
)
def query_retrieval_semantic(project_id: UUID, request: LexicalRequest) -> SemanticResponse:
    try:
        return semantic_search(_settings(), project_id, request)
    except RetrievalProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    except RetrievalQueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SemanticError as exc:
        raise HTTPException(status_code=503, detail=exc.code) from exc
    except psycopg.Error as exc:
        logger.exception("semantic retrieval database query failed")
        raise HTTPException(status_code=503, detail="semantic retrieval unavailable") from exc


@router.post(
    "/api/v1/projects/{project_id}/retrieval/hybrid",
    response_model=HybridResponse,
)
def query_retrieval_hybrid(project_id: UUID, request: HybridRequest) -> HybridResponse:
    try:
        return hybrid_search(_settings(), project_id, request)
    except RetrievalProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    except RetrievalQueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SemanticError as exc:
        raise HTTPException(status_code=503, detail=exc.code) from exc
    except psycopg.Error as exc:
        logger.exception("hybrid retrieval database query failed")
        raise HTTPException(status_code=503, detail="hybrid retrieval unavailable") from exc
