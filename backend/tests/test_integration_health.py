from __future__ import annotations

import pytest
from scripts import integration_health


def isolated_environment(root, **overrides):
    data_root = root / "wo031-data"
    projects_root = root / "wo031-projects"
    environment = {
        "HIVE_WO031_ISOLATED_E2E": "true",
        "HIVE_DATA_ROOT": str(data_root),
        "HIVE_PROJECTS_ROOT": str(projects_root),
        "COMPOSE_PROJECT_NAME": "hive-wo031-tests",
    }
    environment.update(overrides)
    return environment


def test_help_exits_before_environment_checks_or_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_environment_check():
        raise AssertionError("--help must exit before integration startup")

    monkeypatch.setattr(
        integration_health, "isolated_environment_error", unexpected_environment_check
    )
    with pytest.raises(SystemExit) as raised:
        integration_health.main(["--help"])
    assert raised.value.code == 0


def test_integration_refuses_implicit_runtime_before_health_probe(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("HIVE_WO031_ISOLATED_E2E", raising=False)
    monkeypatch.setattr(
        integration_health,
        "fetch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unsafe integration contacted a runtime")
        ),
    )

    assert integration_health.main([]) == 2
    assert "REFUSED" in capsys.readouterr().err


def test_isolation_requires_separate_repository_local_wo031_roots(tmp_path) -> None:
    environment = isolated_environment(tmp_path)
    assert integration_health.isolated_environment_error(environment, repo_root=tmp_path) is None

    unsafe = isolated_environment(tmp_path, HIVE_DATA_ROOT=str(tmp_path / "canonical"))
    assert integration_health.isolated_environment_error(unsafe, repo_root=tmp_path)

    overlapping = isolated_environment(
        tmp_path,
        HIVE_PROJECTS_ROOT=str(tmp_path / "wo031-data" / "projects"),
    )
    assert integration_health.isolated_environment_error(overlapping, repo_root=tmp_path)


def test_isolation_requires_wo031_compose_project_name(tmp_path) -> None:
    environment = isolated_environment(tmp_path, COMPOSE_PROJECT_NAME="hive")
    assert "COMPOSE_PROJECT_NAME" in integration_health.isolated_environment_error(
        environment, repo_root=tmp_path
    )
