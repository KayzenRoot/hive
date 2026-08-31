import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.registry import (
    ProjectCreateRequest,
    ProjectPathError,
    ProjectState,
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
