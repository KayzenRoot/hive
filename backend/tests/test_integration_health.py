from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest
from scripts import integration_health


def isolated_environment(root: Path, **overrides: str) -> dict[str, str]:
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
    def unexpected_environment_check(
        _environment: Mapping[str, str] | None = None,
        *,
        repo_root: Path = integration_health.ROOT,
    ) -> str | None:
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


def test_isolation_requires_separate_repository_local_wo031_roots(tmp_path: Path) -> None:
    environment = isolated_environment(tmp_path)
    assert integration_health.isolated_environment_error(environment, repo_root=tmp_path) is None

    unsafe = isolated_environment(tmp_path, HIVE_DATA_ROOT=str(tmp_path / "canonical"))
    unsafe_error = integration_health.isolated_environment_error(unsafe, repo_root=tmp_path)
    assert unsafe_error is not None

    overlapping = isolated_environment(
        tmp_path,
        HIVE_PROJECTS_ROOT=str(tmp_path / "wo031-data" / "projects"),
    )
    overlap_error = integration_health.isolated_environment_error(overlapping, repo_root=tmp_path)
    assert overlap_error is not None


def test_isolation_requires_wo031_compose_project_name(tmp_path: Path) -> None:
    environment = isolated_environment(tmp_path, COMPOSE_PROJECT_NAME="hive")
    error = integration_health.isolated_environment_error(environment, repo_root=tmp_path)
    assert error is not None
    assert "COMPOSE_PROJECT_NAME" in error


def test_ci_runs_discovery_enabling_e2e_after_manual_fixture_suites() -> None:
    workflow = (integration_health.ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    discovery_enabling_e2e = workflow.index("- name: Run container smoke test")
    manual_fixture_suites = (
        "- name: Run Project Registry real-Git integration test",
        "- name: Run Repository Indexing real-Git integration test",
        "- name: Run Task Intake and CAS integration test",
        "- name: Run Retrieval Corpus, Semantic, and Hybrid integration test",
        "- name: Run Context Manager integration test",
        "- name: Run Memory Lifecycle integration test",
        "- name: Run WO-018 autonomous execution integration test",
        "- name: Run Adaptive Token Budget benchmark",
    )

    assert all(workflow.index(step) < discovery_enabling_e2e for step in manual_fixture_suites)
    assert discovery_enabling_e2e < workflow.index("- name: Collect bounded service logs")
