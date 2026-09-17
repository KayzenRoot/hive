from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from scripts.prepare_release import (
    REQUIRED_FILES,
    build_manifest,
    create_archive,
    migration_head,
)

VERSION = "1.0.0"
TAG = "v1.0.0"


def run_git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def commit_all(repo: Path) -> None:
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-m", "fixture update")


def build_repository(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init", "-b", "main")
    run_git(repo, "config", "user.email", "hive-test@example.invalid")
    run_git(repo, "config", "user.name", "HIVE Test")
    run_git(repo, "config", "commit.gpgsign", "false")
    for relative in sorted(REQUIRED_FILES):
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"content for {relative}\n", encoding="utf-8")
    (repo / "VERSION").write_text(f"{VERSION}\n", encoding="utf-8")
    notes = repo / "docs" / "releases" / f"{TAG}.md"
    notes.parent.mkdir(parents=True, exist_ok=True)
    notes.write_text(
        f"# HIVE {TAG}\n\nStatus: Release candidate (not published).\n",
        encoding="utf-8",
    )
    migrations = repo / "migrations" / "versions"
    migrations.mkdir(parents=True, exist_ok=True)
    (migrations / "0001_init.py").write_text(
        'revision: str = "0001_init"\ndown_revision: str | None = None\n',
        encoding="utf-8",
    )
    commit_all(repo)
    return repo


def test_valid_release_package_and_manifest_are_deterministic(tmp_path: Path) -> None:
    repo = build_repository(tmp_path)
    first = build_manifest(repo, TAG, "HEAD", tmp_path / "out-1", dry_run=True)
    second = build_manifest(repo, TAG, "HEAD", tmp_path / "out-2", dry_run=True)
    assert first["sha256"] == second["sha256"]
    assert first["tag"] == TAG
    assert first["version"] == VERSION
    assert first["migration_head"] == "0001_init"
    assert first["canonical_product_baseline"] == "90cc1b91b48d628dfb3e4773e1672535b4cb8991"
    assert first["checksum_algorithm"] == "sha256"
    assert first["publication"] == "not performed"
    assert first["dry_run"] is True
    assert len(str(first["source_commit"])) == 40
    manifest_path = tmp_path / "out-1" / f"hive-{TAG}.manifest.json"
    assert manifest_path.is_file()
    assert manifest_path.read_text(encoding="utf-8").endswith("\n")


def test_tag_version_mismatch_fails_closed(tmp_path: Path) -> None:
    repo = build_repository(tmp_path)
    with pytest.raises(SystemExit, match="does not match VERSION"):
        build_manifest(repo, "v1.0.1", "HEAD", tmp_path / "out", dry_run=True)


def test_missing_release_notes_fails_closed(tmp_path: Path) -> None:
    repo = build_repository(tmp_path)
    (repo / "docs" / "releases" / f"{TAG}.md").unlink()
    commit_all(repo)
    with pytest.raises(RuntimeError, match="Required path is missing"):
        build_manifest(repo, TAG, "HEAD", tmp_path / "out", dry_run=True)


def test_missing_required_file_fails_closed(tmp_path: Path) -> None:
    repo = build_repository(tmp_path)
    (repo / "LICENSE").unlink()
    commit_all(repo)
    with pytest.raises(RuntimeError, match="missing required files"):
        build_manifest(repo, TAG, "HEAD", tmp_path / "out", dry_run=True)


def test_forbidden_secret_and_local_content_fail_closed(tmp_path: Path) -> None:
    repo = build_repository(tmp_path)
    (repo / ".env").write_text("HIVE_EMBEDDING_API_KEY=not-a-real-key\n", encoding="utf-8")
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "leftpad.js").write_text("module.exports = {};\n", encoding="utf-8")
    commit_all(repo)
    with pytest.raises(RuntimeError, match="forbidden paths"):
        create_archive(repo, TAG, "HEAD", tmp_path / "out")


def test_ambiguous_migration_heads_fail_closed(tmp_path: Path) -> None:
    repo = build_repository(tmp_path)
    migrations = repo / "migrations" / "versions"
    (migrations / "0002_other.py").write_text(
        'revision: str = "0002_other"\ndown_revision: str | None = None\n',
        encoding="utf-8",
    )
    commit_all(repo)
    with pytest.raises(RuntimeError, match="exactly one migration head"):
        migration_head(repo)
