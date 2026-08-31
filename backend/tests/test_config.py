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


def test_environment_values_are_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HIVE_DATA_ROOT", "D:/HIVE")
    monkeypatch.setenv("HIVE_ENVIRONMENT", "test")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3001, http://example.test")

    settings = Settings()

    assert settings.data_root == Path("D:/HIVE")
    assert settings.environment == "test"
    assert settings.cors_origin_list == ["http://localhost:3001", "http://example.test"]
