from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.config import Settings
from app.project_discovery import scan_immediate_git_repositories
from app.registry import ProjectPathError, normalize_project_path


def create_repository(path: Path) -> None:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "HIVE discovery test"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "discovery@example.invalid"],
        check=True,
        capture_output=True,
    )
    (path / "README.md").write_text("# discovery fixture\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "README.md"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "initial fixture"],
        check=True,
        capture_output=True,
    )


def test_scan_is_bounded_to_valid_immediate_git_repositories(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    root.mkdir()
    create_repository(root / "valid-project")
    (root / "ordinary-directory").mkdir()
    create_repository(root / "parent" / "nested-project")

    candidates, examined = scan_immediate_git_repositories(
        Settings.for_testing(projects_root=root, auto_discovery_max_projects=20)
    )

    assert examined == 3
    assert [item.relative_path for item in candidates] == ["valid-project"]
    assert candidates[0].inspection.repository_accessible is True
    assert candidates[0].inspection.git_head_sha is not None


def test_symlink_project_paths_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    outside = tmp_path / "outside"
    root.mkdir()
    create_repository(outside)
    link = root / "linked-project"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks are unavailable in this environment: {type(exc).__name__}")

    settings = Settings.for_testing(projects_root=root)
    candidates, _examined = scan_immediate_git_repositories(settings)

    assert candidates == []
    with pytest.raises(ProjectPathError, match="resolves outside"):
        normalize_project_path("linked-project", settings)
