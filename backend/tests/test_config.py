from pathlib import Path

import pytest

from app.config import Settings


def test_default_data_root_is_repo_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HIVE_DATA_ROOT", raising=False)
    monkeypatch.delenv("HIVE_ENVIRONMENT", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    settings = Settings()
    assert settings.data_root == Path(".hive-data")
    assert settings.cors_origin_list == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    assert settings.projects_root == Path(".hive-projects")


def test_environment_values_are_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HIVE_DATA_ROOT", "D:/HIVE")
    monkeypatch.setenv("HIVE_ENVIRONMENT", "test")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3001, http://example.test")

    settings = Settings()

    assert settings.data_root == Path("D:/HIVE")
    assert settings.environment == "test"
    assert settings.cors_origin_list == ["http://localhost:3001", "http://example.test"]


def test_projects_root_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HIVE_PROJECTS_ROOT", "D:/Projects")

    settings = Settings()

    assert settings.projects_root == Path("D:/Projects")


def test_semantic_retrieval_is_disabled_by_default() -> None:
    settings = Settings()

    assert settings.embedding_enabled is False
    assert settings.embedding_base_url is None
    assert settings.embedding_api_key is None


def test_empty_compose_optional_embedding_values_are_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HIVE_EMBEDDING_DIMENSIONS", "")
    monkeypatch.setenv("HIVE_EMBEDDING_API_KEY", "")

    settings = Settings()

    assert settings.embedding_dimensions is None
    assert settings.embedding_api_key is None


def test_semantic_configuration_requires_provider_identity() -> None:
    settings = Settings(embedding_enabled=True, embedding_base_url="http://127.0.0.1:8080")

    with pytest.raises(ValueError, match="HIVE_EMBEDDING_MODEL is required"):
        settings.validate_embedding_limits()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("embedding_timeout_seconds", 0),
        ("embedding_batch_size", 0),
        ("embedding_max_input_chars", 0),
        ("embedding_max_dimensions", 2001),
        ("embedding_candidate_pool", 0),
        ("embedding_rrf_k", 0),
        ("embedding_lexical_weight", -1),
    ],
)
def test_semantic_configuration_limits_are_bounded(field: str, value: object) -> None:
    settings = Settings.model_validate({field: value})

    with pytest.raises(ValueError):
        settings.validate_embedding_limits()
