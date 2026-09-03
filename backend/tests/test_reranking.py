from __future__ import annotations

import json
from email.message import Message
from typing import cast
from urllib.error import HTTPError, URLError
from uuid import UUID

import pytest
from pydantic import SecretStr, ValidationError

from app import reranking
from app.config import Settings
from app.semantic_retrieval import HybridCandidate, HybridResponse, SemanticState

PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")
CORPUS_RUN_ID = UUID("00000000-0000-0000-0000-000000000010")


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return self.body


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "rerank_enabled": True,
        "rerank_base_url": "http://127.0.0.1:9999",
        "rerank_model": "fixture",
        "rerank_model_revision": "v1",
        "rerank_candidate_pool": 20,
        "rerank_max_document_chars": 120,
    }
    values.update(overrides)
    return Settings.model_validate(values)


def candidate(index: int, *, source_kind: str = "REPOSITORY_FILE") -> HybridCandidate:
    reference_id = UUID(f"00000000-0000-0000-0000-{index + 11:012d}")
    return HybridCandidate(
        project_id=PROJECT_ID,
        reference_id=reference_id,
        chunk_id=UUID(f"00000000-0000-0000-0000-{index + 21:012d}"),
        corpus_run_id=CORPUS_RUN_ID,
        source_kind=source_kind,
        hybrid_score=0.5 - index / 100,
        lexical_score=0.8 - index / 100,
        semantic_score=0.7 - index / 100,
        semantic_distance=0.2 + index / 100,
        lexical_rank=index + 1,
        semantic_rank=index + 1,
        lexical_contribution=0.01,
        semantic_contribution=0.01,
        snippet=f"candidate {index} snippet",
        path=f"src/candidate_{index}.py",
        title=None,
        qualified_symbol=None,
        repository_file_id=reference_id,
        repository_symbol_id=None,
        task_id=None,
        source_content_sha256="a" * 64,
        chunk_content_sha256="b" * 64,
        chunker_version="line-window-v1",
        start_line=1,
        end_line=2,
        start_char=0,
        end_char=20,
    )


def hybrid(*candidates: HybridCandidate, state: str = "HYBRID") -> HybridResponse:
    return HybridResponse(
        project_id=PROJECT_ID,
        query="candidate query",
        normalized_query="candidate query",
        top_k=len(candidates),
        state=state,
        semantic_state=SemanticState.CURRENT,
        fallback_reason=None,
        candidate_pool=len(candidates),
        results=list(candidates),
    )


def adapter_with(
    profile: reranking.RerankerProfile,
    result: list[reranking.RerankScore] | Exception,
) -> reranking.RerankerAdapter:
    class FakeAdapter:
        def __init__(self) -> None:
            self.profile = profile

        def rerank(self, _query: str, _documents: list[str]) -> list[reranking.RerankScore]:
            if isinstance(result, Exception):
                raise result
            return result

    return FakeAdapter()


def test_rerank_settings_are_disabled_by_default() -> None:
    configured = Settings()

    assert configured.rerank_enabled is False
    configured.validate_rerank_limits()


@pytest.mark.parametrize(
    "overrides",
    [
        {"rerank_timeout_seconds": 0},
        {"rerank_timeout_seconds": 121},
        {"rerank_candidate_pool": 0},
        {"rerank_candidate_pool": 101},
        {"rerank_max_document_chars": 0},
        {"rerank_max_query_chars": 513},
    ],
)
def test_rerank_settings_validate_bounds(overrides: dict[str, object]) -> None:
    configured = settings(**overrides)

    with pytest.raises(ValueError):
        configured.validate_rerank_limits()


def test_rerank_settings_require_model_when_enabled() -> None:
    configured = settings(rerank_model=" ")

    with pytest.raises(ValueError, match="RERANK_MODEL"):
        configured.validate_rerank_limits()


def test_rerank_profile_is_stable_and_excludes_secret() -> None:
    first = reranking._profile_from_settings(settings(rerank_api_key=SecretStr("secret")))
    second = reranking._profile_from_settings(settings(rerank_api_key=SecretStr("other")))

    assert first.identity_fingerprint == second.identity_fingerprint
    assert "secret" not in first.identity_fingerprint
    assert "secret" not in repr(settings(rerank_api_key=SecretStr("secret")))
    assert first.serialization_version == reranking.RERANK_SERIALIZATION_VERSION


@pytest.mark.parametrize(
    "overrides",
    [
        {"rerank_model": "another"},
        {"rerank_model_revision": "v2"},
    ],
)
def test_rerank_profile_changes_for_material_identity(overrides: dict[str, object]) -> None:
    first = reranking._profile_from_settings(settings())
    second = reranking._profile_from_settings(settings(**overrides))

    assert first.identity_fingerprint != second.identity_fingerprint


def test_rerank_profile_changes_for_serialization_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = reranking._profile_from_settings(settings())
    monkeypatch.setattr(reranking, "RERANK_SERIALIZATION_VERSION", "rerank-document-v2")
    second = reranking._profile_from_settings(settings())

    assert first.identity_fingerprint != second.identity_fingerprint


def test_rerank_request_rejects_unbounded_candidate_pool() -> None:
    with pytest.raises(ValidationError):
        reranking.RerankRequest(query="query", top_k=1, candidate_pool=101)


def test_serializer_is_stable_bounded_and_omits_volatile_data() -> None:
    source = candidate(0)
    first = reranking.serialize_candidate(source, 120)
    second = reranking.serialize_candidate(source, 120)
    payload = json.loads(first)

    assert first == second
    assert list(payload) == ["source_kind", "path", "title", "qualified_symbol", "snippet"]
    assert len(first) <= 120
    assert "source_content_sha256" not in first
    assert "reference_id" not in first


def test_serializer_normalizes_missing_fields() -> None:
    source = candidate(0).model_copy(update={"path": None, "title": None})

    payload = json.loads(reranking.serialize_candidate(source, 120))

    assert payload["path"] == ""
    assert payload["title"] == ""


def test_http_adapter_reorders_by_explicit_index(monkeypatch: pytest.MonkeyPatch) -> None:
    configured = settings()
    profile = reranking._profile_from_settings(configured)
    body = json.dumps(
        {
            "model": profile.model,
            "results": [
                {"index": 1, "relevance_score": 0.91},
                {"index": 0, "relevance_score": 0.42},
            ],
        }
    ).encode()
    monkeypatch.setattr(reranking, "urlopen", lambda *_args, **_kwargs: FakeResponse(body))

    result = reranking.OpenAICompatibleRerankerAdapter(configured, profile).rerank(
        "query", ["doc 0", "doc 1"]
    )

    assert [(item.index, item.score) for item in result] == [(1, 0.91), (0, 0.42)]


@pytest.mark.parametrize(
    ("results", "message"),
    [
        ([{"index": 0, "relevance_score": 0.1}, {"index": 0, "relevance_score": 0.2}], "index"),
        ([{"index": 0, "relevance_score": 0.1}], "count"),
        ([{"index": 2, "relevance_score": 0.1}, {"index": 1, "relevance_score": 0.2}], "index"),
        (
            [{"index": 0, "relevance_score": float("nan")}, {"index": 1, "relevance_score": 0.2}],
            "non_finite",
        ),
        (
            [{"index": 0, "relevance_score": "high"}, {"index": 1, "relevance_score": 0.2}],
            "invalid",
        ),
    ],
)
def test_http_adapter_fails_closed_on_invalid_results(
    monkeypatch: pytest.MonkeyPatch,
    results: list[dict[str, object]],
    message: str,
) -> None:
    configured = settings()
    profile = reranking._profile_from_settings(configured)
    body = json.dumps({"model": profile.model, "results": results}, allow_nan=True).encode()
    monkeypatch.setattr(reranking, "urlopen", lambda *_args, **_kwargs: FakeResponse(body))

    with pytest.raises(reranking.RerankInvalidResponseError, match=message):
        reranking.OpenAICompatibleRerankerAdapter(configured, profile).rerank(
            "query", ["doc 0", "doc 1"]
        )


def test_http_adapter_rejects_model_mismatch_and_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = settings()
    profile = reranking._profile_from_settings(configured)
    body = json.dumps(
        {"model": "wrong", "results": [{"index": 0, "relevance_score": 0.1}]}
    ).encode()
    monkeypatch.setattr(reranking, "urlopen", lambda *_args, **_kwargs: FakeResponse(body))

    with pytest.raises(reranking.RerankInvalidResponseError, match="model_mismatch"):
        reranking.OpenAICompatibleRerankerAdapter(configured, profile).rerank("query", ["doc"])

    with pytest.raises(reranking.RerankConfigurationError, match="credentials"):
        reranking._normalize_base_url("https://user:password@example.test")


@pytest.mark.parametrize(
    "failure",
    [
        HTTPError("https://example.test", 503, "down", cast("Message[str, str]", None), None),
        URLError("offline"),
        TimeoutError(),
    ],
)
def test_http_adapter_maps_transport_failures_to_bounded_errors(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    configured = settings()
    profile = reranking._profile_from_settings(configured)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(reranking, "urlopen", fail)

    with pytest.raises(reranking.RerankProviderError):
        reranking.OpenAICompatibleRerankerAdapter(configured, profile).rerank("query", ["doc"])


def test_rerank_core_promotes_by_score_and_preserves_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = settings()
    profile = reranking._profile_from_settings(configured)
    first, second = candidate(0), candidate(1)
    monkeypatch.setattr(reranking, "hybrid_search", lambda *_args, **_kwargs: hybrid(first, second))
    monkeypatch.setattr(
        reranking,
        "build_reranker_adapter",
        lambda _settings: adapter_with(
            profile,
            [
                reranking.RerankScore(index=1, score=0.9),
                reranking.RerankScore(index=0, score=0.1),
            ],
        ),
    )

    response = reranking.rerank_search(
        configured, PROJECT_ID, reranking.RerankRequest(query="candidate query", top_k=2)
    )

    assert response.rerank_state == reranking.RerankState.RERANKED
    assert [item.reference_id for item in response.results] == [
        second.reference_id,
        first.reference_id,
    ]
    assert response.results[0].pre_rerank_rank == 2
    assert response.results[0].rerank_rank == 1
    assert response.results[0].rerank_score == pytest.approx(0.9)
    assert response.results[0].source_content_sha256 == second.source_content_sha256


def test_rerank_core_uses_stable_tie_break_and_top_k_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    configured = settings()
    profile = reranking._profile_from_settings(configured)
    candidates = [candidate(index) for index in range(3)]
    monkeypatch.setattr(reranking, "hybrid_search", lambda *_args, **_kwargs: hybrid(*candidates))
    monkeypatch.setattr(
        reranking,
        "build_reranker_adapter",
        lambda _settings: adapter_with(
            profile, [reranking.RerankScore(index=index, score=0.5) for index in range(3)]
        ),
    )

    response = reranking.rerank_search(
        configured, PROJECT_ID, reranking.RerankRequest(query="candidate query", top_k=2)
    )

    assert [item.reference_id for item in response.results] == [
        item.reference_id for item in candidates[:2]
    ]
    assert [item.rerank_rank for item in response.results] == [1, 2]


def test_disabled_rerank_is_exact_hybrid_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    configured = settings(rerank_enabled=False)
    candidates = [candidate(0), candidate(1)]
    monkeypatch.setattr(reranking, "hybrid_search", lambda *_args, **_kwargs: hybrid(*candidates))

    response = reranking.rerank_search(
        configured, PROJECT_ID, reranking.RerankRequest(query="candidate query", top_k=2)
    )

    assert response.rerank_state == reranking.RerankState.RERANK_FALLBACK_DISABLED
    assert [item.reference_id for item in response.results] == [
        item.reference_id for item in candidates
    ]
    assert all(item.rerank_score is None for item in response.results)
    assert response.results[1].pre_rerank_rank == 2
    assert response.results[1].rerank_rank == 2


def test_provider_failure_falls_back_or_returns_strict_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = settings()
    profile = reranking._profile_from_settings(configured)
    candidates = [candidate(0), candidate(1)]
    monkeypatch.setattr(reranking, "hybrid_search", lambda *_args, **_kwargs: hybrid(*candidates))
    monkeypatch.setattr(
        reranking,
        "build_reranker_adapter",
        lambda _settings: adapter_with(profile, reranking.RerankProviderError("provider_http_503")),
    )

    fallback = reranking.rerank_search(
        configured, PROJECT_ID, reranking.RerankRequest(query="candidate query", top_k=2)
    )
    assert fallback.rerank_state == reranking.RerankState.RERANK_FALLBACK_PROVIDER_ERROR
    assert [item.reference_id for item in fallback.results] == [
        item.reference_id for item in candidates
    ]
    assert all(item.rerank_score is None for item in fallback.results)

    with pytest.raises(reranking.RerankStrictError, match="provider_http_503"):
        reranking.rerank_search(
            configured,
            PROJECT_ID,
            reranking.RerankRequest(query="candidate query", top_k=2, strict_rerank=True),
        )


def test_invalid_response_falls_back_without_fake_score(monkeypatch: pytest.MonkeyPatch) -> None:
    configured = settings()
    profile = reranking._profile_from_settings(configured)
    candidates = [candidate(0), candidate(1)]
    monkeypatch.setattr(reranking, "hybrid_search", lambda *_args, **_kwargs: hybrid(*candidates))
    monkeypatch.setattr(
        reranking,
        "build_reranker_adapter",
        lambda _settings: adapter_with(
            profile,
            [
                reranking.RerankScore(index=0, score=0.2),
                reranking.RerankScore(index=0, score=0.1),
            ],
        ),
    )

    response = reranking.rerank_search(
        configured, PROJECT_ID, reranking.RerankRequest(query="candidate query", top_k=2)
    )

    assert response.rerank_state == reranking.RerankState.RERANK_FALLBACK_INVALID_RESPONSE
    assert [item.reference_id for item in response.results] == [
        item.reference_id for item in candidates
    ]
    assert all(item.rerank_score is None for item in response.results)


def test_lexical_hybrid_fallback_can_be_reranked_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    configured = settings()
    profile = reranking._profile_from_settings(configured)
    candidates = [candidate(0), candidate(1)]
    monkeypatch.setattr(
        reranking,
        "hybrid_search",
        lambda *_args, **_kwargs: hybrid(*candidates, state="LEXICAL_FALLBACK_SEMANTIC_STALE"),
    )
    monkeypatch.setattr(
        reranking,
        "build_reranker_adapter",
        lambda _settings: adapter_with(
            profile,
            [
                reranking.RerankScore(index=1, score=0.8),
                reranking.RerankScore(index=0, score=0.2),
            ],
        ),
    )

    response = reranking.rerank_search(
        configured, PROJECT_ID, reranking.RerankRequest(query="candidate query", top_k=2)
    )

    assert response.rerank_state == reranking.RerankState.RERANKED
    assert response.hybrid_state == "LEXICAL_FALLBACK_SEMANTIC_STALE"
    assert [item.reference_id for item in response.results] == [
        candidates[1].reference_id,
        candidates[0].reference_id,
    ]


def test_no_candidates_has_explicit_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    configured = settings()
    monkeypatch.setattr(reranking, "hybrid_search", lambda *_args, **_kwargs: hybrid())

    response = reranking.rerank_search(
        configured, PROJECT_ID, reranking.RerankRequest(query="candidate query", top_k=2)
    )

    assert response.rerank_state == reranking.RerankState.RERANK_FALLBACK_NO_CANDIDATES
    assert response.fallback_reason == "no_candidates"
    assert response.results == []
