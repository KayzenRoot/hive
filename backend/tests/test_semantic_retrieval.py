import json
from uuid import UUID

import pytest
from pydantic import SecretStr

from app import semantic_retrieval
from app.config import Settings
from app.retrieval import LexicalCandidate

PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")
REFERENCE_ID = UUID("00000000-0000-0000-0000-000000000002")
CHUNK_ID = UUID("00000000-0000-0000-0000-000000000003")
CORPUS_RUN_ID = UUID("00000000-0000-0000-0000-000000000004")


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return self.body


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "embedding_enabled": True,
        "embedding_base_url": "http://127.0.0.1:9999",
        "embedding_model": "fixture",
        "embedding_dimensions": 3,
        "embedding_max_dimensions": 3,
    }
    values.update(overrides)
    return Settings.model_validate(values)


def candidate() -> LexicalCandidate:
    return LexicalCandidate(
        project_id=PROJECT_ID,
        reference_id=REFERENCE_ID,
        chunk_id=CHUNK_ID,
        corpus_run_id=CORPUS_RUN_ID,
        source_kind="REPOSITORY_FILE",
        lexical_score=2.0,
        snippet="durable ledger",
        path="src/durability.py",
        title=None,
        qualified_symbol=None,
        repository_file_id=REFERENCE_ID,
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


def test_embedding_profile_identity_excludes_secret() -> None:
    configured = settings(embedding_api_key=SecretStr("super-secret"))

    profile = semantic_retrieval._profile_from_settings(configured)

    assert "super-secret" not in profile.identity_fingerprint
    assert "super-secret" not in repr(configured)
    assert str(configured.embedding_api_key) == "**********"


def test_embedding_base_url_rejects_inline_credentials() -> None:
    with pytest.raises(semantic_retrieval.SemanticConfigurationError):
        semantic_retrieval._normalize_base_url("https://user:password@example.test")


def test_adapter_reorders_by_explicit_provider_index(monkeypatch: pytest.MonkeyPatch) -> None:
    configured = settings()
    profile = semantic_retrieval._profile_from_settings(configured)
    body = json.dumps(
        {
            "model": profile.model,
            "data": [
                {"index": 1, "embedding": [0.2, 0.3, 0.4]},
                {"index": 0, "embedding": [0.1, 0.2, 0.3]},
            ],
        }
    ).encode()
    monkeypatch.setattr(semantic_retrieval, "urlopen", lambda *_args, **_kwargs: FakeResponse(body))

    vectors = semantic_retrieval.OpenAICompatibleEmbeddingAdapter(configured, profile).embed(
        ["first", "second"]
    )

    assert vectors == [(0.1, 0.2, 0.3), (0.2, 0.3, 0.4)]


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ([{"index": 0, "embedding": [0.1, 0.2]}], "provider_dimension_mismatch"),
        ([{"index": 0, "embedding": [0.1, float("nan"), 0.3]}], "provider_vector_non_finite"),
        (
            [
                {"index": 0, "embedding": [0.1, 0.2, 0.3]},
                {"index": 0, "embedding": [0.1, 0.2, 0.3]},
            ],
            "provider_response_index_invalid",
        ),
    ],
)
def test_adapter_fails_closed_on_provider_vectors(
    monkeypatch: pytest.MonkeyPatch,
    data: list[dict[str, object]],
    message: str,
) -> None:
    configured = settings()
    profile = semantic_retrieval._profile_from_settings(configured)
    body = json.dumps({"model": profile.model, "data": data}, allow_nan=True).encode()
    monkeypatch.setattr(semantic_retrieval, "urlopen", lambda *_args, **_kwargs: FakeResponse(body))

    with pytest.raises(semantic_retrieval.EmbeddingProviderError, match=message):
        semantic_retrieval.OpenAICompatibleEmbeddingAdapter(configured, profile).embed(
            ["value"] * len(data)
        )


def test_weighted_rrf_has_visible_independent_contributions() -> None:
    lexical = candidate()
    semantic = semantic_retrieval.SemanticCandidate(
        project_id=PROJECT_ID,
        reference_id=REFERENCE_ID,
        chunk_id=CHUNK_ID,
        corpus_run_id=CORPUS_RUN_ID,
        semantic_run_id=UUID("00000000-0000-0000-0000-000000000005"),
        source_kind="REPOSITORY_FILE",
        semantic_score=0.9,
        semantic_distance=0.1,
        snippet=lexical.snippet,
        path=lexical.path,
        title=None,
        qualified_symbol=None,
        repository_file_id=REFERENCE_ID,
        repository_symbol_id=None,
        task_id=None,
        source_content_sha256=lexical.source_content_sha256,
        chunk_content_sha256=lexical.chunk_content_sha256,
        chunker_version=lexical.chunker_version,
        start_line=1,
        end_line=2,
        start_char=0,
        end_char=20,
    )

    fused = semantic_retrieval._hybrid_candidate(
        lexical_item=lexical,
        lexical_rank=1,
        semantic_item=semantic,
        semantic_rank=2,
        settings=settings(),
    )

    assert fused.lexical_contribution == pytest.approx(1 / 61)
    assert fused.semantic_contribution == pytest.approx(1 / 62)
    assert fused.hybrid_score == pytest.approx((1 / 61) + (1 / 62))


def test_fallback_states_are_explicit() -> None:
    assert semantic_retrieval._fallback_state(
        semantic_retrieval.SemanticNotCurrentError("stale")
    ) == (semantic_retrieval.SemanticState.STALE, "LEXICAL_FALLBACK_SEMANTIC_STALE")
    assert semantic_retrieval._fallback_state(
        semantic_retrieval.EmbeddingProviderError("provider")
    ) == (semantic_retrieval.SemanticState.UNAVAILABLE, "LEXICAL_FALLBACK_PROVIDER_ERROR")
