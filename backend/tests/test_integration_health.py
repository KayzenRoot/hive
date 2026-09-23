from __future__ import annotations

import json
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


def test_postgres_healthcheck_grace_covers_clean_windows_initialization() -> None:
    compose = (integration_health.ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    postgres = compose.split("  postgres:\n", maxsplit=1)[1].split("\n  redis:\n", maxsplit=1)[0]
    healthcheck = postgres.split("    healthcheck:\n", maxsplit=1)[1].split(
        "\n    networks:", maxsplit=1
    )[0]

    assert "start_period: 240s" in healthcheck


def test_integration_requires_full_validation_for_the_exact_candidate() -> None:
    identity = {
        "head_sha": "a" * 40,
        "tracked_diff_sha256": "b" * 64,
        "untracked_file_count": 0,
    }
    summary = {
        "status": "PASS",
        "selected_bucket": "all",
        "failed_steps": [],
        "candidate_identity": {**identity, "stable_during_validation": True},
    }

    assert integration_health.validation_candidate_error(summary, identity) is None
    assert (
        integration_health.validation_candidate_error(
            summary, {**identity, "tracked_diff_sha256": "c" * 64}
        )
        is not None
    )
    assert (
        integration_health.validation_candidate_error(
            summary, {**identity, "untracked_file_count": 1}
        )
        is not None
    )


def test_mcp_stage_reuse_requires_fresh_complete_zero_leak_evidence(tmp_path: Path) -> None:
    evidence = tmp_path / "mcp-surface.json"
    payload = {
        "status": "PASS",
        "mcp_evidence_version": "mcp-core-surface-v1",
        "protocol_handshake_passed": True,
        "real_transport_exercised": True,
        "project_isolation_passed": True,
        "restart_recovery": True,
        "redis_loss_recovery": True,
        "secret_leaks": 0,
        "filesystem_path_leaks": 0,
        "mcp_llm_calls": 0,
        "mcp_provider_calls": 0,
    }
    evidence.write_text(json.dumps(payload), encoding="utf-8")

    assert integration_health.reusable_mcp_stage(evidence.stat().st_mtime - 1, evidence) is not None
    assert integration_health.reusable_mcp_stage(evidence.stat().st_mtime + 1, evidence) is None

    payload["secret_leaks"] = 1
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    assert integration_health.reusable_mcp_stage(evidence.stat().st_mtime - 1, evidence) is None


def test_ci_runs_discovery_enabling_e2e_after_manual_fixture_suites() -> None:
    workflow = (integration_health.ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    validate_evidence_download = workflow.index(
        "- name: Download Validate evidence for integration candidate binding"
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
    assert validate_evidence_download < discovery_enabling_e2e
    evidence_step = workflow[validate_evidence_download:discovery_enabling_e2e]
    assert "uses: actions/download-artifact@v8" in evidence_step
    assert "hive-validation-evidence-${{ github.event.pull_request.head.sha || github.sha }}" in (
        evidence_step
    )
    assert "path: tmp/validation" in evidence_step
