"""Provider-independent, bounded reranking over existing hybrid candidates."""

from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import UUID

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .config import Settings
from .db import database_connection
from .retrieval import (
    MAX_TOP_K,
    LexicalRequest,
    RetrievalProjectNotFoundError,
    RetrievalQueryError,
    normalize_lexical_query,
)
from .semantic_retrieval import (
    HybridCandidate,
    HybridRequest,
    HybridResponse,
    SemanticError,
    SemanticState,
    hybrid_search,
)

logger = logging.getLogger(__name__)

RERANK_ADAPTER_KIND = "openai-compatible-http"
RERANK_SERIALIZATION_VERSION = "rerank-document-v1"
MAX_RERANK_CANDIDATE_POOL = 100
MAX_RERANK_RESPONSE_BYTES = 2_000_000


class RerankState(StrEnum):
    RERANKED = "RERANKED"
    RERANK_FALLBACK_DISABLED = "RERANK_FALLBACK_DISABLED"
    RERANK_FALLBACK_UNCONFIGURED = "RERANK_FALLBACK_UNCONFIGURED"
    RERANK_FALLBACK_PROVIDER_ERROR = "RERANK_FALLBACK_PROVIDER_ERROR"
    RERANK_FALLBACK_INVALID_RESPONSE = "RERANK_FALLBACK_INVALID_RESPONSE"
    RERANK_FALLBACK_NO_CANDIDATES = "RERANK_FALLBACK_NO_CANDIDATES"


class RerankError(RuntimeError):
    """Base class for bounded reranking errors safe to expose as codes."""

    def __init__(self, code: str) -> None:
        self.code = code[:256]
        super().__init__(self.code)


class RerankConfigurationError(RerankError):
    pass


class RerankProviderError(RerankError):
    pass


class RerankInvalidResponseError(RerankError):
    pass


class RerankStrictError(RerankError):
    pass


class RerankerProfile(BaseModel):
    adapter_kind: str
    model: str
    model_revision: str | None
    serialization_version: str
    identity_fingerprint: str


@dataclass(frozen=True)
class RerankScore:
    index: int
    score: float


@dataclass(frozen=True)
class RerankDocument:
    index: int
    serialized: str


class RerankerAdapter(Protocol):
    profile: RerankerProfile

    def rerank(self, query: str, documents: list[str]) -> list[RerankScore]:
        """Return one explicitly indexed finite score for every document."""


class RerankRequest(LexicalRequest):
    candidate_pool: int | None = Field(default=None, ge=1, le=MAX_RERANK_CANDIDATE_POOL)
    strict_rerank: bool = False


class RerankCandidate(HybridCandidate):
    pre_rerank_rank: int
    rerank_rank: int
    rerank_score: float | None


class RerankResponse(BaseModel):
    project_id: UUID
    query: str
    normalized_query: str
    top_k: int
    candidate_pool: int
    hybrid_state: str
    semantic_state: SemanticState
    rerank_state: RerankState
    fallback_reason: str | None
    reranker_profile: RerankerProfile | None
    serialization_version: str
    results: list[RerankCandidate]


class RerankerStatusResponse(BaseModel):
    project_id: UUID
    enabled: bool
    configured: bool
    reranker_profile: RerankerProfile | None
    serialization_version: str
    candidate_pool: int
    max_document_chars: int
    max_query_chars: int


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _normalize_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"}:
        raise RerankConfigurationError("rerank_base_url_invalid_scheme")
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise RerankConfigurationError("rerank_base_url_contains_credentials")
    if parsed.query or parsed.fragment:
        raise RerankConfigurationError("rerank_base_url_invalid")
    return normalized


def _profile_from_settings(settings: Settings) -> RerankerProfile:
    if not settings.rerank_enabled:
        raise RerankConfigurationError("rerank_disabled")
    settings.validate_rerank_limits()
    if not settings.rerank_base_url or not settings.rerank_model:
        raise RerankConfigurationError("rerank_unconfigured")
    model = settings.rerank_model.strip()
    revision = (settings.rerank_model_revision or "").strip() or None
    _normalize_base_url(settings.rerank_base_url)
    identity_payload = {
        "adapter_kind": RERANK_ADAPTER_KIND,
        "model": model,
        "model_revision": revision,
        "serialization_version": RERANK_SERIALIZATION_VERSION,
    }
    identity = _sha256(
        json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return RerankerProfile(
        adapter_kind=RERANK_ADAPTER_KIND,
        model=model,
        model_revision=revision,
        serialization_version=RERANK_SERIALIZATION_VERSION,
        identity_fingerprint=identity,
    )


def _safe_provider_error(error: Exception) -> str:
    if isinstance(error, HTTPError):
        return f"provider_http_{error.code}"
    if isinstance(error, TimeoutError):
        return "provider_timeout"
    if isinstance(error, URLError | OSError):
        return "provider_unavailable"
    return "provider_request_failed"


class OpenAICompatibleRerankerAdapter:
    """Minimal HTTP transport; the core only depends on RerankerAdapter."""

    def __init__(self, settings: Settings, profile: RerankerProfile) -> None:
        if not settings.rerank_base_url:
            raise RerankConfigurationError("rerank_base_url_missing")
        self.settings = settings
        self.profile = profile
        self.url = _normalize_base_url(settings.rerank_base_url) + "/rerank"

    def rerank(self, query: str, documents: list[str]) -> list[RerankScore]:
        if not query or len(query) > self.settings.rerank_max_query_chars:
            raise RerankInvalidResponseError("rerank_query_invalid")
        if not documents or len(documents) > self.settings.rerank_candidate_pool:
            raise RerankInvalidResponseError("rerank_document_count_invalid")
        if any(not isinstance(document, str) for document in documents):
            raise RerankInvalidResponseError("rerank_document_invalid")
        if any(len(document) > self.settings.rerank_max_document_chars for document in documents):
            raise RerankInvalidResponseError("rerank_document_too_large")
        payload = json.dumps(
            {
                "model": self.profile.model,
                "query": query,
                "documents": documents,
                "top_n": len(documents),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.settings.rerank_api_key is not None:
            headers["Authorization"] = f"Bearer {self.settings.rerank_api_key.get_secret_value()}"
        request = Request(self.url, data=payload, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self.settings.rerank_timeout_seconds) as response:
                response_body = response.read(self.settings.rerank_max_response_bytes)
        except (HTTPError, OSError, TimeoutError, URLError) as exc:
            raise RerankProviderError(_safe_provider_error(exc)) from exc
        try:
            decoded = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RerankInvalidResponseError("provider_malformed_response") from exc
        if not isinstance(decoded, dict):
            raise RerankInvalidResponseError("provider_malformed_response")
        model = decoded.get("model")
        if model is not None and model != self.profile.model:
            raise RerankInvalidResponseError("provider_model_mismatch")
        results = decoded.get("results")
        if not isinstance(results, list) or len(results) != len(documents):
            raise RerankInvalidResponseError("provider_response_count_mismatch")
        scores: list[RerankScore] = []
        for result in results:
            if not isinstance(result, dict):
                raise RerankInvalidResponseError("provider_malformed_response")
            index = result.get("index")
            score = result.get("relevance_score")
            if isinstance(index, bool) or not isinstance(index, int):
                raise RerankInvalidResponseError("provider_response_index_invalid")
            if isinstance(score, bool) or not isinstance(score, int | float):
                raise RerankInvalidResponseError("provider_score_invalid")
            converted = float(score)
            if not math.isfinite(converted):
                raise RerankInvalidResponseError("provider_score_non_finite")
            scores.append(RerankScore(index=index, score=converted))
        _validate_scores(scores, len(documents))
        return scores


def build_reranker_adapter(settings: Settings) -> RerankerAdapter | None:
    if not settings.rerank_enabled:
        return None
    try:
        profile = _profile_from_settings(settings)
    except RerankError:
        raise
    except ValueError as exc:
        raise RerankConfigurationError("rerank_configuration_invalid") from exc
    return OpenAICompatibleRerankerAdapter(settings, profile)


def serialize_candidate(candidate: HybridCandidate, max_document_chars: int) -> str:
    """Serialize only bounded, already-authorized candidate fields in stable order."""
    if max_document_chars <= 0:
        raise RerankConfigurationError("rerank_document_limit_invalid")
    payload = {
        "source_kind": candidate.source_kind,
        "path": candidate.path or "",
        "title": candidate.title or "",
        "qualified_symbol": candidate.qualified_symbol or "",
        "snippet": candidate.snippet[:max_document_chars],
    }
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(serialized) > max_document_chars:
        payload["snippet"] = ""
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(serialized) > max_document_chars:
            raise RerankConfigurationError("rerank_document_limit_invalid")
    return serialized


def _validate_scores(scores: object, expected_count: int) -> list[RerankScore]:
    if not isinstance(scores, list) or len(scores) != expected_count:
        raise RerankInvalidResponseError("provider_response_count_mismatch")
    validated: list[RerankScore] = []
    indexes: set[int] = set()
    for raw in scores:
        if not isinstance(raw, RerankScore):
            raise RerankInvalidResponseError("provider_malformed_response")
        if isinstance(raw.index, bool) or not 0 <= raw.index < expected_count:
            raise RerankInvalidResponseError("provider_response_index_invalid")
        if raw.index in indexes:
            raise RerankInvalidResponseError("provider_response_index_invalid")
        if not math.isfinite(raw.score):
            raise RerankInvalidResponseError("provider_score_non_finite")
        indexes.add(raw.index)
        validated.append(raw)
    if indexes != set(range(expected_count)):
        raise RerankInvalidResponseError("provider_response_index_invalid")
    return validated


def _candidate_with_rank(
    candidate: HybridCandidate, *, pre_rank: int, final_rank: int, score: float | None
) -> RerankCandidate:
    return RerankCandidate(
        **candidate.model_dump(),
        pre_rerank_rank=pre_rank,
        rerank_rank=final_rank,
        rerank_score=score,
    )


def _fallback_response(
    *,
    project_id: UUID,
    query: str,
    normalized_query: str,
    request: RerankRequest,
    hybrid: HybridResponse,
    state: RerankState,
    reason: str,
    profile: RerankerProfile | None,
) -> RerankResponse:
    results = [
        _candidate_with_rank(
            candidate,
            pre_rank=index,
            final_rank=index,
            score=None,
        )
        for index, candidate in enumerate(hybrid.results, start=1)
    ][: request.top_k]
    return RerankResponse(
        project_id=project_id,
        query=query,
        normalized_query=normalized_query,
        top_k=request.top_k,
        candidate_pool=len(hybrid.results),
        hybrid_state=hybrid.state,
        semantic_state=hybrid.semantic_state,
        rerank_state=state,
        fallback_reason=reason,
        reranker_profile=profile,
        serialization_version=RERANK_SERIALIZATION_VERSION,
        results=results,
    )


def _error_state(error: RerankError) -> RerankState:
    if isinstance(error, RerankInvalidResponseError):
        return RerankState.RERANK_FALLBACK_INVALID_RESPONSE
    if isinstance(error, RerankConfigurationError):
        return RerankState.RERANK_FALLBACK_UNCONFIGURED
    return RerankState.RERANK_FALLBACK_PROVIDER_ERROR


def rerank_search(settings: Settings, project_id: UUID, request: RerankRequest) -> RerankResponse:
    query = normalize_lexical_query(request.query)
    configured_pool = settings.rerank_candidate_pool
    if request.candidate_pool is not None:
        configured_pool = min(configured_pool, request.candidate_pool)
    candidate_pool = min(configured_pool, MAX_TOP_K)
    if candidate_pool < 1:
        candidate_pool = 1
    hybrid = hybrid_search(
        settings,
        project_id,
        HybridRequest(query=request.query, top_k=candidate_pool, source_kind=request.source_kind),
    )
    if not hybrid.results:
        return _fallback_response(
            project_id=project_id,
            query=query.original,
            normalized_query=query.normalized,
            request=request,
            hybrid=hybrid,
            state=RerankState.RERANK_FALLBACK_NO_CANDIDATES,
            reason="no_candidates",
            profile=None,
        )
    try:
        adapter = build_reranker_adapter(settings)
    except RerankError as exc:
        if request.strict_rerank:
            raise RerankStrictError(exc.code) from exc
        return _fallback_response(
            project_id=project_id,
            query=query.original,
            normalized_query=query.normalized,
            request=request,
            hybrid=hybrid,
            state=_error_state(exc),
            reason=exc.code,
            profile=None,
        )
    if adapter is None:
        return _fallback_response(
            project_id=project_id,
            query=query.original,
            normalized_query=query.normalized,
            request=request,
            hybrid=hybrid,
            state=RerankState.RERANK_FALLBACK_DISABLED,
            reason="rerank_disabled",
            profile=None,
        )
    profile = adapter.profile
    try:
        documents = [
            RerankDocument(
                index=index,
                serialized=serialize_candidate(candidate, settings.rerank_max_document_chars),
            )
            for index, candidate in enumerate(hybrid.results)
        ]
        scores = _validate_scores(
            adapter.rerank(query.original, [document.serialized for document in documents]),
            len(documents),
        )
    except RerankError as exc:
        if request.strict_rerank:
            raise RerankStrictError(exc.code) from exc
        return _fallback_response(
            project_id=project_id,
            query=query.original,
            normalized_query=query.normalized,
            request=request,
            hybrid=hybrid,
            state=_error_state(exc),
            reason=exc.code,
            profile=profile,
        )
    by_index = {score.index: score.score for score in scores}
    ordered = sorted(
        enumerate(hybrid.results),
        key=lambda item: (
            -by_index[item[0]],
            item[0],
            str(item[1].reference_id),
        ),
    )
    results = [
        _candidate_with_rank(
            candidate,
            pre_rank=index + 1,
            final_rank=final_rank,
            score=by_index[index],
        )
        for final_rank, (index, candidate) in enumerate(ordered, start=1)
    ][: request.top_k]
    return RerankResponse(
        project_id=project_id,
        query=query.original,
        normalized_query=query.normalized,
        top_k=request.top_k,
        candidate_pool=len(hybrid.results),
        hybrid_state=hybrid.state,
        semantic_state=hybrid.semantic_state,
        rerank_state=RerankState.RERANKED,
        fallback_reason=None,
        reranker_profile=profile,
        serialization_version=RERANK_SERIALIZATION_VERSION,
        results=results,
    )


def reranker_status(settings: Settings, project_id: UUID) -> RerankerStatusResponse:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM projects WHERE project_id = %s", (project_id,))
        if cursor.fetchone() is None:
            raise RetrievalProjectNotFoundError(str(project_id))
    profile: RerankerProfile | None = None
    configured = False
    if settings.rerank_enabled:
        try:
            profile = _profile_from_settings(settings)
            configured = True
        except RerankError:
            configured = False
    return RerankerStatusResponse(
        project_id=project_id,
        enabled=settings.rerank_enabled,
        configured=configured,
        reranker_profile=profile,
        serialization_version=RERANK_SERIALIZATION_VERSION,
        candidate_pool=min(settings.rerank_candidate_pool, MAX_TOP_K),
        max_document_chars=settings.rerank_max_document_chars,
        max_query_chars=settings.rerank_max_query_chars,
    )


router = APIRouter(tags=["reranking"])


def _settings() -> Settings:
    from .config import get_settings

    return get_settings()


@router.get(
    "/api/v1/projects/{project_id}/retrieval/rerank/status",
    response_model=RerankerStatusResponse,
)
def get_rerank_status(project_id: UUID) -> RerankerStatusResponse:
    try:
        return reranker_status(_settings(), project_id)
    except RetrievalProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="reranker status unavailable") from exc


@router.post(
    "/api/v1/projects/{project_id}/retrieval/rerank",
    response_model=RerankResponse,
)
def query_rerank(project_id: UUID, request: RerankRequest) -> RerankResponse:
    try:
        return rerank_search(_settings(), project_id, request)
    except RetrievalProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    except RetrievalQueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RerankStrictError as exc:
        raise HTTPException(status_code=503, detail=exc.code) from exc
    except SemanticError as exc:
        raise HTTPException(status_code=503, detail=exc.code) from exc
    except psycopg.Error as exc:
        logger.exception("rerank retrieval database query failed")
        raise HTTPException(status_code=503, detail="rerank retrieval unavailable") from exc
