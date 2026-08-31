import subprocess
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.registry import (
    ProjectCreateRequest,
    ProjectPathError,
    ProjectState,
    _find_identity_conflict,
    _run_git,
    inspect_project,
    normalize_project_path,
)


def settings_for(root: Path) -> Settings:
    return Settings(projects_root=root)


def run_git(repository: Path, arguments: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.strip()


def create_git_repository(root: Path) -> Path:
    repository = root / "sample"
    repository.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repository)], check=True, capture_output=True)
    run_git(repository, ["config", "user.email", "test@example.invalid"])
    run_git(repository, ["config", "user.name", "HIVE Tests"])
    (repository / "pyproject.toml").write_text("[project]\nname = 'sample'\n", encoding="utf-8")
    run_git(repository, ["add", "pyproject.toml"])
    run_git(repository, ["commit", "-m", "initial"])
    return repository


def test_request_validation_and_state_serialization() -> None:
    with pytest.raises(ValidationError):
        ProjectCreateRequest(name=" ", relative_path="sample")

    request = ProjectCreateRequest(name="Sample", relative_path="sample")
    assert request.model_dump() == {"name": "Sample", "relative_path": "sample"}
    assert ProjectState.READY.value == "READY"


def test_allowed_root_and_traversal_rejection(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)

    identity, resolved = normalize_project_path("nested/project", settings)

    assert identity == "nested/project"
    assert resolved == tmp_path / "nested" / "project"
    for unsafe in (
        "../outside",
        "nested/../outside",
        "/tmp/outside",
        "C:/outside",
        "nested\\outside",
    ):
        with pytest.raises(ProjectPathError):
            normalize_project_path(unsafe, settings)


def test_symlink_escape_rejection(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"hive-registry-outside-{tmp_path.name}"
    outside.mkdir()
    try:
        (tmp_path / "escape").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unsupported: {exc}")
    with pytest.raises(ProjectPathError):
        normalize_project_path("escape", settings_for(tmp_path))


def test_symlink_alias_resolves_to_canonical_identity(tmp_path: Path) -> None:
    repository = tmp_path / "real-project"
    repository.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(repository, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unsupported: {exc}")

    identity, resolved = normalize_project_path("alias", settings_for(tmp_path))

    assert identity == "real-project"
    assert resolved == repository.resolve()

    class LegacyRows:
        def execute(self, *_args: object) -> None:
            return None

        def fetchall(self) -> list[tuple[UUID, str]]:
            return [(UUID("00000000-0000-0000-0000-000000000002"), "alias")]

    assert (
        _find_identity_conflict(
            cast(Any, LegacyRows()),
            settings_for(tmp_path),
            "real-project",
            repository,
        )
        is not None
    )


def test_symlink_loop_is_a_stable_resolution_error(tmp_path: Path) -> None:
    loop = tmp_path / "loop"
    try:
        loop.symlink_to(loop)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unsupported: {exc}")

    with pytest.raises(ProjectPathError) as error:
        normalize_project_path("loop", settings_for(tmp_path))

    assert error.value.code == "path_resolution_failed"


def test_git_command_scopes_safe_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "true\n", "")

    monkeypatch.setattr("app.registry.subprocess.run", fake_run)

    _run_git(repository, ["rev-parse", "--is-inside-work-tree"])

    command, kwargs = calls[0]
    assert f"safe.directory={repository}" in command
    assert "safe.directory=*" not in command
    assert kwargs["shell"] is False
    assert kwargs["timeout"] == 5
    environment = kwargs["env"]
    assert isinstance(environment, dict)
    assert environment["GIT_OPTIONAL_LOCKS"] == "0"


def test_inspector_detects_git_language_and_clean_state(tmp_path: Path) -> None:
    repository = create_git_repository(tmp_path)

    result = inspect_project(repository)

    assert result.state is ProjectState.READY
    assert result.repository_accessible is True
    assert result.git_branch == "main"
    assert result.git_head_sha == run_git(repository, ["rev-parse", "HEAD"])
    assert result.working_tree_clean is True
    assert result.language_stack == ["python"]


def test_inspector_handles_detached_head(tmp_path: Path) -> None:
    repository = create_git_repository(tmp_path)
    run_git(repository, ["checkout", "--detach", "HEAD"])

    result = inspect_project(repository)

    assert result.state is ProjectState.READY
    assert result.git_branch is None
    assert result.detached_head is True


def test_inspector_distinguishes_offline_and_degraded(tmp_path: Path) -> None:
    offline = inspect_project(tmp_path / "missing")
    (tmp_path / "plain").mkdir()
    degraded = inspect_project(tmp_path / "plain")

    assert offline.state is ProjectState.OFFLINE
    assert offline.inspection_error == "path_unavailable"
    assert degraded.state is ProjectState.DEGRADED
    assert degraded.inspection_error == "git_command_failed"


def test_inspector_captures_git_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()

    def timeout(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(["git"], 5)

    monkeypatch.setattr("app.registry.subprocess.run", timeout)

    result = inspect_project(repository)

    assert result.state is ProjectState.DEGRADED
    assert result.inspection_error == "git_timeout"
